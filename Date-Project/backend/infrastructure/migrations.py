"""数据库迁移版本管理。

每个目标库各有一张 ``schema_migration_history``，记录已执行的迁移文件及其校验和。
迁移文件按 ``YYYYMMDD_描述.sql`` 命名，按文件名排序执行；``*_rollback`` /
``*_verify`` / ``*_validate`` 是人工辅助脚本，不纳入自动执行。

上线前的存量脚本通过 ``db-baseline`` 一次性登记为已执行，不会重放；之后新增的
脚本由 ``python -m backend.cli db-migrate`` 用迁移专用账号执行。应用启动时不再
执行 DDL，只检查并告警待执行的迁移。
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pymysql

from backend.config import PROJECT_ROOT, settings
from backend.sql_statements import split_sql_statements


logger = logging.getLogger(__name__)

HISTORY_TABLE = "schema_migration_history"
VERSIONED_FILE = re.compile(r"^\d{8}_.+\.sql$")
MANUAL_ONLY = re.compile(r"(rollback|verify|validate)", re.IGNORECASE)
DELIMITER_LINE = re.compile(r"^\s*DELIMITER\s+(\S+)\s*$", re.IGNORECASE)
PENDING_STATES = {"pending", "failed", "changed"}
# 只剩注释的片段不能发给 MySQL（会报 Query was empty）；/*! */ 条件注释是可执行语句，保留。
COMMENT_ONLY = re.compile(r"/\*(?!!).*?\*/|(--\s|#)[^\n]*", re.DOTALL)

HISTORY_DDL = f"""
CREATE TABLE IF NOT EXISTS `{HISTORY_TABLE}` (
  `version` VARCHAR(200) NOT NULL COMMENT '迁移版本，即迁移文件名',
  `checksum` CHAR(64) NOT NULL COMMENT '迁移文件内容 SHA-256 校验和',
  `status` VARCHAR(16) NOT NULL COMMENT '状态：baseline 基线登记 / success 执行成功 / failed 执行失败',
  `executed_by` VARCHAR(64) NULL COMMENT '执行迁移的数据库账号',
  `execution_ms` INT NULL COMMENT '执行耗时（毫秒）',
  `error_message` VARCHAR(2000) NULL COMMENT '执行失败时的错误摘要',
  `applied_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '登记或执行时间',
  PRIMARY KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据库迁移执行历史'
"""


@dataclass(frozen=True)
class MigrationTarget:
    name: str
    database: str
    directory: Path


@dataclass(frozen=True)
class MigrationFile:
    version: str
    path: Path
    checksum: str


@dataclass(frozen=True)
class MigrationState:
    version: str
    state: str  # pending / applied / baseline / failed / changed / missing
    checksum: str | None = None
    applied_at: object = None
    error_message: str | None = None


def targets() -> dict[str, MigrationTarget]:
    return {
        "date": MigrationTarget(
            "date", settings.mysql_database, PROJECT_ROOT / "migrations"
        ),
        "erp": MigrationTarget(
            "erp", settings.shop_source_database, Path(settings.erp_sql_dir)
        ),
    }


def resolve_targets(name: str) -> list[MigrationTarget]:
    available = targets()
    if name == "all":
        return list(available.values())
    if name not in available:
        raise ValueError(f"未知迁移目标：{name}，可选 {', '.join(available)} / all")
    return [available[name]]


def discover(target: MigrationTarget) -> list[MigrationFile]:
    if not target.directory.is_dir():
        raise FileNotFoundError(f"迁移目录不存在：{target.directory}")
    files = []
    for path in sorted(target.directory.iterdir(), key=lambda item: item.name):
        if not path.is_file() or not VERSIONED_FILE.match(path.name):
            continue
        if MANUAL_ONLY.search(path.name):
            continue
        files.append(MigrationFile(
            path.name, path, hashlib.sha256(_normalize(path.read_bytes())).hexdigest()
        ))
    return files


def _normalize(content: bytes) -> bytes:
    # 统一换行与 BOM，避免 Windows / Git autocrlf 导致校验和漂移。
    return content.removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")


def split_script(sql: str) -> Iterator[str]:
    """按 mysql 客户端语义切分脚本，支持 DELIMITER 切换（存储过程/触发器）。"""
    delimiter = ";"
    buffer: list[str] = []

    def flush(chunk: str) -> Iterator[str]:
        pieces = split_sql_statements(chunk) if delimiter == ";" else [chunk.strip()]
        yield from (s for s in pieces if COMMENT_ONLY.sub("", s).strip())

    for line in sql.replace("\r\n", "\n").split("\n"):
        match = DELIMITER_LINE.match(line)
        if match:
            yield from flush("\n".join(buffer))
            buffer = []
            delimiter = match.group(1)
            continue
        if delimiter != ";" and line.rstrip().endswith(delimiter):
            buffer.append(line.rstrip()[: -len(delimiter)])
            yield from flush("\n".join(buffer))
            buffer = []
            continue
        buffer.append(line)
    yield from flush("\n".join(buffer))


def _connect(database: str, *, migrator: bool) -> pymysql.connections.Connection:
    user = settings.mysql_user
    password = settings.mysql_password
    if migrator and settings.mysql_migrator_user:
        user = settings.mysql_migrator_user
        password = settings.mysql_migrator_password
    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _quote(identifier: str) -> str:
    return identifier.replace("`", "``")


def _history(cursor, database: str) -> dict[str, dict]:
    cursor.execute(
        "SELECT COUNT(*) AS n FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
        (database, HISTORY_TABLE),
    )
    if not cursor.fetchone()["n"]:
        return {}
    cursor.execute(
        "SELECT version, checksum, status, applied_at, error_message "
        f"FROM `{_quote(database)}`.`{HISTORY_TABLE}`"
    )
    return {row["version"]: row for row in cursor.fetchall()}


def compare(files: list[MigrationFile], history: dict[str, dict]) -> list[MigrationState]:
    states = []
    seen = set()
    for item in files:
        seen.add(item.version)
        row = history.get(item.version)
        if row is None:
            states.append(MigrationState(item.version, "pending", item.checksum))
        elif row["status"] == "failed":
            states.append(MigrationState(
                item.version, "failed", item.checksum,
                row["applied_at"], row.get("error_message"),
            ))
        elif row["status"] == "success" and row["checksum"] != item.checksum:
            states.append(MigrationState(
                item.version, "changed", item.checksum, row["applied_at"]
            ))
        else:
            states.append(MigrationState(
                item.version,
                "baseline" if row["status"] == "baseline" else "applied",
                item.checksum,
                row["applied_at"],
            ))
    for version, row in history.items():
        if version not in seen:
            states.append(MigrationState(
                version, "missing", row["checksum"], row["applied_at"]
            ))
    return states


def status(target: MigrationTarget) -> list[MigrationState]:
    files = discover(target)
    connection = _connect(target.database, migrator=False)
    try:
        with connection.cursor() as cursor:
            return compare(files, _history(cursor, target.database))
    finally:
        connection.close()


def baseline(target: MigrationTarget, *, through: str | None = None) -> int:
    """把现有迁移文件登记为已执行（不执行 SQL），用于冻结线上现状。"""
    files = [
        item for item in discover(target)
        if through is None or item.version <= through
    ]
    connection = _connect(target.database, migrator=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute(HISTORY_DDL)
            history = _history(cursor, target.database)
            registered = 0
            for item in files:
                if item.version in history:
                    continue
                cursor.execute(
                    f"INSERT INTO `{HISTORY_TABLE}` "
                    "(version, checksum, status, executed_by) "
                    "VALUES (%s, %s, 'baseline', CURRENT_USER())",
                    (item.version, item.checksum),
                )
                registered += 1
            return registered
    finally:
        connection.close()


def migrate(target: MigrationTarget, *, dry_run: bool = False) -> list[str]:
    files = discover(target)
    connection = _connect(target.database, migrator=True)
    executed: list[str] = []
    try:
        with connection.cursor() as cursor:
            history = _history(cursor, target.database)
            if not history:
                raise RuntimeError(
                    f"{target.name} 库还没有迁移基线。存量环境请先执行 "
                    f"`db-baseline --target {target.name}`；全新环境请先执行 init-db"
                )
            states = {state.version: state for state in compare(files, history)}
            changed = [v for v, s in states.items() if s.state == "changed"]
            if changed:
                raise RuntimeError(
                    "以下已执行的迁移文件被修改，请改为新增迁移文件：" + "、".join(changed)
                )
            for item in files:
                if states[item.version].state not in {"pending", "failed"}:
                    continue
                if not dry_run:
                    _apply(cursor, target, item)
                executed.append(item.version)
    finally:
        connection.close()
    return executed


def _apply(cursor, target: MigrationTarget, item: MigrationFile) -> None:
    sql = item.path.read_text(encoding="utf-8-sig")
    started = time.monotonic()
    logger.info("执行迁移 %s/%s", target.name, item.version)
    try:
        for statement in split_script(sql):
            cursor.execute(statement)
    except Exception as exc:
        # MySQL 的 DDL 无法回滚，失败位置写入历史表后中止，由人工确认再重跑。
        _record(cursor, target, item, "failed", started, str(exc)[:2000])
        raise RuntimeError(f"迁移 {item.version} 执行失败：{exc}") from exc
    _record(cursor, target, item, "success", started, None)


def _record(cursor, target: MigrationTarget, item: MigrationFile,
            state: str, started: float, error: str | None) -> None:
    # 脚本里可能有 USE 语句切换了当前库，写历史前切回目标库。
    cursor.execute(f"USE `{_quote(target.database)}`")
    cursor.execute(
        f"REPLACE INTO `{HISTORY_TABLE}` "
        "(version, checksum, status, executed_by, execution_ms, error_message) "
        "VALUES (%s, %s, %s, CURRENT_USER(), %s, %s)",
        (item.version, item.checksum, state,
         int((time.monotonic() - started) * 1000), error),
    )


def warn_pending_on_startup() -> None:
    """启动时只读检查，发现待执行迁移只告警，不阻断服务。"""
    for target in targets().values():
        try:
            pending = [
                state.version for state in status(target)
                if state.state in PENDING_STATES
            ]
        except Exception as exc:  # 检查本身失败不能影响服务启动，只记录告警。
            logger.warning("迁移状态检查失败 target=%s: %s", target.name, exc)
            continue
        if pending:
            logger.warning(
                "%s 库有 %d 个待执行迁移：%s。请执行 "
                "python -m backend.cli db-migrate --target %s",
                target.name, len(pending), ", ".join(pending[:10]), target.name,
            )

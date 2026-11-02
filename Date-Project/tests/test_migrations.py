from __future__ import annotations

from pathlib import Path

import pytest

from backend.infrastructure import migrations


def test_split_script_handles_delimiter_blocks():
    sql = """
CREATE TABLE a (id INT);
DELIMITER $$
CREATE PROCEDURE p()
BEGIN
  SELECT 1;
  SELECT 2;
END$$
DELIMITER ;
INSERT INTO a VALUES (1); -- 注释里的 ; 不切分
"""
    statements = list(migrations.split_script(sql))
    assert statements[0] == "CREATE TABLE a (id INT)"
    assert statements[1].startswith("CREATE PROCEDURE p()")
    assert "SELECT 2;" in statements[1] and statements[1].endswith("END")
    assert statements[2].startswith("INSERT INTO a VALUES (1)")
    assert len(statements) == 3


def test_discover_only_takes_versioned_forward_scripts(tmp_path):
    for name in (
        "20261101_add_table.sql",
        "20261102_menu_rollback.sql",
        "20261102_menu_verify.sql",
        "20261103_products_validate.sql",
        "deploy_patch_20260713.sql",
        "20261104_notes.md",
        "jmh_data_platform.sql",
    ):
        (tmp_path / name).write_text("SELECT 1;", encoding="utf-8")
    target = migrations.MigrationTarget("date", "db", tmp_path)

    assert [item.version for item in migrations.discover(target)] == [
        "20261101_add_table.sql"
    ]


def test_checksum_ignores_bom_and_crlf(tmp_path):
    (tmp_path / "20261101_a.sql").write_bytes(b"\xef\xbb\xbfSELECT 1;\r\n")
    (tmp_path / "20261102_b.sql").write_bytes(b"SELECT 1;\n")
    first, second = migrations.discover(
        migrations.MigrationTarget("date", "db", tmp_path)
    )
    assert first.checksum == second.checksum


def _file(version: str, checksum: str = "c1") -> migrations.MigrationFile:
    return migrations.MigrationFile(version, Path(version), checksum)


def test_compare_classifies_every_state():
    files = [_file("1_a.sql"), _file("2_b.sql", "new"), _file("3_c.sql"),
             _file("4_d.sql"), _file("5_e.sql")]
    history = {
        "1_a.sql": {"checksum": "c1", "status": "success", "applied_at": None},
        "2_b.sql": {"checksum": "old", "status": "success", "applied_at": None},
        "3_c.sql": {"checksum": "other", "status": "baseline", "applied_at": None},
        "4_d.sql": {"checksum": "c1", "status": "failed", "applied_at": None,
                    "error_message": "boom"},
        "9_gone.sql": {"checksum": "c1", "status": "success", "applied_at": None},
    }
    states = {s.version: s.state for s in migrations.compare(files, history)}
    assert states == {
        "1_a.sql": "applied",
        "2_b.sql": "changed",
        # 基线登记的是线上已人工执行的历史文件，校验和不作约束。
        "3_c.sql": "baseline",
        "4_d.sql": "failed",
        "5_e.sql": "pending",
        "9_gone.sql": "missing",
    }


def test_migrate_refuses_without_baseline(monkeypatch, tmp_path):
    (tmp_path / "20261101_a.sql").write_text("SELECT 1;", encoding="utf-8")

    class Cursor:
        def execute(self, *args):
            pass

        def fetchone(self):
            return {"n": 0}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(migrations, "_connect", lambda *a, **kw: Connection())
    with pytest.raises(RuntimeError, match="db-baseline"):
        migrations.migrate(migrations.MigrationTarget("date", "db", tmp_path))


@pytest.mark.parametrize("name", ["date", "erp"])
def test_repository_migration_scripts_all_split(name):
    target = migrations.targets()[name]
    files = migrations.discover(target)
    assert files, f"{target.directory} 下没有迁移文件"
    for item in files:
        sql = item.path.read_text(encoding="utf-8-sig")
        assert list(migrations.split_script(sql)) is not None


def test_agent_target_is_managed_from_start(monkeypatch, tmp_path):
    (tmp_path / "20261103_ai_agent.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "20261103_ai_conversations.sql").write_text("SELECT 1;", encoding="utf-8")
    target = migrations.MigrationTarget("agent", "jmh_ai_agent", tmp_path, managed_from_start=True)
    assert migrations.targets()["agent"].managed_from_start
    assert migrations.targets()["agent"].directory.name == "migrations_agent"

    def no_connection(*args, **kwargs):
        raise AssertionError("不应连接数据库")

    monkeypatch.setattr(migrations, "_connect", no_connection)
    # 基线登记会让建表脚本被跳过，新库必须拒绝
    assert migrations.baseline(target) == 0
    monkeypatch.setattr(migrations, "_database_exists", lambda database, migrator: False)
    assert migrations.migrate(target, dry_run=True) == [
        "20261103_ai_agent.sql", "20261103_ai_conversations.sql"]
    assert [s.state for s in migrations.status(target)] == ["pending", "pending"]


def test_repository_agent_migrations_split():
    files = migrations.discover(migrations.targets()["agent"])
    assert [item.version for item in files] == ["20261103_ai_agent.sql", "20261103_ai_conversations.sql"]
    for item in files:
        statements = list(migrations.split_script(item.path.read_text(encoding="utf-8")))
        bodies = [migrations.COMMENT_ONLY.sub("", s).strip().upper() for s in statements]
        assert bodies and all(body.startswith("CREATE TABLE IF NOT EXISTS") for body in bodies)

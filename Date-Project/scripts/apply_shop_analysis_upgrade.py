"""Local-only, additive 06/07 deployment with exclusive backups and before/after checks.

Does not start services or invoke synchronization. Existing configs and procurement
rows must be unchanged; only missing rule/menu records may be added.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import settings


def statements(source):
    """Split reviewed MySQL text, preserving quoted semicolons and removing comments."""
    result, buf = [], []
    i, quote = 0, None
    while i < len(source):
        ch = source[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and i+1 < len(source):
                i += 1
                buf.append(source[i])
            elif ch == quote:
                if i+1 < len(source) and source[i+1] == quote:
                    i += 1
                    buf.append(source[i])
                else:
                    quote = None
        elif source.startswith("--",i) and (i+2 == len(source) or source[i+2].isspace()):
            end = source.find("\n",i)
            i = len(source) if end < 0 else end
            buf.append("\n")
            continue
        elif ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
        elif ch == ";":
            text = "".join(buf).strip()
            if text: result.append(text)
            buf = []
        else:
            buf.append(ch)
        i += 1
    if quote: raise ValueError("SQL引号未闭合")
    if "".join(buf).strip(): result.append("".join(buf).strip())
    return result


def dump(path, value):
    with path.open("x",encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, default=str)


def snapshot(cursor):
    data = {}
    queries = {
        "rules": "SELECT * FROM ebay_replenishment_v2_level_rule ORDER BY rule_no",
        "menus": "SELECT * FROM sys_menu WHERE perms LIKE 'procurement:pendingPurchase:%' ORDER BY menu_id",
        "grants": """SELECT rm.* FROM sys_role_menu rm JOIN sys_menu m ON m.menu_id=rm.menu_id
                    WHERE m.perms LIKE 'procurement:pendingPurchase:%' ORDER BY rm.role_id,rm.menu_id""",
        "purchases": "SELECT * FROM procurement_pending_purchase ORDER BY id",
    }
    for name, query in queries.items():
        try:
            cursor.execute(query)
            data[name] = list(cursor.fetchall())
        except pymysql.err.ProgrammingError as exc:
            if name == "rules" and exc.args[0] == 1146: data[name] = []
            else: raise
    data["schema"] = {}
    for table in ("ebay_replenishment_v2_level_rule","sys_menu","procurement_pending_purchase"):
        try:
            cursor.execute("SHOW CREATE TABLE `" + table + "`")
            data["schema"][table] = cursor.fetchone()
        except pymysql.err.ProgrammingError as exc:
            if table == "ebay_replenishment_v2_level_rule" and exc.args[0] == 1146: continue
            raise
    return data


def run(cursor, sqls):
    result=[]
    for sql in sqls:
        cursor.execute(sql)
        result.append(dict(statement=sql, affected=cursor.rowcount,
                           rows=list(cursor.fetchall()) if cursor.description else None))
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--sql-dir", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--apply", action="store_true")
    args=parser.parse_args()
    if settings.mysql_host not in ("127.0.0.1","localhost","::1"):
        raise SystemExit("拒绝：此执行器只允许本机数据库")
    if settings.shop_source_database.lower() != "jmh_data_platform":
        raise SystemExit("拒绝：源数据库不是jmh_data_platform")
    sqlpath=args.sql_dir/"06_店铺分析与采购优化.sql"
    verify=args.sql_dir/"07_店铺分析与采购优化_验证_只读.sql"
    sqlbytes=sqlpath.read_bytes()
    digest=hashlib.sha256(sqlbytes).hexdigest()
    if digest != args.expected_sha256.lower():
        raise SystemExit("SQL已改变，请重新审核其SHA256")
    sqls=statements(sqlbytes.decode("utf-8-sig"))
    checks=statements(verify.read_text(encoding="utf-8-sig"))
    allowed=r"^(USE `jmh_data_platform`$|SET |START TRANSACTION$|COMMIT$|SELECT |CREATE TABLE IF NOT EXISTS `ebay_replenishment_v2_level_rule`|INSERT INTO `(?:ebay_replenishment_v2_level_rule|sys_menu)`)"
    if any(not re.match(allowed,s,re.I) for s in sqls):
        raise SystemExit("拒绝：06包含白名单以外语句")
    if any(not re.match(r"^(SELECT |USE `jmh_data_platform`$)",s,re.I) for s in checks):
        raise SystemExit("拒绝：07包含非只读语句")
    if not args.apply:
        print(json.dumps(dict(sql_sha256=digest,statements=len(sqls),checks=len(checks))))
        return
    folder=args.sql_dir/"backups"/("shop_analysis_"+datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    folder.mkdir(parents=True,exist_ok=False)
    connection=pymysql.connect(host=settings.mysql_host,port=settings.mysql_port,
        user=settings.mysql_user,password=settings.mysql_password,database="jmh_data_platform",
        charset="utf8mb4",cursorclass=pymysql.cursors.DictCursor,autocommit=False,
        connect_timeout=10,read_timeout=30,write_timeout=30)
    report=dict(sql_sha256=digest,backup=str(folder),host=settings.mysql_host,
                port=settings.mysql_port,database="jmh_data_platform")
    try:
        with connection.cursor() as cursor:
            before=snapshot(cursor)
            dump(folder/"before.json",before)
            connection.rollback()
            dump(folder/"executed_06.json",run(cursor,sqls))
            after=snapshot(cursor)
            dump(folder/"after.json",after)
            old={row["rule_no"]:row for row in before["rules"]}
            current={row["rule_no"]:row for row in after["rules"]}
            assert all(current.get(key)==value for key,value in old.items()), "已有等级配置发生变化"
            old_menus={row["menu_id"]:row for row in before["menus"]}
            new_menus={row["menu_id"]:row for row in after["menus"]}
            assert all(new_menus.get(key)==value for key,value in old_menus.items()), "已有菜单发生变化"
            assert before["purchases"]==after["purchases"], "采购数据在执行期间发生变化，请核对并发操作"
            assert before["grants"]==after["grants"], "角色授权发生变化"
            connection.rollback()
            dump(folder/"repeated_06.json",run(cursor,sqls))
            twice=snapshot(cursor)
            assert twice==after, "重复执行改变了现有数据或结构"
            dump(folder/"verification_07.json",run(cursor,checks))
            report.update(rules_before=len(before["rules"]),rules_after=len(after["rules"]),
                rules_inserted=len(after["rules"])-len(before["rules"]),
                menus_inserted=len(after["menus"])-len(before["menus"]),
                purchases_unchanged=True,purchase_rows=len(before["purchases"]),
                grants_unchanged=True,existing_rules_unchanged=True,idempotent=True,
                verification_statements=len(checks),status="success")
            dump(folder/"result.json",report)
            connection.rollback()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print(json.dumps(report,ensure_ascii=False,default=str))


if __name__ == "__main__":
    main()


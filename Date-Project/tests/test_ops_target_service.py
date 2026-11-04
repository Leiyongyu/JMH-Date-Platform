"""财务中心「运营目标与人效」：合计/达成率与原 Excel 公式结果一致，人效预警、一致性提示、修改校验。"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from backend.services import ops_target_service as service

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "20261104_ops_dept_target.sql"


def seed_rows() -> list[dict]:
    """直接解析迁移里的初始数据，保证测试与入库值一致。"""
    sql = MIGRATION.read_text(encoding="utf-8")
    columns = re.search(r"INSERT IGNORE INTO fin_ops_dept_target\s*\((.*?)\)\s*VALUES", sql, re.S).group(1)
    names = [c.strip() for c in columns.split(",")]
    rows = []
    for group in re.findall(r"\((2026,.*?)\)", sql, re.S):
        values = [v.strip() for v in group.replace("\n", " ").split(",")]
        row = {}
        for name, value in zip(names, values):
            if value == "NULL":
                row[name] = None
            elif value.startswith("'"):
                row[name] = value.strip("'")
            else:
                row[name] = Decimal(value)
        row.update(remark=None, updated_at=None)
        rows.append(row)
    return rows


@pytest.fixture
def seeded(monkeypatch):
    rows = seed_rows()
    monkeypatch.setattr(service.repo, "years", lambda: [2026])
    monkeypatch.setattr(service.repo, "rows", lambda year: rows if year == 2026 else [])
    return rows


def by_dept(report):
    return {row["dept_code"]: row for row in report["rows"]}


def test_seed_matches_excel_and_totals_follow_excel_formulas(seeded):
    report = service.get_report(None)
    assert report["year"] == 2026 and [r["dept_code"] for r in report["rows"]] == ["US1", "US2", "US3&US5", "EU", "eBay"]
    rows, total = by_dept(report), report["total"]
    assert rows["US1"]["achievement_rate"] == 0.6 and rows["EU"]["achievement_rate"] == 1.0214
    assert rows["US3&US5"]["achievement_rate"] is None  # 年度实际未填
    assert (total["floor_target"], total["sprint_target"], total["actual_amount"]) == (1507, 1800, 1251)
    assert total["achievement_rate"] == 0.695
    assert total["new_product_target"] == 2090 and total["est_gross_profit"] == 1490.16
    assert total["labor_cost_pack"] == 10.918 and total["headcount"] == 13
    assert total["target_margin_rate"] == 0.1425  # 各部门平均（Excel 的 119% 是毛利润÷实际，不是毛利率）
    assert total["q1_efficiency_target"] == 19.685 and total["annual_efficiency_target"] == 105.4175
    assert [total[f"q{q}_target"] for q in (1, 2, 3, 4)] == [236.23, 325.5, 376.2, 432.07]
    # Excel 月度表的「合计」是手填的（US1 写 420、US2 写 300、总计 1448），这里按 1~12 月实际相加
    assert total["quarter_target_total"] == 1370 and total["month_target_total"] == 1402.6
    assert rows["US1"]["quarter_target_total"] == 420 and rows["US1"]["month_target_total"] == 394.6
    assert rows["US2"]["month_target_total"] == 280


def test_inconsistencies_are_reported_not_blocked(seeded):
    notes = service.get_report(2026)["notes"]
    assert "US3&US5：月度目标合计 328 万元，与季度目标合计 300 万元不一致" in notes
    assert "EU：月度目标合计 400 万元，与季度目标合计 350 万元不一致" in notes
    assert "US1：季度目标合计 420 万元，与年度冲刺目标 440 万元不一致" in notes
    assert "US1：月度目标合计 394.6 万元，与季度目标合计 420 万元不一致" in notes
    assert "US2：月度目标合计 280 万元，与季度目标合计 300 万元不一致" in notes


def test_efficiency_warnings(seeded):
    seeded[0]["q1_actual"] = Decimal("60")   # 60 ÷ 4 人 = 15 万/人 < 20 → 红色
    seeded[1]["q1_actual"] = Decimal("90")   # 90 ÷ 3 = 30 → 正常
    seeded[1]["labor_cost_pack"] = Decimal("30")  # 30 ÷ 222 = 13.5% > 12% → 红色
    seeded[2]["est_gross_profit"] = Decimal("120")  # 120 ÷ 3 = 40 < 50 → 黄色
    rows = by_dept(service.get_report(2026))
    assert rows["US1"]["q1_actual_efficiency"] == 15 and rows["US1"]["levels"]["q1_actual_efficiency"] == "red"
    assert rows["US1"]["q1_achievement_rate"] == round(60 / 75.23, 4)
    assert "q1_actual_efficiency" not in rows["US2"]["levels"]
    assert rows["US2"]["levels"]["labor_cost_rate"] == "red"
    assert rows["US3&US5"]["levels"]["gross_profit_per_head"] == "yellow"


def test_update_validation_and_passthrough(monkeypatch, seeded):
    saved = {}

    def fake_update(year, dept, values, operator):
        saved.update(year=year, dept=dept, values=values, operator=operator)
        return dept != "NONE"
    monkeypatch.setattr(service.repo, "update_row", fake_update)
    service.update_row(2026, "US1", {"q1_actual": "88.5", "headcount": 5, "target_margin_rate": 0.16,
                                     "new_product_actual": None, "remark": " 备注 "}, "admin")
    assert saved["values"] == {"q1_actual": Decimal("88.5000"), "headcount": 5,
                               "target_margin_rate": Decimal("0.1600"), "new_product_actual": None, "remark": "备注"}
    assert saved["operator"] == "admin"
    for bad, message in [({"q1_actual": -1}, "负数"), ({"headcount": 2.5}, "整数"),
                         ({"target_margin_rate": 15}, "不能大于 1"), ({"q1_actual": "abc"}, "数字"),
                         ({"dept_code": "X"}, "不允许修改")]:
        with pytest.raises(ValueError, match=message):
            service.update_row(2026, "US1", bad, "admin")
    with pytest.raises(LookupError):
        service.update_row(2026, "NONE", {"q1_actual": 1}, "admin")


def test_empty_database_explains_migration(monkeypatch):
    monkeypatch.setattr(service.repo, "years", lambda: [])
    report = service.get_report(2026)
    assert report["rows"] == [] and "迁移" in report["notes"][0]

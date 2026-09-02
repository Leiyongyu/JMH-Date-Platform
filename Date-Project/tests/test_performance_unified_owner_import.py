from contextlib import contextmanager
from io import BytesIO

import pandas as pd
import pytest

from backend.parsers.performance_owner_rule_parser import (
    parse_unified_owner_rule_excel,
)
from backend.services import performance_service


SHEET_KEYS = {
    "EU组-sku品牌负责人": "品牌",
    "EU-OTH负责人": "中间码-OTH",
    "US1组店铺负责人": "店铺名",
    "US2组店铺负责人": "店铺名",
    "US3组店铺负责人": "店铺名",
    # The production template has a blank first-column header here.
    "EBAYsku负责人": "",
}
IGNORED_SHEETS = {
    "女鞋一部": ("组别（US4/US6/多平台）", "店铺"),
    "女鞋二部": ("店铺",),
    "女鞋三部": ("店铺",),
}


def _unified_workbook(
    *,
    august_owner: str = "八月负责人",
    september_owner: str = "九月负责人",
    overrides: dict[str, list[dict]] | None = None,
    extra_sheet: bool = False,
) -> bytes:
    frames = {}
    for index, (sheet_name, key_column) in enumerate(SHEET_KEYS.items(), start=1):
        key = (
            f"店铺{index}"
            if "店铺负责人" in sheet_name
            else f"KEY{index}"
        )
        frames[sheet_name] = pd.DataFrame(
            [
                {
                    key_column: key,
                    "202608负责人": august_owner,
                    "202609负责人": september_owner,
                }
            ]
        )
    for sheet_name, columns in IGNORED_SHEETS.items():
        row = {column: f"忽略-{sheet_name}" for column in columns}
        row.update(
            {
                "202608负责人": "女鞋负责人",
                "202609负责人": "女鞋负责人",
            }
        )
        frames[sheet_name] = pd.DataFrame([row])
    for sheet_name, rows in (overrides or {}).items():
        frames[sheet_name] = pd.DataFrame(rows)
    if extra_sheet:
        frames["说明"] = pd.DataFrame([{"备注": "不允许额外Sheet"}])
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, frame in frames.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()


def test_unified_parser_reads_all_month_columns_and_returns_sheet_stats():
    parsed = parse_unified_owner_rule_excel(
        _unified_workbook(),
        "负责人表.xlsx",
        "batch-1",
    )

    assert parsed["months"] == ["2026-08", "2026-09"]
    assert parsed["month_count"] == 2
    assert parsed["platform_stats"] == {"amazon": 10, "ebay": 2}
    assert len(parsed["rules"]) == 12
    assert {row["principal_name"] for row in parsed["rules"]} == {
        "八月负责人",
        "九月负责人",
    }
    assert {row["stat_month"] for row in parsed["rules"]} == {
        "2026-08",
        "2026-09",
    }
    assert {
        (row["source_sheet"], row["platform"], row["rule_type"])
        for row in parsed["rules"]
    } == {
        ("EU组-sku品牌负责人", "amazon", "BRAND"),
        ("EU-OTH负责人", "amazon", "OTH_CODE"),
        ("US1组店铺负责人", "amazon", "STORE"),
        ("US2组店铺负责人", "amazon", "STORE"),
        ("US3组店铺负责人", "amazon", "STORE"),
        ("EBAYsku负责人", "ebay", "EBAY_BRAND"),
    }
    assert [item["sheet_name"] for item in parsed["sheet_stats"]] == list(
        SHEET_KEYS
    )
    assert all(item["imported_rows"] == 2 for item in parsed["sheet_stats"])
    assert all(item["month_count"] == 2 for item in parsed["sheet_stats"])


def test_unified_parser_ignores_women_sheets():
    parsed = parse_unified_owner_rule_excel(
        _unified_workbook(),
        "sku店铺映射表.xlsx",
        "batch-ignore-women",
    )

    assert {row["source_sheet"] for row in parsed["rules"]}.isdisjoint(
        IGNORED_SHEETS
    )
    assert parsed["ignored_sheets"] == sorted(IGNORED_SHEETS)
    assert parsed["platform_stats"] == {"amazon": 10, "ebay": 2}


def test_unified_parser_requires_required_sheets_and_rejects_unknown_sheets():
    with pytest.raises(ValueError, match="Sheet结构不正确.*非模板Sheet"):
        parse_unified_owner_rule_excel(
            _unified_workbook(extra_sheet=True),
            "负责人表.xlsx",
            "batch-2",
        )


def test_unified_parser_persists_blank_owner_as_unassigned_rule():
    parsed = parse_unified_owner_rule_excel(
        _unified_workbook(
            overrides={
                "EBAYsku负责人": [
                    {
                        "": "BMW",
                        "202608负责人": float("nan"),
                        "202609负责人": "未来负责人",
                    }
                ]
            }
        ),
        "负责人表.xlsx",
        "batch-3",
    )

    ebay_rule = next(
        row
        for row in parsed["rules"]
        if row["source_sheet"] == "EBAYsku负责人"
        and row["stat_month"] == "2026-08"
    )
    ebay_stat = next(
        row
        for row in parsed["sheet_stats"]
        if row["sheet_name"] == "EBAYsku负责人"
    )
    assert ebay_rule["principal_name"] == ""
    assert ebay_stat["imported_rows"] == 2
    assert ebay_stat["unassigned_rows"] == 1
    assert ebay_stat["skipped_blank_principal_rows"] == 0


def test_unified_parser_persists_pending_owner_as_empty_string():
    parsed = parse_unified_owner_rule_excel(
        _unified_workbook(
            overrides={
                "US1组店铺负责人": [
                    {
                        "店铺名": "暂未配置店铺",
                        "202608负责人": "待定",
                        "202609负责人": "未来负责人",
                    }
                ]
            }
        ),
        "sku店铺映射表.xlsx",
        "batch-empty-amazon",
    )

    us1_rule = next(
        row
        for row in parsed["rules"]
        if row["source_sheet"] == "US1组店铺负责人"
        and row["stat_month"] == "2026-08"
    )
    us1_stat = next(
        row
        for row in parsed["sheet_stats"]
        if row["sheet_name"] == "US1组店铺负责人"
    )
    assert us1_rule["principal_name"] == ""
    assert us1_stat["imported_rows"] == 2
    assert us1_stat["unassigned_rows"] == 1


def test_unified_parser_rejects_required_sheet_without_match_keys():
    with pytest.raises(
        ValueError,
        match="US1组店铺负责人.*没有有效匹配键记录",
    ):
        parse_unified_owner_rule_excel(
            _unified_workbook(
                overrides={
                    "US1组店铺负责人": [
                        {
                            "店铺名": float("nan"),
                            "202608负责人": "负责人甲",
                            "202609负责人": "未来负责人",
                        }
                    ]
                }
            ),
            "sku店铺映射表.xlsx",
            "batch-no-match-key",
        )


def test_unified_parser_rejects_conflicting_store_owners_across_us_sheets():
    overrides = {
        "US1组店铺负责人": [
            {
                "店铺名": "同名店铺",
                "202608负责人": "负责人甲",
                "202609负责人": "未来负责人",
            }
        ],
        "US2组店铺负责人": [
            {
                "店铺名": "同名店铺",
                "202608负责人": "负责人乙",
                "202609负责人": "未来负责人",
            }
        ],
    }
    with pytest.raises(ValueError, match="Amazon店铺负责人配置冲突"):
        parse_unified_owner_rule_excel(
            _unified_workbook(overrides=overrides),
            "负责人表.xlsx",
            "batch-4",
        )


def test_unified_import_upserts_all_months_without_deleting_history(
    monkeypatch,
):
    parsed = parse_unified_owner_rule_excel(
        _unified_workbook(),
        "负责人表.xlsx",
        "batch-parser",
    )
    fake_connection = type(
        "FakeConnection",
        (),
        {"commits": 0, "commit": lambda self: setattr(self, "commits", self.commits + 1)},
    )()

    @contextmanager
    def connection_context():
        yield fake_connection

    upsert_calls = []
    batch_calls = []
    refresh_calls = []
    monkeypatch.setattr(
        performance_service,
        "parse_unified_owner_rule_excel",
        lambda *_args, **_kwargs: parsed,
    )
    monkeypatch.setattr(
        performance_service.repo,
        "performance_connection",
        connection_context,
    )

    def upsert(connection, rules, raw_rows):
        upsert_calls.append((connection, rules, raw_rows))

    monkeypatch.setattr(
        performance_service.repo,
        "upsert_owner_rules",
        upsert,
    )
    monkeypatch.setattr(
        performance_service.repo,
        "insert_import_batch",
        lambda connection, payload: batch_calls.append((connection, payload)),
    )

    def refresh(stat_month, platform, **kwargs):
        refresh_calls.append((stat_month, platform, kwargs))
        return {"stat_month": stat_month, "platform": platform}

    monkeypatch.setattr(performance_service, "refresh_performance", refresh)
    monkeypatch.setattr(
        performance_service,
        "performance_months",
        lambda _limit: [{"stat_month": "2026-08"}],
    )

    result = performance_service.import_unified_owner_rules(
        b"workbook",
        "负责人表.xlsx",
        request_id="request-1",
    )

    assert len(upsert_calls) == 1
    assert {row["platform"] for row in upsert_calls[0][1]} == {
        "amazon",
        "ebay",
    }
    assert fake_connection.commits == 1
    assert batch_calls[0][1]["platform"] == "combined"
    assert batch_calls[0][1]["stat_month"] is None
    assert refresh_calls == [
        (
            "2026-08",
            "combined",
            {
                "trigger_source": "unified_owner_rule_import",
                "request_id": "request-1",
            },
        )
    ]
    assert result["month_count"] == 2
    assert result["months"] == ["2026-08", "2026-09"]
    assert result["platform_stats"] == {"amazon": 10, "ebay": 2}
    assert result["deleted_ods_rows"] == 0
    assert result["deleted_dwd_rows"] == 0
    assert result["refreshed_months"] == ["2026-08"]
    assert result["skipped_refresh_months"] == ["2026-09"]
    assert result["ignored_sheets"] == sorted(IGNORED_SHEETS)
    assert len(result["refreshes"]) == 1

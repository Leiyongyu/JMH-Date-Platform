from contextlib import contextmanager
from io import BytesIO

import pandas as pd
import pytest

from backend.parsers.performance_owner_rule_parser import (
    parse_unified_owner_rule_excel,
)
from backend.services import performance_service


SHEET_KEYS = {
    "EU-品牌": "品牌",
    "EU-OTH": "中间码-OTH",
    "US1": "店铺名",
    "US2": "店铺名",
    "Ebay": "品牌",
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
        key = f"KEY{index}" if sheet_name not in {"US1", "US2"} else f"店铺{index}"
        frames[sheet_name] = pd.DataFrame(
            [
                {
                    key_column: key,
                    "202608负责人": august_owner,
                    "202609负责人": september_owner,
                }
            ]
        )
    for sheet_name, rows in (overrides or {}).items():
        frames[sheet_name] = pd.DataFrame(rows)
    if extra_sheet:
        frames["说明"] = pd.DataFrame([{"备注": "不允许额外Sheet"}])
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, frame in frames.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()


def test_unified_parser_reads_only_selected_month_and_returns_sheet_stats():
    parsed = parse_unified_owner_rule_excel(
        _unified_workbook(),
        "负责人表.xlsx",
        "2026-08",
        "batch-1",
    )

    assert parsed["stat_month"] == "2026-08"
    assert parsed["months"] == ["2026-08"]
    assert parsed["platform_stats"] == {"amazon": 4, "ebay": 1}
    assert len(parsed["rules"]) == 5
    assert {row["principal_name"] for row in parsed["rules"]} == {"八月负责人"}
    assert {row["stat_month"] for row in parsed["rules"]} == {"2026-08"}
    assert {
        (row["source_sheet"], row["platform"], row["rule_type"])
        for row in parsed["rules"]
    } == {
        ("EU-品牌", "amazon", "BRAND"),
        ("EU-OTH", "amazon", "OTH_CODE"),
        ("US1", "amazon", "STORE"),
        ("US2", "amazon", "STORE"),
        ("Ebay", "ebay", "EBAY_BRAND"),
    }
    assert [item["sheet_name"] for item in parsed["sheet_stats"]] == list(
        SHEET_KEYS
    )
    assert all(item["imported_rows"] == 1 for item in parsed["sheet_stats"])


def test_unified_parser_requires_exactly_the_five_template_sheets():
    with pytest.raises(ValueError, match="必须且只能包含5个标准Sheet.*非模板Sheet"):
        parse_unified_owner_rule_excel(
            _unified_workbook(extra_sheet=True),
            "负责人表.xlsx",
            "2026-08",
            "batch-2",
        )


def test_unified_parser_rejects_when_any_sheet_has_no_valid_selected_month_rows():
    with pytest.raises(ValueError, match="Ebay.*202608负责人.*没有有效负责人记录"):
        parse_unified_owner_rule_excel(
            _unified_workbook(
                overrides={
                    "Ebay": [
                        {
                            "品牌": "BMW",
                            "202608负责人": float("nan"),
                            "202609负责人": "未来负责人",
                        }
                    ]
                }
            ),
            "负责人表.xlsx",
            "2026-08",
            "batch-3",
        )


def test_unified_parser_rejects_conflicting_store_owners_across_us_sheets():
    overrides = {
        "US1": [
            {
                "店铺名": "同名店铺",
                "202608负责人": "负责人甲",
                "202609负责人": "未来负责人",
            }
        ],
        "US2": [
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
            "2026-08",
            "batch-4",
        )


def test_unified_import_replaces_both_platforms_and_refreshes_combined_once(
    monkeypatch,
):
    parsed = parse_unified_owner_rule_excel(
        _unified_workbook(),
        "负责人表.xlsx",
        "2026-08",
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

    replace_calls = []
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

    def replace(connection, stat_month, rules, raw_rows):
        replace_calls.append((connection, stat_month, rules, raw_rows))
        return {
            "deleted_ods_rows": 10,
            "deleted_dwd_rows": 10,
            "inserted_ods_rows": 5,
            "inserted_dwd_rows": 5,
        }

    monkeypatch.setattr(
        performance_service.repo,
        "replace_unified_owner_rule_month",
        replace,
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

    result = performance_service.import_unified_owner_rules(
        b"workbook",
        "负责人表.xlsx",
        "2026-08",
        request_id="request-1",
    )

    assert len(replace_calls) == 1
    assert replace_calls[0][1] == "2026-08"
    assert {row["platform"] for row in replace_calls[0][2]} == {
        "amazon",
        "ebay",
    }
    assert fake_connection.commits == 1
    assert batch_calls[0][1]["platform"] == "combined"
    assert batch_calls[0][1]["stat_month"] == "2026-08"
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
    assert result["month_count"] == 1
    assert result["platform_stats"] == {"amazon": 4, "ebay": 1}
    assert len(result["refreshes"]) == 1

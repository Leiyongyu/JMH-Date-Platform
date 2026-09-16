"""等级导入离线用例；工作簿全部在内存构造，不读用户文件或连接数据库。"""
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

from backend.services import ebay_inventory_grade_parser as parser
from backend.services import ebay_inventory_detail_service as service


def workbook_bytes(rows, *, extra_sheets=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "等级"
    for row in rows:
        sheet.append(row)
    for title, values in (extra_sheets or {}).items():
        extra = workbook.create_sheet(title)
        for row in values:
            extra.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def standard_rows(*rows):
    return [["SKU", "站点", "等级"], *rows]


def test_site_aliases_normalize_and_grade_text_is_preserved():
    content = workbook_bytes(standard_rows(
        [" frd-70618-0687 ", " de ", " A+ "],
        ["BMW-30055-0182", "UK", "长尾产品-B"],
        ["GM-40066-0056", "US", "正常"],
    ))
    result = parser.parse_grades(content, "ebay-sku产品等级表.xlsx")
    assert result["rows"] == [
        {"site": "德国", "sku": "FRD-70618-0687", "grade": "A+"},
        {"site": "英国", "sku": "BMW-30055-0182", "grade": "长尾产品-B"},
        {"site": "美国", "sku": "GM-40066-0056", "grade": "正常"},
    ]
    assert result["source_rows"] == 3
    assert result["skipped_rows"] == result["duplicate_rows"] == 0


@pytest.mark.parametrize("alias,expected", [
    ("GERMANY", "德国"), ("GB", "英国"), ("UNITED KINGDOM", "英国"),
    ("USA", "美国"), ("UNITED STATES", "美国"), ("FR", "法国"),
    ("德国", "德国"), ("英国", "英国"), ("美国", "美国"),
])
def test_normalize_site_aliases(alias, expected):
    assert parser.normalize_site(alias) == expected


def test_identical_duplicates_deduplicate_across_sheets_and_site_aliases():
    content = workbook_bytes(
        standard_rows(["FRD-70618-0687", "DE", "A"]),
        extra_sheets={"补充": standard_rows(
            ["frd-70618-0687", "德国", "A"],
            ["FRD-70618-0687", "UK", "B"],
        )},
    )
    result = parser.parse_grades(content, "grades.xlsx")
    assert result["source_rows"] == 3
    assert result["duplicate_rows"] == 1
    assert len(result["rows"]) == 2
    assert result["rows"][1]["site"] == "英国"


def test_conflicting_valid_duplicate_rejects_entire_file_before_database_write(monkeypatch):
    content = workbook_bytes(standard_rows(
        ["FRD-70618-0687", "DE", "A"],
        ["frd-70618-0687", "德国", "B"],
    ))
    save = MagicMock()
    monkeypatch.setattr(service.repository, "upsert_grades", save)
    with pytest.raises(ValueError, match="存在不同等级"):
        service.import_grades(content, "grades.xlsx", "operator")
    save.assert_not_called()


def test_bad_rows_skip_with_counts_and_explicit_warnings():
    content = workbook_bytes(standard_rows(
        ["FRD-70618-0687", "DE", "A"],
        ["#N/A", "DE", "A"],
        ["BAD-GRADE", "US", "#VALUE!"],
        ["MISSING-GRADE", "UK", None],
        ["UNKNOWN-SITE", "Atlantis", "B"],
        [None, "DE", "B"],
        ["TOO-LONG-GRADE", "DE", "A" * 65],
        ["S" * 256, "DE", "A"],
    ))
    result = parser.parse_grades(content, "grades.xlsx")
    assert result["source_rows"] == 8
    assert result["skipped_rows"] == result["warning_count"] == 7
    assert len(result["rows"]) == 1
    assert len(result["warnings"]) == 7
    assert all("第" in warning and "行" in warning for warning in result["warnings"])
    assert any("Excel错误值" in warning for warning in result["warnings"])


def test_formula_without_cached_value_is_not_imported_as_a_grade():
    content = workbook_bytes(standard_rows(
        ["FRD-70618-0687", "DE", "A"],
        ["OTHER-SKU", "DE", '=IF(1=1,"A","B")'],
    ))
    result = parser.parse_grades(content, "grades.xlsx")
    assert result["skipped_rows"] == 1
    assert len(result["rows"]) == 1


def test_warning_details_are_capped_but_total_count_is_not():
    content = workbook_bytes(standard_rows(
        ["FRD-70618-0687", "DE", "A"],
        *[[f"BAD-{index}", "unknown", "A"] for index in range(205)],
    ))
    result = parser.parse_grades(content, "grades.xlsx")
    assert result["warning_count"] == result["skipped_rows"] == 205
    assert len(result["warnings"]) == 200


def test_header_can_follow_title_and_columns_may_be_reordered():
    content = workbook_bytes([
        ["eBay产品等级"], [],
        ["备注", "等级", " sku ", "站点"],
        ["无", "A", "FRD-70618-0687", "DE"],
    ])
    result = parser.parse_grades(content, "grades.xlsx")
    assert result["rows"] == [{"site": "德国", "sku": "FRD-70618-0687", "grade": "A"}]


def test_duplicate_required_header_is_rejected():
    content = workbook_bytes([
        ["SKU", "站点", "等级", "SKU"],
        ["FRD-70618-0687", "DE", "A", "OTHER-SKU"],
    ])
    with pytest.raises(ValueError, match="重复"):
        parser.parse_grades(content, "grades.xlsx")


def test_nonempty_short_sheet_without_header_is_not_silently_ignored():
    content = workbook_bytes(
        standard_rows(["FRD-70618-0687", "DE", "A"]),
        extra_sheets={"错误表": [["编码", "国家", "产品等级"], ["X", "DE", "A"]]},
    )
    with pytest.raises(ValueError, match="表头"):
        parser.parse_grades(content, "grades.xlsx")


def test_empty_worksheets_are_harmless():
    content = workbook_bytes(
        standard_rows(["FRD-70618-0687", "DE", "A"]), extra_sheets={"空表": []},
    )
    assert len(parser.parse_grades(content, "grades.xlsx")["rows"]) == 1


@pytest.mark.parametrize("rows", [
    [["SKU", "站点", "等级"]],
    standard_rows(["#N/A", "DE", "A"]),
    [["错误表头"], ["data"]],
])
def test_no_valid_rows_rejected(rows):
    with pytest.raises(ValueError):
        parser.parse_grades(workbook_bytes(rows), "grades.xlsx")


@pytest.mark.parametrize("filename,content", [
    ("grades.xls", b"anything"), ("grades.csv", b"anything"),
    ("grades.xlsx", b""), ("grades.xlsx", b"not a zip"),
])
def test_invalid_container_or_extension_rejected(filename, content):
    with pytest.raises(ValueError):
        parser.parse_grades(content, filename)


def test_compressed_upload_limit_is_enforced_before_loading(monkeypatch):
    content = workbook_bytes(standard_rows(["SKU-1", "DE", "A"]))
    monkeypatch.setattr(parser, "MAX_FILE_BYTES", len(content) - 1)
    with pytest.raises(ValueError, match="10MB"):
        parser.parse_grades(content, "grades.xlsx")


def test_expanded_zip_size_limit_is_enforced(monkeypatch):
    content = workbook_bytes(standard_rows(["SKU-1", "DE", "A"]))
    monkeypatch.setattr(parser, "MAX_EXPANDED_BYTES", 1)
    with pytest.raises(ValueError, match="解压后过大"):
        parser.parse_grades(content, "grades.xlsx")


def test_archive_entry_limit_is_enforced():
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for index in range(2001):
            archive.writestr(f"empty-{index}", b"")
    with pytest.raises(ValueError, match="解压后过大"):
        parser.parse_grades(output.getvalue(), "grades.xlsx")


def test_total_row_limit_is_enforced_across_sheets(monkeypatch):
    content = workbook_bytes(
        standard_rows(["SKU-1", "DE", "A"]),
        extra_sheets={"补充": standard_rows(["SKU-2", "UK", "A"], ["SKU-3", "US", "B"])},
    )
    monkeypatch.setattr(parser, "MAX_ROWS", 2)
    with pytest.raises(ValueError, match="最多导入2行"):
        parser.parse_grades(content, "grades.xlsx")


def test_filename_is_metadata_not_a_file_write_target(monkeypatch):
    content = workbook_bytes(standard_rows(["SKU-1", "DE", "A"]))
    def reject_write(*args, **kwargs):
        raise AssertionError("parser must not write any file")
    monkeypatch.setattr(Path, "write_bytes", reject_write)
    monkeypatch.setattr(Path, "write_text", reject_write)
    result = parser.parse_grades(content, "../../outside/grades.xlsx")
    assert result["rows"][0]["sku"] == "SKU-1"

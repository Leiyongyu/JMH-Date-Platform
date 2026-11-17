from pathlib import Path

import pytest

from backend.sql_statements import split_sql_statements


def test_quoted_semicolons_and_comments_stay_intact():
    statements = [
        "CREATE TABLE `semi;colon` (value TEXT COMMENT 'a;b')",
        "-- comment; stays\nSELECT 'it''s;ok', \"a;b\"",
        "/* block; stays */ SELECT 'escaped\\\';value'",
        "# another; comment\nSELECT 1",
    ]
    assert list(split_sql_statements(';'.join(statements) + ';')) == statements


def test_empty_and_last_statement():
    assert list(split_sql_statements(' ; ; SELECT 1;SELECT 2 ')) == ['SELECT 1', 'SELECT 2']


@pytest.mark.parametrize('sql', ["SELECT 'unfinished", '/* unfinished'])
def test_unterminated_sql_is_rejected(sql):
    with pytest.raises(ValueError):
        list(split_sql_statements(sql))


def test_weekly_schema_comment_is_not_split():
    schema = (Path(__file__).parents[1] / 'backend/schema.sql').read_text(encoding='utf-8')
    statements = list(split_sql_statements(schema))
    bins = [s for s in statements if 'CREATE TABLE IF NOT EXISTS ods_lingxing_inventory_bin_detail_weekly' in s.replace('`', '')]
    assert len(bins) == 1
    assert "COMMENT 'weekly-bin-identity-v1: store_id,msku,fnsku; byte-exact length framing'" in bins[0]
    assert 'uk_bin_week' in bins[0]

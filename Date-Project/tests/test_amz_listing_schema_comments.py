"""Fresh schemas and existing-table patches must carry identical Chinese comments."""
import re
from pathlib import Path

from backend.repositories.amz_listing_raw_repository import FIELDS, METADATA
from backend.sql_statements import split_sql_statements


def test_listing_schema_comments_cover_every_column_and_patch_keeps_definitions():
    root = Path(__file__).parents[1]
    schema = (root / 'migrations/20260918_amz_listing_raw.sql').read_text(encoding='utf-8')
    deploy = (root / 'deploy/amz-listing-raw/01_原始表与Python任务.sql').read_text(encoding='utf-8')
    patch = (root / 'deploy/amz-listing-raw/03_补齐字段中文注释.sql').read_text(encoding='utf-8')
    tables = re.findall(r'CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\) ENGINE', schema, re.S)
    assert len(tables) == 2
    for name, body in tables:
        columns = re.findall(r'^  `(\w+)` (.*),$', body, re.M)
        expected = {'id', *FIELDS, *METADATA} if name.endswith('_latest') else {
            'id', 'sync_batch_id', 'row_count', 'shop_count', 'pulled_at', 'published_at'}
        assert {field for field, _ in columns} == expected
        alter = re.search(r'ALTER TABLE `' + name + r'`\n(.*?);', patch, re.S)[1]
        modifications = re.findall(r'^  MODIFY COLUMN `(\w+)` (.*),$', alter, re.M)
        assert modifications == columns  # Types, nullability, auto increment, comments all identical.
        for field, definition in columns:
            assert re.search(r"COMMENT '[^']*[\u4e00-\u9fff][^']*'$", definition), field
            assert f'`{field}` {definition},' in deploy
    statements = list(split_sql_statements(patch))
    executable = [re.sub(r'^--[^\n]*\n', '', s, flags=re.M).strip() for s in statements]
    assert all(re.match(r'^(USE|SET|ALTER TABLE)\b', s) for s in executable)
    assert patch.count('ALGORITHM=INPLACE, LOCK=NONE') == 2
    assert "`total_volume` LONGTEXT NULL COMMENT '近7天销量，非历史累计销量'" in schema

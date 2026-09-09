import json
from pathlib import Path
import pytest


@pytest.fixture
def level_rows():
    return json.loads((Path(__file__).parent / 'fixtures/ebay_level_rules.json').read_text(encoding='utf-8'))


@pytest.fixture
def level_rules(level_rows):
    from backend.services.ebay_level_rule_service import prepare_levels
    return prepare_levels(level_rows)

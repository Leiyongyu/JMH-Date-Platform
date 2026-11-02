from decimal import Decimal

from backend.services.after_sales_export_common import decimal_text
from backend.utils.values import text, text_keep_zero


def test_text_treats_falsy_values_as_empty():
    assert text(None) == "" and text(0) == "" and text("  A1 ") == "A1"


def test_text_keep_zero_keeps_numeric_zero():
    assert text_keep_zero(None) == "" and text_keep_zero(0) == "0" and text_keep_zero(" 3 ") == "3"


def test_decimal_text_strips_trailing_zeros():
    assert decimal_text(Decimal("1.50")) == "1.5"
    assert decimal_text(Decimal("2.000")) == "2"
    assert decimal_text(Decimal("10")) == "10"

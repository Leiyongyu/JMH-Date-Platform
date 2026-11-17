"""eBay库存明细各类Excel导入共用的工作簿读取上限、站点归一与错误值常量。"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from xml.etree.ElementTree import ParseError

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

try:
    from lxml.etree import XMLSyntaxError
except ImportError:
    XMLSyntaxError = ParseError

WORKBOOK_ERRORS = (BadZipFile, InvalidFileException, OSError, KeyError, ParseError, XMLSyntaxError)

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_EXPANDED_BYTES = 80 * 1024 * 1024
MAX_ROWS = 50000
SITE_NAMES = {
    "DE": "德国", "GERMANY": "德国", "德国": "德国",
    "UK": "英国", "GB": "英国", "UNITED KINGDOM": "英国", "英国": "英国",
    "US": "美国", "USA": "美国", "UNITED STATES": "美国", "美国": "美国",
    "FR": "法国", "FRANCE": "法国", "法国": "法国",
}
ERROR_VALUES = {"#N/A", "#NAME?", "#REF!", "#VALUE!", "#DIV/0!", "#NUM!", "#NULL!"}


def normalize_site(value: str) -> str:
    text = str(value or "").strip()
    return SITE_NAMES.get(text.upper(), text)

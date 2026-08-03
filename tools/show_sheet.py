"""Print compact, non-empty rows from a workbook sheet."""

from __future__ import annotations

import json
import sys

import pandas as pd


def normalize(value):
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value).strip()


path, sheet_name = sys.argv[1], sys.argv[2]
frame = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=object)
rows = []
for index, row in frame.iterrows():
    values = [normalize(value) for value in row.tolist()]
    while values and values[-1] is None:
        values.pop()
    if any(value not in (None, "") for value in values):
        rows.append({"row": index + 1, "values": values})
print(json.dumps(rows, ensure_ascii=False, indent=2))

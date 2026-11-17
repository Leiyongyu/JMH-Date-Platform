"""Analyze row counts, types, nulls, and candidate keys for tax-refund detail files."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


sys.stdout.reconfigure(encoding="utf-8")


def analyze(path: Path, kind: str):
    frame = pd.read_excel(path, sheet_name="Sheet1", header=0, dtype=object)
    if kind == "purchase":
        columns = list(frame.columns)
        columns[2] = "序号"
        frame.columns = columns
    frame = frame.dropna(how="all")
    key_columns = ["申报年月", "申报批次", "序号", "关联号"]
    return {
        "kind": kind,
        "rows": len(frame),
        "columns": [str(column) for column in frame.columns],
        "nonempty": {str(column): int(frame[column].notna().sum()) for column in frame.columns},
        "types": {
            str(column): dict(Counter(type(value).__name__ for value in frame[column].dropna()).most_common())
            for column in frame.columns
        },
        "duplicate_full_rows": int(frame.duplicated(keep=False).sum()),
        "duplicate_key_rows": int(frame.duplicated(key_columns, keep=False).sum()),
        "unique_keys": int(frame[key_columns].drop_duplicates().shape[0]),
    }


print(
    json.dumps(
        [
            analyze(Path(sys.argv[1]), "export"),
            analyze(Path(sys.argv[2]), "purchase"),
        ],
        ensure_ascii=False,
        indent=2,
    )
)

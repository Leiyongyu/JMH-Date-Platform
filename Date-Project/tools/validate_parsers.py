"""Validate all customs workbooks with the production parser, without writing MySQL."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from backend.parsers import parse_workbook


root = Path(sys.argv[1]).resolve()
totals: Counter[str] = Counter()
success = 0
skipped = 0
errors = []
for path in sorted(root.rglob("*.xlsx")):
    if path.name.startswith("~$"):
        continue
    try:
        parsed = parse_workbook(path, root)
        success += 1
        for table, records in parsed.items():
            totals[table] += len(records)
    except ValueError as exc:
        if str(exc).startswith("缺少核心Sheet"):
            skipped += 1
        else:
            errors.append({"file": str(path), "error": str(exc)})
    except Exception as exc:
        errors.append({"file": str(path), "error": repr(exc)})

print(
    json.dumps(
        {"success": success, "skipped": skipped, "totals": totals, "errors": errors},
        ensure_ascii=False,
        indent=2,
    )
)

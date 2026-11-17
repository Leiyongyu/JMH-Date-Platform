"""Filters specific to homepage active-listing owner statistics."""

import re

from backend.parsers.performance_common import normalize_principal, normalize_text


_PC_PREFIX = re.compile(r"^[0-9]*PC(?:-|$)", re.IGNORECASE)


def is_pc_sku(value) -> bool:
    """Exclude PC / any numeric-PC first segment, not PC inside a SKU."""
    return bool(_PC_PREFIX.match(normalize_text(value)))


def include_configured_owners(summary: dict, principals) -> None:
    """Keep this month's configured people visible even without active listings.

    Call only after source/rule availability checks. Never fabricate an
    unassigned zero row or change the sum of actual SKU counts.
    """
    existing = {item['principal_name'] for item in summary['items']}
    for principal in principals:
        name = normalize_principal(principal)
        # Cancellation is a rule-table status, not a person to add to the chart.
        if name in {'未分配', '注销'} or name in existing:
            continue
        summary['items'].append({'principal_name': name, 'sku_count': 0, 'unassigned': False})
        existing.add(name)
    summary['items'].sort(key=lambda item: (-item['sku_count'], item['principal_name']))
    summary['owner_count'] = sum(not item['unassigned'] for item in summary['items'])

/** Selection is shared; export accepts only pending rows, deletion accepts both known states. */
export function partitionPurchaseSelection(rows = []) {
  const unique = new Map()
  for (const row of rows) {
    if (row?.id != null && ['0', '1'].includes(String(row.status))) unique.set(row.id, row)
  }
  const selected = [...unique.values()]
  return {
    ids: selected.map(row => row.id),
    pendingIds: selected.filter(row => String(row.status) === '0').map(row => row.id),
    purchasedCount: selected.filter(row => String(row.status) === '1').length
  }
}


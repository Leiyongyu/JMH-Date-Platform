export function childQuery(parent, filters, calculationVersion, pageNum = 1) {
  return {
    ...filters,
    hierarchyLevel: parent.nodeKind === 'site' ? 'product' : 'sku',
    site: parent.site,
    brandCore: parent.nodeKind === 'product' ? parent.brandCore : undefined,
    calculationVersion,
    pageNum,
    pageSize: 50,
    refresh: false
  }
}

export function withMoreRow(parent, children, total, nextPage) {
  if (children.length >= total) return children
  return [...children, {
    nodeId: `${parent.nodeId}:more`, nodeKind: 'more', parent,
    nodeLabel: `加载更多（已显示 ${children.length} / ${total}）`,
    nextPage, hasChildren: false
  }]
}

export function isSkuRow(row) {
  return row.nodeKind === 'sku'
}

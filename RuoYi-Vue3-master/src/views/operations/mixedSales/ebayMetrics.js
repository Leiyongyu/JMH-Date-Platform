export const ebayMetrics = [
  { key: 'chengduInTransitQty', label: '成都在途' },
  { key: 'chengduSellableQty', label: '成都可售' },
  { key: 'overseasInTransitQty', label: '海外在途' },
  { key: 'overseasSellableQty', label: '海外可售' },
  { key: 'totalInventory', label: '库存合计', tip: '成都在途＋成都可售＋海外在途＋海外可售，沿用补货2.0各站点SKU的库存值。' },
  { key: 'sales30d', label: '近30天销量', tip: '复用补货2.0计算版本中的近30天销量，不含计算当天。' }
]

export const ebaySiteMetrics = [
  ...ebayMetrics.map(col => col.key === 'sales30d'
    ? { ...col, key: 'ebaySales30d', label: 'eBay近30天销量' } : col),
  { key: 'amzSales30d', label: 'Amazon近30天销量', tip: '取领星商品刊登接口 /erp/sc/data/mws/listing 的 thirty_volume，按店铺＋完整MSKU匹配后汇总同一SKU、同一站点；使用最近成功同步的未删除刊登，缺失显示--，真实0保留。' }
]

export function ebayDetailQuery(row, applied, version) {
  return { sku: row.sku, site: applied.site || undefined,
    productName: applied.productName || undefined, calculationVersion: version }
}

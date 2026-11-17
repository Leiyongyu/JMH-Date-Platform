import request, { download } from '@/utils/request'

const base = '/operations/ebay/price-analysis'
// 明细要在查询时派生同站点跨店的对比列，比普通列表慢，给到两分钟。
const LONG_TIMEOUT = 120000

/** 店铺维度上半部分：一行一个「店铺 + 站点」的汇总，不分页 */
export function listEbayPriceAnalysisStores(params) {
  return request({ url: `${base}/stores`, method: 'get', params, timeout: LONG_TIMEOUT })
}

/** 个人维度上半部分：一行一个负责人，库存、货值按「站点 + SKU」只算一份后相加，不分页 */
export function listEbayPriceAnalysisOwners(params) {
  return request({ url: `${base}/owners`, method: 'get', params, timeout: LONG_TIMEOUT })
}

/** 明细表，mode=detail 一行一条刊登，mode=summary 一行一个「站点 + SKU」 */
export function listEbayPriceAnalysisDetail(params) {
  return request({ url: `${base}/detail`, method: 'get', params, timeout: LONG_TIMEOUT })
}

/** 某个 SKU 在所有店铺、所有站点的刊登，以及每个站点的库存；SKU 不存在时返回空数组 */
export function getEbayPriceAnalysisSkuListings(sku) {
  return request({ url: `${base}/sku-listings`, method: 'get', params: { sku }, timeout: LONG_TIMEOUT })
}

/** 导出当前筛选下的全部记录；列由角色的 exportColumn 权限决定，不受页面隐藏列影响 */
export function exportEbayPriceAnalysis(params) {
  const timestamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)
  return download(`${base}/export`, params, `eBay价格分析-${timestamp}.xlsx`, {
    timeout: LONG_TIMEOUT
  })
}

import request, { download } from '@/utils/request'

const base = '/operations/ebay/price-analysis'
// 看板一次要把 KPI、四张图的聚合算完，比普通列表慢，给到两分钟。
const LONG_TIMEOUT = 120000

/** 看板上半部分：KPI、店铺对比、散点、缺口 Top10、待处理事项 */
export function getEbayPriceAnalysisOverview(params) {
  return request({ url: `${base}/overview`, method: 'get', params, timeout: LONG_TIMEOUT })
}

/** 明细表，mode=detail 按店铺、mode=summary 按 SKU 汇总 */
export function listEbayPriceAnalysisDetail(params) {
  return request({ url: `${base}/detail`, method: 'get', params, timeout: LONG_TIMEOUT })
}

/** 导出当前筛选下的全部记录；列由角色的 exportColumn 权限决定，不受页面隐藏列影响 */
export function exportEbayPriceAnalysis(params) {
  const timestamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)
  return download(`${base}/export`, params, `eBay价格分析-${timestamp}.xlsx`, {
    timeout: LONG_TIMEOUT
  })
}

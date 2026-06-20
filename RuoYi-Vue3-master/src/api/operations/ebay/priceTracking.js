import request from '@/utils/request'

/** 增强搜索 */
export function searchPriceTracking(data) {
  return request({ url: '/operations/ebay/price-tracking/search', method: 'post', data })
}

/** distinct 候选值 */
export function fetchDistinctValues(field, keyword) {
  return request({ url: '/operations/ebay/price-tracking/distinct-values', method: 'get', params: { field, keyword } })
}

/** 全量刷新 */
const LONG_TIMEOUT = 600000

export function refreshPriceTracking() {
  return request({ url: '/operations/ebay/price-tracking/refresh', method: 'post', timeout: LONG_TIMEOUT })
}

/** 跟卖利润率+底线价计算 */
export function calcTracking(site, sku, trackingPrice) {
  return request({ url: '/operations/ebay/price-tracking/calc-tracking', method: 'post', data: { site, sku, trackingPrice } })
}

/** 保存跟卖价 */
export function saveTrackingPrice(site, sku, trackingPrice) {
  return request({ url: '/operations/ebay/price-tracking/save-tracking-price', method: 'post', data: { site, sku, trackingPrice } })
}

/** 保存OE号 */
export function saveOe(site, sku, oeNumber) {
  return request({ url: '/operations/ebay/price-tracking/oe', method: 'post', data: { site, sku, oeNumber } })
}

/** 保存备注 */
export function saveRemark(site, sku, remark) {
  return request({ url: '/operations/ebay/price-tracking/remark', method: 'post', data: { site, sku, remark } })
}

/** 导出 */
export function exportPriceTracking(params) {
  return request({ url: '/operations/ebay/price-tracking/export', method: 'post', params, responseType: 'blob' })
}

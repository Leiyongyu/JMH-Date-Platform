import request from '@/utils/request'

function platformPath(platform) {
  if (!['amz', 'ebay'].includes(platform)) throw new Error('不支持的平台')
  return `/operations/${platform}/price-tier`
}
// eBay 支持按统计月份与店铺筛选（数据按月存在单价表里）；AMZ 只有当前一份。
export const getListingPriceTier = (platform, params = {}) =>
  request({ url: `${platformPath(platform)}/summary`, method: 'get', params })
export const refreshListingPriceTier = platform => request({ url: `${platformPath(platform)}/refresh`, method: 'post', timeout: 120000 })
// 产品结构只有 eBay 有：数据源是飞书不良交易刊登表，AMZ 没有对应表。
export const getEbayProductStructure = year =>
  request({ url: '/operations/ebay/price-tier/product-structure', method: 'get', params: { year: year || '' } })

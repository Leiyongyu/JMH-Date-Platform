import request from '@/utils/request'

function platformPath(platform) {
  if (!['amz', 'ebay'].includes(platform)) throw new Error('不支持的平台')
  return `/operations/${platform}/price-tier`
}
export const getListingPriceTier = platform => request({ url: `${platformPath(platform)}/summary`, method: 'get' })
export const refreshListingPriceTier = platform => request({ url: `${platformPath(platform)}/refresh`, method: 'post', timeout: 120000 })
// 产品结构只有 eBay 有：数据源是飞书不良交易刊登表，AMZ 没有对应表。
export const getEbayProductStructure = year =>
  request({ url: '/operations/ebay/price-tier/product-structure', method: 'get', params: { year: year || '' } })

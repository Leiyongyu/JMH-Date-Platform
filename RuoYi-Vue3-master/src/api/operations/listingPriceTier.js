import request from '@/utils/request'

function platformPath(platform) {
  if (!['amz', 'ebay'].includes(platform)) throw new Error('不支持的平台')
  return `/operations/${platform}/price-tier`
}
// eBay 支持按统计月份与店铺筛选（在售刊登按月留档）；AMZ 只有当前一份。
export const getListingPriceTier = (platform, params = {}) =>
  request({ url: `${platformPath(platform)}/summary`, method: 'get', params })
export const refreshListingPriceTier = platform => request({ url: `${platformPath(platform)}/refresh`, method: 'post', timeout: 120000 })
// 产品结构只有 eBay 有。shops 是店铺名数组，空数组=整个eBay合计；
// 后端按逗号切分，所以店铺名里不能有逗号（三个源表的店铺名都没有）。
export const getEbayProductStructure = (year, shops = []) =>
  request({
    url: '/operations/ebay/price-tier/product-structure', method: 'get',
    params: { year: year || '', shops: (shops || []).join(',') },
  })

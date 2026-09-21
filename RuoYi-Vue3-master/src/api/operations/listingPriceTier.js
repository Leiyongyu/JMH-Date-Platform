import request from '@/utils/request'

function platformPath(platform) {
  if (!['amz', 'ebay'].includes(platform)) throw new Error('不支持的平台')
  return `/operations/${platform}/price-tier`
}
export const getListingPriceTier = platform => request({ url: `${platformPath(platform)}/summary`, method: 'get' })
export const refreshListingPriceTier = platform => request({ url: `${platformPath(platform)}/refresh`, method: 'post', timeout: 120000 })

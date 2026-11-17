import request from '@/utils/request'

export function getAmzOwnerSkuSummary() {
  return request({ url: '/operations/amz/owner-sku/summary', method: 'get' })
}

export function getEbayOwnerSkuSummary() {
  return request({ url: '/operations/ebay/owner-sku/summary', method: 'get' })
}

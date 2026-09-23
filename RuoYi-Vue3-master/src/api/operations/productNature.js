import request from '@/utils/request'

export function getProductNatureOwners(platform, month, segmentKey, batchId) {
  if (!['amz', 'ebay'].includes(platform)) throw new Error('不支持的平台')
  return request({
    url: `/operations/${platform}/owner-sku/nature/owners`,
    method: 'get',
    params: { month, segment_key: segmentKey, batch_id: batchId }
  })
}

export function getProductNatureHistory(platform, startMonth, endMonth) {
  if (!['amz', 'ebay'].includes(platform)) throw new Error('不支持的平台')
  return request({
    url: `/operations/${platform}/owner-sku/nature/history`,
    method: 'get',
    params: { start_month: startMonth, end_month: endMonth, include_current: true }
  })
}

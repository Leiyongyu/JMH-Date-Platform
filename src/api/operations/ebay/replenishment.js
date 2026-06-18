import request from '@/utils/request'

export function listEbayReplenishment(query) {
  return request({
    url: '/operations/ebay/replenishment/list',
    method: 'get',
    params: query
  })
}

export function exportEbayReplenishment(query) {
  return request({
    url: '/operations/ebay/replenishment/export',
    method: 'post',
    params: query,
    responseType: 'blob'
  })
}

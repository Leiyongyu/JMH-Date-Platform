import request from '@/utils/request'

export function listSyncShop(query) {
  return request({ url: '/operations/sync/shop/list', method: 'get', params: query })
}

// data：{ pullEnabled: 0|1, pullStopReason, pullStopDate: 'yyyy-MM-dd' }
export function updateShopPull(id, data) {
  return request({ url: `/operations/sync/shop/${id}/pull`, method: 'put', data })
}

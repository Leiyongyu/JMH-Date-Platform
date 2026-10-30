import request from '@/utils/request'

const base = '/procurement/pending-purchase'

export function getPurchaseOrderSyncState() {
  return request({ url: `${base}/po-status`, method: 'get' })
}

export function getPurchaseOrderSummaries(ids) {
  return request({ url: `${base}/po-status/summary`, method: 'get', params: { ids: ids.join(',') } })
}

export function getPurchaseOrderDetails(id) {
  return request({ url: `${base}/po-status/${id}`, method: 'get' })
}

export function syncPurchaseOrderStatus() {
  return request({ url: `${base}/po-status/sync`, method: 'post' })
}

export function listPendingPurchase(params) {
  return request({ url: `${base}/list`, method: 'get', params })
}

export function deletePendingPurchase(ids) {
  return request({ url: base, method: 'delete', data: { ids } })
}

export function submitPendingPurchase(data) {
  return request({ url: base, method: 'post', data })
}

export function exportPendingPurchase(ids) {
  return request({
    url: `${base}/export`,
    method: 'post',
    data: { ids },
    responseType: 'blob',
    timeout: 10 * 60 * 1000
  })
}

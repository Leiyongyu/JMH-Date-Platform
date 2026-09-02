import request from '@/utils/request'

const base = '/procurement/pending-purchase'

export function listPendingPurchase(params) {
  return request({ url: `${base}/list`, method: 'get', params })
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

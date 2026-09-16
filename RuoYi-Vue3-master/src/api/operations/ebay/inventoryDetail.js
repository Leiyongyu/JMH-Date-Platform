import request from '@/utils/request'

const base = '/finance/ebay-inventory-detail'

export function listEbayInventoryDetail(params) {
  return request({ url: `${base}/list`, method: 'get', params, timeout: 120000 })
}

export function listEbayInventoryPivot(params) {
  return request({ url: `${base}/pivot`, method: 'get', params, timeout: 120000 })
}

export function exportEbayInventoryPivot(params) {
  return request({
    url: `${base}/pivot/export`, method: 'get', params,
    responseType: 'blob', timeout: 120000
  })
}

export function exportEbayInventoryDetail(data) {
  return request({
    url: `${base}/export`,
    method: 'post',
    data,
    responseType: 'blob',
    headers: { repeatSubmit: false },
    timeout: 120000
  })
}

export function importEbayInventoryGrades(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: `${base}/grades/import`,
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    timeout: 120000
  })
}

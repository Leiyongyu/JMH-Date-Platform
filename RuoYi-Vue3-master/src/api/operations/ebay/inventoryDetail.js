import request from '@/utils/request'

const base = '/finance/ebay-inventory-detail'

export function listEbayInventoryDetail(params) {
  return request({ url: `${base}/list`, method: 'get', params, timeout: 120000 })
}

export function recalculateEbayInventorySnapshot() {
  // No date or filters: the server always rebuilds today's complete snapshot.
  return request({
    url: `${base}/snapshot/recalculate`, method: 'post',
    headers: { repeatSubmit: false }, timeout: 120000
  })
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
  return importEbayInventoryFile('grades', file)
}

export function importEbayInventoryPrices(file) {
  return importEbayInventoryFile('prices', file)
}

function importEbayInventoryFile(kind, file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: `${base}/${kind}/import`,
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    timeout: kind === 'history' ? 300000 : 120000
  })
}

export function importEbayInventoryHistory(file) {
  return importEbayInventoryFile('history', file)
}

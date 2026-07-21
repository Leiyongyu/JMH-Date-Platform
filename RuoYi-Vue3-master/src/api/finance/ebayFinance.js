import request from '@/utils/request'

const base = '/finance/ebay-finance'

export function listEbayFinance(query) {
  return request({ url: `${base}/list`, method: 'get', params: query })
}

export function listEbayFinanceImports(query) {
  return request({ url: `${base}/imports`, method: 'get', params: query })
}

export function importChiefProfit(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: `${base}/import`,
    method: 'post',
    data,
    timeout: 180000,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
  })
}

export function updateEbayFinance(id, data) {
  return request({ url: `${base}/${id}`, method: 'put', data })
}

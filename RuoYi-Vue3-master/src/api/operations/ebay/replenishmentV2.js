import request from '@/utils/request'

const base = '/operations/ebay/replenishment-v2'

export function listEbayReplenishmentV2(params) {
  return request({
    url: `${base}/list`,
    method: 'get',
    params
  })
}

export function getEbayReplenishmentV2Formula() {
  return request({
    url: `${base}/formula`,
    method: 'get'
  })
}

export function saveEbayReplenishmentV2Formula(data) {
  return request({
    url: `${base}/formula`,
    method: 'post',
    data
  })
}

export function getEbayReplenishmentV2ForecastFormula() {
  return request({
    url: `${base}/forecast-formula`,
    method: 'get'
  })
}

export function saveEbayReplenishmentV2ForecastFormula(data) {
  return request({
    url: `${base}/forecast-formula`,
    method: 'post',
    data
  })
}

export function saveEbayReplenishmentV2LeadTime(data) {
  return request({
    url: `${base}/lead-time`,
    method: 'put',
    data
  })
}

export function importEbayReplenishmentV2WarehouseRent(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: `${base}/warehouse-rent/import`,
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    timeout: 10 * 60 * 1000
  })
}

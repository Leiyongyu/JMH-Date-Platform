import request, { download } from '@/utils/request'

const base = '/operations/ebay/replenishment-v2'

export function exportEbayReplenishmentV2(params) {
  const timestamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)
  return download(`${base}/export`, params, `eBay补货2.0-${timestamp}.xlsx`, {
    timeout: 120000
  })
}

export function saveEbayReplenishmentV2SalesType(data) {
  return request({ url: `${base}/sales-type`, method: 'post', data })
}

export function listEbayReplenishmentV2(params) {
  return request({
    url: `${base}/list`,
    method: 'get',
    params
  })
}

export function getEbayReplenishmentV2LevelRules() {
  return request({ url: `${base}/level-rule`, method: 'get' })
}

export function saveEbayReplenishmentV2LevelRules(data) {
  return request({ url: `${base}/level-rule`, method: 'post', data })
}

export function validateEbayReplenishmentV2LevelRules(data) {
  return request({ url: `${base}/level-rule/validate`, method: 'post', data,
    headers: { repeatSubmit: false } })
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

export function getEbayReplenishmentV2ForecastRules() {
  return request({ url: `${base}/forecast-rule`, method: 'get' })
}

export function saveEbayReplenishmentV2ForecastRules(data) {
  return request({ url: `${base}/forecast-rule`, method: 'post', data })
}

export function validateEbayReplenishmentV2ForecastRules(data) {
  return request({ url: `${base}/forecast-rule/validate`, method: 'post', data,
    headers: { repeatSubmit: false } })
}

export function previewEbayReplenishmentV2ForecastRules(data) {
  return request({ url: `${base}/forecast-rule/preview`, method: 'post', data,
    headers: { repeatSubmit: false } })
}

export function getEbayReplenishmentV2ForecastSku(params) {
  return request({ url: `${base}/forecast-rule/sku`, method: 'get', params })
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

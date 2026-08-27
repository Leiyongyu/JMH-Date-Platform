import request from '@/utils/request'

const base = '/operations/ebay/sku-analysis'

export function getEbaySkuAnalysisDates() {
  return request({ url: `${base}/dates`, method: 'get' })
}

export function getEbaySkuAnalysisSummary(params) {
  return request({ url: `${base}/summary`, method: 'get', params })
}

export function importEbaySkuAnalysis(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: `${base}/import`,
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    timeout: 180000
  })
}

export function importEbaySkuAnalysisProfit(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: `${base}/profit-import`,
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    timeout: 180000
  })
}

export function getEbayReturnDetails(params) {
  return request({ url: `${base}/return-details`, method: 'get', params })
}

export function getEbayReturnCategories() {
  return request({ url: `${base}/return-categories`, method: 'get' })
}

export function saveEbayReturnClassification(data) {
  return request({ url: `${base}/return-classification`, method: 'post', data })
}

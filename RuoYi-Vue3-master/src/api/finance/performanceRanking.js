import request from '@/utils/request'

export function listPerformanceRanking(query) {
  return request({
    url: '/finance/performance-ranking/list',
    method: 'get',
    params: query
  })
}

export function refreshPerformanceRanking(statMonth) {
  return request({
    url: '/finance/performance-ranking/refresh',
    method: 'post',
    params: { statMonth }
  })
}

export function importPerformanceOwnerRules(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/finance/performance-ranking/owner-rules/import',
    method: 'post',
    headers: { 'Content-Type': 'multipart/form-data' },
    data,
    timeout: 120000
  })
}

export function getPerformanceOwnerRuleSummary(statMonth) {
  return request({
    url: '/finance/performance-ranking/owner-rules/summary',
    method: 'get',
    params: { statMonth }
  })
}

export function importEbayPerformanceProfit(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/finance/performance-ranking/ebay/profit/import',
    method: 'post',
    headers: { 'Content-Type': 'multipart/form-data' },
    data,
    timeout: 120000
  })
}

export function importEbayPerformanceOwnerRules(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/finance/performance-ranking/ebay/owner-rules/import',
    method: 'post',
    headers: { 'Content-Type': 'multipart/form-data' },
    data,
    timeout: 120000
  })
}

export function getEbayPerformanceOwnerRuleSummary(statMonth) {
  return request({
    url: '/finance/performance-ranking/ebay/owner-rules/summary',
    method: 'get',
    params: { statMonth }
  })
}

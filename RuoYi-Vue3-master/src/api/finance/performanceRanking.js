import request from '@/utils/request'

export function listPerformanceRanking(query) {
  return request({
    url: '/finance/performance-ranking/list',
    method: 'get',
    params: query
  })
}

export function getPerformanceMonths(limit = 12) {
  return request({
    url: '/finance/performance-ranking/months',
    method: 'get',
    params: { limit }
  })
}

export function refreshPerformanceRanking(statMonth, platform = 'combined') {
  return request({
    url: '/finance/performance-ranking/refresh',
    method: 'post',
    params: { statMonth, platform }
  })
}

export function exportAmzPerformanceSource(statMonth, includeRawJson = false) {
  return request({
    url: '/finance/performance-ranking/amazon/source-export',
    method: 'get',
    params: { statMonth, includeRawJson },
    responseType: 'blob',
    timeout: 600000
  })
}

export function importPerformanceOwnerRules(file, rebuild = true, statMonth) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/finance/performance-ranking/owner-rules/import',
    method: 'post',
    params: { rebuild, statMonth },
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

export function importEbayPerformanceProfit(file, rebuild = true) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/finance/performance-ranking/ebay/profit/import',
    method: 'post',
    params: { rebuild },
    headers: { 'Content-Type': 'multipart/form-data' },
    data,
    timeout: 120000
  })
}

export function importEbayPerformanceOwnerRules(file, rebuild = true, statMonth) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/finance/performance-ranking/ebay/owner-rules/import',
    method: 'post',
    params: { rebuild, statMonth },
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

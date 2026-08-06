import request from '@/utils/request'

export function listSlowMovingClearance(query) {
  return request({
    url: '/finance/slow-moving-clearance/list',
    method: 'get',
    params: query
  })
}

export function getSlowMovingClearanceSummary(pullMonth) {
  return request({
    url: '/finance/slow-moving-clearance/summary',
    method: 'get',
    params: { pullMonth }
  })
}

export function listSlowMovingClearanceMonths(limit = 24) {
  return request({
    url: '/finance/slow-moving-clearance/months',
    method: 'get',
    params: { limit }
  })
}

export function importInventoryAgeCost(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/finance/slow-moving-clearance/inventory-age-cost/import',
    method: 'post',
    headers: { 'Content-Type': 'multipart/form-data' },
    data,
    timeout: 120000
  })
}

export function exportInventoryAgeDetails(pullMonth) {
  return request({
    url: '/finance/slow-moving-clearance/inventory-age-cost/export',
    method: 'get',
    params: { pullMonth },
    responseType: 'blob',
    timeout: 600000
  })
}

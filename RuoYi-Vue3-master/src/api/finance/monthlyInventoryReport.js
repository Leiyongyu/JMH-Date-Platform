import request from '@/utils/request'

export function listMonthlyInventoryMonths(limit = 24) {
  return request({
    url: '/finance/monthly-inventory-report/months',
    method: 'get',
    params: { limit }
  })
}

export function getMonthlyInventorySummary(statMonth) {
  return request({
    url: '/finance/monthly-inventory-report/summary',
    method: 'get',
    params: { statMonth }
  })
}

export function listMonthlyInventoryDetails(query) {
  return request({
    url: '/finance/monthly-inventory-report/list',
    method: 'get',
    params: query
  })
}

export function rebuildMonthlyInventoryReport(statMonth) {
  return request({
    url: '/finance/monthly-inventory-report/rebuild',
    method: 'post',
    params: { statMonth },
    timeout: 600000
  })
}

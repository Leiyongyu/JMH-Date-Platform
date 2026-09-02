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

export function getMonthlyInventoryCostTrend(year, month) {
  return request({
    url: '/finance/monthly-inventory-report/cost-trend',
    method: 'get',
    params: { year, month }
  })
}

export function getMonthlyInventoryDimensionSummary(statMonth, dimensionType) {
  return request({
    url: '/finance/monthly-inventory-report/dimension-summary',
    method: 'get',
    params: { statMonth, dimensionType }
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

export function syncMonthlyInventoryOrderProfit(statMonth) {
  return request({
    url: '/finance/monthly-inventory-report/order-profit-sync',
    method: 'post',
    params: statMonth ? { statMonth } : {}
  })
}

export function importMonthlyInventoryPurchaseOrder(statMonth, file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/finance/monthly-inventory-report/purchase-order-import',
    method: 'post',
    params: { statMonth },
    data,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600000
  })
}

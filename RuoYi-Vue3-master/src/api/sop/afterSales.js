import request from '@/utils/request'

export function listAfterSales(query) {
  return request({
    url: '/sop/after-sales/list',
    method: 'get',
    params: query,
    timeout: 600000
  })
}

export function getAfterSalesCategories() {
  return request({
    url: '/sop/after-sales/categories',
    method: 'get'
  })
}

export function listAfterSalesPeriods(limit = 24) {
  return request({
    url: '/sop/after-sales/periods',
    method: 'get',
    params: { limit }
  })
}

export function exportAfterSales(startDate, endDate) {
  return request({
    url: '/sop/after-sales/export',
    method: 'get',
    params: { startDate, endDate },
    responseType: 'blob',
    timeout: 600000
  })
}

export function exportAfterSalesData(query, selectedSkus = []) {
  return request({
    url: '/sop/after-sales/export-data',
    method: 'get',
    params: {
      startDate: query.startDate,
      endDate: query.endDate,
      bigCategory: query.bigCategory || undefined,
      smallCategory: query.smallCategory || undefined,
      sku: query.sku || undefined,
      skus: selectedSkus.length ? selectedSkus.join(',') : undefined
    },
    responseType: 'blob',
    timeout: 600000
  })
}

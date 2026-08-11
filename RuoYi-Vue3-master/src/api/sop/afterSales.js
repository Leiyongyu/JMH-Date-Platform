import request from '@/utils/request'

export function listAfterSales(query) {
  return request({
    url: '/sop/after-sales/list',
    method: 'get',
    params: query,
    timeout: 600000
  })
}

export function getAfterSalesCategories(platform = 'amz') {
  return request({
    url: '/sop/after-sales/categories',
    method: 'get',
    params: { platform }
  })
}

export function listAfterSalesPeriods(platform = 'amz', limit = 24) {
  return request({
    url: '/sop/after-sales/periods',
    method: 'get',
    params: { platform, limit }
  })
}

export function exportAfterSales(platform, startDate, endDate) {
  return request({
    url: '/sop/after-sales/export',
    method: 'get',
    params: { platform, startDate, endDate },
    responseType: 'blob',
    timeout: 600000
  })
}

export function exportAfterSalesData(platform, query, selectedSkus = []) {
  return request({
    url: '/sop/after-sales/export-data',
    method: 'get',
    params: {
      platform,
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

export function importEbayAfterSalesFile(type, file) {
  const paths = {
    sales: '/sop/after-sales/ebay-sales-import',
    history: '/sop/after-sales/ebay-history-import',
    afterSales: '/sop/after-sales/ebay-after-sales-import'
  }
  const formData = new FormData()
  formData.append('file', file)
  return request({
    url: paths[type],
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data',
      repeatSubmit: false,
      'Idempotency-Key': createUploadIdempotencyKey(type, file)
    },
    timeout: 600000
  })
}

function createUploadIdempotencyKey(type, file) {
  const source = `${file.name}|${file.size}|${file.lastModified}`
  let hash = 2166136261
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return `ebay-sop-${type}-${(hash >>> 0).toString(16)}-${file.size}-${file.lastModified}`
}

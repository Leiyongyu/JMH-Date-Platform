import request from '@/utils/request'

const baseUrl = '/operation/ebay-price'

export function getEbayHealth() {
  return request({
    url: `${baseUrl}/health`,
    method: 'get'
  })
}

export function importSkuOeMapping(file, requestId) {
  const formData = new FormData()
  formData.append('file', file)
  return request({
    url: `${baseUrl}/sku-oe-imports`,
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data',
      'X-Request-ID': requestId,
      repeatSubmit: false
    },
    timeout: 120000
  })
}

export function searchEbayPrices(data, requestId) {
  return request({
    url: `${baseUrl}/searches`,
    method: 'post',
    data,
    headers: {
      'X-Request-ID': requestId,
      repeatSubmit: false
    },
    timeout: 600000
  })
}

export function exportEbayPrices(items, requestId) {
  return request({
    url: `${baseUrl}/exports`,
    method: 'post',
    data: { items },
    headers: {
      'X-Request-ID': requestId,
      repeatSubmit: false
    },
    responseType: 'blob',
    timeout: 600000
  })
}

export function createEbayAuditTask(file, site, requestId) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('site', site)
  return request({
    url: `${baseUrl}/audit-tasks`,
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data',
      'X-Request-ID': requestId,
      repeatSubmit: false
    },
    timeout: 120000
  })
}

export function createEbayManualAuditTask(data, requestId) {
  return request({
    url: `${baseUrl}/audit-tasks/manual`,
    method: 'post',
    data,
    headers: {
      'X-Request-ID': requestId,
      repeatSubmit: false
    },
    timeout: 120000
  })
}

export function getLatestEbayAuditTask() {
  return request({
    url: `${baseUrl}/audit-tasks/latest`,
    method: 'get'
  })
}

export function getEbayAuditTasks() {
  return request({
    url: `${baseUrl}/audit-tasks`,
    method: 'get'
  })
}

export function getEbayAuditTask(taskId) {
  return request({
    url: `${baseUrl}/audit-tasks/${taskId}`,
    method: 'get'
  })
}

export function deleteEbayAuditTask(taskId) {
  return request({
    url: `${baseUrl}/audit-tasks/${taskId}`,
    method: 'delete'
  })
}

export function getEbayAuditOe(taskId, oeId) {
  return request({
    url: `${baseUrl}/audit-tasks/${taskId}/oes/${oeId}`,
    method: 'get'
  })
}

export function reviewEbayAuditOe(taskId, oeId, data) {
  return request({
    url: `${baseUrl}/audit-tasks/${taskId}/oes/${oeId}/review`,
    method: 'put',
    data
  })
}

export function retryEbayAuditOe(taskId, oeId) {
  return request({
    url: `${baseUrl}/audit-tasks/${taskId}/oes/${oeId}/retry`,
    method: 'post'
  })
}

export function exportEbayAuditTask(taskId, requestId) {
  return request({
    url: `${baseUrl}/audit-tasks/${taskId}/exports`,
    method: 'post',
    headers: {
      'X-Request-ID': requestId,
      repeatSubmit: false
    },
    responseType: 'blob',
    timeout: 600000
  })
}

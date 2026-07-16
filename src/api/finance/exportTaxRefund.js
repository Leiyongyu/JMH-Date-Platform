import request from '@/utils/request'

const base = '/finance/export-tax-refund'

export function importCustomsMaterial(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: `${base}/tasks/customs-material`,
    method: 'post',
    data,
    timeout: 60000,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
  })
}

export function importCustomsDeclaration(file, params = {}) {
  const data = new FormData()
  data.append('file', file)
  Object.keys(params).forEach(key => {
    if (params[key] !== undefined && params[key] !== null && params[key] !== '') {
      data.append(key, params[key])
    }
  })
  return request({
    url: `${base}/tasks/customs-declaration`,
    method: 'post',
    data,
    timeout: 60000,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
  })
}

export function importPurchaseInvoice(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: `${base}/tasks/purchase-invoice`,
    method: 'post',
    data,
    timeout: 60000,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
  })
}

export function importForex(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: `${base}/tasks/forex`,
    method: 'post',
    data,
    timeout: 60000,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
  })
}

export function generateRefundPackage(data) {
  return request({
    url: `${base}/tasks/refund-package`,
    method: 'post',
    data,
    timeout: 60000
  })
}

export function getTask(taskId) {
  return request({
    url: `${base}/tasks/${taskId}`,
    method: 'get'
  })
}

export function listTasks(params) {
  return request({
    url: `${base}/tasks`,
    method: 'get',
    params
  })
}

export function listCustomsMaterialItems(params) {
  return request({
    url: `${base}/customs-material-items`,
    method: 'get',
    params
  })
}

export function listExportDetails(params) {
  return request({
    url: `${base}/export-details`,
    method: 'get',
    params
  })
}

export function listPurchaseInventory(params) {
  return request({
    url: `${base}/purchase-inventory`,
    method: 'get',
    params
  })
}

export function listForexReceivables(params) {
  return request({
    url: `${base}/forex-receivables`,
    method: 'get',
    params
  })
}

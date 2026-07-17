import request from '@/utils/request'

const base = '/finance/export-tax-refund'

function appendFiles(data, files) {
  const list = Array.isArray(files) ? files : [files]
  list.filter(Boolean).forEach(file => data.append('file', file))
}

export function importCustomsMaterial(files) {
  const data = new FormData()
  appendFiles(data, files)
  return request({
    url: `${base}/tasks/customs-material`,
    method: 'post',
    data,
    timeout: 60000,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
  })
}

export function importCustomsDeclaration(files, params = {}) {
  const data = new FormData()
  appendFiles(data, files)
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

export function importPurchaseInvoice(files) {
  const data = new FormData()
  appendFiles(data, files)
  return request({
    url: `${base}/tasks/purchase-invoice`,
    method: 'post',
    data,
    timeout: 60000,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
  })
}

export function importForex(files) {
  const data = new FormData()
  appendFiles(data, files)
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

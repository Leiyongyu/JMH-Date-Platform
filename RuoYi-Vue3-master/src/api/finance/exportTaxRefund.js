import request from '@/utils/request'

const base = '/finance/export-tax-refund'

function upload(url, files, multiple = false) {
  const data = new FormData()
  const list = Array.isArray(files) ? files : [files]
  list.filter(Boolean).forEach(file => data.append(multiple ? 'files' : 'file', file))
  return request({
    url: `${base}${url}`,
    method: 'post',
    data,
    timeout: 600000,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
  })
}

export function importCustomsFolder(files) {
  return upload('/imports/customs-folder', files, true)
}

export function importPurchaseInvoiceSummary(file) {
  return upload('/imports/purchase-invoice-summary', file)
}

export function importForeignExchangeReceipts(file) {
  return upload('/imports/foreign-exchange-receipts', file)
}

export function getImportJob(jobId) {
  return request({
    url: `${base}/import-jobs/${jobId}`,
    method: 'get'
  })
}

export function listCustomsDeclarations() {
  return request({
    url: `${base}/customs-declarations`,
    method: 'get'
  })
}

export function createDeclarationBatch(data) {
  return request({
    url: `${base}/declaration-batches`,
    method: 'post',
    data,
    timeout: 600000
  })
}

export function generateFinalPackage(data) {
  return request({
    url: `${base}/packages`,
    method: 'post',
    data,
    timeout: 600000
  })
}

export function downloadLatestPackage() {
  return request({
    url: `${base}/packages/latest/file`,
    method: 'get',
    responseType: 'blob',
    timeout: 600000
  })
}

export function listPurchaseInventory(params) {
  return request({
    url: `${base}/inventory`,
    method: 'get',
    params
  })
}

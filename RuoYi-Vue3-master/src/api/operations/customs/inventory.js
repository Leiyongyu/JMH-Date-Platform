import request from '@/utils/request'

const FILE_TIMEOUT = 10 * 60 * 1000

export function listCustomsInventory(params) {
  return request({
    url: '/operations/customs/inventory/list',
    method: 'get',
    params
  })
}

export function importCustomsInventory(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/operations/customs/inventory/import',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    timeout: FILE_TIMEOUT
  })
}

export function searchCustomsInventoryProducts(params) {
  return request({
    url: '/operations/customs/inventory/product-options',
    method: 'get',
    params
  })
}

export function getCustomsInventoryEditableFields() {
  return request({
    url: '/operations/customs/inventory/editable-fields',
    method: 'get'
  })
}

export function addCustomsInventory(data) {
  return request({
    url: '/operations/customs/inventory',
    method: 'post',
    data
  })
}

export function updateCustomsInventory(data) {
  return request({
    url: '/operations/customs/inventory',
    method: 'put',
    data
  })
}

export function exportCustomsInventory(ids = []) {
  return request({
    url: '/operations/customs/inventory/export',
    method: 'post',
    data: ids,
    responseType: 'blob',
    timeout: FILE_TIMEOUT
  })
}

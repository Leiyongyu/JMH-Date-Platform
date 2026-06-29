import request from '@/utils/request'

const FILE_TIMEOUT = 10 * 60 * 1000

export function searchCustomsProducts(keyword) {
  return request({
    url: '/operations/customs/declaration/products/search',
    method: 'get',
    params: { keyword }
  })
}

export function searchStockOrders(params) {
  return request({
    url: '/operations/customs/declaration/stock-orders/search',
    method: 'get',
    params
  })
}

export function loadStockOrderProducts(data) {
  return request({
    url: '/operations/customs/declaration/stock-orders/products',
    method: 'post',
    data
  })
}

export function searchFbaShipments(params) {
  return request({
    url: '/operations/customs/declaration/fba-shipments/search',
    method: 'get',
    params
  })
}

export function loadFbaShipmentProducts(data) {
  return request({
    url: '/operations/customs/declaration/fba-shipments/products',
    method: 'post',
    data
  })
}

export function importCustomsSkus(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/operations/customs/declaration/import-skus',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    timeout: FILE_TIMEOUT
  })
}

export function importCustomsHistory(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/operations/customs/declaration/import-history',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    timeout: FILE_TIMEOUT
  })
}

export function importFbaShipmentBox(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/operations/customs/declaration/import-fba-shipment-box',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    timeout: FILE_TIMEOUT
  })
}

export function saveCustomsProducts(data) {
  return request({
    url: '/operations/customs/declaration/products',
    method: 'put',
    data
  })
}

export function exportCustomsDeclaration(data) {
  return request({
    url: '/operations/customs/declaration/export',
    method: 'post',
    data,
    responseType: 'blob',
    timeout: FILE_TIMEOUT
  })
}

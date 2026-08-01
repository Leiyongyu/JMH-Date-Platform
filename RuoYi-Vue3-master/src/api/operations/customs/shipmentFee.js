import request from '@/utils/request'

const IMPORT_TIMEOUT = 30 * 60 * 1000

export function importShipmentFee(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/operations/customs/shipment-fee/import',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    timeout: IMPORT_TIMEOUT
  })
}

export function importPackingInfo(file) {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: '/operations/customs/shipment-fee/packing/import',
    method: 'post',
    data,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false },
    timeout: IMPORT_TIMEOUT
  })
}

export function listShipmentFeeBatches(query) {
  return request({
    url: '/operations/customs/shipment-fee/batches',
    method: 'get',
    params: query
  })
}

export function listShipmentFeeLogs(query) {
  return request({
    url: '/operations/customs/shipment-fee/logs',
    method: 'get',
    params: query
  })
}

export function listPackingSubmissions(query) {
  return request({
    url: '/operations/customs/shipment-fee/packing/submissions',
    method: 'get',
    params: query
  })
}

export function submitPackingInfo(inboundPlanId) {
  return request({
    url: '/operations/customs/shipment-fee/packing/submissions/submit',
    method: 'post',
    data: { inboundPlanId },
    timeout: 60 * 1000
  })
}

export function refreshPackingSubmission(id) {
  return request({
    url: `/operations/customs/shipment-fee/packing/submissions/${id}/refresh`,
    method: 'post',
    timeout: 60 * 1000
  })
}

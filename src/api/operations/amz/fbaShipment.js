import request from '@/utils/request'

export function searchFbaShipment(data) {
  return request({ url: '/operations/amz/fba-shipment/search', method: 'post', data })
}

export function saveFbaRemark(data) {
  return request({ url: '/operations/amz/fba-shipment/mark/remark', method: 'post', data })
}

export function confirmFbaShipment(msku, shipmentId) {
  return request({ url: '/operations/amz/fba-shipment/mark/confirm', method: 'post', data: { msku, shipmentId } })
}

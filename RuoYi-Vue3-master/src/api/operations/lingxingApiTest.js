import request from '@/utils/request'

export function queryLingxingApi(data) {
  return request({
    url: '/operations/lingxing/api-test/query',
    method: 'post',
    data,
    timeout: 5 * 60 * 1000
  })
}

export function syncStaInboundPlan(shipmentId) {
  return request({
    url: '/operations/lingxing/sta-inbound-plan/sync',
    method: 'post',
    params: { shipmentId },
    timeout: 5 * 60 * 1000
  })
}

export function syncShipmentOrderMapping(shipmentId) {
  return request({
    url: '/operations/lingxing/shipment-order-mapping/sync',
    method: 'post',
    params: shipmentId ? { shipmentId } : {}
  })
}

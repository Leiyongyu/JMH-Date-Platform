import request from '@/utils/request'

export function searchFbaShipment(data) {
  return request({ url: '/operations/amz/fba-shipment/search', method: 'post', data })
}

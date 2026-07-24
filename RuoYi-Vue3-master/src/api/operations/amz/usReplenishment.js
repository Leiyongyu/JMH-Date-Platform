import request from '@/utils/request'

const LONG_TIMEOUT = 600000
const BASE_URL = '/operations/amz/replenishment/us'

export function searchUsReplenishment(data) {
  return request({ url: `${BASE_URL}/search`, method: 'post', data })
}

export function refreshUsReplenishment() {
  return request({ url: `${BASE_URL}/refresh`, method: 'post', timeout: LONG_TIMEOUT })
}

import request from '@/utils/request'

const LONG_TIMEOUT = 600000 // 快照刷新可能较慢

export function listAmzReplenishment(query) {
  return request({ url: '/operations/amz/replenishment/list', method: 'get', params: query })
}

export function refreshAmzReplenishment() {
  return request({ url: '/operations/amz/replenishment/refresh', method: 'post', timeout: LONG_TIMEOUT })
}

export function exportAmzReplenishment(query) {
  return request({ url: '/operations/amz/replenishment/export', method: 'post', params: query, responseType: 'blob' })
}

import request from '@/utils/request'

export function listAmzReplenishment(query) {
  return request({
    url: '/operations/amz/replenishment/list',
    method: 'get',
    params: query
  })
}

export function refreshAmzReplenishment() {
  return request({ url: '/operations/amz/replenishment/refresh', method: 'post' })
}

export function exportAmzReplenishment(query) {
  return request({
    url: '/operations/amz/replenishment/export',
    method: 'post',
    params: query,
    responseType: 'blob'
  })
}

import request from '@/utils/request'

export function listPerformanceRanking(query) {
  return request({
    url: '/finance/performance-ranking/list',
    method: 'get',
    params: query
  })
}

export function refreshPerformanceRanking(statMonth) {
  return request({
    url: '/finance/performance-ranking/refresh',
    method: 'post',
    params: { statMonth }
  })
}

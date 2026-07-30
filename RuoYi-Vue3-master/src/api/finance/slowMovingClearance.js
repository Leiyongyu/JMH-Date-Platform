import request from '@/utils/request'

export function listSlowMovingClearance(query) {
  return request({
    url: '/finance/slow-moving-clearance/list',
    method: 'get',
    params: query
  })
}

export function getSlowMovingClearanceSummary(pullMonth) {
  return request({
    url: '/finance/slow-moving-clearance/summary',
    method: 'get',
    params: { pullMonth }
  })
}

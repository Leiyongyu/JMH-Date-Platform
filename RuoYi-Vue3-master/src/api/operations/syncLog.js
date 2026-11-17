import request from '@/utils/request'

export function listSyncLog(query) {
  return request({ url: '/operations/sync/log/list', method: 'get', params: query })
}

export function getSyncLogDetail(id) {
  return request({ url: '/operations/sync/log/' + id, method: 'get' })
}

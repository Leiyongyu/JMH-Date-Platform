import request from '@/utils/request'

export function getUserColumnConfig(pageKey) {
  return request({
    url: '/system/user-column-config',
    method: 'get',
    params: { pageKey }
  })
}

export function saveUserColumnConfig(pageKey, configJson) {
  return request({
    url: '/system/user-column-config',
    method: 'post',
    params: { pageKey },
    data: { pageKey, configJson }
  })
}

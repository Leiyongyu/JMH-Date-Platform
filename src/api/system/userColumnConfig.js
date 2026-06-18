import request from '@/utils/request'

export function getColumnConfig(pageKey) {
  return request({ url: '/system/user-column-config', method: 'get', params: { pageKey } })
}

export function saveColumnConfig(pageKey, configJson) {
  return request({ url: '/system/user-column-config', method: 'post', params: { pageKey }, data: configJson })
}

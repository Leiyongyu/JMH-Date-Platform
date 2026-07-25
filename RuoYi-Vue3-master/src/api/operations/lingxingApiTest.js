import request from '@/utils/request'

export function queryLingxingApi(data) {
  return request({
    url: '/operations/lingxing/api-test/query',
    method: 'post',
    data,
    timeout: 5 * 60 * 1000
  })
}

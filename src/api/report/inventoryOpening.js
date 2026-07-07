import request from '@/utils/request'

/** 月初库存货值检查列表 */
export function listInventoryOpening(query) {
  return request({
    url: '/report/inventory-opening/list',
    method: 'get',
    params: query
  })
}

/** 导出月初库存货值检查 */
export function exportInventoryOpening(query) {
  return request({
    url: '/report/inventory-opening/export',
    method: 'post',
    params: query,
    responseType: 'blob'
  })
}

import request from '@/utils/request'

export function listFormulaConfig() {
  return request({ url: '/operations/amz/formula-config/list', method: 'get' })
}

export function getFormulaConfig(id) {
  return request({ url: '/operations/amz/formula-config/' + id, method: 'get' })
}

export function addFormulaConfig(data) {
  return request({ url: '/operations/amz/formula-config/add', method: 'post', data })
}

export function updateFormulaConfig(data) {
  return request({ url: '/operations/amz/formula-config/update', method: 'put', data })
}

export function listWarehouses() {
  return request({ url: '/operations/amz/formula-config/warehouses', method: 'get' })
}

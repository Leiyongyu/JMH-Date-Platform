import request from '@/utils/request'

export function listFormulaConfig() {
  return request({ url: '/operations/amz/formula-config/list', method: 'get' })
}

export function getFormulaConfig(id) {
  return request({ url: '/operations/amz/formula-config/' + id, method: 'get' })
}

export function addFormulaConfig(data) {
  return request({ url: '/operations/amz/formula-config', method: 'post', data })
}

export function updateFormulaConfig(data) {
  return request({ url: '/operations/amz/formula-config', method: 'put', data })
}

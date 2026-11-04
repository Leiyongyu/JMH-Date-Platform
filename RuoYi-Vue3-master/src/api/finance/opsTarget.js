import request from '@/utils/request'

const base = '/finance/ops-target'
export const getOpsTargetReport = year => request({ url: `${base}/report`, method: 'get', params: { year } })
// 部门名含 &（如 US3&US5），按路径段编码
export const updateOpsTarget = (year, deptCode, values) =>
  request({ url: `${base}/rows/${year}/${encodeURIComponent(deptCode)}`, method: 'put', data: { values } })

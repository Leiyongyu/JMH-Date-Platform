import request from '@/utils/request'

const base = '/finance/amz-profit-report'
export const listAmzProfitReportMonths = () => request({ url: `${base}/months`, method: 'get' })
export const getAmzProfitReport = (statMonth, dimension) =>
  request({ url: `${base}/report`, method: 'get', params: { statMonth, dimension } })
export const exportAmzProfitReport = (startMonth, endMonth, dimensions) =>
  request({
    url: `${base}/export`,
    method: 'get',
    params: { startMonth, endMonth, dimensions },
    responseType: 'blob',
    timeout: 300000,
    skipErrorMessage: true
  })

import request from '@/utils/request'

const base = '/finance/amz-profit-report'
export const listAmzProfitReportMonths = () => request({ url: `${base}/months`, method: 'get' })
// currency: CNY（按时间段最大月份的领星 USD「我的汇率」换算）或 USD
export const getAmzProfitReport = (startMonth, endMonth, dimension, currency = 'CNY') =>
  request({ url: `${base}/report`, method: 'get', params: { startMonth, endMonth, dimension, currency } })
export const exportAmzProfitReport = (startMonth, endMonth, dimensions, currency = 'CNY') =>
  request({
    url: `${base}/export`,
    method: 'get',
    params: { startMonth, endMonth, dimensions, currency },
    responseType: 'blob',
    timeout: 300000,
    skipErrorMessage: true
  })

import request from '@/utils/request'

const base = '/finance/amz-monthly-profit'

// 已拉取领星利润报表的月份（新到旧），带拉取时间
export const listAmzMonthlyProfitMonths = () => request({ url: `${base}/months`, method: 'get' })

// 店铺利润、小组利润两张表（人民币，结算口径）
export const getAmzMonthlyProfit = statMonth =>
  request({ url: `${base}/report`, method: 'get', params: { statMonth } })

export const listAmzMonthlyProfitAdjustments = statMonth =>
  request({ url: `${base}/adjustments`, method: 'get', params: { statMonth } })

export const addAmzMonthlyProfitAdjustment = data =>
  request({ url: `${base}/adjustments`, method: 'post', data })

export const updateAmzMonthlyProfitAdjustment = (id, data) =>
  request({ url: `${base}/adjustments/${id}`, method: 'put', data })

export const deleteAmzMonthlyProfitAdjustment = id =>
  request({ url: `${base}/adjustments/${id}`, method: 'delete' })

export const exportAmzMonthlyProfit = statMonth =>
  request({
    url: `${base}/export`,
    method: 'get',
    params: { statMonth },
    responseType: 'blob',
    timeout: 300000,
    skipErrorMessage: true
  })

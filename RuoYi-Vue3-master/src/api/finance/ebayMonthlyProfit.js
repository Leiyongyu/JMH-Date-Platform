import request from '@/utils/request'

const base = '/finance/ebay-monthly-profit'

// 已拉取 eBay 交易流水的月份（新到旧），带拉取时间、店铺数、谷仓账单行数
export const listEbayMonthlyProfitMonths = () => request({ url: `${base}/months`, method: 'get' })

// 站点汇总、个人利润、店铺利润三张表（人民币）
export const getEbayMonthlyProfit = statMonth =>
  request({ url: `${base}/report`, method: 'get', params: { statMonth }, timeout: 120000 })

// 中行折算价月均值
export const getEbayMonthlyProfitRates = statMonth =>
  request({ url: `${base}/rates`, method: 'get', params: { statMonth } })

export const saveEbayMonthlyProfitRates = data =>
  request({ url: `${base}/rates`, method: 'put', data })

export const listEbayMonthlyProfitAdjustments = statMonth =>
  request({ url: `${base}/adjustments`, method: 'get', params: { statMonth } })

export const addEbayMonthlyProfitAdjustment = data =>
  request({ url: `${base}/adjustments`, method: 'post', data })

export const updateEbayMonthlyProfitAdjustment = (id, data) =>
  request({ url: `${base}/adjustments/${id}`, method: 'put', data })

export const deleteEbayMonthlyProfitAdjustment = id =>
  request({ url: `${base}/adjustments/${id}`, method: 'delete' })

export const exportEbayMonthlyProfit = statMonth =>
  request({
    url: `${base}/export`,
    method: 'get',
    params: { statMonth },
    responseType: 'blob',
    timeout: 300000,
    skipErrorMessage: true
  })

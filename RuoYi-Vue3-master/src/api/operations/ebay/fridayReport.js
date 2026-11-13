import request from '@/utils/request'

const base = '/operations/ebay/friday-report'

// 生成记录、指标汇总、店铺列与筛选项；不传日期取最新一期
export const getFridayReportOverview = reportDate =>
  request({ url: `${base}/overview`, method: 'get', params: { reportDate } })

// 有货无货：每条在线 listing 一行
export const listFridayReportListings = params =>
  request({ url: `${base}/listings`, method: 'get', params })

// 海外仓库存：谷仓良品可售 > 0 的每一行，带各店铺链接
export const listFridayReportStocks = params =>
  request({ url: `${base}/stocks`, method: 'get', params })

// 用系统当前的 eBay 刊登与谷仓快照立即重新生成今天这一期
export const generateFridayReport = () =>
  request({ url: `${base}/generate`, method: 'post', timeout: 300000 })

export const saveFridayReportStore = data =>
  request({ url: `${base}/stores`, method: 'put', data })

export const deleteFridayReportStore = storeKey =>
  request({ url: `${base}/stores/${encodeURIComponent(storeKey)}`, method: 'delete' })

export const exportFridayReport = reportDate =>
  request({
    url: `${base}/export`,
    method: 'get',
    params: { reportDate },
    responseType: 'blob',
    timeout: 300000
  })

// 订单售出统计：最新一次上传的透视（按负责人）
export const getFridayOrderSales = () =>
  request({ url: `${base}/order-sales`, method: 'get' })

// 上传数字酋长「Order-交易级别」导出，整份替换上一份
export const importFridayOrderSales = file => {
  const data = new FormData()
  data.append('file', file)
  // request.js 默认 Content-Type 是 application/json，上传必须显式改成 multipart，否则 Java 报「not a multipart request」。
  return request({
    url: `${base}/order-sales/import`,
    method: 'post',
    data,
    timeout: 300000,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
  })
}

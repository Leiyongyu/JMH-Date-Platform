import request from '@/utils/request'

const base = '/finance/project-profit'

// 有数据的月份（领星利润报表 / eBay 已上传或录入过手工项），新到旧
export const listProjectProfitMonths = () => request({ url: `${base}/months`, method: 'get' })

// 小组项目利润表 + 店铺维度利润表（人民币）
export const getProjectProfit = statMonth =>
  request({ url: `${base}/report`, method: 'get', params: { statMonth } })

// 手工项批量保存：items = [{ groupCode, itemCode, amount }]，amount 为空表示清空
export const saveProjectProfitItems = data =>
  request({ url: `${base}/items`, method: 'put', data })

// 上传财务 eBay 利润明细表（约 40MB，读取需要几十秒）
export const importProjectProfitEbay = (statMonth, file) => {
  const data = new FormData()
  data.append('file', file)
  // request.js 默认 Content-Type 是 application/json，上传必须显式改成 multipart，否则 Java 报「not a multipart request」。
  return request({
    url: `${base}/ebay/import`,
    method: 'post',
    params: { statMonth },
    data,
    timeout: 300000,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
  })
}

// 上传领星「利润报表-MSKU」手动导出（按月、币种选人民币，约 10MB），整月替换 AMZ 各列数据
export const importProjectProfitAmz = (statMonth, file) => {
  const data = new FormData()
  data.append('file', file)
  return request({
    url: `${base}/amz/import`,
    method: 'post',
    params: { statMonth },
    data,
    timeout: 300000,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }
  })
}

export const exportProjectProfit = statMonth =>
  request({
    url: `${base}/export`,
    method: 'get',
    params: { statMonth },
    responseType: 'blob',
    timeout: 300000,
    skipErrorMessage: true
  })

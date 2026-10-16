import request from '@/utils/request'

const base = '/finance/sales-dashboard'
export const getSalesOptions = () => request({ url: `${base}/options`, method: 'get' })
export const getSalesReport = params => request({ url: `${base}/report`, method: 'get', params })
export const getSalesAnalysis = params => request({ url: `${base}/analysis`, method: 'get', params })

function upload(path, file, params = {}) {
  const data = new FormData()
  data.append('file', file)
  return request({ url: `${base}/${path}`, method: 'post', data, params,
    headers: { 'Content-Type': 'multipart/form-data', repeatSubmit: false }, timeout: 120000 })
}
export const previewSalesHistory = file => upload('preview', file)
export const importSalesHistory = (file, fileSha256) => upload('import', file, { fileSha256 })

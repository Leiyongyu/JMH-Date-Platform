import request from '@/utils/request'

const base = '/operations/mixed-sales/amz'
export const listAmzMixedSales = params => request({ url: `${base}/list`, method: 'get', params, timeout: 30000 })
export const listAmzMixedSalesDetails = params => request({ url: `${base}/details`, method: 'get', params, timeout: 30000 })
export const getAmzMixedSalesStores = () => request({ url: `${base}/stores`, method: 'get' })

const ebayBase = '/operations/mixed-sales/ebay'
export const listEbayMixedSales = params => request({ url: `${ebayBase}/list`, method: 'get', params, timeout: 120000 })
export const listEbayMixedSalesDetails = params => request({ url: `${ebayBase}/details`, method: 'get', params, timeout: 120000 })

import request from '@/utils/request'
export const getHomeInventory = month => request({ url: '/finance/home-inventory/summary', params: { month } })
export const getHomeInventorySku = month => request({ url: '/finance/home-inventory/sku', params: { month } })
export const captureHomeInventorySku = () => request({ url: '/finance/home-inventory/sku-snapshot', method: 'post' })

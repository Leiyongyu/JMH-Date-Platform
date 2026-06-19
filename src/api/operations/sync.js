import request from '@/utils/request'

/** eBay 全量同步：拉源数据 + 刷新补货/跟价快照 */
export function syncEbayAll() {
  return request({ url: '/operations/sync/manual/ebay', method: 'post' })
}

/** eBay 仅刷新快照（不拉源数据） */
export function refreshEbayOnly() {
  return request({ url: '/operations/sync/manual/ebay/refresh-only', method: 'post' })
}

/** AMZ 全量同步 */
export function syncAmzAll() {
  return request({ url: '/operations/sync/manual/amz', method: 'post' })
}

/** AMZ 仅刷新快照 */
export function refreshAmzOnly() {
  return request({ url: '/operations/sync/manual/amz/refresh-only', method: 'post' })
}

import request from '@/utils/request'

// Async sync: submit returns { submissionId, status: PENDING } immediately.
// Poll GET /operations/sync/manual/status/{submissionId} until terminal state.
// Once terminal, the response includes the real { parentLogId, parentStatus, ...steps }.

/** eBay 全量同步：拉源数据 + 刷新补货/跟价快照 (异步) */
export function syncEbayAll() {
  return request({ url: '/operations/sync/manual/ebay', method: 'post' })
}

/** eBay 仅刷新快照（不拉源数据） (异步) */
export function refreshEbayOnly() {
  return request({ url: '/operations/sync/manual/ebay/refresh-only', method: 'post' })
}

/** AMZ 全量同步 (异步) */
export function syncAmzAll() {
  return request({ url: '/operations/sync/manual/amz', method: 'post' })
}

/** AMZ 仅刷新快照 (异步) */
export function refreshAmzOnly() {
  return request({ url: '/operations/sync/manual/amz/refresh-only', method: 'post' })
}

/** 备货单同步 (异步) */
export function syncStockOrder() {
  return request({ url: '/operations/sync/manual/stock-order', method: 'post' })
}

/** 查询异步任务状态 (submissionId, NOT logId) */
export function getSyncTaskStatus(submissionId) {
  return request({ url: '/operations/sync/manual/status/' + submissionId, method: 'get' })
}

/** 数据校准 (长任务，保留单独超时) */
export function runDataCalibration(data) {
  return request({ url: '/operations/sync/calibration/full', method: 'post', params: data, timeout: 1800000 })
}

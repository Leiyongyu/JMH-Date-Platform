import { ref, onUnmounted } from 'vue'
import { getSyncTaskStatus } from '@/api/operations/sync'

/**
 * Poll async sync task status until terminal, using submissionId (NOT logId).
 *
 * Usage:
 *   const { startPolling, polling } = useTaskPoller()
 *   const resp = await syncEbayAll()
 *   startPolling(resp.data.submissionId, (result) => {
 *     if (result.status === 'SUCCESS') ElMessage.success('eBay同步完成')
 *     else ElMessage.warning('eBay同步: ' + result.status)
 *     refreshPage()
 *   })
 */
export function useTaskPoller() {
  const polling = ref(false)
  let timer = null

  function stop() {
    if (timer) { clearInterval(timer); timer = null }
    polling.value = false
  }

  /**
   * @param {string} submissionId  returned by the submit endpoint
   * @param {function} onDone      called once terminal with full status payload
   * @param {number}   intervalMs  poll interval (default 3s)
   */
  function startPolling(submissionId, onDone, intervalMs = 3000) {
    stop()
    polling.value = true
    timer = setInterval(() => {
      getSyncTaskStatus(submissionId).then(resp => {
        const data = resp?.data || resp
        if (data.isTerminal) {
          stop()
          if (onDone) onDone(data)
        }
      }).catch(() => { /* network error — retry next tick */ })
    }, intervalMs)
  }

  onUnmounted(() => stop())

  return { startPolling, polling, stopPolling: stop }
}

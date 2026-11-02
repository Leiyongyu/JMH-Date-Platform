import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'

const source = fs.readFileSync(new URL('../src/views/finance/monthlyInventoryReport/index.vue', import.meta.url), 'utf8')
const pollFunction = source.slice(source.indexOf('async function loadPurchaseOrderStatus()'), source.indexOf('async function handlePurchaseOrderSync()'))

function context(getStatus) {
  const calls = []
  const ctx = vm.createContext({
    checkPermi: () => true,
    purchaseOrderDisposed: false, purchaseOrderPollTimer: null, purchaseOrderStatusRequest: 0,
    purchaseOrderRequestId: null, purchaseOrderSubmittedAt: 0,
    purchaseOrderSyncing: { value: true }, purchaseOrderStatus: { value: {} },
    purchaseOrderStatusError: { value: '' }, sourceStatMonth: { value: '2026-10' },
    clearTimeout: () => {}, setTimeout: () => { calls.push('poll'); return 1 },
    getMonthlyInventoryPurchaseOrderStatus: getStatus,
    proxy: { $modal: { msgSuccess: () => calls.push('success') } },
    loadPeriods: async () => calls.push('periods'), loadSummary: async () => calls.push('summary'),
    Date
  })
  vm.runInContext(pollFunction, ctx)
  return { ctx, calls }
}

test('completion refreshes the page when observing a scheduled job or returning to the page', async () => {
  const { ctx, calls } = context(async () => ({ data: { running: false, run: { status: 'completed' } } }))
  await ctx.loadPurchaseOrderStatus()
  assert.equal(ctx.purchaseOrderSyncing.value, false)
  assert.deepEqual(calls, ['success', 'periods', 'summary'])
})

test('failed synchronization retains the page and displays the error without success', async () => {
  const { ctx, calls } = context(async () => ({ data: { running: false, run: { status: 'failed', error_message: '分页不完整' } } }))
  await ctx.loadPurchaseOrderStatus()
  assert.equal(ctx.purchaseOrderStatusError.value, '分页不完整')
  assert.deepEqual(calls, [])
})

test('a stale status response cannot overwrite the newly selected month', async () => {
  const resolvers = []
  const { ctx } = context(() => new Promise(resolve => resolvers.push(resolve)))
  const older = ctx.loadPurchaseOrderStatus()
  ctx.sourceStatMonth.value = '2026-09'
  const newer = ctx.loadPurchaseOrderStatus()
  resolvers[1]({ data: { stat_month: '2026-09', running: false } })
  await newer
  resolvers[0]({ data: { stat_month: '2026-10', running: true } })
  await older
  assert.equal(ctx.purchaseOrderStatus.value.stat_month, '2026-09')
  assert.equal(ctx.purchaseOrderSyncing.value, false)
})

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'

const source = readFileSync(new URL('../src/views/operations/ebay/replenishmentV2/index.vue', import.meta.url), 'utf8')

test('inline dates and retired parameters are removed; header explanation retains actual dates', () => {
  assert.doesNotMatch(source, /monthly-metric-month|parameterDialog|parameter-dialog|ParameterDialog/)
  const context = vm.createContext({ latestCompleteMonth: { value: '2026-09-16 ~ 2026-10-15' }, formatMonth: value => value })
  vm.runInContext(source.match(/function columnTip\([^]*?\n\}/)[0], context)
  assert.match(context.columnTip({ monthlyKey: 'salesQty', tip: '近30天销量' }), /2026-09-16 ~ 2026-10-15/)
})

function setup({ fail = false, stale = false } = {}) {
  const row = { site: '德国', sku: 'BMW-1-2', overseasTransitToListingDays: null }
  const context = vm.createContext({
    leadTimeSaveChains: new Map(), leadTimeSavedValues: new Map([['key', 67]]),
    savingLeadTimeKeys: new Set(), leadTimeEditVersions: new Map([['key', 1]]),
    leadTimeFieldMap: { overseasTransitToListingDays: 'overseasTransitToListingDays' },
    numberOrNull: value => value == null ? null : Number(value),
    scheduleRowRecalc: () => {}, ElMessage: { error() {} },
    saveEbayReplenishmentV2LeadTime: async payload => {
      assert.equal(payload.days, null)
      if (fail) throw new Error('save failed')
      if (stale) { context.leadTimeEditVersions.set('key', 2); row.overseasTransitToListingDays = 88 }
      return { data: { days: 67 } }
    }
  })
  vm.runInContext(source.match(/function enqueueLeadTimeSave\([^]*?\n\}/)[0], context)
  context.enqueueLeadTimeSave(row, { key: 'overseasTransitToListingDays', label: '海外时效' }, 'key', null, 1)
  return { row, context, pending: context.leadTimeSaveChains.get('key') }
}

test('clearing overseas lead time displays and caches the server default immediately', async () => {
  const { row, context, pending } = setup()
  await pending
  assert.equal(row.overseasTransitToListingDays, 67)
  assert.equal(context.leadTimeSavedValues.get('key'), 67)
})

test('slow default response does not replace a newer manual edit', async () => {
  const { row, pending } = setup({ stale: true })
  await pending
  assert.equal(row.overseasTransitToListingDays, 88)
})

test('failed lead time save restores previous effective value', async () => {
  const { row, context, pending } = setup({ fail: true })
  await assert.rejects(pending, /save failed/)
  assert.equal(row.overseasTransitToListingDays, 67)
  assert.equal(context.savingLeadTimeKeys.size, 0)
})

import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { ownerDetailRows } from '../src/components/ProductNatureChart/ownerPresentation.js'
import { segmentItems } from '../src/components/ProductNatureChart/presentation.js'

test('hidden categories remain in empty segment totals for owner reconciliation', () => {
  const emptyPoint = segmentItems([{ stat_month: '2026-09', state: 'READY', batch_id: 'b', rule_version: 'v', segments: [] }], '法国')[0]
  assert.deepEqual(emptyPoint.counts, { NEW: 0, OLD: 0, UNKNOWN: 0, CONFLICT: 0 })
  const rows = ownerDetailRows({ ...emptyPoint, reconciled: true, items: [], totals: emptyPoint }, emptyPoint, '法国')
  assert.equal(rows.at(-1).sku_count, 0)
})

const counts = { NEW: 1, OLD: 2, UNKNOWN: 0, CONFLICT: 0 }
const point = { batch_id: 'b', rule_version: 'v', stat_month: '2026-09', sku_count: 3, counts }
const result = () => ({ ...point, state: 'READY', segment_key: 'EU', reconciled: true,
  totals: { sku_count: 3, counts, percentages: { NEW: '33.33', OLD: '66.67' } },
  items: [{ owner_key: 'a', principal_name: '甲', sku_count: 3, counts }] })

test('owner totals appended with original percent units and no mutation', () => {
  const data = result(), before = structuredClone(data)
  const rows = ownerDetailRows(data, point, 'EU')
  assert.equal(rows.length, 2)
  assert.equal(rows.at(-1).principal_name, '合计')
  assert.equal(rows.at(-1).percentages.NEW, '33.33')
  assert.ok(rows.at(-1).isTotal)
  assert.deepEqual(data, before)
})
test('stale batch, region, month, version and inconsistent counts rejected', () => {
  for (const change of [{ batch_id: 'old' }, { rule_version: 'old' }, { segment_key: 'US' },
    { stat_month: '2026-08' }, { reconciled: false }, { totals: { sku_count: 2, counts } }, { items: [] }]) {
    assert.throws(() => ownerDetailRows({ ...result(), ...change }, point, 'EU'))
  }
  assert.throws(() => ownerDetailRows({ state: 'NO_SEGMENT_DETAIL', message: '缺历史明细' }, point, 'EU'), /缺历史明细/)
})
test('owner component compiles and protects requests on month changes and close', () => {
  const source = fs.readFileSync(new URL('../src/components/ProductNatureChart/OwnerDetails.vue', import.meta.url), 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'owner' })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: 'OwnerDetails.vue', id: 'owner', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  assert.match(source, /current !== version/)
  assert.match(source, /onBeforeUnmount.*version\+\+/)
  assert.match(source, /v-model="month"/)
  assert.match(source, /el-color-danger/)
})

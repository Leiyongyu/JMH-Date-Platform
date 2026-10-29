import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { deliveryRow, clearDeliveryResult, deliveryRequest, queryDeliveryRows } from '../src/views/operations/customs/shipmentFee/components/deliveryDates.js'

const validRow = () => Object.assign(deliveryRow(), { inboundPlanId: ' plan-1 ', shipmentNo: ' FBA15MPTRK38 ', sid: '12616' })

test('delivery parameters preserve the FBA number, trim text, and validate SID without numeric precision loss', () => {
  assert.deepEqual(deliveryRequest(validRow()), { inboundPlanId: 'plan-1', shipmentNo: 'FBA15MPTRK38', sid: '12616' })
  assert.equal(deliveryRequest({ ...validRow(), sid: '9223372036854775807' }).sid, '9223372036854775807')
  for (const sid of ['', '0', '-1', '1.5', 'bad', '9223372036854775808']) assert.throws(() => deliveryRequest({ ...validRow(), sid }), /SID/)
  assert.throws(() => deliveryRequest(deliveryRow()), /STA任务编号/)
})

test('bulk queries continue after invalid input and provider failure while preserving raw responses', async () => {
  const rows = [deliveryRow(), validRow(), validRow(), validRow()]
  let calls = 0
  const response = { code: -1, message: '找不到货件' }
  await queryDeliveryRows(rows, async () => {
    calls++
    if (calls === 1) throw new Error('接口超时')
    if (calls === 2) return { success: false, message: '找不到货件', response }
    return { success: true, options: [], optionCount: 0 }
  })
  assert.equal(calls, 3)
  assert.deepEqual(rows.map(row => row.status), ['ERROR', 'ERROR', 'ERROR', 'SUCCESS'])
  assert.equal(rows[1].error, '接口超时')
  assert.equal(rows[2].result.response, response)
  assert.equal(rows[3].result.optionCount, 0)
})

test('closing and requerying ignores old responses and stops later requests from the old batch', async () => {
  const rows = [validRow(), validRow()]
  let release, run = 1, calls = 0
  const old = queryDeliveryRows(rows, () => { calls++; return new Promise(resolve => { release = resolve }) }, () => run === 1)
  run++
  rows.forEach(clearDeliveryResult)
  await queryDeliveryRows([rows[0]], async () => ({ success: true, marker: 'new' }))
  release({ success: true, marker: 'old' })
  await old
  assert.equal(rows[0].result.marker, 'new')
  assert.equal(calls, 1)
  assert.equal(rows[1].status, 'PENDING')
})

for (const file of ['index.vue', 'components/DeliveryDateDialog.vue']) {
  test(`STA ${file} compiles`, () => {
    const source = readFileSync(new URL(`../src/views/operations/customs/shipmentFee/${file}`, import.meta.url), 'utf8')
    const { descriptor, errors } = parse(source)
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: 'sta-delivery' })
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: 'sta-delivery',
      compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  })
}

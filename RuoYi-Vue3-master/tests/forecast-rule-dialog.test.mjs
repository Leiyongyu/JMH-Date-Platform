// Offline component-state tests. All HTTP and timers are mocked; no browser login/service needed.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const source = readFileSync(new URL('../src/views/operations/ebay/replenishmentV2/components/ForecastRuleDialog.vue', import.meta.url), 'utf8')
const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\r?\n/gm, '')
const names = ['configs', 'revision', 'validation', 'sample', 'previewResult', 'previewing',
  'skuSite', 'skuCode', 'sourceText', 'errorText', 'saving', 'draftChanged',
  'validateCurrent', 'runPreview', 'saveRules', 'loadSku', 'sampleChanged', 'cancelPending']

function fixture() {
  const calls = { validate: [], preview: [], save: [], sku: [], emitted: [] }
  const timers = new Map()
  const configs = Array.from({ length: 13 }, (_, i) => ({
    rule_no: i + 1, product_nature: i === 0 ? '新品' : '老品',
    condition_expr: 'true', formula_expr: 's30', remark: '', status: 1
  }))
  let timerId = 0
  const context = vm.createContext({
    ref: value => ({ value }), reactive: value => value, watch: () => {},
    onBeforeUnmount: () => {}, defineProps: () => ({ modelValue: true, siteOptions: [] }),
    defineEmits: () => (...args) => calls.emitted.push(args),
    ElMessage: { warning: () => {}, success: () => {} },
    setTimeout: (fn, delay) => { const id = ++timerId; timers.set(id, { fn, delay }); return id },
    clearTimeout: id => timers.delete(id),
    validateEbayReplenishmentV2ForecastRules: async body => {
      calls.validate.push(body)
      return { data: { valid: true, rows: body.configs.map(row => ({ rule_no: row.rule_no, valid: true, errors: {} })) } }
    },
    previewEbayReplenishmentV2ForecastRules: async body => {
      calls.preview.push(body)
      return { data: { result: { status: 'matched', matched_rule_no: 2, value: '59.00' } } }
    },
    saveEbayReplenishmentV2ForecastRules: async body => { calls.save.push(body); return { data: {} } },
    getEbayReplenishmentV2ForecastSku: async body => { calls.sku.push(body); return { data: {} } }
  })
  vm.runInContext(script + '\nglobalThis.editor = {' + names.join(',') + '}', context)
  const editor = context.editor
  editor.configs.value = configs
  editor.revision.value = 'a'.repeat(64)
  editor.sample.product_nature = '老品'
  return { editor, calls, timers, context }
}

const flush = () => new Promise(resolve => setImmediate(resolve))
const deferred = () => {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

test('rapid edits debounce into a single 500ms validation request', async () => {
  const { editor, timers, calls } = fixture()
  editor.draftChanged(2)
  editor.draftChanged(3)
  editor.draftChanged(2)
  assert.equal(timers.size, 1)
  const timer = [...timers.values()][0]
  assert.equal(timer.delay, 500)
  timer.fn()
  await flush()
  assert.equal(calls.validate.length, 1)
})

test('preview sends unsaved formulas and preserves decimal input text', async () => {
  const { editor, calls } = fixture()
  editor.configs.value[1].formula_expr = 's30 * 0.1234567890123456789'
  editor.sample.sales_7d = '1.1234567890123456789'
  await editor.runPreview()
  assert.equal(calls.preview[0].configs[1].formula_expr, 's30 * 0.1234567890123456789')
  assert.equal(calls.preview[0].sales_7d, '1.1234567890123456789')
  assert.equal(calls.save.length, 0)
  assert.equal(editor.previewResult.value.matched_rule_no, 2)
})

test('invalid validation blocks both save and preview', async () => {
  const { editor, calls, context } = fixture()
  context.validateEbayReplenishmentV2ForecastRules = async body => ({ data: {
    valid: false, rows: body.configs.map(row => ({ rule_no: row.rule_no, valid: false, errors: { condition_expr: '未知变量 r5' } }))
  } })
  await editor.saveRules()
  await editor.runPreview()
  assert.equal(calls.save.length, 0)
  assert.equal(calls.preview.length, 0)
  assert.equal(editor.saving.value, false)
})

test('failed validation request blocks writes', async () => {
  const { editor, calls, context } = fixture()
  context.validateEbayReplenishmentV2ForecastRules = async () => { throw new Error('offline failure') }
  await editor.saveRules()
  assert.equal(calls.save.length, 0)
  assert.match(editor.errorText.value, /offline failure/)
})

test('save includes revision and emits refresh only after success', async () => {
  const { editor, calls } = fixture()
  await editor.saveRules()
  assert.equal(calls.save.length, 1)
  assert.equal(calls.save[0].revision, 'a'.repeat(64))
  assert.equal(calls.save[0].configs.length, 13)
  assert.equal(calls.emitted[0][0], 'saved')
  assert.equal(calls.emitted[1][0], 'update:modelValue')
  assert.equal(calls.emitted[1][1], false)
})

test('save conflict retains the open draft without emitting refresh', async () => {
  const { editor, calls, context } = fixture()
  context.saveEbayReplenishmentV2ForecastRules = async () => { throw new Error('规则已被其他人修改') }
  await editor.saveRules()
  assert.equal(calls.emitted.length, 0)
  assert.equal(editor.configs.value.length, 13)
  assert.match(editor.errorText.value, /其他人修改/)
})

test('slow preview cannot overwrite a subsequent input edit', async () => {
  const { editor, context } = fixture()
  const wait = deferred()
  context.previewEbayReplenishmentV2ForecastRules = () => wait.promise
  const pending = editor.runPreview()
  await flush()
  editor.sample.sales_7d = '999'
  editor.sampleChanged()
  wait.resolve({ data: { result: { status: 'matched', value: '1.00' } } })
  await pending
  assert.equal(editor.previewResult.value, null)
  assert.equal(editor.previewing.value, false)
})

test('late validation cannot mark changed rules as valid', async () => {
  const { editor, context } = fixture()
  const wait = deferred()
  context.validateEbayReplenishmentV2ForecastRules = () => wait.promise
  const pending = editor.validateCurrent()
  editor.configs.value[1].condition_expr = 'r5 > 0'
  editor.draftChanged(2)
  wait.resolve({ data: { valid: true, rows: editor.configs.value.map(row => ({ rule_no: row.rule_no, valid: true })) } })
  assert.equal(await pending, false)
  assert.equal(editor.validation.value[2], null)
})

test('late exact SKU response cannot overwrite manually edited trial values', async () => {
  const { editor, context } = fixture()
  const wait = deferred()
  context.getEbayReplenishmentV2ForecastSku = () => wait.promise
  editor.skuSite.value = '英国'
  editor.skuCode.value = 'ABC-001-YXR'
  const pending = editor.loadSku()
  editor.sample.sales_7d = '999'
  editor.sampleChanged()
  wait.resolve({ data: { sales_7d: '1', sales_15d: '2', sales_30d: '3', age_days: '58', product_nature: '新品' } })
  await pending
  assert.equal(editor.sample.sales_7d, '999')
})

test('closing cancels debounce and invalidates pending preview', async () => {
  const { editor, timers } = fixture()
  editor.draftChanged(2)
  assert.equal(timers.size, 1)
  editor.cancelPending()
  assert.equal(timers.size, 0)
  assert.equal(editor.previewResult.value, null)
})

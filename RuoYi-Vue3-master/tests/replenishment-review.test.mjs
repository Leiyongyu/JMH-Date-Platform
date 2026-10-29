import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const page = readFileSync(new URL('../src/views/operations/ebay/replenishmentV2/index.vue', import.meta.url), 'utf8')
const cell = readFileSync(new URL('../src/views/operations/ebay/replenishmentV2/components/ReviewNoteCell.vue', import.meta.url), 'utf8')

test('rolling page and editable note component compile, retired columns are gone', () => {
  for (const source of [page, cell]) {
    const { descriptor, errors } = parse(source)
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: 'review' })
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: 'review.vue', id: 'review', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  }
  assert.doesNotMatch(page, /有单天数|\bADI\b|完整自然月|数据最新日/)
  assert.match(page, /operations:ebayReplenishmentV2:purchase/)
  assert.doesNotMatch(page, /procurement:pendingPurchase:add|submitPendingPurchase/)
  assert.doesNotMatch(cell, /el-popover|\sreadonly\s/)
  assert.match(cell, /@focus="startEdit"/)
  assert.match(cell, /@update:model-value="updateDraft"/)
  assert.match(page, /operationsConfirmed: typeof queryParams.operationsConfirmed === 'boolean'/)
  assert.match(page, /operationsNote: '__append__', developmentNote: '__append__'/)
  assert.match(cell, /Array.from\(props.value \|\| ''\).slice\(0, 5\)/)
})

test('operations confirmation cancel writes nothing; success stores only after second confirm', async () => {
  const sent = []
  const context = vm.createContext({ reviewAvailable: { value: true }, isNoteBusy: () => false,
    confirmingRows: new Set(), rowKey: row => `${row.site}|${row.sku}`,
    ElMessageBox: { confirm: async () => { throw 'cancel' } }, ElMessage: { success() {} },
    confirmEbayReplenishmentReview: async data => { sent.push(data); return { data: { operations_confirmed: true } } },
    applyReview: (row, data) => { row.operationsConfirmed = data.operations_confirmed }
  })
  vm.runInContext(page.match(/async function confirmOperations\([^]*?\n\}/)[0], context)
  const row = { site: '德国', sku: 'BMW-1-2', operationsVersion: 3, operationsConfirmed: false }
  await context.confirmOperations(row)
  assert.equal(sent.length, 0)
  context.ElMessageBox.confirm = async () => true
  await context.confirmOperations(row)
  assert.equal(sent.length, 1)
  assert.equal(sent[0].expected_version, 3)
  assert.equal(row.operationsConfirmed, true)
})

function noteState(fail = false) {
  const events = [], sent = []
  const props = { site: '德国', sku: 'BMW-1-2', field: 'operations', value: '原始完整备注', version: 2, disabled: false }
  const source = cell.split('const preview =', 2)[1].split('</script>', 1)[0]
  const context = vm.createContext({ props, emit: (...args) => events.push(args),
    computed: fn => ({ get value() { return fn() } }), ref: value => ({ value }),
    saveEbayReplenishmentReviewNote: async payload => {
      sent.push(payload)
      if (fail) throw new Error('conflict')
      return { data: { operations_note: payload.text, operations_version: 3 } }
    }
  })
  vm.runInContext(`const preview = ${source}\nthis.state = { preview, draft, error, editing, startEdit, finishEdit, save, discard, handleEnter }`, context)
  return { state: context.state, sent, events, context }
}

test('five-character preview does not truncate saved text; repeated save is deduplicated', async () => {
  const { state, sent } = noteState()
  assert.equal(state.preview.value, '原始完整备')
  state.startEdit()
  state.draft.value = '完整备注内容超过五个字符😀'
  await Promise.all([state.save(), state.save()])
  assert.equal(sent.length, 1)
  assert.equal(sent[0].text, state.draft.value)
  assert.equal(sent[0].expected_version, 2)
})

test('failed saves preserve draft on reopening and allow explicit discard', async () => {
  const { state, events } = noteState(true)
  state.startEdit()
  state.draft.value = '未保存内容'
  await state.finishEdit()
  state.startEdit()
  assert.equal(state.draft.value, '未保存内容')
  assert.ok(state.error.value)
  state.discard()
  assert.deepEqual(events.at(-1), ['busy', false])
})

test('Chinese IME candidate confirmation does not submit unfinished notes', async () => {
  const { state, sent } = noteState()
  state.startEdit()
  state.draft.value = '中文输入中'
  await state.handleEnter({ isComposing: true, preventDefault: () => assert.fail('IME must stay active') })
  assert.equal(sent.length, 0)
  let prevented = false
  await state.handleEnter({ isComposing: false, preventDefault: () => { prevented = true } })
  assert.equal(prevented, true)
  assert.equal(sent.length, 1)
})

test('out-of-order note responses never roll back newer operations confirmation', () => {
  const context = vm.createContext({queryParams: {}, scheduleTreeReload: () => {}})
  vm.runInContext(page.match(/function applyReview\([^]*?\n\}/)[0], context)
  const row = { operationsVersion: 4, developmentVersion: 1, operationsNote: '新运营备注', operationsConfirmed: true }
  context.applyReview(row, { operations_version: 3, operations_note: '旧运营备注', operations_confirmed: false,
    development_version: 2, development_note: '新开发备注' })
  assert.equal(row.operationsConfirmed, true)
  assert.equal(row.operationsNote, '新运营备注')
  assert.equal(row.developmentNote, '新开发备注')
})

test('refocusing during a slow blur save keeps the input editable', async () => {
  const { state, context, events } = noteState()
  let resolve
  context.saveEbayReplenishmentReviewNote = () => new Promise(done => { resolve = done })
  state.startEdit()
  state.draft.value = '等待保存'
  const pending = state.finishEdit()
  state.startEdit()
  resolve({ data: { operations_note: '等待保存', operations_version: 3 } })
  await pending
  assert.equal(state.editing.value, true)
  assert.deepEqual(events.at(-1), ['busy', true])
  await state.finishEdit()
  assert.equal(state.editing.value, false)
})

test('column filters preserve false, combine both notes and pass to child requests', async () => {
  let requests = 0
  const queryParams = { pageNum: 3 }
  const context = vm.createContext({ queryParams, loadRows: () => { requests += 1 } })
  vm.runInContext(page.match(/function handleColumnFilterChange\([^]*?\n\}/)[0], context)
  vm.runInContext(page.match(/function noteFilterValues\([^]*?\n\}/)[0], context)
  context.handleColumnFilterChange({ operationsNote: [true], developmentNote: [false] })
  assert.equal(queryParams.operationsNoteFilled, true)
  assert.equal(queryParams.developmentNoteFilled, false)
  assert.equal(queryParams.pageNum, 1)
  assert.deepEqual(Array.from(context.noteFilterValues({ reviewField: 'development' })), [false])
  const { childQuery } = await import('../src/views/operations/ebay/replenishmentV2/hierarchy.js')
  const child = childQuery({ nodeKind: 'site', site: '英国' }, queryParams, 'a'.repeat(32))
  assert.equal(child.operationsNoteFilled, true)
  assert.equal(child.developmentNoteFilled, false)
  context.handleColumnFilterChange({ operationsNote: [] })
  assert.equal(queryParams.operationsNoteFilled, undefined)
  assert.equal(queryParams.developmentNoteFilled, false)
  assert.equal(requests, 2)
})

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const page = readFileSync(new URL('../src/views/operations/ebay/replenishmentV2/index.vue', import.meta.url), 'utf8')
const code = name => page.match(new RegExp(`(?:async )?function ${name}\\([^]*?\\n\\}`))[0]

test('refresh forces a rebuild, pagination and searches reuse calculated results', () => {
  const calls = []
  const context = vm.createContext({ loadRows: (...args) => calls.push(args), queryParams: { pageNum: 5 } })
  vm.runInContext(code('refreshRows'), context)
  vm.runInContext(code('handleQuery'), context)
  context.refreshRows()
  context.handleQuery()
  assert.deepEqual(calls, [[true], []])
  assert.match(page, /@queryTable="refreshRows"/)
  assert.match(page, /@pagination="loadRows"/)
  assert.match(page, /refresh: forceRefresh === true/)
  assert.match(page, /@saved="refreshRows"/)
})

test('row recalculation requests an exact SKU and forces updated inputs', () => {
  assert.match(code('recalcRow'), /exactSku: true/)
  assert.match(code('recalcRow'), /refresh: true/)
  assert.match(code('recalcRow'), /calculationVersion.value = ''/)
  assert.match(code('scheduleRowRecalc'), /calculationVersion.value = ''/)
})

test('export pins the displayed generation and refreshes a mixed edited page first', async () => {
  const sent = []
  let reloads = 0
  const context = vm.createContext({
    checkPermi: () => true, exporting: { value: false }, loading: { value: false }, calculationVersion: { value: 'version1' },
    rowRecalcTimers: new Map(), recalculatingRowKeys: new Set(),
    leadTimeSaveTimers: new Map(), leadTimeSaveChains: new Map(), salesTypeSaving: new Set(),
    noteBusy: new Set(), confirmingRows: new Set(), ElMessage: { warning: () => assert.fail('unexpected warning') },
    buildRequestParams: () => ({ pageNum: 2, pageSize: 50, productLevel: 'S', principalName: '任雅婷' }),
    exportEbayReplenishmentV2: async params => sent.push(params),
    loadRows: async force => { assert.equal(force, true); reloads++; context.calculationVersion.value = 'version2' }
  })
  vm.runInContext(code('handleExport'), context)
  await context.handleExport()
  assert.equal(sent[0].calculationVersion, 'version1')
  assert.equal(sent[0].productLevel, 'S')
  assert.equal(sent[0].principalName, '任雅婷')
  assert.equal(sent[0].pageNum, undefined)
  assert.equal(reloads, 0)
  context.calculationVersion.value = ''
  await context.handleExport()
  assert.equal(reloads, 1)
  assert.equal(sent[1].calculationVersion, 'version2')
})

test('export waits for debounced or running recalculation', async () => {
  let warnings = 0
  const context = vm.createContext({
    checkPermi: () => true, exporting: { value: false }, loading: { value: false },
    rowRecalcTimers: new Map([['row', 1]]), recalculatingRowKeys: new Set(),
    ElMessage: { warning: () => warnings++ },
    exportEbayReplenishmentV2: () => assert.fail('export ran before recalculation')
  })
  vm.runInContext(code('handleExport'), context)
  await context.handleExport()
  context.rowRecalcTimers.clear()
  context.recalculatingRowKeys.add('row')
  await context.handleExport()
  assert.equal(warnings, 2)
})

test('owner dropdown forwards selected and unassigned names, clearing removes the filter', () => {
  assert.match(page, /label="负责人" prop="principalName"/)
  assert.match(page, /v-model="queryParams.principalName"[^]*?@change="handleQuery"/)
  assert.match(page, /principalOptions.value = Array.isArray\(data.principals\)/)
  assert.match(code('resetQuery'), /resetFields\(\)/)
  const context = vm.createContext({ queryParams: { pageNum: 3, pageSize: 50, principalName: '未分配' } })
  vm.runInContext(code('buildRequestParams'), context)
  assert.equal(context.buildRequestParams().principalName, '未分配')
  context.queryParams.principalName = '任雅婷'
  assert.equal(context.buildRequestParams().principalName, '任雅婷')
  context.queryParams.principalName = ''
  assert.equal(context.buildRequestParams().principalName, undefined)
})

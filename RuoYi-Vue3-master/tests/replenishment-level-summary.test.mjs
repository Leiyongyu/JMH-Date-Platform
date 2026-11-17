import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const source = readFileSync(new URL('../src/views/operations/ebay/replenishmentV2/index.vue', import.meta.url), 'utf8')
const functionSource = name => source.match(new RegExp(`(?:async )?function ${name}\\([^]*?\\n\\}`))[0]

test('all four derived columns request server sorting and grade keeps its original dropdown style', () => {
  for (const key of ['safetyStockQty', 'suggestedReplenishmentQty', 'safetyStockQty2', 'suggestedReplenishmentQty2']) {
    assert.match(source, new RegExp(`key: '${key}'[^\\n]+sortable: true`))
    assert.match(source, new RegExp(`${key}: '${key}'`))
  }
  assert.match(source, /:sortable="col.sortable \? 'custom' : false"/)
  assert.match(source, /productLevelOptions = \['', 'S', 'A', 'B', 'C', '--'\]/)
  const gradeFilter = source.match(/<el-form-item label="产品等级"[^]*?<\/el-form-item>/)[0]
  assert.match(gradeFilter, /<el-select[^>]*v-model="queryParams.productLevel"[^>]*clearable[^>]*style="width: 160px"[^>]*@change="handleQuery"/)
  assert.match(gradeFilter, /:label="levelOptionLabel\(level\)"/)
  assert.doesNotMatch(gradeFilter, /el-radio|level-filter|level-summary-note/)
  let queries = 0
  const context = vm.createContext({ queryParams: { pageNum: 9 }, loadRows: () => queries++ })
  vm.runInContext(functionSource('handleQuery'), context)
  context.handleQuery()
  assert.equal(context.queryParams.pageNum, 1)
  assert.equal(queries, 1)
})

test('grade dropdown labels append both quantity totals including zero and ungraded; owner column is appended', () => {
  const context = vm.createContext({
    levelSummary: { value: { ALL: { qty: '1200' }, '--': { qty: '0', suggested_replenishment_quantity: '0', suggested_replenishment_quantity_2: '0' },
      S: { suggested_replenishment_quantity: '1234', suggested_replenishment_quantity_2: '56' } } },
    formatNumber: value => Number(value).toLocaleString('en-US'),
    ownerRuleMonth: { value: '2026-10' }
  })
  vm.runInContext(functionSource('levelQuantity'), context)
  vm.runInContext(functionSource('levelOptionLabel'), context)
  vm.runInContext(functionSource('columnTip'), context)
  assert.equal(context.levelQuantity('', 'qty'), '1,200')
  assert.equal(context.levelQuantity('--', 'qty'), '0')
  assert.equal(context.levelQuantity('S', 'qty'), '--')
  assert.equal(context.levelOptionLabel('S'), 'S（1,234 / 56）')
  assert.equal(context.levelOptionLabel('--'), '--（0 / 0）')
  assert.match(context.columnTip({ key: 'principalName', tip: '按当月品牌' }), /2026-10/)
  assert.match(source, /principalName: '__append__'/)
  assert.match(source, /principalName: item.principal_name \|\| \(item.node_kind && item.node_kind !== 'sku' \? '--' : '未分配'\)/)
})

async function recalc({ stale = false } = {}) {
  const row = { site: '德国', sku: 'BMW-1-1', productLevel: 'S', suggestedReplenishmentQty: 3,
    suggestedReplenishmentQty2: 7 }
  const context = vm.createContext({
    rowsRequest: 4, leadTimeFieldMap: {}, leadTimeSaveChains: new Map(),
    calculationVersion: { value: 'old-generation' },
    rowRecalcVersions: new Map([['row', 1]]), recalculatingRowKeys: new Set(),
    levelSummary: { value: {
      ALL: { suggested_replenishment_quantity: '100', suggested_replenishment_quantity_2: '200' },
      S: { suggested_replenishment_quantity: '30', suggested_replenishment_quantity_2: '70' },
      A: { suggested_replenishment_quantity: '70', suggested_replenishment_quantity_2: '130' }
    } },
    numberOrNull: value => value == null ? null : Number(value),
    listEbayReplenishmentV2: async () => {
      if (stale) context.rowsRequest++
      return { data: {
        items: [{ site: row.site, sku: row.sku, suggested_replenishment_quantity: '13', suggested_replenishment_quantity_2: '5' }],
        level_summary: { ALL: { suggested_replenishment_quantity: '13' } }
      } }
    }
  })
  vm.runInContext(functionSource('recalcRow'), context)
  await context.recalcRow(row, 'row', 1)
  return { row, summary: context.levelSummary.value }
}

test('editing lead time adjusts only the row grade and all-grade totals, never replaces them with a single-SKU summary', async () => {
  const { row, summary } = await recalc()
  assert.equal(row.suggestedReplenishmentQty, 13)
  assert.equal(row.suggestedReplenishmentQty2, 5)
  assert.equal(summary.ALL.suggested_replenishment_quantity, '110')
  assert.equal(summary.ALL.suggested_replenishment_quantity_2, '198')
  assert.equal(summary.S.suggested_replenishment_quantity, '40')
  assert.equal(summary.S.suggested_replenishment_quantity_2, '68')
  assert.equal(summary.A.suggested_replenishment_quantity, '70')
})

test('late row recalculation cannot alter totals after a new table query', async () => {
  const { row, summary } = await recalc({ stale: true })
  assert.equal(row.suggestedReplenishmentQty, 3)
  assert.equal(summary.ALL.suggested_replenishment_quantity, '100')
})

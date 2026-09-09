import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

const source = fs.readFileSync(new URL('../src/views/operations/ebay/replenishmentV2/index.vue', import.meta.url), 'utf8')
function setup(fails = false) {
  const sent = []
  const context = {
    canEditSalesType: true, salesTypeAvailable: { value: true },
    salesTypeOptions: [{ value: 'NORMAL' }, { value: 'BRUSH' }],
    salesTypeSaving: new Set(), rowKey: row => JSON.stringify([row.site, row.sku]),
    queryParams: { salesType: 'NORMAL', pageNum: 3 },
    ElMessage: { success() {} }, loadRows: async () => {},
    saveEbayReplenishmentV2SalesType: async data => {
      sent.push(data)
      if (fails) throw new Error('save failed')
    }
  }
  vm.createContext(context)
  vm.runInContext(source.match(/async function saveSalesType\([^]*?\n\}/)[0], context)
  return { context, sent }
}

test('保存成功才更新标记，当前筛选重查第一页', async () => {
  const { context, sent } = setup()
  const row = { site: '德国', sku: '2PC-FULL-SKU', salesType: 'NORMAL' }
  await context.saveSalesType(row, 'BRUSH')
  assert.equal(row.salesType, 'BRUSH')
  assert.equal(sent[0].sku, '2PC-FULL-SKU')
  assert.equal(context.queryParams.pageNum, 1)
  assert.equal(context.salesTypeSaving.size, 0)
})

test('失败保留原值，释放保存状态', async () => {
  const { context } = setup(true)
  const row = { site: '德国', sku: 'SKU', salesType: 'NORMAL' }
  await assert.rejects(context.saveSalesType(row, 'BRUSH'), /save failed/)
  assert.equal(row.salesType, 'NORMAL')
  assert.equal(context.salesTypeSaving.size, 0)
})

test('无权限、未部署、非法值、相同值均不提交', async () => {
  const { context, sent } = setup()
  const row = { site: '德国', sku: 'SKU', salesType: 'NORMAL' }
  await context.saveSalesType(row, 'NORMAL')
  await context.saveSalesType(row, 'INVALID')
  context.canEditSalesType = false
  await context.saveSalesType(row, 'BRUSH')
  context.canEditSalesType = true
  context.salesTypeAvailable.value = false
  await context.saveSalesType(row, 'BRUSH')
  assert.equal(sent.length, 0)
})

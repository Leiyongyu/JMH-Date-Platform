import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { inventoryColumnHelp } from '../src/views/operations/ebay/inventoryDetail/columnHelp.js'

const filename = new URL('../src/views/operations/ebay/inventoryDetail/index.vue', import.meta.url)
const source = fs.readFileSync(filename, 'utf8')
const columnBlock = source.match(/const columnDefs = (\[[\s\S]*?\n\])\.map/)?.[1]
assert.ok(columnBlock, 'column definitions remain decorated with help by field key')
const columnKeys = Array.from(columnBlock.matchAll(/key: '([^']+)'/g), match => match[1])

test('all 29 columns have source API, source table, formula and empty handling', () => {
  assert.equal(columnKeys.length, 29)
  assert.equal(new Set(columnKeys).size, 29)
  assert.deepEqual(Object.keys(inventoryColumnHelp).sort(), [...columnKeys].sort())
  for (const key of columnKeys) {
    for (const field of ['sourceApi', 'sourceTable', 'formula', 'emptyHandling']) {
      assert.equal(typeof inventoryColumnHelp[key][field], 'string', `${key}.${field}`)
      assert.ok(inventoryColumnHelp[key][field].trim().length > 0, `${key}.${field}`)
    }
  }
  assert.ok(source.includes('help: inventoryColumnHelp[column.key]'))
})

test('middle code follows SKU with textual leading-zero and missing-value help', () => {
  assert.equal(columnKeys[columnKeys.indexOf('sku') + 1], 'sku_middle_code')
  assert.match(inventoryColumnHelp.sku_middle_code.formula, /MCD-20017-0071→20017/)
  assert.match(inventoryColumnHelp.sku_middle_code.formula, /保留前导零/)
  assert.match(inventoryColumnHelp.sku_middle_code.emptyHandling, /null.*--/)
  assert.ok(source.includes("{ sku_middle_code: 'sku' }"))
})

test('top metadata and warning banner are removed while field and import warnings remain', () => {
  const template = parse(source).descriptor.template.content
  for (const text of ['data-context', 'data-warning', '部分数据需留意', '库存实际拉取',
    '销量截至', '负责人规则', '仓租范围', '汇率月份', '采购价快照', '库龄实际拉取', '库龄拉取归属月']) {
    assert.ok(!template.includes(text), text)
  }
  for (const field of ['rent_warning', 'price_warning', 'age_warning']) {
    assert.ok(template.includes(':content="row.' + field + '"'), field)
  }
  assert.ok(template.includes('importWarnings'))
  assert.doesNotMatch(source, /metadata\.value|const metadata =|const warnings =/)
})

test('stock lineage uses only the latest successful weekly batch and preserves warehouse scope', () => {
  for (const key of ['overseas_in_transit_quantity', 'overseas_sellable_quantity',
    'chengdu_in_transit_quantity', 'chengdu_sellable_quantity']) {
    const help = inventoryColumnHelp[key]
    assert.match(help.sourceTable, /date-project\.ods_lingxing_inventory_detail_weekly/)
    assert.doesNotMatch(help.sourceTable, /warehouse_inventory_detail/)
    assert.match(help.sourceApi, /每周一07:30/)
    assert.match(help.formula, /最新的成功快照批次/)
    assert.match(help.formula, /同仓库wid＋产品product_id多店铺记录/)
    assert.match(help.formula, /选一条完整记录/)
    assert.match(help.formula, /不混合历史批次、不回退旧库存表/)
  }
  assert.match(inventoryColumnHelp.overseas_sellable_quantity.formula, /德国18699、英国18702、美国18700＋18701/)
  assert.match(inventoryColumnHelp.chengdu_sellable_quantity.formula, /德国18674、英国18675、美国18676/)
})

test('lineage distinguishes Excel imports, reserved fields and monetary missing values', () => {
  assert.match(inventoryColumnHelp.sales_qty_30d.sourceApi, /Excel.*非 eBay 在线销量接口/)
  assert.match(inventoryColumnHelp.grade.sourceApi, /Excel等级表导入/)
  assert.match(inventoryColumnHelp.owner.sourceApi, /Excel/)
  assert.match(inventoryColumnHelp.owner.emptyHandling, /未分配/)
  assert.match(inventoryColumnHelp.procurement_plan_quantity.sourceApi, /业务默认值/)
  assert.match(inventoryColumnHelp.procurement_plan_quantity.formula, /所有站点、SKU.*固定为0/)
  assert.match(inventoryColumnHelp.procurement_plan_quantity.emptyHandling, /Excel写入数值0，不留空/)
  const rent = inventoryColumnHelp.warehouse_rent_30d_cny
  assert.match(rent.sourceApi, /get_wh_inventory_storage_detail/)
  assert.match(rent.formula, /warehouse_rent_amount/)
  assert.match(rent.formula, /pulled_at月份的my_rate/)
  assert.match(rent.emptyHandling, /无收费记录时显示0/)
  assert.match(rent.emptyHandling, /显示--/)
})

test('pending outbound uses confirmed product_total across all seven warehouses', () => {
  const help = inventoryColumnHelp.pending_outbound_quantity
  assert.match(help.sourceTable, /ods_lingxing_inventory_detail_weekly.product_total/)
  assert.match(help.sourceApi, /inventoryDetails/)
  assert.match(help.formula, /全部7个仓库/)
  assert.match(help.formula, /最新的成功快照批次/)
  assert.match(help.formula, /选一条完整记录/)
  assert.match(help.emptyHandling, /为空时按0/)
  for (const key of ['cycle_total_quantity', 'total_stock_sales_ratio_months', 'purchase_quantity']) {
    assert.match(inventoryColumnHelp[key].sourceTable, /product_total/)
  }
})

test('purchase quantity uses fixed 4.03 months and last sold month uses all history', () => {
  const help = inventoryColumnHelp.purchase_quantity
  assert.match(help.formula, /近3个月均销量×总时长（月）－周期总库存/)
  assert.match(help.formula, /使用未舍入值/)
  assert.match(help.formula, /ROUND_HALF_UP四舍五入到整数/)
  assert.match(help.formula, /不将负数截为0/)
  assert.match(help.emptyHandling, /总时长固定4.03/)
  assert.match(inventoryColumnHelp.total_duration_months.formula, /固定为4.03个月/)
  assert.match(inventoryColumnHelp.total_duration_months.sourceApi, /无外部接口/)
  assert.match(inventoryColumnHelp.last_sold_at.formula, /站点＋完整SKU.*全部历史订单.*MAX\(payment_time\).*YYYY-MM/)
  assert.match(inventoryColumnHelp.last_sold_at.emptyHandling, /返回null，页面显示--、Excel留空/)
  assert.match(columnBlock, /key: 'purchase_quantity'[^\n]+format: 'quantity'/)
})

test('overseas maximum age uses the isolated weekly GoodCang latest batch and checks both suffix collision sides', () => {
  const help = inventoryColumnHelp.overseas_max_age_days
  assert.match(help.sourceApi, /谷仓 POST \/inventory\/inventory_age_list/)
  assert.match(help.sourceApi, /独立任务计划每周一06:00（中国时区）刷新/)
  assert.match(help.sourceApi, /页面只查库，不新增接口或触发拉取/)
  assert.match(help.sourceTable, /jmh_data_platform\.ods_goodcang_inventory_age_latest/)
  assert.match(help.sourceTable, /仅保存最新成功拉取的单批数据/)
  assert.doesNotMatch(help.sourceTable, /ods_goodcang_inventory_age_monthly/)
  for (const field of ['warehouse_age', 'warehouse_code', 'product_sku', 'snapshot_month', 'pulled_at']) {
    assert.ok(help.sourceTable.includes(field), field)
  }
  assert.match(help.formula, /最新单批全表，不按snapshot_month筛选/)
  assert.match(help.formula, /snapshot_month仅标记拉取归属月，pulled_at为实际拉取时间/)
  assert.match(help.formula, /事务整表覆盖、只留一批，与月度库存及滞销月快照隔离/)
  assert.match(help.formula, /两端仅去首段前缀.*按站点＋剩余完整尾码匹配/)
  assert.match(help.formula, /DE\/CZ\/IT→德国，UK→英国，FR→法国，US开头→美国/)
  assert.match(help.formula, /同一拉取批次内，同站点多仓库、多库存批次取MAX\(warehouse_age\)/)
  assert.match(help.formula, /不加距快照日的天数，不做库存加权/)
  assert.match(help.formula, /不依赖成本match_status或采购价格/)
  assert.match(help.emptyHandling, /刷新失败保留上次成功数据及其实际拉取时间/)
  assert.match(help.emptyHandling, /缺快照、无匹配或无效库龄.*null.*--/)
  assert.match(help.emptyHandling, /真实warehouse_age=0时显示0/)
  assert.match(help.emptyHandling, /库存侧同站点不同完整SKU同尾码冲突/)
  assert.match(help.emptyHandling, /来源侧同站点不同product_sku同尾码冲突/)
  assert.doesNotMatch(help.sourceApi, /预留字段|尚未接入/)
  assert.match(columnBlock, /key: 'overseas_max_age_days'[^\n]+format: 'quantity'[^\n]+sortable: true/)
  assert.match(source, /column.key === 'overseas_max_age_days' && row.age_warning/)
  assert.match(source, /:content="row.age_warning"/)
  assert.doesNotMatch(source, /库龄快照月/)
})

test('purchase price uses latest procurement cg_price by complete SKU across sites', () => {
  for (const key of ['unit_price_tax', 'overseas_sellable_value', 'overseas_total_value']) {
    const help = inventoryColumnHelp[key]
    assert.match(help.sourceApi, /productList.*batchGetProductInfo.*cg_price/)
    assert.match(help.sourceTable, /jmh_data_platform\.ods_lingxing_product_procurement_monthly/)
    assert.match(help.sourceTable, /cg_price/)
    assert.match(help.formula, /最新snapshot_month整月批次/)
    assert.match(help.formula, /完整SKU精确匹配cg_price，不区分站点、不去前缀、不按库存加权/)
    assert.match(help.formula, /不按SKU回退旧月份价格/)
    assert.match(help.formula, /人民币原值.*不再汇率换算或额外加税/)
    assert.match(help.formula, /ROUND_HALF_UP保留2位/)
    assert.match(help.emptyHandling, /未匹配.*为空.*异常.*null.*--/)
    assert.match(help.emptyHandling, /明确为0是有效价格/)
    assert.doesNotMatch(help.sourceApi, /预留字段|尚未接入/)
    assert.doesNotMatch(help.formula, /purchase_price|product_total|seller_id/)
    assert.match(columnBlock, new RegExp("key: '" + key + "'[^\\n]+format: 'money'[^\\n]+sortable: true"))
  }
  assert.match(inventoryColumnHelp.unit_price_tax.formula, /不据此宣称接口自动含税/)
  assert.match(inventoryColumnHelp.overseas_sellable_value.formula, /海外可售货值＝未舍入cg_price原价×当前海外可售/)
  assert.match(inventoryColumnHelp.overseas_total_value.formula, /海外总货值＝未舍入cg_price原价×当前海外总库存/)
  for (const key of ['overseas_sellable_value', 'overseas_total_value']) {
    assert.match(inventoryColumnHelp[key].formula, /不先把单价舍入再乘/)
    assert.match(inventoryColumnHelp[key].formula, /快照与当前库存可能来自不同批次时间/)
    assert.match(inventoryColumnHelp[key].emptyHandling, /有效价格.*为0.*¥0\.00/)
  }
  assert.match(source, /priceColumnKeys\.includes\(column.key\) && row.price_warning/)
  assert.match(source, /:content="row.price_warning"/)
})

test('monthly total stock-sales ratio uses three complete natural months and fixed divisor', () => {
  const help = inventoryColumnHelp.total_stock_sales_ratio_months
  assert.match(help.sourceApi, /inventoryDetails/)
  assert.match(help.sourceApi, /Excel.*非 eBay 在线销量接口/)
  assert.match(help.sourceTable, /date-project\.dwd_ebay_sku_analysis_order/)
  for (const field of ['payment_time', 'site_name', 'inventory_sku', 'purchase_quantity']) {
    assert.ok(help.sourceTable.includes(field), field)
  }
  assert.match(help.formula, /总库销比（月）＝周期总库存÷近3月均销量/)
  assert.match(help.formula, /中国时区查询当月以前三个完整自然月.*合计÷固定3/)
  assert.match(help.formula, /按站点＋完整SKU/)
  assert.match(help.formula, /2026年9月查询取6、7、8月/)
  assert.match(help.formula, /不是近30天日均、预估销量2或滚动90天销量/)
  assert.match(help.formula, /不按有销量月数作分母/)
  assert.match(help.formula, /周期总库存＝海外总库存＋成都在途＋成都可售＋采购计划＋待出库/)
  assert.match(help.formula, /分母不预先舍入为2位/)
  assert.match(help.formula, /原比值保留6位/)
  assert.match(help.formula, /不重复乘100/)
  assert.match(help.emptyHandling, /无销量或均销量为0.*返回0.*0.00%/)
  assert.match(help.emptyHandling, /缺失月份按0.*固定3/)
  assert.match(columnBlock, /key: 'total_stock_sales_ratio_months'[^\n]+format: 'percent'[^\n]+sortable: true/)
})

test('header tooltip wraps the label, renders four plain-text sections and compiles', () => {
  const parsed = parse(source, { filename: filename.pathname })
  assert.deepEqual(parsed.errors, [])
  const script = compileScript(parsed.descriptor, { id: 'inventory-detail' })
  const result = compileTemplate({
    source: parsed.descriptor.template.content, filename: filename.pathname,
    id: 'inventory-detail', compilerOptions: { bindingMetadata: script.bindings }
  })
  assert.deepEqual(result.errors, [])
  for (const label of ['来源接口', '源表', '计算公式', '空值处理']) {
    assert.ok(source.includes(`<dt>${label}</dt>`))
  }
  assert.match(source, /<span class="column-heading"[^>]*tabindex="0"[^>]*>[\s\S]*?column.label[\s\S]*?<\/span>\s*<\/el-tooltip>/)
  assert.ok(!source.includes('column.tip'))
  assert.ok(!source.includes('v-html'))
})

test('three-month average and percent ratios show two decimals without changing other formats', () => {
  const context = vm.createContext({})
  for (const name of ['hasValue', 'formatValue']) {
    const code = source.match(new RegExp('function ' + name + '\\([^]*?\\n\\}'))?.[0]
    assert.ok(code, name)
    vm.runInContext(code, context)
  }
  assert.equal(context.formatValue('1.73', 'decimal2'), '1.73')
  assert.equal(context.formatValue('0.4', 'decimal2'), '0.40')
  assert.equal(context.formatValue('0', 'decimal2'), '0.00')
  assert.equal(context.formatValue('1', 'decimal2'), '1.00')
  assert.equal(context.formatValue(null, 'decimal2'), '--')
  assert.equal(context.formatValue('1.666667', 'decimal'), '1.666667')
  assert.equal(context.formatValue('81.03', 'money'), '¥81.03')
  assert.equal(context.formatValue('0', 'money'), '¥0.00')
  assert.equal(context.formatValue(null, 'money'), '--')
  assert.equal(context.formatValue('0', 'quantity'), '0')
  assert.equal(context.formatValue('58', 'quantity'), '58')
  assert.equal(context.formatValue(null, 'quantity'), '--')
  for (const [raw, expected] of [
    ['0', '0.00%'], [0, '0.00%'], ['0.125', '12.50%'], ['1.25', '125.00%'],
    ['1.666667', '166.67%'], ['2.5', '250.00%'],
    [null, '--'], [undefined, '--'], ['', '--'], ['invalid', '--']
  ]) assert.equal(context.formatValue(raw, 'percent'), expected)
  for (const key of ['in_stock_sales_ratio', 'total_stock_sales_ratio', 'total_stock_sales_ratio_months']) {
    assert.match(columnBlock, new RegExp("key: '" + key + "'[^\\n]+format: 'percent'"))
    assert.match(inventoryColumnHelp[key].formula, /比值×100%/)
    assert.match(inventoryColumnHelp[key].emptyHandling, /0.00%/)
  }
  assert.match(columnBlock, /key: 'average_monthly_sales_3m'[^\n]+label: '近3个月均销量'[^\n]+format: 'decimal2'[^\n]+sortable: true/)
  assert.ok(!columnKeys.includes('average_daily_sales_30d'))
  const help = inventoryColumnHelp.average_monthly_sales_3m
  assert.match(help.formula, /近3个完整自然月.*总销量÷固定3/)
  assert.match(help.formula, /2026年9月取6、7、8月，不包含9月/)
  assert.match(help.formula, /四舍五入.*保留2位小数/)
  assert.match(help.emptyHandling, /缺失月份按0计，仍固定除以3/)
  assert.match(source, /average_daily_sales_30d: 'average_monthly_sales_3m'/)
})

test('renamed column retains saved order and hidden state, including legacy array configs', async () => {
  const composable = fs.readFileSync(new URL('../src/composables/useColumnConfig.js', import.meta.url), 'utf8')
    .replace(/^import .*$/gm, '').replace('export function useColumnConfig', 'function useColumnConfig')
  for (const [saved, expected] of [
    [{ visibleKeys: ['site', 'average_daily_sales_30d', 'sku'], allKeys: ['site', 'sku', 'average_daily_sales_30d'] }, ['site', 'average_monthly_sales_3m', 'sku']],
    [{ visibleKeys: ['site', 'sku'], allKeys: ['site', 'sku', 'average_daily_sales_30d'] }, ['site', 'sku']],
    [['site', 'average_daily_sales_30d', 'sku'], ['site', 'average_monthly_sales_3m', 'sku']]
  ]) {
    const context = vm.createContext({
      computed: fn => ({ get value() { return fn() } }), ref: value => ({ value }),
      getUserColumnConfig: async () => ({ data: JSON.stringify(saved) }),
      saveUserColumnConfig: async () => {}, localStorage: { setItem() {}, getItem() { return null } }
    })
    vm.runInContext(composable, context)
    const config = context.useColumnConfig('page',
      ['site', 'sku', 'average_monthly_sales_3m'].map(key => ({ key })), [], [],
      { average_daily_sales_30d: 'average_monthly_sales_3m' })
    await config.initColumnConfig()
    assert.deepEqual(Array.from(config.visibleKeys.value), expected)
  }
})

import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const page = fs.readFileSync(new URL('../src/views/operations/ebay/replenishmentV2/index.vue', import.meta.url), 'utf8')

test('logistics column sits before the Chengdu inventory columns and is placed for saved configs', () => {
  const logistics = page.indexOf("key: 'purchaseLogistics', label: '物流状态'")
  assert.ok(logistics > 0)
  assert.ok(logistics < page.indexOf("key: 'chengduInTransitQty'"), '物流状态排在成都在途前面')
  assert.ok(page.includes("purchaseLogistics: { before: 'chengduInTransitQty', after: 'salesType' }"),
    '已保存列配置的用户也能看到新列，位置不跑到最后')
})

test('only SKU rows with open orders show the hover trigger; others show --', () => {
  assert.ok(page.includes('v-if="!isSkuRow(scope.row) || !scope.row.purchaseLogistics" class="logistics-empty">--</span>'))
  assert.ok(page.includes('@mouseenter="showLogisticsPopover($event, scope.row)"'))
  assert.ok(page.includes('@mouseleave="hideLogisticsPopover"'))
})

test('hover shows order date, expected ship date and order status for every order', () => {
  for (const header of ['<th>PO</th>', '<th>订单状态</th>', '<th>下单日期</th>', '<th>预计发货时间</th>']) {
    assert.ok(page.includes(header), header)
  }
  assert.ok(page.includes('{{ order.orderDate ||'))
  assert.ok(page.includes('{{ order.expectedShipDate ||'))
  assert.ok(page.includes('{{ order.orderStatus }}'))
  assert.ok(page.includes('（已逾期）'))
  assert.equal(page.match(/:virtual-ref="logisticsPopoverRef"/g)?.length, 1, '全表共用一个弹层实例')
})

test('backend fields are mapped without recomputing on the page', () => {
  assert.ok(page.includes('purchaseLogistics: normalizeLogistics(item.purchase_logistics)'))
  for (const field of ['status_summary', 'earliest_expected_ship_date', 'overdue_count', 'order_date', 'expected_ship_date', 'order_status']) {
    assert.ok(page.includes(`value.${field}`) || page.includes(`order.${field}`), field)
  }
  assert.ok(page.includes('data.purchase_logistics_synced_at'))
})

test('hover is split into two logistics phases, every item listed with 0 when empty', () => {
  assert.ok(page.includes('v-for="(phase, phaseIndex) in logisticsPopoverRow.purchaseLogistics.phases"'))
  assert.ok(page.includes('阶段{{ phaseIndex + 1 }}：{{ phase.label }}'))
  assert.ok(page.includes('<td>{{ item.quantity }}件</td>'), '没有数据也显示 0 件，不显示 --')
  assert.ok(page.includes("<td>{{ item.orderCount === null ? '' : `${item.orderCount}单` }}</td>"), '采购状态显示单数，库存项只显示件数')
  assert.ok(page.includes('<td>小计</td>'), '每个阶段有小计')
  assert.ok(page.includes('<span>全链路合计</span>'), '最下面是全链路合计')
  assert.ok(page.includes("quantity: item.quantity ?? '0'"))
  assert.doesNotMatch(page, /stage\.quantity === null \? '--'/, '不再用 -- 表示没有数')
})

test('popover stays open while the mouse is inside so order details can be read and scrolled', () => {
  assert.ok(page.includes('@mouseenter="keepLogisticsPopover" @mouseleave="hideLogisticsPopover"'))
  assert.ok(page.includes('logisticsPopoverTimer = setTimeout(() => { logisticsPopoverVisible.value = false }, 200)'))
  assert.ok(page.includes('.logistics-orders { max-height: 220px; overflow-y: auto; }'))
  assert.ok(page.includes('采购单明细（{{ logisticsPopoverRow.purchaseLogistics.orderCount }}单）'))
  assert.ok(page.includes('data.inventory_stock_synced_at'))
  assert.ok(page.includes('if (!logistics.orderCount) return `全链路'), '没有采购单、只有库存的SKU也显示')
})

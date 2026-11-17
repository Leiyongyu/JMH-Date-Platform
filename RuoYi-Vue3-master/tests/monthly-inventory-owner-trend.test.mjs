import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const view = read('../src/views/finance/monthlyInventoryReport/index.vue')
const dialog = read('../src/views/finance/monthlyInventoryReport/OwnerTrendDialog.vue')
const api = read('../src/api/finance/monthlyInventoryReport.js')

test('owner dimension shows a trend button that opens the trend dialog', () => {
  assert.match(view, /v-if="activeDimension === 'owner' && canViewOwner"[\s\S]{0,200}@click="ownerTrendVisible = true"/)
  assert.match(view, /<owner-trend-dialog v-if="canViewOwner" v-model="ownerTrendVisible" :end-month="statMonth" \/>/)
  assert.match(view, /import OwnerTrendDialog from '\.\/OwnerTrendDialog\.vue'/)
})

test('trend dialog filters by month range and owner and draws the four metrics', () => {
  assert.match(dialog, /type="monthrange"/)
  assert.match(dialog, /v-model="selectedOwners"[\s\S]{0,40}multiple/)
  for (const key of ['sales_amount', 'gross_profit', 'turnover_days', 'aged_181_plus_cost'])
    assert.match(dialog, new RegExp(`key: '${key}'`))
  assert.match(dialog, /getMonthlyInventoryOwnerTrend\(start, end\)/)
  assert.match(dialog, /connectNulls: false/)
  assert.match(dialog, /new Set\(\['未分配', '注销'\]\)/)
})

test('trend api calls the Java owner-trend endpoint with both months', () => {
  assert.match(api, /url: '\/finance\/monthly-inventory-report\/owner-trend'[\s\S]{0,60}params: \{ startMonth, endMonth \}/)
})

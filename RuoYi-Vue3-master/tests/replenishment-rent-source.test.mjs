import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const page = fs.readFileSync(new URL('../src/views/operations/ebay/replenishmentV2/index.vue', import.meta.url), 'utf8')
const api = fs.readFileSync(new URL('../src/api/operations/ebay/replenishmentV2.js', import.meta.url), 'utf8')

test('补货2.0保留仓租展示，但不再提供Excel上传入口', () => {
  assert.match(page, /warehouseRentAmount: numberOrNull\(item\.warehouse_rent_amount_cny\)/)
  assert.doesNotMatch(page, /上传仓租|warehouseRentDialogVisible|submitWarehouseRentImport/)
  assert.doesNotMatch(api, /warehouse-rent\/import|importEbayReplenishmentV2WarehouseRent/)
})

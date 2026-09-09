import test from 'node:test'
import assert from 'node:assert/strict'
import { partitionPurchaseSelection } from '../src/utils/pendingPurchaseSelection.js'

test('已采购可选用于删除，但不能导出', () => {
  assert.deepEqual(partitionPurchaseSelection([{ id: 1, status: '1' }]),
    { ids: [1], pendingIds: [], purchasedCount: 1 })
})
test('混合选择：删除全部，导出仅待采购', () => {
  assert.deepEqual(partitionPurchaseSelection([{ id: 1, status: '0' }, { id: 2, status: '1' }]),
    { ids: [1, 2], pendingIds: [1], purchasedCount: 1 })
})
test('跨页去重并采用最新状态', () => {
  assert.deepEqual(partitionPurchaseSelection([{ id: 1, status: '0' }, { id: 2, status: '0' }, { id: 1, status: '1' }]),
    { ids: [1, 2], pendingIds: [2], purchasedCount: 1 })
})
test('空选择及未知状态不产生操作ID', () => {
  assert.deepEqual(partitionPurchaseSelection([{ id: 1, status: 'bad' }, null]),
    { ids: [], pendingIds: [], purchasedCount: 0 })
})


import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const page = fs.readFileSync(
  new URL('../src/views/finance/performanceRanking/index.vue', import.meta.url),
  'utf8'
)
const api = fs.readFileSync(
  new URL('../src/api/finance/performanceRanking.js', import.meta.url),
  'utf8'
)

test('ranking query excludes the unassigned bucket by default', () => {
  // The charts compare real owners, so the catch-all must not be a bar.
  assert.match(page, /excludeUnassigned:\s*true/)
})

test('page offers an unmatched diagnostics entry point', () => {
  assert.match(page, /未匹配排查/)
  assert.match(page, /openUnmatched/)
  assert.match(page, /listPerformanceUnmatched/)
})

test('diagnostics api points at the ERP proxy route', () => {
  assert.match(api, /export function listPerformanceUnmatched/)
  assert.match(api, /'\/finance\/performance-ranking\/unmatched'/)
})

test('dialog states the three rules that most often cause 未分配', () => {
  // Month-scoped rules, the US store-name segment, and the dead EU-店铺 sheet
  // are the three findings operators keep tripping over.
  assert.match(page, /按月独立生效，不会沿用上个月/)
  assert.match(page, /去掉 US1\/US2 前缀后的店铺主体名/)
  assert.match(page, /在「EU-店铺」页配负责人不生效/)
})

test('dialog surfaces reason, match key and sample columns', () => {
  for (const label of ['匹配维度', '匹配键', '原因', '利润行数', '毛利润', '示例']) {
    assert.ok(page.includes(label), `missing column: ${label}`)
  }
})

test('rows whose money never entered the ranking are marked', () => {
  assert.match(page, /countsInRanking/)
  assert.match(page, /金额未计入排名/)
})

test('every backend reason code has a tag colour', () => {
  for (const reason of [
    'RULE_MISSING',
    'OWNER_BLANK',
    'OWNER_WHITESPACE',
    'KEY_EMPTY',
    'SHOP_UNKNOWN'
  ]) {
    assert.ok(page.includes(reason), `missing reason mapping: ${reason}`)
  }
})

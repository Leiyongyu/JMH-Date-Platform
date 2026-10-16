import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const java = read('../../RuoYi-Vue-springboot3/ruoyi-system/src/main/java/com/ruoyi/system/service/operation/ebay/EbayReplenishmentV2ExportService.java')
const migration = read('../../RuoYi-Vue-springboot3/sql/20261016_ebay_replenishment_v2_export_columns.sql')
const page = read('../src/views/operations/ebay/replenishmentV2/index.vue')

test('role menu migration defines every Excel column exactly once, including detail-only columns', () => {
  const definitions = java.slice(java.indexOf('private static final List<Column> COLUMNS'), java.indexOf('public void export('))
  const keys = [...definitions.matchAll(/new Column\("[^"]+", "([^"]+)"/g)].map(match => match[1])
  const entries = [...migration.matchAll(/^\('([^']+)','([^']+)',\d+\)/gm)]
  assert.equal(keys.length, 41)
  assert.equal(entries.length, 41)
  assert.equal(new Set(entries.map(entry => entry[1])).size, 41)
  assert.deepEqual(entries.map(entry => entry[1]).sort(), keys.sort())
  for (const [, key, title] of entries) {
    assert.ok(`operations:ebayReplenishmentV2:exportColumn:${key}`.length <= 100)
    assert.ok(`导出字段-${title}`.length <= 50)
  }
  assert.match(migration, /JOIN tmp_ebay_replenishment_export_columns c ON c\.is_new=1/)
  assert.doesNotMatch(migration, /\bALTER TABLE\b|\bCREATE TABLE\b|\bDELETE FROM\b/i)
})

test('page columns and list stay independent of export-field permissions', () => {
  assert.match(page, /仅包含角色授权的导出字段/)
  assert.doesNotMatch(page, /exportColumn:/)
  assert.match(page, /const columnDefs = \[/)
  assert.match(page, /exportEbayReplenishmentV2\(params\)/)
})

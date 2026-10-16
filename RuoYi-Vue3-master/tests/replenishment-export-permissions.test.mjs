import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const java = read('../../RuoYi-Vue-springboot3/ruoyi-system/src/main/java/com/ruoyi/system/service/operation/ebay/EbayReplenishmentV2ExportService.java')
const migration = read('../../RuoYi-Vue-springboot3/sql/20261016_ebay_replenishment_v2_export_columns.sql')
const ownerMigration = read('../../RuoYi-Vue-springboot3/sql/20261016_ebay_replenishment_v2_owner_export.sql')
const page = read('../src/views/operations/ebay/replenishmentV2/index.vue')
const grouping = read('../../RuoYi-Vue-springboot3/sql/20261016_ebay_replenishment_v2_export_menu.sql')

test('role menu migration defines every Excel column exactly once, including detail-only columns', () => {
  const definitions = java.slice(java.indexOf('private static final List<Column> COLUMNS'), java.indexOf('public void export('))
  const keys = [...definitions.matchAll(/new Column\("[^"]+", "([^"]+)"/g)].map(match => match[1])
  const entries = [...migration.matchAll(/^\('([^']+)','([^']+)',\d+\)/gm)]
  assert.equal(keys.length, 42)
  assert.equal(entries.length, 41)
  assert.equal(new Set(entries.map(entry => entry[1])).size, 41)
  assert.deepEqual([...entries.map(entry => entry[1]), 'principal_name'].sort(), keys.sort())
  assert.match(ownerMigration, /operations:ebayReplenishmentV2:exportColumn:principal_name/)
  assert.match(ownerMigration, /@owner_export_new=1 AND r.role_key='admin'/)
  assert.match(ownerMigration, /allowed.menu_id=@owner_export_parent/)
  assert.doesNotMatch(ownerMigration, /\bALTER TABLE\b|\bDELETE FROM\b|UPDATE sys_role_menu/i)
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
  assert.match(page, /v-hasPermi="\['operations:ebayReplenishmentV2:export'\]"/)
})

test('export total switch prevents a request without permission', async () => {
  let sent = 0, warned = 0
  const context = vm.createContext({ checkPermi: () => false, ElMessage: { warning: () => warned++ },
    exportEbayReplenishmentV2: () => sent++ })
  vm.runInContext(page.match(/async function handleExport\(\) \{[^]*?\n\}/)[0], context)
  await context.handleExport()
  assert.equal(warned, 1)
  assert.equal(sent, 0)
})

test('upgrade moves existing field menus and bootstraps only the newly created export switch', () => {
  assert.match(grouping, /UPDATE sys_menu\s+SET parent_id=@ebay_export_button_id/)
  assert.match(grouping, /@ebay_export_button_is_new=1/)
  assert.match(grouping, /JOIN sys_role_menu field_grant/)
  assert.doesNotMatch(grouping, /\bALTER TABLE\b|\bDELETE FROM\b|UPDATE sys_role_menu/i)
  assert.match(migration, /@ebay_export_field_parent_id := COALESCE/)
})

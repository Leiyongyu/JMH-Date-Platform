import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import TreeStore from '../node_modules/element-plus/es/components/tree/src/model/tree-store.mjs'
import { EBAY_EXPORT_PERMISSION, setExportBranchChecked } from '../src/views/system/role/exportFieldSelection.mjs'

function fixture(checkStrictly = false) {
  const branch = { id: 3, label: '导出', perms: EBAY_EXPORT_PERMISSION, children: [
    { id: 4, label: '站点', perms: 'operations:ebayReplenishmentV2:exportColumn:site' },
    { id: 5, label: 'SKU', perms: 'operations:ebayReplenishmentV2:exportColumn:sku' }
  ] }
  const store = new TreeStore({ key: 'id', props: { label: 'label', children: 'children' }, checkStrictly,
    data: [{ id: 1, label: '运营中心', children: [{ id: 2, label: '补货', children: [branch,
      { id: 6, label: '采购' }, { id: 7, label: '时效' }] }] }, { id: 8, label: '其他功能' }] })
  store.initialize()
  return { store, branch }
}

for (const strict of [false, true]) {
  test(`export branch select/clear preserve siblings and ancestors; checkStrictly=${strict}`, () => {
    const { store, branch } = fixture(strict)
    store.setChecked(6, true, false)
    store.setChecked(8, true, false)
    setExportBranchChecked(store, branch, true)
    for (const id of [3, 4, 5, 6, 8]) assert.equal(store.getNode(id).checked, true)
    assert.equal(store.getNode(7).checked, false, 'cannot grant unrelated time-edit permission')
    for (const id of [1, 2]) assert.ok(store.getNode(id).checked || store.getNode(id).indeterminate)
    setExportBranchChecked(store, branch, false)
    for (const id of [3, 4, 5, 7]) assert.equal(store.getNode(id).checked, false)
    for (const id of [6, 8]) assert.equal(store.getNode(id).checked, true)
    for (const id of [1, 2]) assert.ok(store.getNode(id).checked || store.getNode(id).indeterminate)
  })

  test(`clearing last export permission keeps page access and survives saved-key reload; strict=${strict}`, () => {
    const { store, branch } = fixture(strict)
    setExportBranchChecked(store, branch, true)
    setExportBranchChecked(store, branch, false)
    const saved = [...store.getCheckedKeys(), ...store.getHalfCheckedKeys()]
    assert.ok(saved.includes(1) && saved.includes(2))
    assert.ok(!saved.includes(3) && !saved.includes(4) && !saved.includes(5))
    const restored = fixture(strict).store
    // 与角色页回显方式一致：只设置当前节点，不递归授权子节点。
    saved.forEach(id => restored.setChecked(id, true, false))
    assert.ok(restored.getNode(2).checked)
    for (const id of [3, 4, 5, 6, 7]) assert.equal(restored.getNode(id).checked, false)
  })
}

test('partial selection is preserved on role reload and unrelated nodes cannot invoke batch action', () => {
  const { store, branch } = fixture()
  store.setChecked(4, true, false)
  assert.equal(store.getNode(3).indeterminate, true)
  const before = store.getCheckedKeys()
  setExportBranchChecked(store, { ...branch, perms: 'other' }, true)
  assert.deepEqual(store.getCheckedKeys(), before)
  assert.equal(store.getNode(5).checked, false)
})

test('role dialog compiles with export-only actions and does not change the department tree', () => {
  const source = readFileSync(new URL('../src/views/system/role/index.vue', import.meta.url), 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'role-export' })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: 'role.vue', id: 'role-export',
    compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  assert.match(source, /data\.perms === EBAY_EXPORT_PERMISSION/)
  assert.match(source, /全选字段/)
  assert.match(source, /全部取消/)
  assert.match(source, /@click\.stop/)
  assert.equal((source.match(/permission-branch-actions"/g) || []).length, 1)
})

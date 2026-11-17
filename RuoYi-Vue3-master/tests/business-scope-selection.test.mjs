import assert from 'node:assert/strict'
import test from 'node:test'
import TreeStore from '../node_modules/element-plus/es/components/tree/src/model/tree-store.mjs'
import { setBusinessScope } from '../src/views/system/role/businessScopeSelection.mjs'

function fixture(strict) {
  const branch = { id: 3, perms: 'operations:ebayReplenishmentV2:data', children: [
    { id: 4, perms: 'operations:ebayReplenishmentV2:data:self' },
    { id: 5, perms: 'operations:ebayReplenishmentV2:data:dept' },
    { id: 6, perms: 'operations:ebayReplenishmentV2:data:all' }
  ] }
  const store = new TreeStore({ key: 'id', props: { label: 'label', children: 'children' }, checkStrictly: strict,
    data: [{ id: 1, children: [{ id: 2, children: [branch, { id: 7 }] }] }, { id: 8 }] })
  store.initialize()
  return { store, branch }
}

for (const strict of [false, true]) {
  test(`only one scope remains; unrelated permissions survive; strict=${strict}`, () => {
    const { store, branch } = fixture(strict)
    store.setChecked(7, true, false)
    store.setChecked(8, true, false)
    for (const [scope, id] of [['all', 6], ['self', 4], ['dept', 5]]) {
      setBusinessScope(store, branch, scope)
      for (const leaf of [4, 5, 6]) assert.equal(store.getNode(leaf).checked, leaf === id)
      assert.ok(store.getNode(7).checked && store.getNode(8).checked)
      const saved = [...store.getCheckedKeys(), ...store.getHalfCheckedKeys()]
      const restored = fixture(strict).store
      saved.forEach(key => restored.setChecked(key, true, false))
      for (const leaf of [4, 5, 6]) assert.equal(restored.getNode(leaf).checked, leaf === id)
    }
  })
}

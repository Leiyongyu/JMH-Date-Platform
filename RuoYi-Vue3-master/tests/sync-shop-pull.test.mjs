import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { firstDayOfMonth, pullState } from '../src/views/operations/sync/shop/shopPull.js'

test('store pull page compiles, uses no v-html and gates editing by permission', () => {
  const source = fs.readFileSync(new URL('../src/views/operations/sync/shop/index.vue', import.meta.url), 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'shop' })
  const compiled = compileTemplate({
    source: descriptor.template.content, filename: 'index.vue', id: 'shop',
    compilerOptions: { bindingMetadata: script.bindings }
  })
  assert.deepEqual(compiled.errors, [])
  assert.doesNotMatch(source, /v-html/)
  assert.match(source, /checkPermi\(\['operations:shopPull:edit'\]\)/)
})

test('pull state: removed from Lingxing wins over the manual switch', () => {
  assert.deepEqual(pullState({ lingxingPresent: 1, pullEnabled: 1 }), { label: '拉取中', type: 'success' })
  assert.deepEqual(pullState({ lingxingPresent: 1, pullEnabled: 0 }), { label: '已停止拉取', type: 'danger' })
  assert.equal(pullState({ lingxingPresent: 0, pullEnabled: 1 }).label, '领星已移除')
})

test('default stop date is the first day of the current month', () => {
  assert.equal(firstDayOfMonth(new Date(2026, 10, 5)), '2026-11-01')
  assert.equal(firstDayOfMonth(new Date(2026, 0, 31)), '2026-01-01')
})

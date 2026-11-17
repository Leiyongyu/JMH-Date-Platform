import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const filename = new URL('../src/views/operations/ebay/replenishmentV2/index.vue', import.meta.url)
const source = fs.readFileSync(filename, 'utf8')
const context = {}
vm.createContext(context)
for (const name of ['numberOrNull', 'formatNumber', 'formatQualityReturn']) {
  const functionSource = source.match(new RegExp('function ' + name + '\\([^]*?\\n\\}'))?.[0]
  assert.ok(functionSource, name)
  vm.runInContext(functionSource, context)
}

test('质量问题无值或为0显示--，有值显示整数数量/百分比', () => {
  for (const value of [null, undefined, '', 'invalid', 0, '0.000000']) {
    assert.equal(context.formatQualityReturn(value), '--')
    assert.equal(context.formatQualityReturn(value, true), '--')
  }
  assert.equal(context.formatQualityReturn('5.0000'), '5')
  assert.equal(context.formatQualityReturn('0.050000', true), '5.00%')
})

test('Vue脚本模板可编译；仅退货量弹窗扩展，保留其他悬浮内容', () => {
  const parsed = parse(source, { filename: filename.pathname })
  assert.deepEqual(parsed.errors, [])
  const script = compileScript(parsed.descriptor, { id: 'replenishment-v2' })
  const result = compileTemplate({
    source: parsed.descriptor.template.content, filename: filename.pathname,
    id: 'replenishment-v2', compilerOptions: { bindingMetadata: script.bindings }
  })
  assert.deepEqual(result.errors, [])
  assert.ok(source.includes('monthlyPopoverKey === \'returnQty\''))
  assert.ok(source.includes('metric[monthlyPopoverKey]'))
  assert.ok(source.includes('item.quality_return_summary?.quality_return_rate'))
  assert.ok(source.includes('metric.quality_return_rate'))
  assert.ok(source.includes('中间分类为“产品质量问题”'))
  assert.ok(source.includes('所有下级分类'))
})

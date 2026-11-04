import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import {
  EFFICIENCY_RULES, REVIEW_MECHANISM, TABS, formatValue, fromInput, toInput
} from '../src/views/finance/opsTarget/columns.js'

const page = new URL('../src/views/finance/opsTarget/index.vue', import.meta.url)

test('ops target page compiles, uses no v-html and gates editing by permission', () => {
  const source = fs.readFileSync(page, 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'ops' })
  const compiled = compileTemplate({
    source: descriptor.template.content, filename: 'index.vue', id: 'ops',
    compilerOptions: { bindingMetadata: script.bindings }
  })
  assert.deepEqual(compiled.errors, [])
  assert.doesNotMatch(source, /v-html/)
  assert.match(source, /checkPermi\(\['finance:opsTarget:edit'\]\)/)
})

test('editable columns match the backend whitelist (remark is not shown on the page)', () => {
  const repo = fs.readFileSync(new URL('../../Date-Project/backend/repositories/ops_target_repository.py', import.meta.url), 'utf8')
  const block = repo.slice(repo.indexOf('EDITABLE_FIELDS'), repo.indexOf('COLUMNS ='))
  const expected = new Set([...block.matchAll(/"([a-z_0-9]+)": "(money|rate|int)"/g)].map(m => m[1]))
  for (const q of [1, 2, 3, 4]) ['target', 'actual', 'efficiency_target'].forEach(s => expected.add(`q${q}_${s}`))
  for (let m = 1; m <= 12; m += 1) expected.add(`m${String(m).padStart(2, '0')}_target`)
  const editable = new Set(TABS.flatMap(tab => tab.columns).filter(c => !c.derived).map(c => c.key))
  assert.deepEqual([...editable].sort(), [...expected].sort())
})

test('the four tabs mirror the workbook sheets and the two explanation sheets are static content', () => {
  assert.deepEqual(TABS.map(tab => tab.label), ['公司年度目标汇总', '季度目标分解', '月度目标明细', '季度人效KPI'])
  assert.equal(REVIEW_MECHANISM.rows.length, 6)
  assert.equal(REVIEW_MECHANISM.list.length, 6)
  assert.equal(EFFICIENCY_RULES.rows.length, 4)
  assert.equal(EFFICIENCY_RULES.list.length, 5)
})

test('rates are edited as percent and stored as decimals; formatting', () => {
  assert.equal(toInput(0.15, 'rate'), 15)
  assert.equal(fromInput(15, 'rate'), 0.15)
  assert.equal(fromInput(12.5, 'rate'), 0.125)
  assert.equal(fromInput(null, 'money'), null)
  assert.equal(formatValue(0.695, 'rate'), '69.50%')
  assert.equal(formatValue(1507, 'money'), '1,507.00')
  assert.equal(formatValue(null, 'money'), '--')
  assert.equal(formatValue(13, 'int'), '13')
})

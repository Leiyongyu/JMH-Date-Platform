import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import {
  briefSchedule, parseAnswerBlocks, pendingMemories, verificationNotice
} from '../src/components/AiAssistant/agentRun.js'

const results = [
  { title: '10月销售', columns: [{ key: 'k', label: '组别' }], rows: [{ k: 'A' }], rowCount: 1 },
  { title: '环比', columns: [{ key: 'k', label: '组别' }], rows: [{ k: 'B' }], rowCount: 1 }
]

test('[[表:N]] references render backend result tables and unknown refs are dropped', () => {
  const blocks = parseAnswerBlocks('结论如下：\n[[表:2]]\n另见 [[表:1]] 和 [[表:9]]。\n来源：测试', results)
  assert.deepEqual(blocks.map(b => b.type), ['text', 'result', 'text', 'result', 'text'])
  assert.equal(blocks[1].result.title, '环比')
  assert.equal(blocks[3].result.title, '10月销售')
  assert.ok(!blocks.some(b => b.type === 'text' && b.content.includes('[[表:')))
  // 没有结果时引用直接去掉，不影响原有 Markdown 表格解析
  assert.deepEqual(parseAnswerBlocks('看 [[表:1]]').map(b => b.type), ['text'])
})

test('verification notice only appears for unmatched numbers', () => {
  assert.equal(verificationNotice(null), '')
  assert.equal(verificationNotice({ status: 'passed', unmatched: [] }), '')
  assert.match(verificationNotice({ status: 'warned', unmatched: ['4.7%', '12,000'] }), /4\.7%、12,000/)
})

test('pending memories and brief schedule text', () => {
  assert.deepEqual(pendingMemories({ memories: [{ id: 1, status: 'active' }, { id: 2, status: 'pending' }] }).map(m => m.id), [2])
  assert.deepEqual(pendingMemories(null), [])
  assert.equal(briefSchedule({ frequency: 'daily', runHour: 9 }), '每天 09:00')
  assert.equal(briefSchedule({ frequency: 'weekly', weekday: 1, runHour: 8 }), '每周一 08:00')
  assert.equal(briefSchedule({ frequency: 'monthly', monthDay: 3, runHour: 18 }), '每月3日 18:00')
})

for (const file of ['AnswerContent.vue', 'BriefPanel.vue', 'AgentStatsPanel.vue', 'index.vue']) {
  test(`${file} compiles without v-html`, () => {
    const source = fs.readFileSync(new URL(`../src/components/AiAssistant/${file}`, import.meta.url), 'utf8')
    const { descriptor, errors } = parse(source)
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: file })
    const compiled = compileTemplate({
      source: descriptor.template.content, filename: file, id: file,
      compilerOptions: { bindingMetadata: script.bindings }
    })
    assert.deepEqual(compiled.errors, [])
    assert.doesNotMatch(source, /v-html/)
  })
}

test('stats panel is admin only and feedback is wired', () => {
  const source = fs.readFileSync(new URL('../src/components/AiAssistant/index.vue', import.meta.url), 'utf8')
  assert.match(source, /<AgentStatsPanel v-if="isAdmin"/)
  assert.match(source, /sendAgentFeedback\(/)
  assert.match(source, /confirmAiMemory\(/)
})

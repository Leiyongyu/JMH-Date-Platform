import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import {
  callSummary, formatCell, parseAnswerBlocks, planProgress, pollAgentRun
} from '../src/components/AiAssistant/agentRun.js'

test('poll keeps reporting progress until the run finishes', async () => {
  const states = [
    { status: 'running', plan: [{ title: 'A', status: 'in_progress' }] },
    { status: 'running', plan: [{ title: 'A', status: 'completed' }] },
    { status: 'completed', answer: 'ok' }
  ]
  const seen = []
  const run = await pollAgentRun('r1', {
    fetchRun: async () => states.shift(), onUpdate: value => seen.push(value.status), sleep: async () => {}
  })
  assert.equal(run.answer, 'ok')
  assert.deepEqual(seen, ['running', 'running', 'completed'])
})

test('poll tolerates transient errors but gives up after repeated failures and on timeout', async () => {
  let calls = 0
  const run = await pollAgentRun('r1', {
    fetchRun: async () => { calls += 1; if (calls < 3) throw new Error('net'); return { status: 'failed', error: 'x' } },
    sleep: async () => {}
  })
  assert.equal(run.status, 'failed')
  await assert.rejects(pollAgentRun('r1', {
    fetchRun: async () => { throw new Error('down') }, sleep: async () => {}, maxErrors: 2
  }), /down/)
  let clock = 0
  await assert.rejects(pollAgentRun('r1', {
    fetchRun: async () => ({ status: 'running' }), sleep: async () => { clock += 1000 },
    now: () => clock, timeoutMs: 3000
  }), /超时/)
})

test('plan progress and call summary text', () => {
  assert.equal(planProgress([
    { title: '查9月', status: 'completed' }, { title: '查10月', status: 'in_progress' }, { title: '汇总', status: 'pending' }
  ]), '第2/3步：查10月')
  assert.equal(planProgress([{ title: 'a', status: 'completed' }]), '已完成1/1步')
  assert.equal(callSummary([{ status: 'completed' }, { status: 'denied' }]), '调用2次，1次未成功')
})

test('answer markdown tables become structured blocks rendered without v-html', () => {
  const blocks = parseAnswerBlocks('结论：**Alice** 最高\n\n| 负责人 | 毛利润 |\n|---|---:|\n| Alice | 1,200 |\n| <b>Bob</b> | 600 |\n\n来源：测试')
  assert.deepEqual(blocks.map(b => b.type), ['text', 'table', 'text'])
  assert.equal(blocks[0].content, '结论：Alice 最高')
  assert.deepEqual(blocks[1].headers, ['负责人', '毛利润'])
  assert.deepEqual(blocks[1].rows, [['Alice', '1,200'], ['<b>Bob</b>', '600']])
  const source = fs.readFileSync(new URL('../src/components/AiAssistant/index.vue', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /v-html/)
})

test('cell formatting', () => {
  assert.equal(formatCell(null), '--')
  assert.equal(formatCell(1234567), '1,234,567')
  assert.equal(formatCell(0.1235), '0.1235')
  assert.equal(formatCell('A-1'), 'A-1')
})

test('assistant component compiles and uses the agent run API', () => {
  const source = fs.readFileSync(new URL('../src/components/AiAssistant/index.vue', import.meta.url), 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'ai' })
  const compiled = compileTemplate({
    source: descriptor.template.content, filename: 'index.vue', id: 'ai',
    compilerOptions: { bindingMetadata: script.bindings }
  })
  assert.deepEqual(compiled.errors, [])
  assert.match(source, /startAgentRun\(/)
  assert.match(source, /pollAgentRun\(/)
  assert.doesNotMatch(source, /chatWithAiAssistant/)
})

test('live view shows only the tail of the latest thinking round', async () => {
  const { latestThinking } = await import('../src/components/AiAssistant/agentRun.js')
  assert.deepEqual(latestThinking([]), { round: 0, content: '' })
  const result = latestThinking([{ round: 1, content: 'a' }, { round: 2, content: 'x'.repeat(500) + '结尾' }], 10)
  assert.equal(result.round, 2)
  assert.equal(result.content, '…' + 'x'.repeat(8) + '结尾')
  const source = fs.readFileSync(new URL('../src/components/AiAssistant/index.vue', import.meta.url), 'utf8')
  assert.match(source, /思考过程/)
})

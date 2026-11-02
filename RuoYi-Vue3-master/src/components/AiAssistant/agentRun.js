// 数据助手前端逻辑：轮询后台任务、计划进度、把回答里的 Markdown 表格拆成结构化数据。
// 回答一律用文本插值渲染，不使用 v-html。

export const STEP_STATUS = {
  pending: '待执行',
  in_progress: '进行中',
  completed: '已完成',
  skipped: '已跳过'
}

export const CALL_STATUS = {
  completed: '成功',
  failed: '失败',
  denied: '无权限',
  invalid: '参数有误'
}

export const TOOL_TITLES = {
  list_report_months: '查询可用月份',
  performance_ranking: '查询绩效排名',
  owner_rule_summary: '查询负责人规则',
  sales_dashboard_report: '查询销售看板',
  monthly_inventory_summary: '查询月度库存',
  ebay_replenishment: '查询eBay补货'
}

const FINISHED = new Set(['completed', 'failed'])

/**
 * 轮询运行记录直到结束。每次拿到新状态都回调 onUpdate，便于展示计划与进度。
 * 连续失败 maxErrors 次或超过 timeoutMs 时抛错。
 */
export async function pollAgentRun(runId, {
  fetchRun, onUpdate = () => {}, sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
  intervalMs = 1500, timeoutMs = 300000, maxErrors = 5, now = () => Date.now(), isCancelled = () => false
}) {
  const deadline = now() + timeoutMs
  let errors = 0
  while (now() < deadline) {
    if (isCancelled()) return null
    try {
      const run = await fetchRun(runId)
      errors = 0
      onUpdate(run)
      if (FINISHED.has(run?.status)) return run
    } catch (error) {
      errors += 1
      if (errors >= maxErrors) throw error
    }
    await sleep(intervalMs)
  }
  throw new Error('数据助手执行超时，请稍后在对话记录中查看结果')
}

export function planProgress(plan = []) {
  if (!plan.length) return ''
  const done = plan.filter(step => step.status === 'completed' || step.status === 'skipped').length
  const current = plan.find(step => step.status === 'in_progress')
  return current ? `第${Math.min(done + 1, plan.length)}/${plan.length}步：${current.title}` : `已完成${done}/${plan.length}步`
}

export function callSummary(steps = []) {
  const failed = steps.filter(step => step.status !== 'completed').length
  return failed ? `调用${steps.length}次，${failed}次未成功` : `调用${steps.length}次`
}

function splitCells(line) {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return trimmed.split('|').map(cell => cell.trim().replace(/\*\*/g, ''))
}

const SEPARATOR = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/

/** 把回答拆成 text / table 块；表格块为 {headers, rows}。 */
export function parseAnswerBlocks(text = '') {
  const lines = String(text).replace(/\r\n/g, '\n').split('\n')
  const blocks = []
  let buffer = []
  const flushText = () => {
    const content = buffer.join('\n').replace(/\*\*/g, '').trim()
    if (content) blocks.push({ type: 'text', content })
    buffer = []
  }
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    if (line.trim().startsWith('|') && i + 1 < lines.length && SEPARATOR.test(lines[i + 1])) {
      flushText()
      const headers = splitCells(line)
      const rows = []
      i += 2
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        const cells = splitCells(lines[i])
        rows.push(headers.map((_header, index) => cells[index] ?? ''))
        i += 1
      }
      i -= 1
      blocks.push({ type: 'table', headers, rows })
    } else {
      buffer.push(line)
    }
  }
  flushText()
  return blocks
}

export function formatCell(value) {
  if (value === null || value === undefined || value === '') return '--'
  if (typeof value === 'number') {
    return Number.isInteger(value) ? value.toLocaleString('zh-CN')
      : value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
  }
  return String(value)
}

/** 执行中只展示最新一轮思考的结尾部分，避免长文本把进度挤出视野。 */
export function latestThinking(thinking = [], maxChars = 400) {
  const last = thinking[thinking.length - 1]
  if (!last) return { round: 0, content: '' }
  const content = String(last.content || '')
  return { round: last.round, content: content.length > maxChars ? `…${content.slice(-maxChars)}` : content }
}

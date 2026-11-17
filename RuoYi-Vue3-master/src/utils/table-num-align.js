/**
 * 表格数字列自动右对齐
 * ------------------------------------------------------------
 * 给 el-table 里的「数字列」打上 .is-num（样式见 styles/ui.scss）：
 * 先按列统计数字单元格占比，占比 ≥ 60% 判定为数字列，
 * 再把整列（含表头）一起右对齐，避免同列有的靠左有的靠右。
 *
 * - 列上显式写了 align 时，Element Plus 会输出内联 text-align，
 *   优先级高于 .is-num，因此不会破坏页面已有的对齐配置。
 * - 只做读取 + 加 class，不改变任何数据与结构。
 */

// 1,280 / 36.4 / ¥4,186.58 / -0.5% / 12.1 / 0
const NUM_RE = /^[¥￥$€]?\s?[-+]?\d[\d,]*(?:\.\d+)?\s?%?$/

const seen = new WeakSet()

/** 标记单张表的数字列，并同步表头 */
function markTable(table) {
  const body = table.querySelector('.el-table__body')
  if (!body) return

  const rows = body.querySelectorAll('tbody > tr')
  if (!rows.length) return

  const stat = [] // 每列数字占比统计
  const colCells = [] // 每列的单元格容器

  for (const tr of rows) {
    const cells = tr.children
    for (let i = 0; i < cells.length; i++) {
      const cell = cells[i].querySelector('.cell')
      if (!cell) continue
      ;(colCells[i] || (colCells[i] = [])).push(cell)

      const txt = cell.textContent.trim()
      if (!txt) continue
      const s = stat[i] || (stat[i] = { num: 0, all: 0 })
      s.all++
      if (NUM_RE.test(txt)) s.num++
    }
  }

  const numCol = stat.map(s => !!s && s.all > 0 && s.num / s.all >= 0.6)

  colCells.forEach((cells, i) => {
    cells.forEach(cell => cell.classList.toggle('is-num', !!numCol[i]))
  })

  const head = table.querySelector('.el-table__header')
  if (!head) return
  for (const tr of head.querySelectorAll('thead > tr')) {
    const cells = tr.children
    for (let i = 0; i < cells.length; i++) {
      const cell = cells[i].querySelector('.cell')
      if (!cell) continue
      cell.classList.toggle('is-num', !!numCol[i])
    }
  }
}

/** 单表监听：数据刷新 / 翻页 / 排序后重新标记 */
function observeTable(table) {
  markTable(table)
  const target = table.querySelector('.el-table__body-wrapper') || table
  let timer = null
  const observer = new MutationObserver(() => {
    clearTimeout(timer)
    timer = setTimeout(() => markTable(table), 60)
  })
  observer.observe(target, { childList: true, subtree: true })
}

let scanTimer = null
let bodyObserver = null

function scanTables() {
  document.querySelectorAll('.el-table').forEach(table => {
    if (seen.has(table)) return
    seen.add(table)
    observeTable(table)
  })
}

function scheduleScan() {
  clearTimeout(scanTimer)
  scanTimer = setTimeout(scanTables, 200)
}

/** 启动（main.js 调用一次） */
export function setupTableNumAlign() {
  if (bodyObserver) return
  scanTables()
  bodyObserver = new MutationObserver(scheduleScan)
  bodyObserver.observe(document.body, { childList: true, subtree: true })
}

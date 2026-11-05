// 店铺管理：拉取状态的展示规则（与后端口径一致：领星已移除优先于人工开关）。

export function pullState(row) {
  if (row.lingxingPresent === 0) return { label: '领星已移除', type: 'info' }
  if (row.pullEnabled === 0) return { label: '已停止拉取', type: 'danger' }
  return { label: '拉取中', type: 'success' }
}

export function firstDayOfMonth(date) {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  return `${date.getFullYear()}-${month}-01`
}

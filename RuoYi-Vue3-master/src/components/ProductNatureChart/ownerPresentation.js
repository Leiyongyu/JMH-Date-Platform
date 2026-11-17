import { ALL_NATURE_KEYS } from './presentation.js'

export function ownerDetailRows(data, point, segment) {
  const fail = message => { throw Object.assign(new Error(message), { ownerDetailMessage: message }) }
  if (!data || data.state !== 'READY') fail(data?.message || '该月份没有可用的负责人明细')
  if (data.batch_id !== point.batch_id || data.rule_version !== point.rule_version || data.stat_month !== point.stat_month || data.segment_key !== segment) {
    fail('报表快照已变化，请关闭弹窗并刷新图表后重试')
  }
  const keys = ALL_NATURE_KEYS
  if (!Array.isArray(data.items) || !data.reconciled || !data.totals || data.totals.sku_count !== point.sku_count ||
      keys.some(key => data.totals.counts?.[key] !== point.counts?.[key])) fail('负责人明细与图表数量不一致，请刷新后重试')
  if (data.items.reduce((n, row) => n + row.sku_count, 0) !== data.totals.sku_count ||
      keys.some(key => data.items.reduce((n, row) => n + row.counts?.[key], 0) !== data.totals.counts[key])) fail('负责人合计校验失败，请刷新后重试')
  return [...data.items, { ...data.totals, owner_key: '__total__', principal_name: '合计', isTotal: true }]
}

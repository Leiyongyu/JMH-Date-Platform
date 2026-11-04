// 运营目标与人效：各页签的列定义与说明内容（说明页对应原 Excel 最后两个工作表，只展示不入库）。
// type：money 万元金额 / rate 小数比例（显示为百分比）/ int 整数 / eff 万元每人；derived=true 为后端计算列，不可编辑。

const money = (key, label, extra = {}) => ({ key, label, type: 'money', ...extra })
const quarters = [1, 2, 3, 4]

export const TABS = [
  {
    name: 'annual',
    label: '公司年度目标汇总',
    columns: [
      money('floor_target', '年度保底目标(万元)'),
      money('sprint_target', '年度冲刺目标(万元)'),
      money('actual_amount', '年度实际(万元)-含退款'),
      { key: 'achievement_rate', label: '累计目标达成率', type: 'rate', derived: true, help: '年度实际 ÷ 年度冲刺目标' },
      { key: 'new_product_target', label: '新品数目标', type: 'int' },
      { key: 'new_product_actual', label: '新品实际上新', type: 'int' },
      { key: 'target_margin_rate', label: '月均目标毛利率', type: 'rate', help: '合计行为各部门简单平均' },
      money('est_gross_profit', '全年预估毛利润(万元)'),
      money('labor_cost_pack', '人力成本包(万元)')
    ]
  },
  {
    name: 'quarter',
    label: '季度目标分解',
    columns: [
      ...quarters.flatMap(q => [
        money(`q${q}_target`, `Q${q}目标(万元)`),
        money(`q${q}_actual`, `Q${q}实际(万元)`),
        { key: `q${q}_achievement_rate`, label: `Q${q}达成率`, type: 'rate', derived: true, help: `Q${q}实际 ÷ Q${q}目标` }
      ]),
      money('quarter_target_total', '全年目标(万元)', { derived: true, help: 'Q1~Q4 目标之和' })
    ]
  },
  {
    name: 'month',
    label: '月度目标明细',
    columns: [
      ...Array.from({ length: 12 }, (_, i) => money(`m${String(i + 1).padStart(2, '0')}_target`, `${i + 1}月`)),
      money('month_target_total', '合计', { derived: true, help: '1~12 月目标之和' })
    ]
  },
  {
    name: 'efficiency',
    label: '季度人效KPI',
    columns: [
      ...quarters.map(q => ({ key: `q${q}_efficiency_target`, label: `Q${q}人效目标(万元/人)`, type: 'eff' })),
      { key: 'annual_efficiency_target', label: '年度人效目标', type: 'eff' },
      { key: 'headcount', label: '当前编制', type: 'int' },
      money('labor_cost_pack', '人力成本包(万元)'),
      ...quarters.map(q => ({
        key: `q${q}_actual_efficiency`, label: `Q${q}实际人效`, type: 'eff', derived: true,
        help: `Q${q}实际 ÷ 当前编制；低于 20 万/人红色预警`
      })),
      { key: 'labor_cost_rate', label: '人力成本率', type: 'rate', derived: true, help: '人力成本包 ÷ 年度实际；>10% 黄色、>12% 红色' },
      { key: 'gross_profit_per_head', label: '人均毛利贡献(万元/人)', type: 'eff', derived: true, help: '全年预估毛利润 ÷ 当前编制；<50 万/人黄色' }
    ]
  }
]

/** 合计行里取平均值的列（其他金额、个数列为求和）。 */
export const AVERAGE_KEYS = new Set([
  'target_margin_rate', 'annual_efficiency_target', ...quarters.map(q => `q${q}_efficiency_target`)
])

export const REVIEW_MECHANISM = {
  title: '汽配运营26年季度复盘机制',
  headers: ['复盘维度', 'Q1重点', 'Q2重点', 'Q3重点', 'Q4重点', '复盘频率'],
  rows: [
    ['销售目标达成', '完成率分析、差距原因', '调整策略、资源优化', '冲刺策略、风险预警', '全年总结、次年规划', '月度+季度'],
    ['毛利率达成', '成本结构分析、定价优化', '供应链优化、库存周转', '促销策略、清货计划', '年度毛利复盘', '月度+季度'],
    ['人效达成', '编制合理性、人员能力', '人效提升、培训计划', '绩效优化、激励机制', '年度人效评估', '季度'],
    ['新品开发', '上新数量、质量评估', '产品线优化、爆款打造', '季节性产品、库存控制', '次年产品规划', '月度+季度'],
    ['库存管理', '库存周转、滞销清理', '安全库存、补货策略', '旺季备货、库存优化', '年度库存复盘', '周度+月度'],
    ['人力成本', '编制执行、成本管控', '人效提升、成本优化', '绩效挂钩、成本预警', '年度成本复盘', '月度+季度']
  ],
  listTitle: '复盘流程',
  list: [
    '数据收集：每月5日前收集上月经营数据',
    '数据分析：对比目标vs实际，分析差异原因',
    '问题识别：识别人效、毛利、库存等关键问题',
    '改进措施：制定下月/下季度改进计划',
    '资源调配：根据人效情况调整编制和人力成本包',
    '跟踪执行：月度跟踪改进措施执行情况'
  ]
}

export const EFFICIENCY_RULES = {
  title: '人力成本包管控规则',
  headers: ['管控指标', '计算方式', '预警阈值', '调整机制'],
  rows: [
    ['人效(万元/人)', '季度销售额/季度平均人数', '<20万/人：红色预警', '连续2季度<20万：减编或调岗'],
    ['人力成本率', '人力成本/销售额', '>10%：黄色预警；>12%：红色预警', '超预算部分从下季度预算扣除'],
    ['人均毛利贡献', '毛利额/人数', '<50万/人：黄色预警', '优化人员结构或提升销售'],
    ['编制执行率', '实际人数/编制人数', '>110%：红色预警；<80%：黄色预警', '超编需特批，缺编需说明']
  ],
  listTitle: '人力成本包使用原则',
  list: [
    '年度人力成本包按季度分解，每季度初锁定',
    '季度内人效达标可保留结余，可用于季度末激励',
    '季度人效不达标，结余部分回收，缺口部分从下季度扣除',
    '特殊情况(如新品孵化期)可申请临时增编，需总经理审批',
    '每季度末进行人效复盘，调整下季度编制和成本包'
  ]
}

export function formatValue(value, type) {
  if (value === null || value === undefined || value === '') return '--'
  const number = Number(value)
  if (Number.isNaN(number)) return String(value)
  if (type === 'rate') return `${(number * 100).toFixed(2)}%`
  if (type === 'int') return number.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
  return number.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 编辑框里比例按百分数输入（15 表示 15%），保存时换回小数。 */
export function toInput(value, type) {
  if (value === null || value === undefined) return null
  return type === 'rate' ? Math.round(Number(value) * 100 * 10000) / 10000 : Number(value)
}

export function fromInput(value, type) {
  if (value === null || value === undefined || value === '') return null
  return type === 'rate' ? Math.round(Number(value) * 100) / 10000 : Number(value)
}

<template>
  <el-dialog v-model="visible" title="数据助手运行看板" width="760px" append-to-body @open="load">
    <div class="stats-toolbar">
      <el-radio-group v-model="days" size="small" @change="load">
        <el-radio-button :value="7">近7天</el-radio-button>
        <el-radio-button :value="30">近30天</el-radio-button>
        <el-radio-button :value="90">近90天</el-radio-button>
      </el-radio-group>
    </div>
    <div v-loading="loading">
      <div class="stats-cards">
        <div v-for="card in cards" :key="card.label" class="stats-card">
          <span>{{ card.label }}</span><strong>{{ card.value }}</strong>
        </div>
      </div>
      <div class="stats-section">工具调用</div>
      <el-table :data="stats.tools || []" size="small" border empty-text="暂无调用">
        <el-table-column label="工具" min-width="120">
          <template #default="{ row }">{{ TOOL_TITLES[row.tool] || row.tool }}</template>
        </el-table-column>
        <el-table-column prop="calls" label="次数" width="70" />
        <el-table-column label="成功率" width="80">
          <template #default="{ row }">{{ percent(row.completed, row.calls) }}</template>
        </el-table-column>
        <el-table-column prop="failed" label="失败" width="60" />
        <el-table-column prop="denied" label="无权限" width="70" />
        <el-table-column prop="invalid" label="参数有误" width="80" />
        <el-table-column label="平均耗时" width="90">
          <template #default="{ row }">{{ row.avgDurationMs }}ms</template>
        </el-table-column>
      </el-table>
      <div class="stats-section">最近被点「没帮助」的提问</div>
      <el-table :data="stats.downVoted || []" size="small" border max-height="260" empty-text="暂无">
        <el-table-column prop="username" label="用户" width="90" />
        <el-table-column prop="question" label="提问" min-width="160" show-overflow-tooltip />
        <el-table-column prop="comment" label="意见" min-width="140" show-overflow-tooltip />
        <el-table-column prop="answer" label="回答摘录" min-width="160" show-overflow-tooltip />
      </el-table>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getAgentStats } from '@/api/system/aiAssistant'
import { TOOL_TITLES } from './agentRun'

const visible = defineModel({ type: Boolean, default: false })
const days = ref(30)
const stats = ref({})
const loading = ref(false)

function percent(part, total) {
  return total ? `${((part / total) * 100).toFixed(1)}%` : '--'
}

const cards = computed(() => {
  const s = stats.value
  return [
    { label: '提问次数', value: s.runs ?? '--' },
    { label: '使用人数', value: s.users ?? '--' },
    { label: '成功率', value: percent(s.completed, s.runs) },
    { label: '平均耗时', value: s.avgDurationMs ? `${(s.avgDurationMs / 1000).toFixed(1)}秒` : '--' },
    { label: '数字核对未通过', value: s.verificationWarned ?? '--' },
    { label: '自动修正', value: s.verificationRepaired ?? '--' },
    { label: '有帮助 / 没帮助', value: `${s.feedbackUp ?? 0} / ${s.feedbackDown ?? 0}` },
    { label: 'Token（输入/输出）', value: `${(s.promptTokens ?? 0).toLocaleString('zh-CN')} / ${(s.completionTokens ?? 0).toLocaleString('zh-CN')}` }
  ]
})

async function load() {
  loading.value = true
  try {
    const response = await getAgentStats(days.value, `erp-ai-stats-${Date.now()}`)
    stats.value = response.data || {}
  } catch (error) {
    ElMessage.error(error?.msg || error?.message || '加载运行看板失败')
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss" scoped>
.stats-toolbar { margin-bottom: 12px; }
.stats-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.stats-card {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;

  span { color: var(--el-text-color-secondary, #909399); font-size: 12px; }
  strong { font-size: 16px; }
}
.stats-section { margin: 16px 0 8px; font-weight: 600; font-size: 13px; }
</style>

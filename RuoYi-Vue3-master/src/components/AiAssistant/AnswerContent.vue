<template>
  <template v-for="(block, index) in blocks" :key="index">
    <div v-if="block.type === 'text'" class="answer-text">{{ block.content }}</div>
    <div v-else-if="block.type === 'table'" class="answer-table-wrap">
      <table class="answer-table">
        <thead><tr><th v-for="header in block.headers" :key="header">{{ header }}</th></tr></thead>
        <tbody><tr v-for="(row, rowIndex) in block.rows" :key="rowIndex"><td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td></tr></tbody>
      </table>
    </div>
    <div v-else class="answer-result">
      <div class="answer-result-title">
        {{ block.result.title }}<small>（{{ block.result.rowCount }}行{{ block.result.rowCount > block.result.rows.length ? `，显示前${block.result.rows.length}行` : '' }}）</small>
      </div>
      <el-table :data="block.result.rows.slice(0, 200)" size="small" max-height="320" border>
        <el-table-column v-for="column in block.result.columns" :key="column.key" :prop="column.key" :label="column.label" min-width="96" show-overflow-tooltip>
          <template #default="{ row }">{{ formatCell(row[column.key]) }}</template>
        </el-table-column>
      </el-table>
      <div class="answer-result-meta">来源：{{ block.result.source || '--' }} ｜ 统计区间：{{ block.result.period || '--' }}</div>
    </div>
  </template>
</template>

<script setup>
import { computed } from 'vue'
import { formatCell, parseAnswerBlocks } from './agentRun'

const props = defineProps({
  content: { type: String, default: '' },
  results: { type: Array, default: () => [] }
})

// 回答和表格一律用文本插值渲染，不把模型输出当作 HTML 插入。
const blocks = computed(() => parseAnswerBlocks(props.content, props.results))
</script>

<style lang="scss" scoped>
.answer-text { white-space: pre-wrap; }
.answer-table-wrap { margin: 8px 0; overflow-x: auto; }
.answer-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
  line-height: 1.5;

  th, td {
    padding: 5px 8px;
    border: 1px solid var(--el-border-color-lighter, #ebeef5);
    text-align: left;
    white-space: nowrap;
  }

  th { background: var(--el-fill-color-light, #f5f7fa); font-weight: 600; }
}
.answer-result { margin: 8px 0; }
.answer-result-title {
  margin-bottom: 4px;
  font-size: 12.5px;
  font-weight: 600;

  small { color: var(--el-text-color-secondary, #909399); font-weight: 400; }
}
.answer-result-meta { margin-top: 4px; color: var(--el-text-color-secondary, #909399); font-size: 11.5px; }
</style>

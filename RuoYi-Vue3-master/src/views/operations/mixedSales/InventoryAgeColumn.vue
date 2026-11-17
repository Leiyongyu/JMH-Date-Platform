<template>
  <el-table-column prop="inventoryAge" label="库龄" min-width="140" align="right">
    <template #header>
      <el-tooltip :content="tip" placement="top"><span>库龄</span></el-tooltip>
    </template>
    <template #default="{ row }">
      <el-tooltip v-if="row.inventoryAge" :content="sourceTip(row)" placement="top">
        <span>{{ row.inventoryAge }}<el-tag v-if="row.inventoryAgeShared" size="small" type="info" style="margin-left: 4px">含共享仓</el-tag></span>
      </el-tooltip>
      <span v-else>--</span>
    </template>
  </el-table-column>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ platform: { type: String, required: true } })
const tip = computed(() => props.platform === 'amz'
  ? '按SKU和当前店铺取最高库龄区间。优先按SID归属；SID缺失时按所属店铺完整名称匹配。共享仓记录会标注，区间不是精确天数。'
  : '取谷仓最新库龄快照中仍有库存的最大库龄天数；主表按SKU，明细按SKU和站点。')
function sourceTip(row) {
  return [row.inventoryAgeShared && '包含该店铺关联的共享仓库龄，不代表独立国家库存库龄',
    row.inventoryAgeNameMatched && '包含按所属店铺完整名称匹配的记录',
    row.inventoryAgeSourceMonth && `来源月份：${row.inventoryAgeSourceMonth}`,
    row.inventoryAgeUpdatedAt && `同步时间：${row.inventoryAgeUpdatedAt}`].filter(Boolean).join('；') || tip.value
}
</script>

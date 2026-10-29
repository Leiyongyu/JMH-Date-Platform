<template>
  <el-dialog v-model="visible" title="批量修改提交时间" width="min(1280px, 96vw)" append-to-body>
    <el-alert title="先查询可选送达时间，当前阶段不提交修改。填写STA任务编号、货件单号和SID，可逐行添加多个货件。" type="info" :closable="false" show-icon />
    <div class="query-tools">
      <el-button icon="Plus" :disabled="busy || rows.length >= 20" @click="rows.push(deliveryRow())">新增货件</el-button>
      <el-button type="primary" icon="Search" :loading="busy" @click="queryRows">{{ busy ? '正在查询' : '查询' }}</el-button>
      <span>最多20条；已完成 {{ completed }} / {{ rows.length }}</span>
    </div>
    <el-table :data="rows" border max-height="340">
      <el-table-column type="index" label="序号" width="60" />
      <el-table-column label="STA任务编号（inboundPlanId）" min-width="340"><template #default="{ row }">
        <el-input v-model="row.inboundPlanId" :disabled="busy" maxlength="128" placeholder="填写STA任务编号" @input="clearDeliveryResult(row)" />
      </template></el-table-column>
      <el-table-column label="货件单号" min-width="230"><template #default="{ row }">
        <el-input v-model="row.shipmentNo" :disabled="busy" maxlength="128" placeholder="FBA货件单号 / 接口shipmentId" @input="clearDeliveryResult(row)" />
      </template></el-table-column>
      <el-table-column label="店铺SID" min-width="130"><template #default="{ row }">
        <el-input v-model="row.sid" :disabled="busy" maxlength="19" placeholder="例如12616" @input="clearDeliveryResult(row)" />
      </template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="{ row }">
        <el-tag :type="row.status === 'SUCCESS' ? 'success' : row.status === 'ERROR' ? 'danger' : 'info'">{{ statusLabel(row.status) }}</el-tag>
      </template></el-table-column>
      <el-table-column label="操作" width="70"><template #default="{ $index }">
        <el-button link type="danger" :disabled="busy || rows.length === 1" @click="rows.splice($index, 1)">删除</el-button>
      </template></el-table-column>
    </el-table>
    <el-empty v-if="!completed && !busy" description="填写货件信息并点击查询，结果将在下方按货件展示" :image-size="64" />
    <section v-for="row in results" :key="row.id" class="delivery-result">
      <header><strong>{{ row.shipmentNo }} · SID {{ row.sid }}</strong><el-tag :type="row.status === 'SUCCESS' ? 'success' : 'danger'">{{ row.status === 'SUCCESS' ? `${row.result.optionCount}个可选时间` : '查询失败' }}</el-tag></header>
      <p class="context">STA：{{ row.inboundPlanId }}<template v-if="row.result">；查询时间：{{ row.result.queriedAt }}<br>接口shipmentId：{{ row.result.shipmentId }}</template></p>
      <el-alert v-if="row.error" :title="row.error" type="error" :closable="false" show-icon />
      <el-table v-if="row.status === 'SUCCESS'" :data="row.result.options" border max-height="380" empty-text="领星返回成功，但当前没有可选送达时间">
        <el-table-column prop="deliveryWindowOptionId" label="送达时间ID（deliveryWindowOptionId）" min-width="360" show-overflow-tooltip />
        <el-table-column prop="startDate" label="开始时间" min-width="170" />
        <el-table-column prop="endDate" label="结束时间" min-width="170" />
        <el-table-column prop="validUntil" label="过期时间" min-width="170" />
      </el-table>
      <el-collapse v-if="row.result?.response" class="raw-response"><el-collapse-item title="查看领星原始响应" name="response"><pre>{{ JSON.stringify(row.result.response, null, 2) }}</pre></el-collapse-item></el-collapse>
    </section>
    <template #footer><el-button @click="visible = false">关闭</el-button></template>
  </el-dialog>
</template>
<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { queryStaDeliveryDates } from '@/api/operations/customs/shipmentFee'
import { clearDeliveryResult, deliveryRow, queryDeliveryRows } from './deliveryDates'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue'])
const visible = computed({ get: () => props.modelValue, set: value => emit('update:modelValue', value) })
const rows = ref([deliveryRow()])
const busy = ref(false)
let run = 0
const results = computed(() => rows.value.filter(row => ['SUCCESS', 'ERROR'].includes(row.status)))
const completed = computed(() => results.value.length)
const statusLabel = status => ({ PENDING: '待查询', QUERYING: '查询中', SUCCESS: '成功', ERROR: '失败' })[status]

async function queryRows() {
  if (busy.value) return
  const current = ++run
  busy.value = true
  rows.value.forEach(clearDeliveryResult)
  try {
    await queryDeliveryRows(rows.value, async request => (await queryStaDeliveryDates(request)).data,
      () => current === run && props.modelValue)
  } finally {
    if (current === run) busy.value = false
  }
}

watch(() => props.modelValue, value => {
  if (!value) {
    run++
    busy.value = false
    rows.value.filter(row => row.status === 'QUERYING').forEach(clearDeliveryResult)
  }
})
onBeforeUnmount(() => { run++ })
</script>
<style scoped>
.query-tools { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 16px 0; }
.query-tools > span, .context { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.8; }
.delivery-result { margin-top: 20px; padding: 16px; border: 1px solid var(--el-border-color-light); border-radius: 8px; }
.delivery-result header { display: flex; gap: 12px; align-items: center; justify-content: space-between; flex-wrap: wrap; }
.context { overflow-wrap: anywhere; margin: 8px 0 12px; }
.raw-response { margin-top: 12px; }
pre { max-height: 280px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; }
</style>

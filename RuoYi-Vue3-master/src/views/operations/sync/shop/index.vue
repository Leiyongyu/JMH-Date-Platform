<template>
  <div class="app-container">
    <el-alert class="shop-tip" type="info" :closable="false" show-icon>
      <template #title>
        停止拉取后，所有向领星拉数据的定时任务都会跳过该店铺，已入库的历史数据不受影响；按月拉取的任务（绩效、AMZ利润报表、月度库存）
        对开始于「生效日期」之前的月份仍会拉取，重跑历史月份不会丢数据。领星已不再返回的店铺由每日店铺同步自动标记为「领星已移除」并停止拉取。
      </template>
    </el-alert>

    <el-form :model="queryParams" :inline="true">
      <el-form-item label="平台">
        <el-select v-model="queryParams.platformCode" clearable style="width: 120px" @change="handleQuery">
          <el-option label="Amazon" value="10001" />
          <el-option label="eBay" value="10003" />
        </el-select>
      </el-form-item>
      <el-form-item label="店铺">
        <el-input v-model="queryParams.keyword" placeholder="店铺名称或 sid" clearable style="width: 200px" @keyup.enter="handleQuery" @clear="handleQuery" />
      </el-form-item>
      <el-form-item label="拉取">
        <el-select v-model="queryParams.pullEnabled" clearable style="width: 120px" @change="handleQuery">
          <el-option label="拉取中" :value="1" />
          <el-option label="已停止" :value="0" />
        </el-select>
      </el-form-item>
      <el-form-item label="领星状态">
        <el-select v-model="queryParams.lingxingPresent" clearable style="width: 130px" @change="handleQuery">
          <el-option label="领星存在" :value="1" />
          <el-option label="领星已移除" :value="0" />
        </el-select>
      </el-form-item>
      <el-form-item><el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button></el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="list" border stripe>
      <el-table-column label="平台" width="80"><template #default="{ row }">{{ PLATFORM[row.platformCode] || row.platformCode }}</template></el-table-column>
      <el-table-column label="店铺名称" prop="storeName" min-width="170" show-overflow-tooltip />
      <el-table-column label="sid" prop="sid" width="90" />
      <el-table-column label="国家" prop="countryCode" width="70" />
      <el-table-column label="是否拉取" width="130">
        <template #default="{ row }">
          <el-tag :type="pullState(row).type">{{ pullState(row).label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="停止原因" prop="pullStopReason" min-width="200" show-overflow-tooltip />
      <el-table-column label="生效日期" prop="pullStopDate" width="110" />
      <el-table-column label="领星最近出现" width="160"><template #default="{ row }">{{ row.lingxingLastSeenAt || '--' }}</template></el-table-column>
      <el-table-column label="修改人" width="140">
        <template #default="{ row }">{{ row.pullUpdatedBy ? `${row.pullUpdatedBy} ${row.pullUpdatedAt || ''}` : '--' }}</template>
      </el-table-column>
      <el-table-column v-if="canEdit" label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.pullEnabled === 1" link type="danger" @click="openStop(row)">停止拉取</el-button>
          <el-button v-else link type="primary" @click="resume(row)">恢复拉取</el-button>
        </template>
      </el-table-column>
    </el-table>
    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />

    <el-dialog v-model="stopVisible" title="停止拉取" width="460px" append-to-body>
      <el-form ref="stopRef" :model="stopForm" :rules="stopRules" label-width="80px">
        <el-form-item label="店铺">{{ stopForm.storeName }}（sid {{ stopForm.sid }}）</el-form-item>
        <el-form-item label="原因" prop="pullStopReason">
          <el-select v-model="stopForm.pullStopReason" filterable allow-create default-first-option style="width: 100%" placeholder="选择或输入原因">
            <el-option v-for="reason in REASONS" :key="reason" :label="reason" :value="reason" />
          </el-select>
        </el-form-item>
        <el-form-item label="生效日期" prop="pullStopDate">
          <el-date-picker v-model="stopForm.pullStopDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          <div class="form-help">按月拉取的任务：开始于这一天之前的月份仍会拉取。默认本月 1 日，即从本月起不再拉取。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="stopVisible = false">取消</el-button>
        <el-button type="danger" :loading="saving" @click="submitStop">确认停止</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="ShopPull">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listSyncShop, updateShopPull } from '@/api/operations/syncShop'
import { checkPermi } from '@/utils/permission'
import { pullState, firstDayOfMonth } from './shopPull'

const PLATFORM = { 10001: 'Amazon', 10003: 'eBay' }
const REASONS = ['封店，领星数据停止同步', '停店，领星数据停止同步', '国内主体已注销', '国内主体申请注销', '店铺暂停运营']

const list = ref([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const stopVisible = ref(false)
const stopRef = ref()
const canEdit = computed(() => checkPermi(['operations:shopPull:edit']))
const queryParams = reactive({ pageNum: 1, pageSize: 50, platformCode: '10001', keyword: '', pullEnabled: undefined, lingxingPresent: undefined })
const stopForm = reactive({ id: null, storeName: '', sid: '', pullStopReason: '', pullStopDate: '' })
const stopRules = {
  pullStopReason: [{ required: true, message: '请填写停止原因', trigger: 'change' }],
  pullStopDate: [{ required: true, message: '请选择生效日期', trigger: 'change' }]
}

async function getList() {
  loading.value = true
  try {
    const response = await listSyncShop(queryParams)
    list.value = response.rows || []
    total.value = response.total || 0
  } finally {
    loading.value = false
  }
}

function handleQuery() {
  queryParams.pageNum = 1
  getList()
}

function openStop(row) {
  Object.assign(stopForm, { id: row.id, storeName: row.storeName, sid: row.sid, pullStopReason: '', pullStopDate: firstDayOfMonth(new Date()) })
  stopVisible.value = true
}

async function submitStop() {
  if (!(await stopRef.value.validate().catch(() => false))) return
  saving.value = true
  try {
    await updateShopPull(stopForm.id, { pullEnabled: 0, pullStopReason: stopForm.pullStopReason, pullStopDate: stopForm.pullStopDate })
    ElMessage.success('已停止拉取')
    stopVisible.value = false
    await getList()
  } finally {
    saving.value = false
  }
}

async function resume(row) {
  try {
    await ElMessageBox.confirm(`恢复后，下次定时任务会重新拉取「${row.storeName}」的数据，确定恢复吗？`, '恢复拉取', { type: 'warning' })
  } catch {
    return
  }
  await updateShopPull(row.id, { pullEnabled: 1 })
  ElMessage.success('已恢复拉取')
  await getList()
}

onMounted(getList)
</script>

<style scoped>
.shop-tip { margin-bottom: 12px; }
.form-help { margin-top: 4px; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.5; }
</style>

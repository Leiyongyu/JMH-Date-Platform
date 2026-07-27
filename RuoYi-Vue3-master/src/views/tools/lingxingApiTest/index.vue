<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>领星查询接口测试</span>
          <el-tag type="success">只读接口</el-tag>
        </div>
      </template>

      <el-alert
        title="填写领星 API Path 与请求 JSON，调用成功后后端会把完整原始响应保存为 TXT。写入、更新、提交和删除类路径会被拒绝。"
        type="info"
        :closable="false"
        show-icon
        class="mb16"
      />

      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="测试名称" prop="testName">
          <el-input v-model="form.testName" placeholder="例如 shipment-detail" />
        </el-form-item>
        <el-form-item label="文件标识" prop="identifier">
          <el-input v-model="form.identifier" placeholder="例如 SP260715005" />
        </el-form-item>
        <el-form-item label="API Path" prop="path">
          <el-input
            v-model="form.path"
            placeholder="erp/sc/routing/storage/shipment/getInboundShipmentListMwsDetail"
          />
        </el-form-item>
        <el-form-item label="请求 JSON" prop="bodyText">
          <el-input
            v-model="form.bodyText"
            type="textarea"
            :rows="9"
            spellcheck="false"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleQuery">
            拉取并生成 TXT
          </el-button>
          <el-button @click="resetShipmentDetail">恢复本次示例</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span>STA任务同步测试</span>
          <el-tag type="primary">最近一年 / 创建时间</el-tag>
        </div>
      </template>
      <el-alert
        title="按货件ID或货件单号精确查询，dateType固定为1，保存STA任务及全部商品明细到本地数据库。"
        type="info"
        :closable="false"
        show-icon
        class="mb16"
      />
      <el-form :inline="true">
        <el-form-item label="货件ID/货件单号">
          <el-input
            v-model="staShipmentId"
            clearable
            style="width: 280px"
            placeholder="例如 FBA19JSMN5B7"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="staSyncLoading" @click="handleStaSync">
            拉取并保存到本地表
          </el-button>
        </el-form-item>
      </el-form>
      <el-input
        v-if="staSyncResult"
        :model-value="JSON.stringify(staSyncResult, null, 2)"
        type="textarea"
        :rows="10"
        readonly
      />
    </el-card>

    <el-card v-if="result" shadow="never" class="result-card">
      <template #header>
        <span>调用结果</span>
      </template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="输出文件">{{ result.outputFile }}</el-descriptions-item>
        <el-descriptions-item label="API Path">{{ result.apiPath }}</el-descriptions-item>
      </el-descriptions>
      <el-input
        :model-value="responseText"
        type="textarea"
        :rows="20"
        readonly
        class="response-json"
      />
    </el-card>
  </div>
</template>

<script setup>
import { computed, getCurrentInstance, reactive, ref } from 'vue'
import { queryLingxingApi, syncStaInboundPlan } from '@/api/operations/lingxingApiTest'

const { proxy } = getCurrentInstance()
const formRef = ref()
const loading = ref(false)
const result = ref(null)
const staShipmentId = ref('FBA19JSMN5B7')
const staSyncLoading = ref(false)
const staSyncResult = ref(null)

const shipmentDetailExample = () => ({
  testName: 'shipment-detail',
  identifier: 'SP260715005',
  path: 'erp/sc/routing/storage/shipment/getInboundShipmentListMwsDetail',
  bodyText: JSON.stringify({
    shipment_sn: 'SP260715005',
    return_deleted: false
  }, null, 2)
})

const form = reactive(shipmentDetailExample())
const rules = {
  testName: [{ required: true, message: '测试名称不能为空', trigger: 'blur' }],
  identifier: [{ required: true, message: '文件标识不能为空', trigger: 'blur' }],
  path: [{ required: true, message: 'API Path 不能为空', trigger: 'blur' }],
  bodyText: [{ required: true, message: '请求 JSON 不能为空', trigger: 'blur' }]
}

const responseText = computed(() =>
  result.value ? JSON.stringify(result.value.response, null, 2) : ''
)

function resetShipmentDetail() {
  Object.assign(form, shipmentDetailExample())
  result.value = null
  formRef.value?.clearValidate()
}

function handleQuery() {
  formRef.value.validate(async valid => {
    if (!valid) return

    let body
    try {
      body = JSON.parse(form.bodyText)
    } catch (error) {
      proxy.$modal.msgError(`请求 JSON 格式错误：${error.message}`)
      return
    }
    if (!body || Array.isArray(body) || typeof body !== 'object') {
      proxy.$modal.msgError('请求 JSON 必须是对象')
      return
    }

    loading.value = true
    try {
      const response = await queryLingxingApi({
        testName: form.testName,
        identifier: form.identifier,
        path: form.path,
        body
      })
      result.value = response.data
      proxy.$modal.msgSuccess('拉取成功，TXT 已生成')
    } finally {
      loading.value = false
    }
  })
}

async function handleStaSync() {
  const shipmentId = staShipmentId.value?.trim()
  if (!shipmentId) {
    proxy.$modal.msgError('请输入货件ID或货件单号')
    return
  }
  staSyncLoading.value = true
  try {
    const response = await syncStaInboundPlan(shipmentId)
    staSyncResult.value = response.data
    proxy.$modal.msgSuccess('STA任务及商品明细已保存')
  } finally {
    staSyncLoading.value = false
  }
}
</script>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mb16 {
  margin-bottom: 16px;
}

.result-card {
  margin-top: 16px;
}

.response-json {
  margin-top: 16px;
}
</style>

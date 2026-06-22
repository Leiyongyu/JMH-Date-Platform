<template>
  <div class="app-container">
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" icon="Plus" @click="handleAdd" v-hasPermi="['operations:amzReplenishment:list']">新增</el-button>
      </el-col>
    </el-row>

    <el-table v-loading="loading" :data="list" border stripe>
      <el-table-column label="区域组" prop="regionGroup" width="80" />
      <el-table-column label="区域名称" prop="regionName" width="120" />
      <el-table-column label="包含市场" prop="marketplaces" width="220" show-overflow-tooltip />
      <el-table-column label="14天权重" prop="salesWeight14d" width="100" align="right" />
      <el-table-column label="30天权重" prop="salesWeight30d" width="100" align="right" />
      <el-table-column label="60天权重" prop="salesWeight60d" width="100" align="right" />
      <el-table-column label="月销乘数" prop="monthMultiplier" width="90" align="right" />
      <el-table-column label="安全天数" prop="safetyDays" width="90" align="right" />
      <el-table-column label="发货天数" prop="shipDays" width="90" align="right" />
      <el-table-column label="补货天数" prop="replenishDays" width="90" align="right" />
      <el-table-column label="启用" prop="enabled" width="70" align="center">
        <template #default="scope">{{ scope.row.enabled === 1 ? '是' : '否' }}</template>
      </el-table-column>
      <el-table-column label="备注" prop="remark" width="180" show-overflow-tooltip />
      <el-table-column label="更新时间" width="160" align="center">
        <template #default="scope">{{ parseTime(scope.row.updateTime) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="80" align="center" fixed="right">
        <template #default="scope">
          <el-button size="small" text type="primary" @click="handleEdit(scope.row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :title="dialogTitle" v-model="dialogVisible" width="620px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-divider content-position="left" style="margin-top:0">基本信息</el-divider>
        <el-form-item label="区域组代码" prop="regionGroup">
          <el-input v-model="form.regionGroup" placeholder="如 US / EU / JP" :disabled="isEdit" style="width:200px" />
        </el-form-item>
        <el-form-item label="区域名称" prop="regionName">
          <el-input v-model="form.regionName" placeholder="如：美国组 / 欧洲组" style="width:260px" />
        </el-form-item>
        <el-form-item label="包含市场" prop="marketplaces">
          <el-input v-model="form.marketplaces" placeholder="逗号分隔，如：US,CA,MX 或 DE,FR,IT,ES,UK" />
        </el-form-item>

        <el-divider content-position="left">销量权重系数</el-divider>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="14天权重" align="center"><el-input-number v-model="form.salesWeight14d" :min="0" :max="1" :step="0.1" :precision="3" size="small" style="width:110px" /></el-descriptions-item>
          <el-descriptions-item label="30天权重" align="center"><el-input-number v-model="form.salesWeight30d" :min="0" :max="1" :step="0.1" :precision="3" size="small" style="width:110px" /></el-descriptions-item>
          <el-descriptions-item label="60天权重" align="center"><el-input-number v-model="form.salesWeight60d" :min="0" :max="1" :step="0.1" :precision="3" size="small" style="width:110px" /></el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">计算天数与乘数</el-divider>
        <el-descriptions :column="4" border size="small">
          <el-descriptions-item label="月销乘数" align="center"><el-input-number v-model="form.monthMultiplier" :min="1" :step="1" size="small" style="width:100px" /></el-descriptions-item>
          <el-descriptions-item label="安全天数" align="center"><el-input-number v-model="form.safetyDays" :min="1" :step="1" size="small" style="width:100px" /></el-descriptions-item>
          <el-descriptions-item label="发货天数" align="center"><el-input-number v-model="form.shipDays" :min="1" :step="1" size="small" style="width:100px" /></el-descriptions-item>
          <el-descriptions-item label="补货天数" align="center"><el-input-number v-model="form.replenishDays" :min="1" :step="1" size="small" style="width:100px" /></el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left" style="margin-bottom:12px">其他</el-divider>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" :active-value="1" :inactive-value="0" />
          <span style="margin-left:10px;font-size:12px;color:#909399">{{ form.enabled === 1 ? '刷新快照时套用此公式' : '暂不使用' }}</span>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="备注说明，如：欧洲组安全库存120天" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="AmzFormulaConfig">
import { ref, reactive, getCurrentInstance } from 'vue'
import { listFormulaConfig, addFormulaConfig, updateFormulaConfig } from '@/api/operations/amz/formulaConfig'
import { parseTime } from '@/utils/ruoyi'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const list = ref([])
const dialogVisible = ref(false)
const dialogTitle = ref('')
const isEdit = ref(false)
const formRef = ref(null)

const defaultForm = { regionGroup: '', regionName: '', marketplaces: '', salesWeight14d: 0.5, salesWeight30d: 0.4, salesWeight60d: 0.1, monthMultiplier: 30, safetyDays: 90, shipDays: 90, replenishDays: 120, enabled: 1, remark: '' }
const form = reactive({ ...defaultForm })

const rules = {
  regionGroup: [{ required: true, message: '请输入区域组代码', trigger: 'blur' }],
  regionName: [{ required: true, message: '请输入区域名称', trigger: 'blur' }],
  marketplaces: [{ required: true, message: '请输入包含的市场', trigger: 'blur' }],
}

function getList() {
  loading.value = true
  listFormulaConfig().then(res => { list.value = res.data || [] }).finally(() => { loading.value = false })
}

function handleAdd() {
  isEdit.value = false
  dialogTitle.value = '新增公式配置'
  Object.assign(form, { ...defaultForm })
  dialogVisible.value = true
}

function handleEdit(row) {
  isEdit.value = true
  dialogTitle.value = '编辑公式配置'
  Object.assign(form, { ...row })
  dialogVisible.value = true
}

function resetForm() {
  formRef.value?.resetFields()
}

function submitForm() {
  formRef.value?.validate(async (valid) => {
    if (!valid) return
    const api = isEdit.value ? updateFormulaConfig : addFormulaConfig
    await api({ ...form })
    proxy.$modal.msgSuccess(isEdit.value ? '修改成功' : '新增成功')
    dialogVisible.value = false
    getList()
  })
}

getList()
</script>

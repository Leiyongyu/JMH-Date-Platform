<template>
  <div class="app-container">
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="handleAdd">新增</el-button>
      </el-col>
    </el-row>

    <el-table v-loading="loading" :data="list" border stripe height="540">
      <el-table-column label="站点" align="center" prop="site" width="120" />
      <el-table-column label="售前链接" align="left" prop="presaleUrl" min-width="280" show-overflow-tooltip />
      <el-table-column label="售后链接" align="left" prop="soldUrl" min-width="280" show-overflow-tooltip />
      <el-table-column label="目标利润率(%)" align="center" prop="profitRate" width="120" />
      <el-table-column label="实时汇率" align="center" prop="exchangeRate" width="100" />
      <el-table-column label="操作" align="center" width="150" fixed="right">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleEdit(scope.row)">修改</el-button>
          <el-button link type="danger" icon="Delete" @click="handleDelete(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :title="isEdit ? '修改链接模版' : '新增链接模版'" v-model="dialogVisible" width="520px" append-to-body>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="站点" prop="site">
          <el-select v-model="form.site" placeholder="选择站点" :disabled="isEdit" style="width:100%">
            <el-option label="美国" value="美国" /><el-option label="英国" value="英国" /><el-option label="德国" value="德国" />
          </el-select>
        </el-form-item>
        <el-form-item label="售前链接" prop="presaleUrl">
          <el-input v-model="form.presaleUrl" placeholder="输入售前链接模版，{oe}代表OE号" />
        </el-form-item>
        <el-form-item label="售后链接" prop="soldUrl">
          <el-input v-model="form.soldUrl" placeholder="输入售后链接模版，{oe}代表OE号" />
        </el-form-item>
        <el-form-item label="目标利润率(%)" prop="profitRate">
          <el-input-number v-model="form.profitRate" :min="0" :max="100" placeholder="默认8" style="width:100%" />
        </el-form-item>
        <el-form-item label="实时汇率" prop="exchangeRate">
          <el-input v-model="form.exchangeRate" placeholder="如 7.25" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取 消</el-button>
        <el-button type="primary" @click="submitForm">确 定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="LinkTemplate">
import request from '@/utils/request'

const { proxy } = getCurrentInstance()
const loading = ref(false), list = ref([]), dialogVisible = ref(false), isEdit = ref(false)
const form = reactive({ site: '', presaleUrl: '', soldUrl: '', profitRate: null, exchangeRate: '' })
const rules = { site: [{ required: true, message: '站点不能为空' }] }

function getList() {
  loading.value = true
  request({ url: '/operations/ebay/price-tracking/link-template', method: 'get' }).then(r => {
    list.value = r.data || []
  }).finally(() => { loading.value = false })
}

function handleAdd() { isEdit.value = false; Object.assign(form, { site: '', presaleUrl: '', soldUrl: '', profitRate: null, exchangeRate: '' }); dialogVisible.value = true }
function handleEdit(row) { isEdit.value = true; Object.assign(form, row); dialogVisible.value = true }

function submitForm() {
  proxy.$refs.formRef.validate(async valid => {
    if (!valid) return
    try {
      await request({ url: '/operations/ebay/price-tracking/link-template', method: 'post', data: form })
      proxy.$modal.msgSuccess(isEdit.value ? '修改成功' : '新增成功')
      dialogVisible.value = false; getList()
    } catch { proxy.$modal.msgError('保存失败') }
  })
}

function handleDelete(row) {
  proxy.$modal.confirm(`确认删除站点"${row.site}"的链接模版吗？`).then(async () => {
    await request({ url: '/operations/ebay/price-tracking/link-template/' + row.site, method: 'delete' })
    getList(); proxy.$modal.msgSuccess('删除成功')
  }).catch(() => {})
}

getList()
</script>

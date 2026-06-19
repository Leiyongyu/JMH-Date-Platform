<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="80px">
      <el-form-item label="品牌代码" prop="brandCode">
        <el-input v-model="queryParams.brandCode" placeholder="请输入品牌代码" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="负责人" prop="ownerName">
        <el-input v-model="queryParams.ownerName" placeholder="请输入负责人" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="handleAdd" v-hasPermi="['operations:brandOwner:add']">新增</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="list" border stripe height="540">
      <el-table-column label="品牌代码" align="center" prop="brandCode" width="150" />
      <el-table-column label="负责人" align="center" prop="ownerName" width="200" />
      <el-table-column label="创建时间" align="center" prop="createTime" width="170">
        <template #default="scope"><span>{{ parseTime(scope.row.createTime) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="180" fixed="right">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleEdit(scope.row)" v-hasPermi="['operations:brandOwner:edit']">修改</el-button>
          <el-button link type="danger" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['operations:brandOwner:remove']">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total>0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />

    <el-dialog :title="dialogTitle" v-model="dialogVisible" width="480px" append-to-body>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="品牌代码" prop="brandCode">
          <el-input v-model="form.brandCode" placeholder="请输入品牌代码" />
        </el-form-item>
        <el-form-item label="负责人" prop="ownerName">
          <el-input v-model="form.ownerName" placeholder="请输入负责人" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取 消</el-button>
        <el-button type="primary" @click="submitForm">确 定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="BrandOwner">
import request from '@/utils/request'

const { proxy } = getCurrentInstance()
const loading = ref(false), showSearch = ref(true), total = ref(0), list = ref([])
const dialogVisible = ref(false), isEdit = ref(false)

const data = reactive({
  queryParams: { pageNum: 1, pageSize: 20, brandCode: undefined, ownerName: undefined },
  form: { id: null, brandCode: '', ownerName: '' }
})
const { queryParams, form } = toRefs(data)
const dialogTitle = computed(() => isEdit.value ? '修改品牌负责人' : '新增品牌负责人')
const rules = { brandCode: [{ required: true, message: '品牌代码不能为空', trigger: 'blur' }], ownerName: [{ required: true, message: '负责人不能为空', trigger: 'blur' }] }

function getList() {
  loading.value = true
  request({ url: '/operations/brand-owner/list', method: 'get', params: queryParams.value }).then(r => {
    list.value = r.rows || []; total.value = r.total || 0
  }).finally(() => { loading.value = false })
}

function handleQuery() { queryParams.value.pageNum = 1; getList() }
function resetQuery() { proxy.resetForm('queryRef'); handleQuery() }
function handleAdd() { isEdit.value = false; form.value = { id: null, brandCode: '', ownerName: '' }; dialogVisible.value = true }
function handleEdit(row) { isEdit.value = true; form.value = { id: row.id, brandCode: row.brandCode, ownerName: row.ownerName }; dialogVisible.value = true }

function submitForm() {
  proxy.$refs.formRef.validate(valid => {
    if (!valid) return
    const method = isEdit.value ? 'put' : 'post'
    request({ url: '/operations/brand-owner', method, data: form.value }).then(() => {
      proxy.$modal.msgSuccess(isEdit.value ? '修改成功' : '新增成功')
      dialogVisible.value = false; getList()
    })
  })
}

function handleDelete(row) {
  proxy.$modal.confirm('确认删除品牌"' + row.brandCode + '"吗？').then(() => {
    return request({ url: '/operations/brand-owner/' + row.id, method: 'delete' })
  }).then(() => { getList(); proxy.$modal.msgSuccess('删除成功') }).catch(() => {})
}

getList()
</script>

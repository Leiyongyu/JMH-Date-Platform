<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch">
      <el-form-item label="同步类型" prop="syncType">
        <el-input v-model="queryParams.syncType" placeholder="如 ebay_manual_sync" clearable style="width:200px" @keyup.enter="handleQuery"/>
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-select v-model="queryParams.status" clearable style="width:140px">
          <el-option label="成功" value="SUCCESS"/><el-option label="失败" value="FAILED"/>
          <el-option label="部分成功" value="PARTIAL_SUCCESS"/><el-option label="执行中" value="RUNNING"/>
        </el-select>
      </el-form-item>
      <el-form-item label="触发方式" prop="triggerType">
        <el-select v-model="queryParams.triggerType" clearable style="width:120px">
          <el-option label="手动" value="MANUAL"/><el-option label="定时" value="JOB"/>
        </el-select>
      </el-form-item>
      <el-form-item><el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button></el-form-item>
    </el-form>
    <el-table v-loading="loading" :data="list" border stripe @row-click="handleRowClick" highlight-current-row>
      <el-table-column label="ID" prop="id" width="70"/>
      <el-table-column label="同步名称" prop="syncName" min-width="160"/>
      <el-table-column label="状态" width="100"><template #default="{row}">
        <el-tag :type="row.status==='SUCCESS'?'success':row.status==='FAILED'?'danger':row.status==='RUNNING'?'warning':'info'">{{ row.status }}</el-tag>
      </template></el-table-column>
      <el-table-column label="触发" prop="triggerType" width="60"/>
      <el-table-column label="成功/总数" width="100"><template #default="{row}">{{ row.successCount }}/{{ row.totalCount }}</template></el-table-column>
      <el-table-column label="操作人" prop="operator" width="80"/>
      <el-table-column label="开始时间" width="160"><template #default="{row}">{{ row.startTime }}</template></el-table-column>
      <el-table-column label="耗时" width="80"><template #default="{row}">{{ row.endTime ? ((new Date(row.endTime)-new Date(row.startTime))/1000).toFixed(1)+'s' : '-' }}</template></el-table-column>
    </el-table>
    <pagination v-show="total>0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList"/>
    <el-dialog title="同步详情" v-model="detailVisible" width="800px">
      <el-descriptions :column="2" border v-if="detail.parent">
        <el-descriptions-item label="同步名称">{{ detail.parent.syncName }}</el-descriptions-item>
        <el-descriptions-item label="状态"><el-tag :type="detail.parent.status==='SUCCESS'?'success':'danger'">{{ detail.parent.status }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="API路径">{{ detail.parent.apiPath }}</el-descriptions-item>
        <el-descriptions-item label="触发方式">{{ detail.parent.triggerType }}</el-descriptions-item>
        <el-descriptions-item label="成功/失败/总数">{{ detail.parent.successCount }}/{{ detail.parent.failCount }}/{{ detail.parent.totalCount }}</el-descriptions-item>
        <el-descriptions-item label="操作人">{{ detail.parent.operator }}</el-descriptions-item>
        <el-descriptions-item label="错误信息" :span="2">{{ detail.parent.errorMessage || '-' }}</el-descriptions-item>
      </el-descriptions>
      <el-divider v-if="detail.children && detail.children.length">子步骤</el-divider>
      <el-table v-if="detail.children && detail.children.length" :data="detail.children" border size="small">
        <el-table-column label="步骤" prop="syncName" width="160"/>
        <el-table-column label="状态" width="80"><template #default="{row}"><el-tag :type="row.status==='SUCCESS'?'success':'danger'" size="small">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column label="成功/失败/总数" width="110"><template #default="{row}">{{ row.successCount }}/{{ row.failCount }}/{{ row.totalCount }}</template></el-table-column>
        <el-table-column label="错误" prop="errorMessage" min-width="150"/>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup name="SyncLog">
import { ref, reactive } from 'vue'
import { listSyncLog, getSyncLogDetail } from '@/api/operations/syncLog'
const { proxy } = getCurrentInstance()
const loading = ref(false); const showSearch = ref(true); const total = ref(0)
const list = ref([]); const detailVisible = ref(false); const detail = ref({})
const queryParams = reactive({ pageNum:1, pageSize:10, syncType:'', status:'', triggerType:'' })
function getList() {
  loading.value = true
  listSyncLog(queryParams).then(r => { list.value = r.rows; total.value = r.total }).finally(() => loading.value = false)
}
function handleQuery() { queryParams.pageNum = 1; getList() }
function handleRowClick(row) {
  getSyncLogDetail(row.id).then(r => { detail.value = r.data; detailVisible.value = true })
}
getList()
</script>

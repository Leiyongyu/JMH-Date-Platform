<template>
   <div class="app-container">
      <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch">
         <el-form-item label="任务名称" prop="jobName">
            <el-input
               v-model="queryParams.jobName"
               placeholder="请输入任务名称"
               clearable
               style="width: 200px"
               @keyup.enter="handleQuery"
            />
         </el-form-item>
         <el-form-item label="任务组名" prop="jobGroup">
            <el-select v-model="queryParams.jobGroup" placeholder="请选择任务组名" clearable style="width: 200px">
               <el-option
                  v-for="dict in sys_job_group"
                  :key="dict.value"
                  :label="dict.label"
                  :value="dict.value"
               />
            </el-select>
         </el-form-item>
         <el-form-item label="任务状态" prop="status">
            <el-select v-model="queryParams.status" placeholder="请选择任务状态" clearable style="width: 200px">
               <el-option
                  v-for="dict in sys_job_status"
                  :key="dict.value"
                  :label="dict.label"
                  :value="dict.value"
               />
            </el-select>
         </el-form-item>
         <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
            <el-button icon="Refresh" @click="resetQuery">重置</el-button>
         </el-form-item>
      </el-form>

      <el-row :gutter="10" class="mb8">
         <el-col :span="1.5">
            <el-button
               type="primary"
               plain
               icon="Plus"
               @click="handleAdd"
               v-hasPermi="['monitor:job:add']"
            >新增</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button
               type="success"
               plain
               icon="Edit"
               :disabled="single"
               @click="handleUpdate"
               v-hasPermi="['monitor:job:edit']"
            >修改</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button
               type="danger"
               plain
               icon="Delete"
               :disabled="multiple"
               @click="handleDelete"
               v-hasPermi="['monitor:job:remove']"
            >删除</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button
               type="warning"
               plain
               icon="Download"
               @click="handleExport"
               v-hasPermi="['monitor:job:export']"
            >导出</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button
               type="info"
               plain
               icon="Operation"
               @click="handleJobLog"
               v-hasPermi="['monitor:job:query']"
            >日志</el-button>
         </el-col>
         <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
      </el-row>

      <el-table v-loading="loading" :data="jobList" @selection-change="handleSelectionChange">
         <el-table-column type="selection" width="55" align="center" />
         <el-table-column label="任务编号" width="100" align="center" prop="jobId" />
         <el-table-column label="任务名称" align="center" :show-overflow-tooltip="true">
            <template #default="scope">
               <a class="link-type" style="cursor:pointer" @click="handleView(scope.row)">{{ scope.row.jobName }}</a>
            </template>
         </el-table-column>
         <el-table-column label="任务组名" align="center" prop="jobGroup">
            <template #default="scope">
               <dict-tag :options="sys_job_group" :value="scope.row.jobGroup" />
            </template>
         </el-table-column>
         <el-table-column label="调用目标字符串" align="center" prop="invokeTarget" :show-overflow-tooltip="true" />
         <el-table-column label="cron执行表达式" align="center" prop="cronExpression" :show-overflow-tooltip="true" />
         <el-table-column label="备注" align="center" prop="remark" :show-overflow-tooltip="true" />
         <el-table-column label="状态" align="center">
            <template #default="scope">
               <el-switch
                  v-model="scope.row.status"
                  active-value="0"
                  inactive-value="1"
                  @change="handleStatusChange(scope.row)"
               ></el-switch>
            </template>
         </el-table-column>
         <el-table-column label="操作" align="center" width="200" class-name="small-padding fixed-width">
            <template #default="scope">
               <el-tooltip content="修改" placement="top">
                  <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="['monitor:job:edit']"></el-button>
               </el-tooltip>
               <el-tooltip content="删除" placement="top">
                  <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['monitor:job:remove']"></el-button>
               </el-tooltip>
               <el-tooltip content="执行一次" placement="top">
                  <el-button link type="primary" icon="CaretRight" @click="handleRun(scope.row)" v-hasPermi="['monitor:job:changeStatus']"></el-button>
               </el-tooltip>
               <el-tooltip content="调度日志" placement="top">
                  <el-button link type="primary" icon="Operation" @click="handleJobLog(scope.row)" v-hasPermi="['monitor:job:query']"></el-button>
               </el-tooltip>
            </template>
         </el-table-column>
      </el-table>

      <pagination
         v-show="total > 0"
         :total="total"
         v-model:page="queryParams.pageNum"
         v-model:limit="queryParams.pageSize"
         @pagination="getList"
      />

      <!-- 添加或修改定时任务对话框 -->
      <el-dialog :title="title" v-model="open" width="780px" append-to-body>
         <el-form ref="jobRef" :model="form" :rules="rules" label-width="100px">
            <el-row :gutter="16">
               <el-col :span="12">
                  <el-form-item label="任务名称" prop="jobName">
                     <el-input v-model="form.jobName" placeholder="请输入任务名称" />
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="任务分组" prop="jobGroup">
                     <el-select v-model="form.jobGroup" placeholder="请选择">
                        <el-option v-for="dict in sys_job_group" :key="dict.value" :label="dict.label" :value="dict.value" />
                     </el-select>
                  </el-form-item>
               </el-col>
               <el-col :span="24">
                  <el-form-item prop="invokeTarget">
                     <template #label>
                        <span>调用方法
                           <el-tooltip placement="top">
                              <template #content><div>Bean调用示例：ryTask.ryParams('ry')<br/>Class类调用示例：com.ruoyi.quartz.task.RyTask.ryParams('ry')<br/>参数说明：支持字符串，布尔类型，长整型，浮点型，整型</div></template>
                              <el-icon><question-filled /></el-icon>
                           </el-tooltip>
                        </span>
                     </template>
                     <el-input v-model="form.invokeTarget" placeholder="请输入调用目标字符串" />
                  </el-form-item>
               </el-col>
               <!-- 可视化 Cron 配置 -->
               <el-col :span="24">
                  <el-form-item label="执行频率" prop="cronExpression">
                     <div class="cron-builder">
                        <div class="freq-cards">
                           <div class="freq-card" :class="{active:cronFreq==='day'}" @click="setFreq('day')"><span>每天</span></div>
                           <div class="freq-card" :class="{active:cronFreq==='week'}" @click="setFreq('week')"><span>每周</span></div>
                           <div class="freq-card" :class="{active:cronFreq==='month'}" @click="setFreq('month')"><span>每月</span></div>
                           <div class="freq-card" :class="{active:cronFreq==='custom'}" @click="setFreq('custom')"><span>自定义</span></div>
                        </div>
                        <div v-if="cronFreq==='week'" class="week-days">
                           <el-checkbox-button v-for="d in weekDays" :key="d.value" v-model="cronWeekDays[d.value]" size="small" @change="updateCron">{{ d.label }}</el-checkbox-button>
                        </div>
                        <div v-if="cronFreq==='month'" class="month-days">
                           <span class="mr8">每月</span>
                           <el-select v-model="cronMonthDay" size="small" style="width:100px" @change="updateCron">
                              <el-option v-for="d in 31" :key="d" :label="d+'号'" :value="d" />
                           </el-select>
                           <span class="ml8">执行</span>
                        </div>
                        <div class="time-row">
                           <el-time-select v-model="cronTime" placeholder="执行时间" start="00:00" step="00:30" end="23:59" size="small" style="width:130px" @change="updateCron" />
                           <span v-if="cronPreview" class="preview-text">{{ cronPreview }}</span>
                        </div>
                     </div>
                  </el-form-item>
               </el-col>
               <el-col :span="24">
                  <div v-if="cronNextDates.length" class="cron-preview-card">
                     <div class="preview-header">📅 执行计划预览</div>
                     <div class="preview-body">
                        <div>下次执行：<b>{{ cronNextDates[0] }}</b></div>
                        <div v-if="cronNextDates[1]">后续：{{ cronNextDates.slice(1).join('、') }}</div>
                     </div>
                  </div>
               </el-col>
               <el-col :span="24">
                  <el-collapse>
                     <el-collapse-item title="高级设置 / Cron 表达式">
                        <el-input v-model="form.cronExpression" placeholder="请输入 Cron 表达式" size="small" @change="parseCron">
                           <template #append><el-button size="small" @click="handleShowCron">生成器</el-button></template>
                        </el-input>
                     </el-collapse-item>
                  </el-collapse>
               </el-col>
               <!-- 其他 -->
               <el-col :span="12">
                  <el-form-item label="执行策略" prop="misfirePolicy">
                     <el-radio-group v-model="form.misfirePolicy"><el-radio-button value="1">立即执行</el-radio-button><el-radio-button value="2">执行一次</el-radio-button><el-radio-button value="3">放弃执行</el-radio-button></el-radio-group>
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="是否并发" prop="concurrent">
                     <el-radio-group v-model="form.concurrent"><el-radio-button value="0">允许</el-radio-button><el-radio-button value="1">禁止</el-radio-button></el-radio-group>
                  </el-form-item>
               </el-col>
               <el-col :span="12" v-if="form.jobId !== undefined">
                  <el-form-item label="状态">
                     <el-radio-group v-model="form.status"><el-radio v-for="dict in sys_job_status" :key="dict.value" :value="dict.value">{{ dict.label }}</el-radio></el-radio-group>
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="备注"><el-input v-model="form.remark" placeholder="执行时间说明" /></el-form-item>
               </el-col>
            </el-row>
         </el-form>
         <template #footer>
            <el-button @click="cancel">取消</el-button>
            <el-button type="primary" @click="submitForm">保存</el-button>
            <el-button type="success" @click="submitAndRun" v-if="form.jobId">保存并立即执行</el-button>
         </template>
      </el-dialog>

     <el-dialog title="Cron表达式生成器" v-model="openCron" append-to-body destroy-on-close>
       <crontab ref="crontabRef" @hide="openCron=false" @fill="crontabFill" :expression="expression"></crontab>
     </el-dialog>

      <!-- 任务详细 -->
      <job-detail v-model:visible="openView" :row="form" type="job" />
   </div>
</template>

<script setup name="Job">
import Crontab from '@/components/Crontab'
import JobDetail from './detail'
import { listJob, getJob, delJob, addJob, updateJob, runJob, changeJobStatus } from "@/api/monitor/job"

const router = useRouter()
const { proxy } = getCurrentInstance()
const { sys_job_group, sys_job_status } = useDict("sys_job_group", "sys_job_status")

const jobList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref("")
const openView = ref(false)
const openCron = ref(false)
const expression = ref("")

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    jobName: undefined,
    jobGroup: undefined,
    status: undefined
  },
  rules: {
    jobName: [{ required: true, message: "任务名称不能为空", trigger: "blur" }],
    invokeTarget: [{ required: true, message: "调用目标字符串不能为空", trigger: "blur" }],
    cronExpression: [{ required: true, message: "cron执行表达式不能为空", trigger: "change" }]
  }
})

const { queryParams, form, rules } = toRefs(data)

// ---- 可视化 Cron 构建 ----
const cronFreq = ref('week')
const cronWeekDays = reactive({1:true,2:false,3:true,4:false,5:true,6:false,0:false})
const cronMonthDay = ref(1)
const cronTime = ref('09:00')
const weekDays = [{value:1,label:'周一'},{value:2,label:'周二'},{value:3,label:'周三'},{value:4,label:'周四'},{value:5,label:'周五'},{value:6,label:'周六'},{value:0,label:'周日'}]
const monthDayLabels = {1:'1号',15:'15号',28:'28号'}

const cronPreview = computed(() => {
  const t = cronTime.value; if (!t) return ''
  const [h,m] = t.split(':')
  if (cronFreq.value === 'day') return `每天 ${t} 执行`
  if (cronFreq.value === 'week') {
    const ds = weekDays.filter(d => cronWeekDays[d.value]).map(d => d.label).join('、')
    return ds ? `每周${ds} ${t} 执行` : '请选择星期'
  }
  if (cronFreq.value === 'month') return `每月${cronMonthDay.value}号 ${t} 执行`
  return ''
})

const cronNextDates = computed(() => {
  const expr = form.value.cronExpression
  if (!expr) return []
  const parts = expr.split(' ')
  if (parts.length < 6) return []
  const now = new Date(); const results = []
  let test = new Date(now); test.setSeconds(0,0)
  for (let i = 0; i < 20 && results.length < 4; i++) {
    test = new Date(test.getTime() + 60000)
    if (matchCron(test, parts)) results.push(formatDate(test))
  }
  return results
})

function matchCron(d, parts) {
  const vals = [d.getMinutes(), d.getHours(), d.getDate(), d.getMonth()+1, d.getDay(), d.getFullYear()]
  const p = [parts[0], parts[1], parts[2], parts[3], parts[4]]
  return p.every((v, i) => v === '*' || v === '?' || v.split(',').some(s => {
    if (s.includes('/')) { const [b, step] = s.split('/'); return +step && vals[i] % +step === 0 }
    if (s.includes('-')) { const [lo, hi] = s.split('-').map(Number); return vals[i] >= lo && vals[i] <= hi }
    return +s === vals[i]
  }))
}
function formatDate(d) {
  const pad = n => String(n).padStart(2,'0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function setFreq(f) { cronFreq.value = f; updateCron() }
function updateCron() {
  const [h,m] = (cronTime.value || '09:00').split(':')
  let expr = '0 '+m+' '+h+' '
  if (cronFreq.value === 'day') expr += '* * ?'
  else if (cronFreq.value === 'week') { const ds = weekDays.filter(d => cronWeekDays[d.value]).map(d => d.value).join(','); expr += '? * '+(ds||'1') }
  else if (cronFreq.value === 'month') expr += cronMonthDay.value + ' * ?'
  else return
  form.value.cronExpression = expr; validateCron()
}
function parseCron() {
  const v = form.value.cronExpression; if (!v) return
  const parts = v.trim().split(/\s+/)
  if (parts.length < 5) { cronFreq.value='custom'; return }
  const [m, h, day, month, week] = parts
  cronTime.value = h.padStart(2,'0')+':'+m.padStart(2,'0')
  if (day === '*' && month === '*' && week === '?') cronFreq.value = 'day'
  else if (day === '?' && month === '*') { cronFreq.value = 'week'; week.split(',').forEach(w => { const n=+w; if (n>=0&&n<=6) cronWeekDays[n]=true }) }
  else if (month === '*' && week === '?' && day !== '*') { cronFreq.value = 'month'; cronMonthDay.value = +day||1 }
  else cronFreq.value = 'custom'
}
function validateCron() { if (form.value.cronExpression) formRef.value?.validateField('cronExpression') }

/** cron表达式按钮操作 */
function handleShowCron() { expression.value = form.value.cronExpression; openCron.value = true }
function crontabFill(value) { form.value.cronExpression = value; parseCron() }

function submitAndRun() {
  proxy.$refs["jobRef"].validate(async valid => {
    if (!valid) return
    if (form.value.jobId != undefined) {
      await updateJob(form.value)
      await handleRun({ jobId: form.value.jobId, jobName: form.value.jobName, jobGroup: form.value.jobGroup })
      proxy.$modal.msgSuccess("保存并立即执行成功")
    } else {
      await addJob(form.value)
      proxy.$modal.msgSuccess("新增成功")
    }
    open.value = false; getList()
  })
}

// 编辑时回显
watch(open, v => { if (v) { parseCron() } })

/** 表单重置 */
function reset() {
  form.value = { jobId: undefined, jobName: undefined, jobGroup: undefined, invokeTarget: undefined, cronExpression: undefined, misfirePolicy: '1', concurrent: '1', remark: '', status: "0" }
  cronFreq.value = 'week'
  Object.keys(cronWeekDays).forEach(k => cronWeekDays[k] = false)
  cronWeekDays[1] = cronWeekDays[3] = cronWeekDays[5] = true
  cronMonthDay.value = 1; cronTime.value = '09:00'
  proxy.resetForm("jobRef")
}

/** 查询定时任务列表 */
function getList() {
  loading.value = true
  listJob(queryParams.value).then(response => {
    jobList.value = response.rows
    total.value = response.total
    loading.value = false
  })
}

/** 取消按钮 */
function cancel() {
  open.value = false
  reset()
}

/** 搜索按钮操作 */

/** 搜索按钮操作 */
function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

/** 重置按钮操作 */
function resetQuery() {
  proxy.resetForm("queryRef")
  handleQuery()
}

// 多选框选中数据
function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.jobId)
  single.value = selection.length != 1
  multiple.value = !selection.length
}

// 任务状态修改
function handleStatusChange(row) {
  let text = row.status === "0" ? "启用" : "停用"
  proxy.$modal.confirm('确认要"' + text + '""' + row.jobName + '"任务吗?').then(function () {
    return changeJobStatus(row.jobId, row.status)
  }).then(() => {
    proxy.$modal.msgSuccess(text + "成功")
  }).catch(function () {
    row.status = row.status === "0" ? "1" : "0"
  })
}

/* 立即执行一次 */
function handleRun(row) {
  proxy.$modal.confirm('确认要立即执行一次"' + row.jobName + '"任务吗?').then(function () {
    return runJob(row.jobId, row.jobGroup)
  }).then(() => {
    proxy.$modal.msgSuccess("执行成功")
  }).catch(() => {})
}

/** 任务详细信息 */
function handleView(row) {
  getJob(row.jobId).then(response => {
    form.value = response.data
    openView.value = true
  })
}


/** 任务日志列表查询 */
function handleJobLog(row) {
  const jobId = row.jobId || 0
  router.push('/monitor/job-log/index/' + jobId)
}

/** 新增按钮操作 */
function handleAdd() {
  reset()
  open.value = true
  title.value = "添加任务"
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset()
  const jobId = row.jobId || ids.value
  getJob(jobId).then(response => {
    form.value = response.data
    open.value = true
    title.value = "修改任务"
  })
}

/** 提交按钮 */
function submitForm() {
  proxy.$refs["jobRef"].validate(valid => {
    if (valid) {
      if (form.value.jobId != undefined) {
        updateJob(form.value).then(response => {
          proxy.$modal.msgSuccess("修改成功")
          open.value = false
          getList()
        })
      } else {
        addJob(form.value).then(response => {
          proxy.$modal.msgSuccess("新增成功")
          open.value = false
          getList()
        })
      }
    }
  })
}

/** 删除按钮操作 */
function handleDelete(row) {
  const jobIds = row.jobId || ids.value
  proxy.$modal.confirm('是否确认删除定时任务编号为"' + jobIds + '"的数据项?').then(function () {
    return delJob(jobIds)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => {})
}

/** 导出按钮操作 */
function handleExport() {
  proxy.download("monitor/job/export", {
    ...queryParams.value,
  }, `job_${new Date().getTime()}.xlsx`)
}

getList()
</script>

<style scoped>
.cron-builder { padding:12px 14px; border-radius:8px; background:#f8f9fb; border:1px solid #e8eaed }
.freq-cards { display:flex; gap:10px; margin-bottom:10px }
.freq-card { flex:1; padding:10px 0; text-align:center; border-radius:6px; cursor:pointer; font-size:14px; color:#5f6368; background:#fff; border:1px solid #dadce0; transition:all .2s }
.freq-card:hover { border-color:#409eff; color:#409eff }
.freq-card.active { background:#e6f4ff; border-color:#409eff; color:#409eff; font-weight:600 }
.freq-card span { user-select:none }
.week-days { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:10px }
.month-days { margin-bottom:10px; display:flex; align-items:center }
.time-row { display:flex; align-items:center; gap:12px }
.preview-text { font-size:13px; color:#5f6368 }
.cron-preview-card { margin-top:10px; padding:12px 16px; border-radius:8px; background:#e6f4ff; border:1px solid #b3d8ff }
.preview-header { font-size:13px; font-weight:600; color:#1890ff; margin-bottom:6px }
.preview-body { font-size:13px; color:#303133; line-height:1.8 }
.preview-body b { color:#0d6efd }
.mr8 { margin-right:8px }
.ml8 { margin-left:8px }
</style>

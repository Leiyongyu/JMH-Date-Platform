<template>
  <div class="script-tools-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">SOP AUTOMATION</p>
        <h2>脚本菜单</h2>
        <p class="description">从 ERP 安全打开本机自动化工具，账号和内部密钥不会传到浏览器。</p>
      </div>
    </div>

    <div class="config-bar">
      <div class="config-summary">
        <div class="config-status-icon" :class="configStatus.ready ? 'is-ready' : 'is-warning'">
          <el-icon><Lock /></el-icon>
        </div>
        <div>
          <strong>紫鸟用户配置</strong>
          <p v-if="configStatus.ready">
            {{ configStatus.accountName }}，密码缓存剩余 {{ passwordTtlText }}
          </p>
          <p v-else>{{ configStatusMessage }}</p>
        </div>
      </div>
      <el-button
        v-hasPermi="['sop:amazonImageUpload:use']"
        type="primary"
        plain
        :loading="configLoading"
        @click="openConfigDialog"
      >
        <el-icon><Setting /></el-icon>
        配置
      </el-button>
    </div>

    <div class="tool-grid">
      <div class="tool-card">
        <div class="tool-icon">
          <el-icon><PictureFilled /></el-icon>
        </div>
        <div class="tool-content">
          <h3>亚马逊主图批量上传</h3>
          <p>通过紫鸟店铺依次打开 Amazon 德国站，按 SKU 批量更新商品图片。</p>
          <div class="tool-tags">
            <el-tag size="small" type="success">单机串行</el-tag>
            <el-tag size="small" type="info">支持断点续传</el-tag>
          </div>
        </div>
        <el-button
          v-hasPermi="['sop:amazonImageUpload:use']"
          type="primary"
          :loading="opening"
          @click="openAmazonImageUpload"
        >
          <el-icon><TopRight /></el-icon>
          {{ opening ? '正在建立安全会话' : '打开工具' }}
        </el-button>
      </div>
    </div>

    <el-dialog
      v-model="configDialogVisible"
      title="紫鸟用户配置"
      width="560px"
      :close-on-click-modal="false"
      destroy-on-close
      @closed="clearPasswordInput"
    >
      <el-alert
        title="密码不会保存到数据库"
        description="密码仅在 Redis 中按当前 ERP 用户缓存 8 小时，到期后必须重新输入。公司名、账号和客户端路径可长期保存并随时修改。"
        type="warning"
        show-icon
        :closable="false"
        class="config-alert"
      />

      <el-form
        ref="configFormRef"
        :model="configForm"
        :rules="configRules"
        label-width="112px"
        @submit.prevent
      >
        <el-form-item label="公司名称" prop="companyName">
          <el-input
            v-model="configForm.companyName"
            maxlength="128"
            placeholder="请输入紫鸟企业/公司名称"
          />
        </el-form-item>
        <el-form-item label="紫鸟账号" prop="accountName">
          <el-input
            v-model="configForm.accountName"
            maxlength="128"
            autocomplete="off"
            placeholder="请输入当前用户的紫鸟账号"
          />
        </el-form-item>
        <el-form-item label="紫鸟密码" prop="password">
          <div class="password-field">
            <el-input
              v-model="configForm.password"
              type="password"
              show-password
              maxlength="512"
              autocomplete="off"
              :placeholder="configStatus.passwordCached ? '密码已缓存，留空表示不更新' : '请输入密码'"
            />
            <span class="field-hint">
              {{ configStatus.passwordCached ? `当前剩余 ${passwordTtlText}` : '当前没有可用的缓存密码' }}
            </span>
          </div>
        </el-form-item>
        <el-form-item label="紫鸟路径" prop="clientPath">
          <el-input
            v-model="configForm.clientPath"
            maxlength="500"
            placeholder="例如 D:\ziniao\ziniao.exe"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <div class="dialog-footer">
          <el-button
            v-if="configStatus.passwordCached"
            type="danger"
            plain
            :loading="clearingPassword"
            @click="clearCachedPassword"
          >
            立即清除缓存密码
          </el-button>
          <span class="footer-spacer" />
          <el-button @click="configDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="configSaving" @click="saveConfig">
            保存配置
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Lock, PictureFilled, Setting, TopRight } from '@element-plus/icons-vue'
import {
  clearAmazonImageUploadPassword,
  createAmazonImageUploadSession,
  getAmazonImageUploadConfig,
  saveAmazonImageUploadConfig
} from '@/api/sop/scriptTools'

const opening = ref(false)
const configDialogVisible = ref(false)
const configLoading = ref(false)
const configSaving = ref(false)
const clearingPassword = ref(false)
const configLoaded = ref(false)
const configFormRef = ref()
const savedIdentity = reactive({ companyName: '', accountName: '' })
const configStatus = reactive({
  companyName: '',
  accountName: '',
  clientPath: '',
  configured: false,
  passwordCached: false,
  passwordExpiresInSeconds: 0,
  ready: false
})
const configForm = reactive({
  companyName: '',
  accountName: '',
  password: '',
  clientPath: ''
})

const passwordTtlText = computed(() => {
  const seconds = Math.max(0, Number(configStatus.passwordExpiresInSeconds || 0))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.ceil((seconds % 3600) / 60)
  if (hours > 0) return `${hours}小时${minutes > 0 ? `${minutes}分钟` : ''}`
  return `${Math.max(1, minutes)}分钟`
})

const configStatusMessage = computed(() => {
  if (!configStatus.configured) return '请先配置公司名、紫鸟账号和客户端路径'
  if (!configStatus.passwordCached) return '密码未输入或已超过 8 小时，请重新输入'
  return '配置尚未完成'
})

function validateClientPath(rule, value, callback) {
  const normalized = String(value || '').trim().replaceAll('/', '\\').toLowerCase()
  if (!normalized) return callback(new Error('请输入紫鸟客户端路径'))
  if (!normalized.endsWith('\\ziniao.exe')) {
    return callback(new Error('客户端路径必须指向 ziniao.exe'))
  }
  callback()
}

function validatePassword(rule, value, callback) {
  const identityChanged = configForm.companyName.trim() !== savedIdentity.companyName
    || configForm.accountName.trim() !== savedIdentity.accountName
  if (!String(value || '').trim() && (!configStatus.passwordCached || identityChanged)) {
    return callback(new Error(identityChanged
      ? '公司名或账号已修改，请重新输入密码'
      : '请输入紫鸟密码'))
  }
  callback()
}

const configRules = {
  companyName: [{ required: true, message: '请输入公司名称', trigger: 'blur' }],
  accountName: [{ required: true, message: '请输入紫鸟账号', trigger: 'blur' }],
  password: [{ validator: validatePassword, trigger: 'blur' }],
  clientPath: [{ validator: validateClientPath, trigger: 'blur' }]
}

function proxyBase() {
  const baseApi = String(import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return `${baseApi}/sop/script-tools/amazon-image-upload/proxy`
}

async function openAmazonImageUpload() {
  if (opening.value) return
  if (configLoaded.value && !configStatus.ready) {
    ElMessage.warning(configStatusMessage.value)
    openConfigDialog()
    return
  }
  const toolWindow = window.open('about:blank', '_blank')
  if (!toolWindow) {
    ElMessage.warning('浏览器阻止了新窗口，请允许本站弹出窗口后重试')
    return
  }
  toolWindow.opener = null
  toolWindow.document.title = '正在打开亚马逊主图上传…'
  toolWindow.document.body.innerHTML = '<div style="font-family:system-ui;padding:32px;color:#475569">正在建立 ERP 安全会话，请稍候…</div>'

  opening.value = true
  try {
    const response = await createAmazonImageUploadSession()
    const session = response?.data?.session
    if (!session) throw new Error('Java 后端未返回脚本工具安全会话')
    const query = new URLSearchParams({ erp_session: session })
    toolWindow.location.replace(`${proxyBase()}/?${query.toString()}`)
  } catch (error) {
    toolWindow.close()
    const message = error?.message || '脚本工具打开失败'
    ElMessage.error(message)
    if (message.includes('紫鸟') || message.includes('密码') || message.includes('配置')) {
      openConfigDialog()
    }
  } finally {
    opening.value = false
  }
}

function applyConfigStatus(data, fillForm = false) {
  Object.assign(configStatus, {
    companyName: data?.companyName || '',
    accountName: data?.accountName || '',
    clientPath: data?.clientPath || '',
    configured: Boolean(data?.configured),
    passwordCached: Boolean(data?.passwordCached),
    passwordExpiresInSeconds: Number(data?.passwordExpiresInSeconds || 0),
    ready: Boolean(data?.ready)
  })
  configLoaded.value = true
  if (fillForm) {
    configForm.companyName = configStatus.companyName
    configForm.accountName = configStatus.accountName
    configForm.clientPath = configStatus.clientPath
    configForm.password = ''
    savedIdentity.companyName = configStatus.companyName
    savedIdentity.accountName = configStatus.accountName
  }
}

async function loadConfigStatus(fillForm = false) {
  configLoading.value = true
  try {
    const response = await getAmazonImageUploadConfig()
    applyConfigStatus(response?.data || {}, fillForm)
  } catch (error) {
    if (fillForm) ElMessage.error(error?.message || '加载紫鸟配置失败')
  } finally {
    configLoading.value = false
  }
}

function openConfigDialog() {
  configDialogVisible.value = true
  loadConfigStatus(true)
}

function clearPasswordInput() {
  configForm.password = ''
  configFormRef.value?.clearValidate()
}

async function saveConfig() {
  const valid = await configFormRef.value?.validate().catch(() => false)
  if (!valid) return
  configSaving.value = true
  try {
    const response = await saveAmazonImageUploadConfig({
      companyName: configForm.companyName.trim(),
      accountName: configForm.accountName.trim(),
      clientPath: configForm.clientPath.trim(),
      password: configForm.password
    })
    configForm.password = ''
    applyConfigStatus(response?.data || {}, true)
    configDialogVisible.value = false
    ElMessage.success('紫鸟配置已保存，密码将在 8 小时后自动失效')
  } catch (error) {
    configForm.password = ''
    ElMessage.error(error?.message || '保存紫鸟配置失败')
  } finally {
    configSaving.value = false
  }
}

async function clearCachedPassword() {
  try {
    await ElMessageBox.confirm(
      '清除后必须重新输入密码才能打开主图上传工具，是否继续？',
      '清除缓存密码',
      { type: 'warning' }
    )
  } catch {
    return
  }
  clearingPassword.value = true
  try {
    const response = await clearAmazonImageUploadPassword()
    configForm.password = ''
    applyConfigStatus(response?.data || {}, true)
    ElMessage.success('已清除当前用户的缓存密码')
  } catch (error) {
    ElMessage.error(error?.message || '清除缓存密码失败')
  } finally {
    clearingPassword.value = false
  }
}

onMounted(() => loadConfigStatus(false))
</script>

<style scoped>
.script-tools-page {
  min-height: calc(100vh - 84px);
  padding: 24px;
  background: #f5f7fb;
}

.page-heading {
  padding: 22px 24px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 6px 22px rgba(15, 23, 42, 0.05);
}

.eyebrow {
  margin: 0 0 6px;
  color: #4f46e5;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
}

h2 { margin: 0; color: #172033; font-size: 24px; }
.description { margin: 8px 0 0; color: #64748b; }

.config-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-top: 18px;
  padding: 16px 18px;
  border: 1px solid #dfe5ef;
  border-radius: 14px;
  background: #fff;
}

.config-summary { display: flex; align-items: center; gap: 12px; min-width: 0; }
.config-summary strong { color: #1e293b; }
.config-summary p { margin: 4px 0 0; color: #64748b; font-size: 13px; }
.config-status-icon {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  font-size: 18px;
}
.config-status-icon.is-ready { color: #047857; background: #d1fae5; }
.config-status-icon.is-warning { color: #b45309; background: #fef3c7; }

.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 520px));
  gap: 18px;
  margin-top: 20px;
}

.tool-card {
  display: grid;
  grid-template-columns: 54px 1fr;
  gap: 16px;
  align-items: start;
  padding: 22px;
  border: 1px solid #dfe5ef;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.06);
}

.tool-icon {
  width: 54px;
  height: 54px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  color: #fff;
  font-size: 26px;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
}

.tool-content h3 { margin: 2px 0 8px; color: #1e293b; font-size: 18px; }
.tool-content p { margin: 0; color: #64748b; line-height: 1.65; }
.tool-tags { display: flex; gap: 8px; margin-top: 12px; }
.tool-card > .el-button { grid-column: 1 / -1; width: 100%; margin-top: 4px; }

.config-alert { margin-bottom: 20px; }
.password-field { width: 100%; }
.field-hint { display: block; margin-top: 6px; color: #909399; font-size: 12px; line-height: 1.4; }
.dialog-footer { display: flex; align-items: center; width: 100%; }
.footer-spacer { flex: 1; }

@media (max-width: 640px) {
  .script-tools-page { padding: 12px; }
  .config-bar { align-items: stretch; flex-direction: column; }
  .config-bar > .el-button { width: 100%; }
  .tool-grid { grid-template-columns: 1fr; }
}
</style>

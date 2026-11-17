<template>
  <div class="python-tools-gateway">
    <div v-if="loading" class="gateway-state">
      <app-icon name="refresh" :size="40" spin class="state-icon" />
      <h3>正在打开 Python 脚本工作台</h3>
      <p>正在读取当前 ERP 用户的脚本权限并建立安全会话。</p>
    </div>

    <div v-else-if="errorMessage" class="gateway-state error-state">
      <app-icon name="warning" :size="40" class="state-icon" />
      <h3>脚本工作台暂时无法打开</h3>
      <p>{{ errorMessage }}</p>
      <el-button type="primary" @click="initialize"><app-icon name="resync" :size="15" class="btn-icon" />重新连接</el-button>
    </div>

    <iframe
      v-else
      class="workbench-frame"
      :src="workbenchUrl"
      title="Python 脚本工作台"
      referrerpolicy="no-referrer"
    />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { createPythonToolsSession } from '@/api/sop/scriptTools'

const loading = ref(true)
const errorMessage = ref('')
const workbenchUrl = ref('')

function javaProxyBase() {
  const apiPrefix = String(import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return new URL(`${apiPrefix}/sop/image-sop/proxy`, window.location.origin).toString()
}

function buildWorkbenchUrl(data) {
  const rawUrl = String(data?.workbenchUrl || '').trim()
  if (!rawUrl) throw new Error('Java 后端未配置 Python 脚本工作台地址')
  const url = new URL(rawUrl, window.location.origin)
  if (['127.0.0.1', 'localhost'].includes(url.hostname)
      && !['127.0.0.1', 'localhost'].includes(window.location.hostname)) {
    url.hostname = window.location.hostname
  }
  const permissions = Array.isArray(data?.permissions) ? data.permissions.filter(Boolean) : []
  url.searchParams.set('permissions', permissions.join(','))
  url.searchParams.set('image_proxy_base', javaProxyBase())
  url.searchParams.set('erp_session', String(data?.workbenchSession || ''))
  url.searchParams.set('erp_user_id', String(data?.userId || ''))
  url.searchParams.set('embedded', '1')
  return url.toString()
}

async function initialize() {
  loading.value = true
  errorMessage.value = ''
  workbenchUrl.value = ''
  try {
    const response = await createPythonToolsSession()
    workbenchUrl.value = buildWorkbenchUrl(response?.data || {})
  } catch (error) {
    errorMessage.value = error?.message || '脚本工作台会话创建失败'
  } finally {
    loading.value = false
  }
}

onMounted(initialize)
</script>

<style scoped>
.python-tools-gateway {
  height: calc(100vh - 84px);
  min-height: 680px;
  overflow: hidden;
  background: var(--jb-page, #f5f7fb);
}
.workbench-frame { width: 100%; height: 100%; display: block; border: 0; background: var(--jb-page, #f5f7fb); }
.gateway-state {
  height: 100%; padding: 36px; display: flex; flex-direction: column; align-items: center;
  justify-content: center; color: var(--jb-ink-500, #5a6b85); text-align: center;
}
.gateway-state h3 { margin: 14px 0 6px; color: var(--jb-ink-700, #24334a); font-size: 20px; }
.gateway-state p { margin: 0 0 18px; }
.gateway-state .el-button { border-radius: 8px; font-weight: 500; }
.btn-icon { margin-right: 5px; vertical-align: -2px; }
.state-icon { color: var(--jb-brand-500, #1257d6); }
.error-state .state-icon { color: #f5b545; }
</style>

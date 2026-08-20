<template>
  <div class="python-tools-gateway">
    <div v-if="loading" class="gateway-state">
      <el-icon class="state-icon is-loading"><Loading /></el-icon>
      <h3>正在打开 Python 脚本工作台</h3>
      <p>正在读取当前 ERP 用户的脚本权限并建立安全会话。</p>
    </div>

    <div v-else-if="errorMessage" class="gateway-state error-state">
      <el-icon class="state-icon"><WarningFilled /></el-icon>
      <h3>脚本工作台暂时无法打开</h3>
      <p>{{ errorMessage }}</p>
      <el-button type="primary" :icon="RefreshRight" @click="initialize">重新连接</el-button>
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
import { Loading, RefreshRight, WarningFilled } from '@element-plus/icons-vue'
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
  background: #f3f6fb;
}
.workbench-frame { width: 100%; height: 100%; display: block; border: 0; background: #f3f6fb; }
.gateway-state {
  height: 100%; padding: 36px; display: flex; flex-direction: column; align-items: center;
  justify-content: center; color: #64748b; text-align: center;
}
.gateway-state h3 { margin: 14px 0 6px; color: #1e293b; font-size: 20px; }
.gateway-state p { margin: 0 0 18px; }
.state-icon { color: #4f46e5; font-size: 40px; }
.error-state .state-icon { color: #f59e0b; }
</style>

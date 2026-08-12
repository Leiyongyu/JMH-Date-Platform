<template>
  <div class="image-sop-page">
    <section class="workspace-bar">
      <div class="workspace-title">
        <div class="logo-tile"><el-icon><PictureFilled /></el-icon></div>
        <div>
          <div class="eyebrow">SOP · IMAGE WORKBENCH</div>
          <h2>图片 SOP</h2>
        </div>
      </div>
      <div class="workspace-meta">
        <el-tag :type="statusTagType" effect="light" round>
          <span class="status-dot" :class="serviceStatus"></span>{{ statusText }}
        </el-tag>
        <el-tag v-if="lingxingText" :type="lingxingOk ? 'success' : 'warning'" effect="plain" round>
          {{ lingxingText }}
        </el-tag>
        <el-button :icon="RefreshRight" :loading="initializing" @click="initialize">重新连接</el-button>
        <el-button :icon="FullScreen" :disabled="!workbenchUrl" @click="openStandalone">新窗口打开</el-button>
      </div>
    </section>

    <section class="frame-shell">
      <div v-if="initializing" class="state-panel">
        <el-icon class="state-icon is-loading"><Loading /></el-icon>
        <h3>正在连接图片 SOP 服务</h3>
        <p>正在建立 ERP 安全会话并检查 Python 服务。</p>
      </div>

      <div v-else-if="errorMessage" class="state-panel error-state">
        <el-icon class="state-icon"><WarningFilled /></el-icon>
        <h3>图片 SOP 暂时不可用</h3>
        <p>{{ errorMessage }}</p>
        <el-button type="primary" :icon="RefreshRight" @click="initialize">重新连接</el-button>
        <div class="hint">请确认 Python 8010 服务已启动，并且 Java 与 Python 使用相同的内部令牌。</div>
      </div>

      <template v-else>
        <div v-if="frameLoading" class="frame-loading">
          <el-icon class="is-loading"><Loading /></el-icon><span>工作台加载中…</span>
        </div>
        <iframe
          :key="frameKey"
          class="workbench-frame"
          :src="workbenchUrl"
          title="图片SOP工作台"
          referrerpolicy="no-referrer"
          @load="frameLoading = false"
        />
      </template>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { FullScreen, Loading, PictureFilled, RefreshRight, WarningFilled } from '@element-plus/icons-vue'
import { createImageSopSession } from '@/api/sop/imageSop'

const initializing = ref(true)
const frameLoading = ref(true)
const errorMessage = ref('')
const serviceStatus = ref('checking')
const workbenchUrl = ref('')
const lingxingOk = ref(false)
const lingxingText = ref('')
const frameKey = ref(0)

const statusText = computed(() => ({
  online: 'Python 服务正常',
  offline: 'Python 服务异常',
  checking: '正在检查服务'
}[serviceStatus.value]))

const statusTagType = computed(() => ({
  online: 'success',
  offline: 'danger',
  checking: 'info'
}[serviceStatus.value]))

function proxyBase() {
  const baseApi = String(import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return `${baseApi}/sop/image-sop/proxy`
}

async function checkHealth(base, session) {
  const query = new URLSearchParams({ erp_session: session })
  const response = await fetch(`${base}/api/health?${query.toString()}`, {
    headers: { Accept: 'application/json' },
    credentials: 'same-origin'
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok || !data.ok) {
    throw new Error(data.detail || `Python 服务返回 HTTP ${response.status}`)
  }
  lingxingOk.value = Boolean(data.lingxing?.configured && data.lingxing?.token_ok)
  lingxingText.value = lingxingOk.value ? '领星连接正常' : '领星配置待检查'
}

async function initialize() {
  initializing.value = true
  frameLoading.value = true
  errorMessage.value = ''
  serviceStatus.value = 'checking'
  lingxingText.value = ''
  workbenchUrl.value = ''
  try {
    const response = await createImageSopSession()
    const session = response?.data?.session
    if (!session) throw new Error('Java 后端未返回图片SOP安全会话')
    const base = proxyBase()
    await checkHealth(base, session)
    const query = new URLSearchParams({
      api_base: base,
      erp_session: session,
      embedded: '1'
    })
    workbenchUrl.value = `${base}/index.html?${query.toString()}`
    serviceStatus.value = 'online'
    frameKey.value += 1
  } catch (error) {
    serviceStatus.value = 'offline'
    errorMessage.value = error?.message || String(error)
  } finally {
    initializing.value = false
  }
}

function openStandalone() {
  if (workbenchUrl.value) window.open(workbenchUrl.value, '_blank', 'noopener,noreferrer')
}

onMounted(initialize)
</script>

<style scoped>
.image-sop-page {
  height: calc(100vh - 84px);
  min-height: 680px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #f5f7fb;
}

.workspace-bar {
  min-height: 64px;
  padding: 9px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 4px 18px rgba(15, 23, 42, 0.05);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.workspace-title, .workspace-meta { display: flex; align-items: center; gap: 10px; }
.workspace-meta { justify-content: flex-end; flex-wrap: wrap; }
.logo-tile {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 22px;
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  box-shadow: 0 8px 18px rgba(79, 70, 229, 0.22);
}
.eyebrow { color: #6366f1; font-size: 10px; font-weight: 800; letter-spacing: 0.14em; }
h2 { margin: 1px 0 0; color: #172033; font-size: 20px; line-height: 1.2; }
.status-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-right: 6px;
  border-radius: 50%;
  background: #94a3b8;
}
.status-dot.online { background: #10b981; box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.14); }
.status-dot.offline { background: #ef4444; box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.12); }

.frame-shell {
  min-height: 0;
  flex: 1;
  position: relative;
  overflow: hidden;
  border: 1px solid #dfe5ef;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.06);
}
.workbench-frame { width: 100%; height: 100%; display: block; border: 0; background: #eef2ff; }
.frame-loading {
  position: absolute;
  z-index: 2;
  inset: 0;
  display: grid;
  place-content: center;
  grid-auto-flow: column;
  gap: 8px;
  color: #64748b;
  background: rgba(255, 255, 255, 0.88);
}
.state-panel {
  height: 100%;
  padding: 36px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #64748b;
  text-align: center;
}
.state-panel h3 { margin: 14px 0 5px; color: #1e293b; font-size: 20px; }
.state-panel p { margin: 0 0 18px; }
.state-icon { color: #6366f1; font-size: 38px; }
.error-state .state-icon { color: #f59e0b; }
.hint { margin-top: 16px; color: #94a3b8; font-size: 12px; }

@media (max-width: 900px) {
  .image-sop-page { height: calc(100vh - 74px); padding: 8px; }
  .workspace-bar { align-items: flex-start; flex-direction: column; }
  .workspace-meta { justify-content: flex-start; }
}
</style>

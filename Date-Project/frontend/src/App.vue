<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import registry from './scripts.js'
import { resolveScriptUrl } from './scriptUrl.js'
import ScriptFrame from './components/ScriptFrame.vue'

const OPEN_MODE_LABELS = {
  embed: '内嵌',
  new_window: '新窗口',
  redirect: '跳转',
}

const pageParams = new URLSearchParams(window.location.search)

const grantedPermissions = new Set(
  String(pageParams.get('permissions') || '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean),
)
const requestedTools = new Set(
  String(pageParams.get('tools') || '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean),
)
const imageProxyBase = pageParams.get('image_proxy_base') || ''
const erpSession = pageParams.get('erp_session') || ''

// 可见性过滤：
// - 有 permissions 参数：按 ERP 授予的按钮权限过滤（permission 为空 = 公开）
// - 有 tools 参数（旧版）：按 code 过滤
// - 开发环境且无任何参数：显示全部，便于本地调试
// - 生产环境且无任何参数：一律不显示（安全边界由 ERP 下发权限保障）
const scripts = computed(() => {
  const hasPerms = pageParams.has('permissions')
  const hasTools = pageParams.has('tools')
  if (import.meta.env.DEV && !hasPerms && !hasTools) return registry
  return registry.filter((script) => {
    if (hasTools && !requestedTools.has(script.code)) return false
    if (hasPerms) return !script.permission || grantedPermissions.has(script.permission)
    return false
  })
})

const activeCode = ref('')
const activeScript = computed(() => (
  scripts.value.find((script) => script.code === activeCode.value) || null
))

function normalizeCode(raw) {
  const code = String(raw || '').replace(/^#\/?/, '').split('?')[0]
  return scripts.value.some((script) => script.code === code) ? code : ''
}

function syncRoute() {
  const code = normalizeCode(window.location.hash)
  activeCode.value = code
}

function openScript(script) {
  if (script.openMode === 'embed') {
    activeCode.value = script.code
    window.history.replaceState(null, '', `#/${script.code}`)
    return
  }
  const url = resolveScriptUrl(script, { imageProxyBase, erpSession, isDev: import.meta.env.DEV })
  if (!url) return
  if (script.openMode === 'redirect') {
    window.location.href = url
  } else {
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}

function openInNewWindow(script) {
  const url = resolveScriptUrl(script, { imageProxyBase, erpSession, isDev: import.meta.env.DEV })
  if (url) window.open(url, '_blank', 'noopener,noreferrer')
}

function goHome() {
  activeCode.value = ''
  window.history.replaceState(null, '', '#/')
}

onMounted(() => {
  syncRoute()
  window.addEventListener('hashchange', syncRoute)
})

onBeforeUnmount(() => window.removeEventListener('hashchange', syncRoute))
</script>

<template>
  <div class="workbench">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">J</div>
        <div class="brand-copy">
          <strong>JMH 脚本中心</strong>
          <span>Python Automation Workbench</span>
        </div>
      </div>
      <div class="topbar-meta">
        <span class="count-badge">已授权 {{ scripts.length }} 个脚本</span>
        <span class="erp-badge" title="入口由 ERP 菜单与按钮权限管理">ERP 入口</span>
      </div>
    </header>

    <main class="stage">
      <!-- 内嵌详情视图 -->
      <template v-if="activeScript">
        <div class="detail-bar">
          <button type="button" class="back-button" @click="goHome">‹ 返回脚本列表</button>
          <span class="detail-crumb">{{ activeScript.name }}</span>
        </div>
        <div class="detail-frame">
          <ScriptFrame
            :script="activeScript"
            :proxy-base="imageProxyBase"
            :erp-session="erpSession"
          />
        </div>
      </template>

      <!-- 卡片网格 -->
      <template v-else-if="scripts.length">
        <div class="grid-caption">
          <h1>自动化工具</h1>
          <p>点击卡片打开脚本，或使用「新窗口」在独立标签页运行。</p>
        </div>
        <div class="script-grid">
          <article
            v-for="script in scripts"
            :key="script.code"
            class="script-card"
            role="button"
            tabindex="0"
            @click="openScript(script)"
            @keydown.enter="openScript(script)"
          >
            <div class="card-top">
              <span class="card-icon">{{ script.icon }}</span>
              <span class="open-mode-tag">{{ OPEN_MODE_LABELS[script.openMode] || '打开' }}</span>
            </div>
            <h2 class="card-name">{{ script.name }}</h2>
            <p class="card-desc">{{ script.description || 'Python 自动化脚本' }}</p>
            <div class="card-meta">
              <span v-if="script.permission" class="perm-tag" :title="script.permission">
                {{ script.permission }}
              </span>
              <span v-else class="perm-tag public">公开</span>
            </div>
            <div class="card-actions">
              <button type="button" class="card-open" @click.stop="openScript(script)">打开</button>
              <button type="button" class="card-new-window" @click.stop="openInNewWindow(script)">
                新窗口
              </button>
            </div>
          </article>
        </div>
      </template>

      <!-- 空态 -->
      <section v-else class="empty-state">
        <div class="empty-icon">!</div>
        <h2>当前账号没有可用的 Python 脚本</h2>
        <p>请联系 ERP 管理员为当前角色分配对应脚本的按钮权限后，重新进入脚本菜单。</p>
      </section>
    </main>
  </div>
</template>

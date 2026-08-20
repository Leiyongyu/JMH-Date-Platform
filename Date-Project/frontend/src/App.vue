<script setup>
import { computed, ref } from 'vue'
import registry from './scripts.js'
import { resolveScriptUrl } from './scriptUrl.js'

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
const erpUserId = pageParams.get('erp_user_id') || ''

// 生产环境只展示 ERP 明确下发权限的脚本；本地开发无参数时展示全部。
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

const searchText = ref('')
const activeCategory = ref('全部')
const categories = computed(() => [
  '全部',
  ...new Set(scripts.value.map((script) => script.category || '其他')),
])
const visibleScripts = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  return scripts.value.filter((script) => {
    if (activeCategory.value !== '全部' && (script.category || '其他') !== activeCategory.value) return false
    if (!keyword) return true
    return [script.name, script.description, script.category, ...(script.tags || [])]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword))
  })
})

function openScript(script) {
  const url = resolveScriptUrl(script, {
    imageProxyBase,
    erpSession,
    erpUserId,
    isDev: import.meta.env.DEV,
  })
  if (url) window.open(url, '_blank', 'noopener,noreferrer')
}
</script>

<template>
  <div class="workbench">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">J</div>
        <div class="brand-copy">
          <strong>JMH 脚本中心</strong>
          <span>PYTHON AUTOMATION</span>
        </div>
      </div>
      <div class="topbar-meta">
        <span class="count-badge">{{ scripts.length }} 个可用工具</span>
        <span class="erp-badge">ERP 权限接入</span>
      </div>
    </header>

    <main class="stage">
      <section class="hero-panel">
        <div class="hero-copy">
          <span class="hero-eyebrow">AUTOMATION WORKSPACE</span>
          <h1>脚本工具工作台</h1>
          <p>集中管理日常自动化工具。所有脚本均在独立窗口运行，不影响当前 ERP 页面。</p>
        </div>
        <div class="hero-stat">
          <strong>{{ scripts.length }}</strong>
          <span>已授权组件</span>
        </div>
      </section>

      <template v-if="scripts.length">
        <section class="tool-toolbar">
          <label class="search-box">
            <span class="search-icon">⌕</span>
            <input v-model="searchText" type="search" placeholder="搜索脚本名称或功能" />
          </label>
          <nav class="category-tabs" aria-label="脚本分类">
            <button
              v-for="category in categories"
              :key="category"
              type="button"
              :class="['category-tab', { active: activeCategory === category }]"
              @click="activeCategory = category"
            >
              {{ category }}
            </button>
          </nav>
        </section>

        <section v-if="visibleScripts.length" class="script-grid">
          <article v-for="script in visibleScripts" :key="script.code" class="script-card">
            <div class="card-heading">
              <span class="card-icon">{{ script.icon }}</span>
              <span class="available-tag"><i />可使用</span>
            </div>
            <div class="card-content">
              <span class="card-category">{{ script.category || '其他工具' }}</span>
              <h2>{{ script.name }}</h2>
              <p>{{ script.description || 'Python 自动化脚本' }}</p>
            </div>
            <div v-if="script.tags?.length" class="card-tags">
              <span v-for="tag in script.tags" :key="tag">{{ tag }}</span>
            </div>
            <button type="button" class="launch-button" @click="openScript(script)">
              <span>新窗口打开</span>
              <b aria-hidden="true">↗</b>
            </button>
          </article>
        </section>

        <section v-else class="empty-state compact">
          <div class="empty-icon">⌕</div>
          <h2>没有找到匹配的脚本</h2>
          <p>请更换关键词或选择其他分类。</p>
        </section>
      </template>

      <section v-else class="empty-state">
        <div class="empty-icon">!</div>
        <h2>当前账号没有可用的 Python 脚本</h2>
        <p>请联系 ERP 管理员为当前角色分配对应脚本按钮权限，然后重新进入脚本菜单。</p>
      </section>
    </main>
  </div>
</template>

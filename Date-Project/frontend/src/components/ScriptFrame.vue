<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { resolveScriptUrl } from '../scriptUrl.js'

const props = defineProps({
  script: { type: Object, required: true },
  proxyBase: { type: String, default: '' },
  erpSession: { type: String, default: '' },
})

const frameKey = ref(0)
const loading = ref(true)
const loadTimer = ref(null)

const frameUrl = computed(() => resolveScriptUrl(props.script, {
  imageProxyBase: props.proxyBase,
  erpSession: props.erpSession,
  isDev: import.meta.env.DEV,
}))

function startLoading() {
  loading.value = true
  if (loadTimer.value) window.clearTimeout(loadTimer.value)
  loadTimer.value = window.setTimeout(() => { loading.value = false }, 12000)
}

function reload() {
  startLoading()
  frameKey.value += 1
}

function loaded() {
  loading.value = false
  if (loadTimer.value) window.clearTimeout(loadTimer.value)
  loadTimer.value = null
}

function openStandalone() {
  if (frameUrl.value) window.open(frameUrl.value, '_blank', 'noopener,noreferrer')
}

startLoading()
onBeforeUnmount(() => {
  if (loadTimer.value) window.clearTimeout(loadTimer.value)
})
</script>

<template>
  <section class="tool-shell">
    <header class="tool-heading">
      <div>
        <div class="tool-kicker">PYTHON AUTOMATION</div>
        <h2>{{ script.name }}</h2>
        <p>{{ script.description || '当前脚本作为统一 Python 工作台组件运行。' }}</p>
      </div>
      <div class="tool-actions">
        <button type="button" class="secondary-action" @click="reload">重新加载</button>
        <button type="button" class="primary-action" @click="openStandalone">新窗口打开</button>
      </div>
    </header>

    <div class="frame-wrap">
      <div v-if="loading" class="frame-loading">
        <span class="loading-ring" />
        <strong>正在加载{{ script.name }}</strong>
        <small>首次进入时需要初始化脚本服务</small>
      </div>
      <iframe
        :key="frameKey"
        class="tool-frame"
        :src="frameUrl"
        :title="script.name"
        allow="clipboard-read; clipboard-write"
        @load="loaded"
      />
    </div>
  </section>
</template>

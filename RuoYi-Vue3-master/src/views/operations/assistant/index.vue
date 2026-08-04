<template>
  <div class="assistant-page">
    <div class="assistant-toolbar">
      <div>
        <h3>运营助手</h3>
        <span>领星刊登、补货填充、SOP 图片生成与批次库存工具</span>
      </div>
      <div class="assistant-actions">
        <el-button icon="Refresh" @click="refreshFrame">刷新</el-button>
        <el-button type="primary" plain icon="TopRight" @click="openWindow">新窗口打开</el-button>
      </div>
    </div>

    <div class="assistant-frame-wrap" v-loading="loading" element-loading-text="正在加载运营助手…">
      <iframe
        :key="frameKey"
        :src="assistantUrl"
        title="运营助手"
        allow="clipboard-read; clipboard-write"
        @load="loading = false"
      />
    </div>
  </div>
</template>

<script setup>
const configuredUrl = String(import.meta.env.VITE_OPERATION_ASSISTANT_URL || '').trim()
const assistantUrl = configuredUrl || '/operation-assistant/hub/'
const loading = ref(true)
const frameKey = ref(0)

function refreshFrame() {
  loading.value = true
  frameKey.value += 1
}

function openWindow() {
  window.open(assistantUrl, '_blank', 'noopener,noreferrer')
}
</script>

<style scoped>
.assistant-page {
  height: calc(100vh - 84px);
  min-height: 640px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  background: #f4f6f8;
}

.assistant-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 12px;
  padding: 14px 18px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 1px 4px rgb(15 23 42 / 8%);
}

.assistant-toolbar h3 {
  margin: 0 0 4px;
  color: #1f2937;
  font-size: 18px;
}

.assistant-toolbar span {
  color: #64748b;
  font-size: 13px;
}

.assistant-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
}

.assistant-frame-wrap {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 1px 6px rgb(15 23 42 / 10%);
}

.assistant-frame-wrap iframe {
  width: 100%;
  height: 100%;
  border: 0;
  background: #fff;
}

@media (max-width: 768px) {
  .assistant-page {
    padding: 8px;
  }

  .assistant-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>

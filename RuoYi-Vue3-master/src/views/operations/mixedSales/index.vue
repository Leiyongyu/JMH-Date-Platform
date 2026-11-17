<template>
  <div class="mixed-sales-page">
    <div class="platform-toolbar">
      <h2>混销</h2>
      <el-radio-group v-model="platform" aria-label="切换平台" class="platform-switch">
        <el-radio-button value="AMZ">Amazon</el-radio-button>
        <el-radio-button value="EBAY">eBay</el-radio-button>
      </el-radio-group>
    </div>
    <amz-panel v-if="platform === 'AMZ'" />
    <ebay-panel v-else />
  </div>
</template>

<script setup name="MixedSales">
import { ref } from 'vue'
import AmzPanel from './AmzPanel.vue'
import EbayPanel from './EbayPanel.vue'
const platform = ref('AMZ')
</script>

<style scoped>
.mixed-sales-page { background: var(--jb-page, #f5f7fb); min-height: calc(100vh - 84px); }
.platform-toolbar { display: flex; align-items: center; gap: 22px; padding: 20px 20px 0; }
.platform-toolbar h2 { margin: 0; font-size: 20px; color: var(--jb-ink-700, #24334a); }

/* 平台切换：分段控件 */
.platform-switch :deep(.el-radio-button__inner) {
  border: none !important;
  background: transparent;
  box-shadow: none !important;
  border-radius: 8px !important;
  height: 32px;
  line-height: 32px;
  padding: 0 18px;
  font-size: 13px;
  color: var(--jb-ink-500, #5a6b85);
  transition: color .2s;
}
.platform-switch {
  background: #e9eef7;
  border-radius: 10px;
  padding: 3px;
}
.platform-switch :deep(.el-radio-button.is-active .el-radio-button__inner) {
  background: linear-gradient(135deg, var(--jb-brand-600, #0e45a8) 0%, var(--jb-brand-500, #1257d6) 60%, #2c74f0 100%);
  color: #fff;
  box-shadow: 0 2px 6px rgba(18, 87, 214, .3) !important;
}
</style>

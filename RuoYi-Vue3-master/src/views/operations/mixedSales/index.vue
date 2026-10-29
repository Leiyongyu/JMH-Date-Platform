<template>
  <div class="mixed-sales-page">
    <div class="platform-toolbar">
      <h2>混销</h2>
      <el-radio-group v-model="platform" aria-label="切换平台">
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
.platform-toolbar { display: flex; align-items: center; gap: 22px; padding: 20px 20px 0; }
.platform-toolbar h2 { margin: 0; font-size: 20px; }
</style>

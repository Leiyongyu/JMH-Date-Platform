<template>
  <div class="amz-replenishment-entry">
    <div class="region-switch">
      <span class="region-label">补货分组：</span>
      <el-radio-group v-model="activeRegion" size="large">
        <el-radio-button value="US">美国组</el-radio-button>
        <el-radio-button value="EU">欧洲组</el-radio-button>
      </el-radio-group>
    </div>

    <KeepAlive>
      <component :is="activePage" :key="activeRegion" />
    </KeepAlive>
  </div>
</template>

<script setup name="AmzReplenishment">
import { computed, ref } from 'vue'
import AmzUsReplenishment from './us/index.vue'
import AmzEuReplenishment from './eu/index.vue'

const activeRegion = ref('US')
const activePage = computed(() => activeRegion.value === 'EU' ? AmzEuReplenishment : AmzUsReplenishment)
</script>

<style scoped>
.amz-replenishment-entry {
  background: #f5f7fa;
  min-height: 100%;
}

.region-switch {
  display: flex;
  align-items: center;
  padding: 14px 20px 0;
  background: #f5f7fa;
}

.region-label {
  margin-right: 10px;
  color: #606266;
  font-size: 14px;
  font-weight: 600;
}
</style>

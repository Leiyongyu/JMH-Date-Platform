<template>
  <nav class="dashboard-nav" aria-label="首页报表板块">
    <router-link to="/index" class="dashboard-tab" :class="{ active: active === 'product' }"
                 :aria-current="active === 'product' ? 'page' : undefined">商品分析</router-link>
    <router-link v-if="salesVisible" to="/sales-dashboard/index" class="dashboard-tab"
                 :class="{ active: active === 'sales' }" :aria-current="active === 'sales' ? 'page' : undefined">销售看板</router-link>
  </nav>
</template>

<script setup>
defineProps({
  active: { type: String, required: true, validator: value => ['product', 'sales'].includes(value) },
  salesVisible: { type: Boolean, default: false }
})
</script>

<style scoped>
.dashboard-nav { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid var(--el-border-color-light); }
.dashboard-tab { display: inline-flex; align-items: center; justify-content: center; padding: 10px 24px; border-radius: 6px; border: 1px solid transparent; font-size: 15px; font-weight: 500; color: var(--el-text-color-regular); background: var(--el-bg-color); }
.dashboard-tab:hover, .dashboard-tab:focus-visible { color: var(--el-color-primary); border-color: var(--el-color-primary); }
.dashboard-tab.active { color: var(--el-color-white); background: var(--el-color-primary); border-color: var(--el-color-primary); }
</style>

<template>
  <div class="app-container" aria-label="销售看板页面">
    <SalesDashboard v-if="canView" />
    <el-empty v-else description="暂无销售看板查看权限" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { checkPermi } from '@/utils/permission'
import SalesDashboard from '@/components/SalesDashboard/index.vue'

defineOptions({ name: 'SalesDashboard' })
const canView = computed(() => checkPermi(['finance:salesDashboard:list']))
</script>

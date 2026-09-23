<template>
  <div class="app-container home" aria-label="首页">
    <div v-if="canViewInventory" class="home-switch" role="group" aria-label="首页看板切换">
      <el-button :type="activeBoard === 'products' ? 'primary' : 'default'" :aria-pressed="activeBoard === 'products'" @click="activeBoard = 'products'">商品分析</el-button>
      <el-button :type="activeBoard === 'inventory' ? 'primary' : 'default'" :aria-pressed="activeBoard === 'inventory'" @click="activeBoard = 'inventory'">库存分析</el-button>
    </div>
    <HomeInventoryDashboard v-if="activeBoard === 'inventory' && canViewInventory" />
    <template v-else-if="availablePlatforms.length">
      <div class="owner-dashboards">
        <AmzOwnerSkuChart v-for="platform in availablePlatforms" :key="platform.value" :platform="platform.value" />
      </div>
      <div class="price-dashboards">
        <ListingPriceTierChart v-for="platform in availablePlatforms" :key="`price-${platform.value}`" :platform="platform.value" />
      </div>
      <div class="nature-dashboards">
        <ProductNatureChart v-for="platform in availablePlatforms" :key="`nature-${platform.value}`" :platform="platform.value" />
      </div>
    </template>
    <el-empty v-else description="暂无可查看的首页看板" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { checkPermi } from '@/utils/permission'
import AmzOwnerSkuChart from '@/components/AmzOwnerSkuChart/index.vue'
import ListingPriceTierChart from '@/components/ListingPriceTierChart/index.vue'
import ProductNatureChart from '@/components/ProductNatureChart/index.vue'
import HomeInventoryDashboard from '@/components/HomeInventoryDashboard/index.vue'

defineOptions({ name: 'Index' })
const canViewInventory = checkPermi(['finance:monthlyInventoryReport:list']) && checkPermi(['finance:slowMovingClearance:list'])
const activeBoard = ref('products')
const availablePlatforms = computed(() => [
  { value: 'amz', label: 'AMZ', permission: 'operations:amzReplenishment:list' },
  { value: 'ebay', label: 'eBay', permission: 'operations:ebayReplenishmentV2:list' }
].filter(platform => checkPermi([platform.permission])))
</script>

<style scoped>
.home {
  min-height: calc(100vh - 84px);
}
.home-switch { display: flex; gap: 4px; width: fit-content; padding: 4px; border: 1px solid var(--el-border-color-lighter); border-radius: 10px; background: var(--el-fill-color-light); margin-bottom: 18px; }
.home-switch :deep(.el-button) { border: 0; border-radius: 7px; padding: 9px 20px; height: 34px; background: transparent; }
.home-switch :deep(.el-button--primary) { background: var(--el-color-primary); box-shadow: 0 2px 5px #2563eb20; }
.home-switch :deep(.el-button + .el-button) { margin-left: 0; }
.owner-dashboards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); align-items: start; gap: 14px; width: 100%; }
.price-dashboards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: 14px; width: 100%; margin-top: 14px; }
.nature-dashboards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; width: 100%; margin-top: 14px; }
@media (max-width: 1199px) { .owner-dashboards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 639px) { .owner-dashboards, .price-dashboards, .nature-dashboards { grid-template-columns: minmax(0, 1fr); } }
</style>

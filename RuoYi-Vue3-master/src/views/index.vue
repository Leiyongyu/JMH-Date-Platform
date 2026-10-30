<template>
  <div class="app-container home" aria-label="首页">
    <h2 class="home-title">商品分析</h2>
    <section v-if="availablePlatforms.length" aria-label="商品分析">
      <div class="owner-dashboards">
        <AmzOwnerSkuChart v-for="platform in availablePlatforms" :key="platform.value" :platform="platform.value" />
      </div>
      <div class="price-dashboards">
        <ListingPriceTierChart v-for="platform in availablePlatforms" :key="`price-${platform.value}`" :platform="platform.value" />
      </div>
      <div class="nature-dashboards">
        <ProductNatureChart v-for="platform in availablePlatforms" :key="`nature-${platform.value}`" :platform="platform.value" />
      </div>
    </section>
    <el-empty v-else description="暂无可查看的商品分析报表" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { checkPermi } from '@/utils/permission'
import AmzOwnerSkuChart from '@/components/AmzOwnerSkuChart/index.vue'
import ListingPriceTierChart from '@/components/ListingPriceTierChart/index.vue'
import ProductNatureChart from '@/components/ProductNatureChart/index.vue'

defineOptions({ name: 'Index' })
const availablePlatforms = computed(() => [
  { value: 'amz', label: 'AMZ', permission: 'operations:amzReplenishment:list' },
  { value: 'ebay', label: 'eBay', permission: 'operations:ebayReplenishmentV2:list' }
].filter(platform => checkPermi([platform.permission])))
</script>

<style scoped>
.home {
  min-height: calc(100vh - 84px);
}
.home-title { margin: 0 0 20px; font-size: 20px; font-weight: 600; }
.owner-dashboards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); align-items: start; gap: 14px; width: 100%; }
.price-dashboards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: 14px; width: 100%; margin-top: 14px; }
.nature-dashboards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; width: 100%; margin-top: 14px; }
@media (max-width: 1199px) { .owner-dashboards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 639px) { .owner-dashboards, .price-dashboards, .nature-dashboards { grid-template-columns: minmax(0, 1fr); } }
</style>

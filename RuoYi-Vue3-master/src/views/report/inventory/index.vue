<template>
  <div class="app-container">
    <el-page-header content="库存报表" @back="$router.push('/')" />
    <el-divider />

    <el-table :data="reports" border stripe highlight-current-row @row-click="(row) => $router.push(row.path)">
      <el-table-column label="报表名称" prop="name" width="240">
        <template #default="{row}">
          <el-link type="primary" :underline="false">
            <el-icon :size="18"><component :is="row.icon" /></el-icon>
            {{ row.name }}
          </el-link>
        </template>
      </el-table-column>
      <el-table-column label="说明" prop="desc" min-width="400" />
    </el-table>
  </div>
</template>

<script setup name="ReportInventory">
import { Money } from '@element-plus/icons-vue'

const reports = [
  { name: '月初库存货值检查', desc: '每月期初库存数量、成本、异常状态检查', icon: Money, path: '/report/inventory-opening' }
  // 后续在这里加链接
]
</script>

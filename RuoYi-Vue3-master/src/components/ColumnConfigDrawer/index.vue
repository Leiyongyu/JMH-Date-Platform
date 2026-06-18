<template>
  <el-drawer :model-value="showDrawer" title="列设置" :size="480" direction="rtl">
    <div style="display:flex;gap:16px;min-height:300px">
      <div style="width:160px;flex-shrink:0;border-right:1px solid #eee;padding:8px;max-height:400px;overflow-y:auto">
        <div style="margin-bottom:8px"><el-checkbox :model-value="isAllChecked" @change="toggleAll">全选</el-checkbox></div>
        <el-checkbox v-for="c in leftCols" :key="c.key" :model-value="c.checked" :disabled="c.disabled" @change="() => toggleColumn(c.key)" style="display:block;margin-bottom:4px">{{ c.title }}</el-checkbox>
      </div>
      <div style="flex:1;padding:8px;max-height:400px;overflow-y:auto">
        <div style="font-size:12px;color:#999;margin-bottom:8px">已选字段（拖拽排序）</div>
        <div v-for="(c, idx) in selectedColumns" :key="c.key"
             :class="['config-item', { fixed: fixedKeys.includes(c.key) }]"
             :draggable="!fixedKeys.includes(c.key)"
             @dragstart="() => onDragStart(idx)" @dragover="onDragOver" @drop="() => onDrop(idx)" @dragend="onDragEnd">
          <span class="drag-handle" :style="{visibility: fixedKeys.includes(c.key)?'hidden':'visible'}">⋮⋮</span>
          <span>{{ c.label }}</span>
        </div>
      </div>
    </div>
    <template #footer>
      <div style="text-align:right">
        <el-button @click="onCancel">取消</el-button>
        <el-button type="primary" @click="onApply">应用</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
defineProps({
  showDrawer: Boolean, leftCols: Array, selectedColumns: Array, isAllChecked: Boolean, fixedKeys: Array,
  toggleAll: Function, toggleColumn: Function, onDragStart: Function, onDragOver: Function, onDrop: Function, onDragEnd: Function
})
const emit = defineEmits(['close', 'save'])
function onCancel() { emit('close') }
function onApply() { emit('save'); emit('close') }
</script>

<style scoped>
.config-item { display:flex;align-items:center;gap:6px;padding:6px 10px;margin-bottom:4px;background:#fafafa;border-radius:4px;cursor:grab;font-size:13px;border:1px solid #eee }
.config-item:hover { background:#e6f4ff }
.config-item.fixed { background:#f5f5f5;color:#999;cursor:default }
.drag-handle { color:#bbb;font-size:14px;user-select:none }
</style>

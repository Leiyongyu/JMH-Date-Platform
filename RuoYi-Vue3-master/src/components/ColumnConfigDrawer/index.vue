<template>
  <el-drawer v-model="drawerVisible" title="列配置" size="480px" append-to-body>
    <div class="column-config">
      <div class="column-config__panel">
        <div class="column-config__head">
          <span>可选字段</span>
          <el-checkbox :model-value="allChecked" :indeterminate="indeterminate" @change="toggleAll">全选</el-checkbox>
        </div>
        <el-scrollbar height="calc(100vh - 220px)">
          <div
            v-for="col in columns"
            :key="col.key"
            class="column-config__option"
          >
            <el-checkbox
              :model-value="editingKeys.includes(col.key)"
              :disabled="fixedKeys.includes(col.key)"
              @change="toggleColumn(col.key)"
            >
              {{ col.label }}
            </el-checkbox>
          </div>
        </el-scrollbar>
      </div>

      <div class="column-config__panel">
        <div class="column-config__head">
          <span>已选字段</span>
          <span class="column-config__hint">拖拽排序</span>
        </div>
        <el-scrollbar height="calc(100vh - 220px)">
          <div
            v-for="(col, index) in selectedColumns"
            :key="col.key"
            class="column-config__selected"
            :class="{ 'is-fixed': fixedKeys.includes(col.key) }"
            draggable="true"
            @dragstart="onDragStart(index, col.key)"
            @dragover.prevent
            @drop="onDrop(index)"
            @dragend="dragIndex = null"
          >
            <el-icon><Rank /></el-icon>
            <span>{{ col.label }}</span>
            <el-tag v-if="fixedKeys.includes(col.key)" size="small" type="info">固定</el-tag>
          </div>
        </el-scrollbar>
      </div>
    </div>

    <template #footer>
      <el-button @click="drawerVisible = false">取消</el-button>
      <el-button type="primary" @click="handleApply">应用</el-button>
    </template>
  </el-drawer>
</template>

<script setup>
import { Rank } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  columns: {
    type: Array,
    default: () => []
  },
  fixedKeys: {
    type: Array,
    default: () => []
  },
  visibleKeys: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue', 'apply'])
const editingKeys = ref([])
const dragIndex = ref(null)

const drawerVisible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const allNonFixedKeys = computed(() => props.columns.map((col) => col.key).filter((key) => !props.fixedKeys.includes(key)))
const selectedColumns = computed(() => editingKeys.value.map((key) => props.columns.find((col) => col.key === key)).filter(Boolean))
const allChecked = computed(() => allNonFixedKeys.value.every((key) => editingKeys.value.includes(key)))
const indeterminate = computed(() => allNonFixedKeys.value.some((key) => editingKeys.value.includes(key)) && !allChecked.value)

watch(() => props.modelValue, (val) => {
  if (val) editingKeys.value = normalizeKeys(props.visibleKeys)
})

function normalizeKeys(keys) {
  const allKeys = props.columns.map((col) => col.key)
  const next = []
  props.fixedKeys.forEach((key) => {
    if (allKeys.includes(key) && !next.includes(key)) next.push(key)
  })
  ;(Array.isArray(keys) ? keys : []).forEach((key) => {
    if (allKeys.includes(key) && !next.includes(key)) next.push(key)
  })
  return next
}

function toggleAll() {
  if (allChecked.value) {
    editingKeys.value = props.fixedKeys.filter((key) => props.columns.some((col) => col.key === key))
  } else {
    editingKeys.value = props.columns.map((col) => col.key)
  }
}

function toggleColumn(key) {
  if (props.fixedKeys.includes(key)) return
  if (editingKeys.value.includes(key)) {
    editingKeys.value = editingKeys.value.filter((item) => item !== key)
  } else {
    editingKeys.value.push(key)
  }
}

function onDragStart(index, key) {
  if (props.fixedKeys.includes(key)) return
  dragIndex.value = index
}

function onDrop(index) {
  if (dragIndex.value === null || dragIndex.value === index) return
  const targetKey = editingKeys.value[index]
  if (props.fixedKeys.includes(targetKey)) return
  const next = [...editingKeys.value]
  const [moved] = next.splice(dragIndex.value, 1)
  next.splice(index, 0, moved)
  editingKeys.value = normalizeKeys(next)
}

function handleApply() {
  emit('apply', editingKeys.value)
  drawerVisible.value = false
}
</script>

<style scoped>
.column-config {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.column-config__panel {
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  overflow: hidden;
  background: #fff;
}

.column-config__head {
  height: 42px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e4e7ed;
  color: #303133;
  font-weight: 600;
}

.column-config__hint {
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}

.column-config__option,
.column-config__selected {
  min-height: 36px;
  padding: 0 12px;
  display: flex;
  align-items: center;
}

.column-config__selected {
  gap: 8px;
  cursor: move;
  border-bottom: 1px solid #f0f2f5;
}

.column-config__selected.is-fixed {
  color: #909399;
  cursor: not-allowed;
  background: #fafafa;
}
</style>

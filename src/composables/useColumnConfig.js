import { ref, computed } from 'vue'
import { getColumnConfig, saveColumnConfig } from '@/api/system/userColumnConfig'

export function useColumnConfig(pageKey, fixedKeys = [], columnMap = {}) {
  const allKeys = Object.keys(columnMap)
  const visibleKeys = ref([...allKeys])
  const showDrawer = ref(false)
  const loading = ref(false)
  let snapshot = []

  async function init() {
    loading.value = true
    try {
      const res = await getColumnConfig(pageKey)
      if (res?.data && Array.isArray(JSON.parse(res.data))) {
        const saved = JSON.parse(res.data)
        const newKeys = allKeys.filter(k => !saved.includes(k))
        visibleKeys.value = [...saved.filter(k => allKeys.includes(k)), ...newKeys]
      }
    } catch (e) { /* 无配置则用默认 */ }
    finally { loading.value = false }
  }

  function openDrawer() {
    snapshot = [...visibleKeys.value]
    showDrawer.value = true
  }

  function closeDrawer(apply) {
    if (apply) save()
    else visibleKeys.value = [...snapshot]
    showDrawer.value = false
  }

  const selectedColumns = computed(() =>
    visibleKeys.value.filter(k => allKeys.includes(k)).map(k => ({ key: k, ...columnMap[k] }))
  )

  const leftCols = computed(() =>
    allKeys.map(k => ({
      key: k, title: columnMap[k]?.label || k,
      checked: visibleKeys.value.includes(k), disabled: fixedKeys.includes(k)
    }))
  )

  const isAllChecked = computed(() => visibleKeys.value.length === allKeys.length)

  function toggleAll() {
    if (isAllChecked.value) visibleKeys.value = [...fixedKeys]
    else visibleKeys.value = [...allKeys]
  }

  function toggleColumn(key) {
    if (fixedKeys.includes(key)) return
    const idx = visibleKeys.value.indexOf(key)
    if (idx >= 0) visibleKeys.value.splice(idx, 1)
    else visibleKeys.value.push(key)
  }

  let dragIdx = -1
  function onDragStart(idx) { dragIdx = idx }
  function onDragOver(e) { e.preventDefault() }
  function onDrop(idx) {
    if (dragIdx < 0 || dragIdx === idx) return
    const arr = [...visibleKeys.value]
    const item = arr.splice(dragIdx, 1)[0]
    if (fixedKeys.includes(item) && idx > fixedKeys.length - 1) return
    arr.splice(idx, 0, item)
    visibleKeys.value = arr
    dragIdx = -1
  }
  function onDragEnd() { dragIdx = -1 }

  async function save() {
    const keys = visibleKeys.value.filter(k => allKeys.includes(k))
    try { await saveColumnConfig(pageKey, JSON.stringify(keys)) }
    catch { /* silent */ }
  }

  function colVisible(key) { return visibleKeys.value.includes(key) }

  return {
    visibleKeys, showDrawer, loading, selectedColumns, leftCols, isAllChecked,
    init, openDrawer, closeDrawer, colVisible,
    toggleAll, toggleColumn, onDragStart, onDragOver, onDrop, onDragEnd
  }
}

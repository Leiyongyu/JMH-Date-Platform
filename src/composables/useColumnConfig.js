import { ref, computed } from 'vue'
import { getColumnConfig, saveColumnConfig } from '@/api/system/userColumnConfig'

/**
 * 服务端持久化列配置 composable。
 * @param {string} pageKey 页面标识
 * @param {string[]} fixedKeys 固定列（不可取消/不可拖到非常规区域）
 * @param {object} columnMap { key: { label, prop } }
 */
export function useColumnConfig(pageKey, fixedKeys = [], columnMap = {}) {
  const allKeys = Object.keys(columnMap)
  const visibleKeys = ref([...allKeys])
  const showDrawer = ref(false)
  const loading = ref(false)

  // 初始化：从服务端加载已保存配置
  async function init() {
    loading.value = true
    try {
      const res = await getColumnConfig(pageKey)
      if (res?.data && Array.isArray(JSON.parse(res.data))) {
        const saved = JSON.parse(res.data)
        // 过滤掉不存在的key, 新字段追加到末尾
        const newKeys = allKeys.filter(k => !saved.includes(k))
        visibleKeys.value = [...saved.filter(k => allKeys.includes(k)), ...newKeys]
      }
    } catch (e) { /* 无配置则用默认 */ }
    finally { loading.value = false }
  }

  // 已选列（按顺序）
  const selectedColumns = computed(() =>
    visibleKeys.value.filter(k => allKeys.includes(k)).map(k => ({ key: k, ...columnMap[k] }))
  )

  // 可切换的列（固定列不可取消）
  const leftCols = computed(() =>
    allKeys.map(k => ({
      key: k,
      title: columnMap[k]?.label || k,
      checked: visibleKeys.value.includes(k),
      disabled: fixedKeys.includes(k)
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

  // 拖拽排序
  let dragIdx = -1
  function onDragStart(idx) { dragIdx = idx }
  function onDragOver(e) { e.preventDefault() }
  function onDrop(idx) {
    if (dragIdx < 0 || dragIdx === idx) return
    const arr = [...visibleKeys.value]
    const item = arr.splice(dragIdx, 1)[0]
    // 固定列不可拖到非常规位置
    if (fixedKeys.includes(item) && idx > fixedKeys.length - 1) return
    arr.splice(idx, 0, item)
    visibleKeys.value = arr
    dragIdx = -1
  }
  function onDragEnd() { dragIdx = -1 }

  async function save(proxy) {
    const keys = visibleKeys.value.filter(k => allKeys.includes(k))
    try {
      await saveColumnConfig(pageKey, JSON.stringify(keys))
      if (proxy) proxy.$modal.msgSuccess('列配置已保存')
    } catch (e) {
      if (proxy) proxy.$modal.msgError('保存失败')
    }
  }

  return {
    visibleKeys, showDrawer, loading, selectedColumns, leftCols, isAllChecked,
    init, toggleAll, toggleColumn, onDragStart, onDragOver, onDrop, onDragEnd, save
  }
}

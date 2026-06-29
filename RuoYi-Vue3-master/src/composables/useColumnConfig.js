import { computed, ref } from 'vue'
import { getUserColumnConfig, saveUserColumnConfig } from '@/api/system/userColumnConfig'

export function useColumnConfig(pageKey, columns, fixedKeys = [], requiredKeys = fixedKeys) {
  const showColumnDrawer = ref(false)
  const allKeys = columns.map((item) => item.key)
  const columnMap = new Map(columns.map((item) => [item.key, item]))
  const visibleKeys = ref([...allKeys])
  const columnConfigLoaded = ref(false)
  const cacheKey = `user-column-config:${pageKey}`

  function normalizeKeys(keys, appendMissing = true) {
    const valid = Array.isArray(keys) ? keys.filter((key) => columnMap.has(key)) : []
    const validSet = new Set(valid)
    const merged = []
    requiredKeys.forEach((key) => {
      if (columnMap.has(key) && !merged.includes(key)) merged.push(key)
    })
    fixedKeys.forEach((key) => {
      if (columnMap.has(key) && !merged.includes(key) && (validSet.has(key) || appendMissing)) merged.push(key)
    })
    valid.forEach((key) => {
      if (!fixedKeys.includes(key) && !merged.includes(key)) merged.push(key)
    })
    if (appendMissing) {
      allKeys.forEach((key) => {
        if (!merged.includes(key)) merged.push(key)
      })
    }
    return merged
  }

  function parseSavedConfig(raw) {
    let parsed = raw
    for (let i = 0; i < 3 && typeof parsed === 'string'; i++) {
      if (!parsed.trim()) break
      parsed = JSON.parse(parsed)
    }
    if (Array.isArray(parsed)) {
      return {
        visibleKeys: parsed,
        knownKeys: parsed,
        appendMissing: false
      }
    }
    if (!parsed || typeof parsed !== 'object') {
      return {
        visibleKeys: [],
        knownKeys: [],
        appendMissing: true
      }
    }
    return {
      visibleKeys: Array.isArray(parsed.visibleKeys) ? parsed.visibleKeys : [],
      knownKeys: Array.isArray(parsed.allKeys) ? parsed.allKeys : [],
      appendMissing: true
    }
  }

  function restoreKeys(saved) {
    const restored = normalizeKeys(saved.visibleKeys, false)
    if (!saved.appendMissing) return restored

    const knownKeys = new Set(saved.knownKeys || [])
    allKeys.forEach((key) => {
      if (!knownKeys.has(key) && !restored.includes(key)) {
        restored.push(key)
      }
    })
    return restored
  }

  async function initColumnConfig() {
    try {
      const res = await getUserColumnConfig(pageKey)
      if (res.data) {
        visibleKeys.value = restoreKeys(parseSavedConfig(res.data))
        localStorage.setItem(cacheKey, JSON.stringify({
          version: 1,
          visibleKeys: visibleKeys.value,
          allKeys
        }))
      } else {
        restoreLocalConfig()
      }
    } catch (e) {
      restoreLocalConfig()
    } finally {
      columnConfigLoaded.value = true
    }
  }

  async function applyColumnConfig(keys) {
    visibleKeys.value = normalizeKeys(keys, false)
    const payload = JSON.stringify({
      version: 1,
      visibleKeys: visibleKeys.value,
      allKeys
    })
    localStorage.setItem(cacheKey, payload)
    await saveUserColumnConfig(pageKey, payload)
  }

  function restoreLocalConfig() {
    const local = localStorage.getItem(cacheKey)
    if (local) {
      try {
        visibleKeys.value = restoreKeys(parseSavedConfig(local))
        return
      } catch (e) {}
    }
    visibleKeys.value = normalizeKeys([], true)
  }

  function isColumnVisible(key) {
    return visibleKeys.value.includes(key)
  }

  function openColumnConfig() {
    showColumnDrawer.value = true
  }

  const visibleColumns = computed(() => visibleKeys.value.map((key) => columnMap.get(key)).filter(Boolean))
  const exportColumns = computed(() => visibleColumns.value.map((item) => ({ key: item.key, title: item.label })))
  const columnTableKey = computed(() => `${pageKey}:${visibleKeys.value.join('|')}`)

  return {
    showColumnDrawer,
    columnConfigLoaded,
    columnTableKey,
    visibleKeys,
    visibleColumns,
    exportColumns,
    isColumnVisible,
    openColumnConfig,
    initColumnConfig,
    applyColumnConfig
  }
}

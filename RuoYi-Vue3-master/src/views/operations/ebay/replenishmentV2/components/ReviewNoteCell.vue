<template>
  <div class="review-note-input">
    <div class="note-editor">
      <el-tooltip :content="value || '暂无备注，点击填写'" placement="top" :disabled="editing">
        <el-input :model-value="editing ? draft : value" :readonly="saving" :disabled="disabled"
          :class="{ 'note-preview': !editing && value }"
          :aria-label="field === 'operations' ? '运营备注' : '开发备注'" :maxlength="2000"
          placeholder="填写备注" size="small" @focus="startEdit" @update:model-value="updateDraft"
          @blur="finishEdit" @keydown.enter.exact="handleEnter" />
      </el-tooltip>
      <!-- Keep the native input value intact: switching a truncated value on focus can disturb selection. -->
      <span v-if="!editing && value" class="note-preview-label" aria-hidden="true">{{ preview }}</span>
    </div>
    <div v-if="saving || error" class="note-status" role="status">{{ saving ? '保存中…' : error }}</div>
    <el-button v-if="error" link type="warning" @mousedown.prevent @click="discard">放弃编辑</el-button>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { saveEbayReplenishmentReviewNote } from '@/api/operations/ebay/replenishmentV2'

const props = defineProps({ site: String, sku: String, field: String, value: { type: String, default: '' },
  version: { type: Number, default: 0 }, disabled: Boolean })
const emit = defineEmits(['saved', 'busy'])
const preview = computed(() => Array.from(props.value || '').slice(0, 5).join(''))
const editing = ref(false)
const focused = ref(false)
const saving = ref(false)
const draft = ref('')
const error = ref('')
let baseVersion = 0
let baseValue = ''
let pending = null

function handleEnter(event) {
  // 中文输入法确认候选词时的回车不能提交半成品备注。
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  return save()
}

function startEdit() {
  if (props.disabled) return
  focused.value = true
  if (pending || editing.value) return
  editing.value = true
  if (error.value) return
  draft.value = props.value
  baseValue = props.value
  baseVersion = props.version
  error.value = ''
  emit('busy', true)
}

function updateDraft(value) {
  draft.value = value
}

function discard() {
  draft.value = baseValue
  error.value = ''
  editing.value = false
  focused.value = false
  emit('busy', false)
}

async function save() {
  if (pending) return pending
  if (props.disabled || draft.value === baseValue) return true
  saving.value = true
  error.value = ''
  const text = draft.value
  pending = (async () => {
    try {
      const response = await saveEbayReplenishmentReviewNote({ site: props.site, sku: props.sku,
        field: props.field, text, expected_version: baseVersion })
      baseValue = text
      baseVersion = Number(response.data[`${props.field}_version`])
      emit('saved', response.data)
      return true
    } catch (e) {
      error.value = '保存失败，内容仍保留。若提示版本冲突，请复制备注后刷新核对。'
      return false
    } finally {
      saving.value = false
      pending = null
    }
  })()
  return pending
}

async function finishEdit() {
  focused.value = false
  const success = await save()
  // Failed drafts remain editable and must not become a truncated preview.
  if (!success) return
  // A slow blur save must not close an input that the user has already focused again.
  editing.value = focused.value
  emit('busy', focused.value)
}
</script>

<style scoped>
.review-note-input { min-width: 0; }
.note-editor { position: relative; width: 85px; }
.note-preview :deep(input) { color: transparent; }
.note-preview-label { position: absolute; left: 8px; top: 0; line-height: 24px; max-width: calc(100% - 16px); overflow: hidden; white-space: nowrap; pointer-events: none; color: var(--el-text-color-regular); font-size: 12px; }
.note-status { margin-top: 4px; color: #e6a23c; font-size: 12px; overflow-wrap: anywhere; }
</style>

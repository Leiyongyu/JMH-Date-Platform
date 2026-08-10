<template>
  <div class="ai-assistant-entry">
    <el-tooltip content="AI助手" effect="dark" placement="bottom">
      <button class="ai-nav-trigger" type="button" aria-label="打开AI助手" @click="openAssistant">
        <svg viewBox="0 0 32 32" aria-hidden="true">
          <path d="M16 3v3M12.8 3h6.4" />
          <rect x="6" y="7" width="20" height="16" rx="6" />
          <circle cx="12.5" cy="14" r="1.6" class="robot-eye" />
          <circle cx="19.5" cy="14" r="1.6" class="robot-eye" />
          <path d="M12 18.5c1.1.9 2.4 1.3 4 1.3s2.9-.4 4-1.3M6 13H3.8v5H6M26 13h2.2v5H26M11 23v4M21 23v4M9 28h4M19 28h4" />
        </svg>
      </button>
    </el-tooltip>

    <el-drawer
      v-model="visible"
      class="ai-assistant-drawer"
      direction="rtl"
      size="520px"
      append-to-body
      :with-header="false"
      :close-on-click-modal="false"
      @opened="handleOpened"
    >
      <div class="assistant-shell">
        <div class="assistant-header">
          <div class="assistant-avatar">
            <svg viewBox="0 0 32 32" aria-hidden="true">
              <rect x="6" y="7" width="20" height="17" rx="6" />
              <circle cx="12.5" cy="14.5" r="1.7" />
              <circle cx="19.5" cy="14.5" r="1.7" />
              <path d="M12 19c1.1.8 2.4 1.2 4 1.2s2.9-.4 4-1.2M16 3v4" />
            </svg>
          </div>
          <div class="assistant-title">
            <strong>JMH AI助手</strong>
            <span><i :class="['status-dot', statusClass]" />{{ statusText }}</span>
          </div>
          <div class="header-actions">
            <button
              class="new-chat-button"
              type="button"
              :disabled="loading || conversationLoading"
              @click="startNewConversation"
            >
              新对话
            </button>
            <button class="drawer-close-button" type="button" aria-label="关闭AI助手" @click="visible = false">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
        </div>

        <div class="conversation-toolbar">
          <el-select
            v-model="activeConversationId"
            class="conversation-select"
            placeholder="新的对话"
            :loading="conversationLoading"
            :disabled="loading"
            @change="loadConversation"
          >
            <el-option
              v-for="conversation in conversations"
              :key="conversation.id"
              :label="conversation.title"
              :value="conversation.id"
            >
              <div class="conversation-option">
                <span>{{ conversation.title }}</span>
                <small>{{ formatConversationTime(conversation.updatedAt) }}</small>
              </div>
            </el-option>
          </el-select>
          <button
            class="delete-chat-button"
            type="button"
            :disabled="!activeConversationId || loading || conversationLoading"
            @click="removeCurrentConversation"
          >
            删除
          </button>
        </div>

        <div ref="messageContainer" class="message-container">
          <div v-if="messages.length === 0" class="welcome-panel">
            <div class="welcome-avatar">AI</div>
            <h3>你好，我是JMH AI助手</h3>
            <p>可以帮助你解答问题、整理思路和分析文本。当前版本不会直接读取或修改ERP业务数据。</p>
            <div class="suggestion-list">
              <button type="button" @click="useSuggestion('帮我整理一份今日工作计划')">整理今日工作计划</button>
              <button type="button" @click="useSuggestion('帮我分析一个业务问题，需要我提供哪些信息？')">分析业务问题</button>
              <button type="button" @click="useSuggestion('帮我把下面的内容整理成清晰的要点：')">整理文本要点</button>
            </div>
          </div>

          <div
            v-for="message in messages"
            :key="message.id"
            :class="['message-row', message.role]"
          >
            <div class="message-avatar">{{ message.role === 'user' ? userInitial : 'AI' }}</div>
            <div class="message-body">
              <div class="message-name">{{ message.role === 'user' ? userDisplayName : 'JMH AI助手' }}</div>
              <div :class="['message-bubble', { error: message.error }]">{{ message.content }}</div>
            </div>
          </div>

          <div v-if="loading" class="message-row assistant">
            <div class="message-avatar">AI</div>
            <div class="message-body">
              <div class="message-name">JMH AI助手</div>
              <div class="message-bubble typing-bubble">
                <i /><i /><i />
              </div>
            </div>
          </div>
        </div>

        <div class="composer">
          <el-input
            ref="inputRef"
            v-model="inputText"
            type="textarea"
            :rows="3"
            resize="none"
            maxlength="4000"
            show-word-limit
            :disabled="loading || conversationLoading || statusState !== 'ready'"
            :placeholder="composerPlaceholder"
            @keydown="handleInputKeydown"
          />
          <div class="composer-footer">
            <span>Enter发送，Shift + Enter换行</span>
            <el-button
              type="primary"
              :loading="loading"
              :disabled="!canSend"
              @click="sendMessage"
            >
              发送
            </el-button>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import {
  chatWithAiAssistant,
  createAiConversation,
  deleteAiConversation,
  getAiAssistantStatus,
  getAiConversation,
  listAiConversations
} from '@/api/system/aiAssistant'
import useUserStore from '@/store/modules/user'

const route = useRoute()
const userStore = useUserStore()
const visible = ref(false)
const loading = ref(false)
const conversationLoading = ref(false)
const inputText = ref('')
const messages = ref([])
const conversations = ref([])
const activeConversationId = ref('')
const messageContainer = ref()
const inputRef = ref()
const statusState = ref('checking')
const statusModel = ref('')

const userDisplayName = computed(() => userStore.nickName || userStore.name || '我')
const userInitial = computed(() => userDisplayName.value.trim().slice(0, 1).toUpperCase() || '我')
const statusClass = computed(() => ({
  ready: 'online',
  unconfigured: 'warning',
  offline: 'offline',
  checking: 'checking'
}[statusState.value]))
const statusText = computed(() => {
  if (statusState.value === 'ready') return statusModel.value ? `已连接 · ${statusModel.value}` : '已连接'
  if (statusState.value === 'unconfigured') return '等待配置API Key'
  if (statusState.value === 'offline') return 'Python服务不可用'
  return '正在检查服务'
})
const composerPlaceholder = computed(() => {
  if (statusState.value === 'unconfigured') return '请先在Python服务的 .env 中配置 DEEPSEEK_API_KEY'
  if (statusState.value === 'offline') return 'Python AI服务暂时不可用'
  if (statusState.value === 'checking') return '正在检查AI服务配置...'
  return '请输入你想咨询的问题...'
})
const canSend = computed(() => (
  statusState.value === 'ready' && !loading.value && !conversationLoading.value && inputText.value.trim().length > 0
))

async function openAssistant() {
  visible.value = true
  await Promise.all([loadStatus(), loadConversations()])
}

async function loadStatus() {
  statusState.value = 'checking'
  try {
    const response = await getAiAssistantStatus(createRequestId('status'))
    const data = response.data || {}
    statusModel.value = data.model || ''
    statusState.value = data.configured ? 'ready' : 'unconfigured'
  } catch (error) {
    statusState.value = 'offline'
  }
}

function handleOpened() {
  scrollToBottom()
  nextTick(() => inputRef.value?.focus())
}

function useSuggestion(text) {
  inputText.value = text
  nextTick(() => inputRef.value?.focus())
}

function handleInputKeydown(event) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  sendMessage()
}

async function sendMessage() {
  const content = inputText.value.trim()
  if (!content || !canSend.value) return

  messages.value.push(createMessage('user', content))
  inputText.value = ''
  loading.value = true
  await scrollToBottom()

  try {
    if (!activeConversationId.value) {
      const created = await createAiConversation({}, createRequestId('conversation-create'))
      activeConversationId.value = created.data?.id || ''
      if (!activeConversationId.value) throw new Error('创建AI对话失败')
    }
    const response = await chatWithAiAssistant({
      conversation_id: activeConversationId.value,
      message: content,
      page_context: {
        path: route.fullPath,
        title: route.meta?.title || document.title
      }
    }, createRequestId('chat'))
    const answer = response.data?.content?.trim()
    if (!answer) throw new Error('AI助手未返回有效回答')
    const assistantMessage = createMessage('assistant', answer)
    assistantMessage.id = response.data?.assistantMessageId || assistantMessage.id
    messages.value.push(assistantMessage)
    await loadConversations(false)
  } catch (error) {
    const detail = error?.msg || error?.message || 'AI助手暂时无法回答，请稍后重试'
    messages.value.push(createMessage('assistant', detail, true))
  } finally {
    loading.value = false
    await scrollToBottom()
    nextTick(() => inputRef.value?.focus())
  }
}

async function startNewConversation() {
  if (loading.value || conversationLoading.value) return
  try {
    if (messages.value.length > 0) {
      await ElMessageBox.confirm('当前对话已经保存，确定开始一个新对话吗？', '新对话', {
        confirmButtonText: '开始新对话',
        cancelButtonText: '取消',
        type: 'info'
      })
    }
    activeConversationId.value = ''
    messages.value = []
    inputText.value = ''
    ElMessage.success('已开始新对话')
    nextTick(() => inputRef.value?.focus())
  } catch (error) {
    // 用户取消，不做处理。
  }
}

async function loadConversations(loadActive = true) {
  conversationLoading.value = true
  try {
    const response = await listAiConversations(createRequestId('conversation-list'))
    conversations.value = Array.isArray(response.data) ? response.data : []
    if (!loadActive) return
    const activeExists = conversations.value.some(item => item.id === activeConversationId.value)
    const targetId = activeExists ? activeConversationId.value : conversations.value[0]?.id
    if (targetId) {
      await loadConversation(targetId, false)
    } else {
      activeConversationId.value = ''
      messages.value = []
    }
  } catch (error) {
    ElMessage.error(error?.msg || error?.message || '加载AI历史对话失败')
  } finally {
    conversationLoading.value = false
  }
}

async function loadConversation(conversationId, manageLoading = true) {
  if (!conversationId || loading.value) return
  if (manageLoading) conversationLoading.value = true
  try {
    const response = await getAiConversation(conversationId, createRequestId('conversation-detail'))
    const data = response.data || {}
    activeConversationId.value = data.id || conversationId
    messages.value = Array.isArray(data.messages)
      ? data.messages.map(message => ({
          id: message.id || `${Date.now()}-${Math.random().toString(16).slice(2)}`,
          role: message.role,
          content: message.content,
          error: Boolean(message.error)
        }))
      : []
    await scrollToBottom()
  } catch (error) {
    ElMessage.error(error?.msg || error?.message || '加载对话内容失败')
  } finally {
    if (manageLoading) conversationLoading.value = false
  }
}

async function removeCurrentConversation() {
  const conversationId = activeConversationId.value
  if (!conversationId || loading.value || conversationLoading.value) return
  try {
    await ElMessageBox.confirm('删除后将无法恢复，确定删除当前对话吗？', '删除对话', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    conversationLoading.value = true
    await deleteAiConversation(conversationId, createRequestId('conversation-delete'))
    activeConversationId.value = ''
    messages.value = []
    ElMessage.success('对话已删除')
    await loadConversations()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.msg || error?.message || '删除对话失败')
    }
  } finally {
    conversationLoading.value = false
  }
}

function createMessage(role, content, error = false) {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    error
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messageContainer.value) {
    messageContainer.value.scrollTop = messageContainer.value.scrollHeight
  }
}

function formatConversationTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
  })
}

function createRequestId(scope) {
  const random = Math.random().toString(16).slice(2, 10)
  return `erp-ai-${scope}-${Date.now()}-${random}`
}
</script>

<style lang="scss" scoped>
.ai-assistant-entry {
  display: flex;
  align-items: center;
  height: 100%;
}

.ai-nav-trigger {
  width: 36px;
  height: 36px;
  padding: 6px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--el-text-color-regular, #5a5e66);
  cursor: pointer;
  transition: color 0.2s, background 0.2s, transform 0.2s;

  &:hover {
    color: var(--el-color-primary, #409eff);
    background: var(--el-color-primary-light-9, #ecf5ff);
    transform: translateY(-1px);
  }

  svg {
    display: block;
    width: 24px;
    height: 24px;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }

  .robot-eye {
    fill: currentColor;
    stroke: none;
  }
}

:global(.ai-assistant-drawer) {
  max-width: calc(100vw - 24px);
  border-radius: 16px 0 0 16px;
  overflow: hidden;
}

:global(.ai-assistant-drawer .el-drawer__body) {
  padding: 0;
  overflow: hidden;
}

.assistant-shell {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
}

.assistant-header {
  min-height: 72px;
  padding: 14px 16px 14px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
  background: linear-gradient(135deg, var(--el-color-primary-light-9, #ecf5ff), var(--el-bg-color, #fff) 62%);
}

.assistant-avatar {
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  display: grid;
  place-items: center;
  border-radius: 13px;
  color: #fff;
  background: linear-gradient(145deg, #66b2ff, #3478f6);
  box-shadow: 0 6px 16px rgba(64, 158, 255, 0.25);

  svg {
    width: 27px;
    height: 27px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.8;
    stroke-linecap: round;
  }

  circle {
    fill: currentColor;
    stroke: none;
  }
}

.assistant-title {
  min-width: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
  line-height: 1.35;

  strong {
    color: var(--el-text-color-primary, #303133);
    font-size: 17px;
  }

  span {
    margin-top: 3px;
    color: var(--el-text-color-secondary, #909399);
    font-size: 12px;
  }
}

.status-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-right: 6px;
  border-radius: 50%;
  background: #a8abb2;

  &.online { background: #41b883; box-shadow: 0 0 0 3px rgba(65, 184, 131, 0.14); }
  &.warning { background: #e6a23c; }
  &.offline { background: #f56c6c; }
  &.checking { animation: status-pulse 1s infinite alternate; }
}

.new-chat-button {
  height: 32px;
  padding: 0 13px;
  border: 1px solid var(--el-border-color, #dcdfe6);
  border-radius: 9px;
  background: var(--el-bg-color, #fff);
  color: var(--el-text-color-regular, #606266);
  cursor: pointer;

  &:hover:not(:disabled) {
    color: var(--el-color-primary, #409eff);
    border-color: var(--el-color-primary-light-5, #a0cfff);
  }

  &:disabled { opacity: 0.45; cursor: not-allowed; }
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 7px;
}

.drawer-close-button {
  width: 32px;
  height: 32px;
  padding: 7px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--el-text-color-secondary, #909399);
  cursor: pointer;
  transition: color 0.2s, background 0.2s;

  &:hover {
    color: var(--el-text-color-primary, #303133);
    background: var(--el-fill-color, #f0f2f5);
  }

  svg {
    display: block;
    width: 18px;
    height: 18px;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-width: 1.8;
  }
}

.conversation-toolbar {
  padding: 10px 16px;
  display: flex;
  align-items: center;
  gap: 9px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
  background: var(--el-bg-color, #fff);
}

.conversation-select {
  min-width: 0;
  flex: 1;

  :deep(.el-select__wrapper) {
    min-height: 36px;
    border-radius: 9px;
  }
}

.conversation-option {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;

  span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  small {
    flex: none;
    color: var(--el-text-color-placeholder, #a8abb2);
    font-size: 11px;
  }
}

.delete-chat-button {
  height: 34px;
  padding: 0 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--el-text-color-secondary, #909399);
  cursor: pointer;

  &:hover:not(:disabled) {
    background: var(--el-color-danger-light-9, #fef0f0);
    color: var(--el-color-danger, #f56c6c);
  }

  &:disabled { opacity: 0.4; cursor: not-allowed; }
}

.message-container {
  flex: 1;
  min-height: 0;
  padding: 22px;
  overflow-y: auto;
  background: var(--el-fill-color-lighter, #fafafa);
  scroll-behavior: smooth;
}

.welcome-panel {
  max-width: 510px;
  margin: 34px auto;
  text-align: center;

  .welcome-avatar {
    width: 54px;
    height: 54px;
    margin: 0 auto 14px;
    display: grid;
    place-items: center;
    border-radius: 18px;
    background: linear-gradient(145deg, #66b2ff, #3478f6);
    color: #fff;
    font-weight: 700;
    box-shadow: 0 8px 24px rgba(64, 158, 255, 0.22);
  }

  h3 { margin: 0 0 8px; color: var(--el-text-color-primary, #303133); font-size: 18px; }
  p { margin: 0; color: var(--el-text-color-secondary, #909399); font-size: 13px; line-height: 1.7; }
}

.suggestion-list {
  margin-top: 22px;
  display: grid;
  gap: 9px;

  button {
    padding: 10px 14px;
    border: 1px solid var(--el-border-color-lighter, #ebeef5);
    border-radius: 10px;
    background: var(--el-bg-color, #fff);
    color: var(--el-text-color-regular, #606266);
    text-align: left;
    cursor: pointer;
    transition: border-color 0.2s, color 0.2s, transform 0.2s;

    &:hover {
      color: var(--el-color-primary, #409eff);
      border-color: var(--el-color-primary-light-5, #a0cfff);
      transform: translateX(2px);
    }
  }
}

.message-row {
  margin-bottom: 20px;
  display: flex;
  align-items: flex-start;
  gap: 10px;

  &.user { flex-direction: row-reverse; }
}

.message-avatar {
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  display: grid;
  place-items: center;
  border-radius: 11px;
  background: linear-gradient(145deg, #66b2ff, #3478f6);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.user .message-avatar { background: linear-gradient(145deg, #67c23a, #3ba272); }

.message-body { max-width: 78%; min-width: 0; }
.user .message-body { display: flex; align-items: flex-end; flex-direction: column; }
.message-name { margin: 0 2px 5px; color: var(--el-text-color-secondary, #909399); font-size: 11px; }

.message-bubble {
  padding: 11px 14px;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 4px 13px 13px 13px;
  background: var(--el-bg-color, #fff);
  color: var(--el-text-color-primary, #303133);
  font-size: 14px;
  line-height: 1.7;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  box-shadow: 0 2px 7px rgba(0, 0, 0, 0.035);

  &.error { color: var(--el-color-danger, #f56c6c); border-color: var(--el-color-danger-light-7, #fab6b6); }
}

.user .message-bubble {
  border: 0;
  border-radius: 13px 4px 13px 13px;
  background: var(--el-color-primary, #409eff);
  color: #fff;
}

.typing-bubble {
  height: 43px;
  display: flex;
  align-items: center;
  gap: 5px;

  i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--el-text-color-placeholder, #a8abb2);
    animation: typing 1.2s infinite ease-in-out;
  }
  i:nth-child(2) { animation-delay: 0.15s; }
  i:nth-child(3) { animation-delay: 0.3s; }
}

.composer {
  padding: 15px 18px 16px;
  border-top: 1px solid var(--el-border-color-lighter, #ebeef5);
  background: var(--el-bg-color, #fff);

  :deep(.el-textarea__inner) {
    padding: 11px 13px 24px;
    border-radius: 11px;
    box-shadow: 0 0 0 1px var(--el-border-color, #dcdfe6) inset;

    &:focus { box-shadow: 0 0 0 1px var(--el-color-primary, #409eff) inset; }
  }
}

.composer-footer {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;

  span { color: var(--el-text-color-placeholder, #a8abb2); font-size: 11px; }
  .el-button { min-width: 82px; border-radius: 9px; }
}

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.45; }
  30% { transform: translateY(-4px); opacity: 1; }
}

@keyframes status-pulse {
  from { opacity: 0.35; }
  to { opacity: 1; }
}

@media (max-width: 760px) {
  :global(.ai-assistant-drawer) {
    width: calc(100vw - 12px) !important;
    max-width: none;
  }

  .message-container { padding: 16px; }
  .message-body { max-width: 86%; }
  .assistant-header { padding-left: 14px; }
}
</style>

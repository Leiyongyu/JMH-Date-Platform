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
      size="640px"
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
            <el-popover placement="bottom-end" :width="320" trigger="click" @show="loadMemories">
              <template #reference>
                <button class="new-chat-button" type="button">记忆</button>
              </template>
              <div class="memory-panel">
                <div class="memory-title">助手记住的偏好（只影响回答习惯，不影响数据权限）</div>
                <div v-if="memoriesLoading" class="memory-empty">加载中...</div>
                <div v-else-if="memories.length === 0" class="memory-empty">暂无记忆。可以对助手说「以后默认看德国站」。</div>
                <div v-for="memory in memories" :key="memory.id" class="memory-item">
                  <span><em v-if="memory.status === 'pending'" class="memory-pending">待确认</em>{{ memory.content }}</span>
                  <span class="memory-actions">
                    <button v-if="memory.status === 'pending'" type="button" class="confirm" @click="confirmMemory(memory)">确认</button>
                    <button type="button" @click="removeMemory(memory)">删除</button>
                  </span>
                </div>
              </div>
            </el-popover>
            <button v-if="isAdmin" class="new-chat-button" type="button" @click="statsVisible = true">看板</button>
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
            <h3>你好，我是JMH数据助手</h3>
            <p>可以按你的账号权限查询绩效排名、销售看板、月度库存、eBay补货等数据，先规划再查询，结果附来源与统计区间。只读，不会修改任何数据。</p>
            <div class="suggestion-list">
              <button type="button" @click="useSuggestion('最新月份综合绩效排名前5名是谁？未分配有多少？')">最新绩效排名与未分配</button>
              <button type="button" @click="useSuggestion('对比Amazon最近两个月各组别的净销售额和毛利率')">Amazon 各组别销售对比</button>
              <button type="button" @click="useSuggestion('德国站建议补货量最大的10个SKU')">德国站补货建议</button>
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
              <div v-if="message.role === 'user' || message.error" :class="['message-bubble', { error: message.error }]">{{ message.content }}</div>
              <div v-else class="message-bubble answer-bubble">
                <AnswerContent :content="message.content" :results="message.run?.results || []" />
                <div v-if="verificationNotice(message.run?.verification)" class="verification-notice">
                  {{ verificationNotice(message.run.verification) }}
                </div>
              </div>
              <div v-if="message.run && pendingMemories(message.run).length" class="memory-suggestion">
                <div v-for="memory in pendingMemories(message.run)" :key="memory.id">
                  助手想记住：{{ memory.content }}
                  <button type="button" class="confirm" @click="confirmMemory(memory, message.run)">记住</button>
                  <button type="button" @click="removeMemory(memory, message.run)">不用</button>
                </div>
              </div>
              <div v-if="message.run?.runId" class="feedback-bar">
                <button type="button" :class="{ active: message.run.feedback?.rating === 1 }" @click="sendFeedback(message.run, 1)">有帮助</button>
                <button type="button" :class="{ active: message.run.feedback?.rating === -1 }" @click="sendFeedback(message.run, -1)">没帮助</button>
              </div>
              <div v-if="message.run" class="run-detail">
                <el-collapse>
                  <el-collapse-item v-if="message.run.thinking?.length" :title="`思考过程（${message.run.thinking.length}轮）`" name="thinking">
                    <div v-for="item in message.run.thinking" :key="item.round" class="thinking-round">
                      <div class="thinking-label">第{{ item.round }}轮</div>
                      <div class="thinking-text">{{ item.content }}</div>
                    </div>
                  </el-collapse-item>
                  <el-collapse-item v-if="message.run.plan?.length" :title="`执行计划 · ${planProgress(message.run.plan)}`" name="plan">
                    <ol class="plan-list">
                      <li v-for="(step, index) in message.run.plan" :key="index" :class="step.status">
                        <span>{{ step.title }}</span><small>{{ STEP_STATUS[step.status] || step.status }}</small>
                      </li>
                    </ol>
                    <div class="call-list">
                      <span v-for="step in message.run.steps" :key="step.seq" :class="['call-chip', step.status]">
                        {{ toolTitle(step.tool) }} ·{{ CALL_STATUS[step.status] || step.status }} · {{ step.durationMs }}ms
                      </span>
                    </div>
                  </el-collapse-item>
                  <el-collapse-item
                    v-for="(result, index) in message.run.results"
                    :key="`result-${index}`"
                    :title="`数据：${result.title}（${result.rowCount}行）`"
                    :name="`result-${index}`"
                  >
                    <div class="result-meta">来源：{{ result.source || '--' }} ｜ 统计区间：{{ result.period || '--' }}</div>
                    <div v-for="note in result.notes" :key="note" class="result-note">{{ note }}</div>
                    <el-table v-if="result.rows?.length" :data="result.rows.slice(0, 200)" size="small" max-height="320" border>
                      <el-table-column v-for="column in result.columns" :key="column.key" :prop="column.key" :label="column.label" min-width="96" show-overflow-tooltip>
                        <template #default="{ row }">{{ formatCell(row[column.key]) }}</template>
                      </el-table-column>
                    </el-table>
                  </el-collapse-item>
                </el-collapse>
              </div>
            </div>
          </div>

          <div v-if="loading" class="message-row assistant">
            <div class="message-avatar">AI</div>
            <div class="message-body">
              <div class="message-name">JMH AI助手</div>
              <div v-if="liveRun?.plan?.length || liveRun?.thinking?.length || liveRun?.answer" class="message-bubble live-plan">
                <div v-if="liveRun.plan?.length" class="live-progress">{{ planProgress(liveRun.plan) }}<span v-if="liveRun.steps?.length"> ｜ {{ callSummary(liveRun.steps) }}</span></div>
                <ol v-if="liveRun.plan?.length" class="plan-list">
                  <li v-for="(step, index) in liveRun.plan" :key="index" :class="step.status">
                    <span>{{ step.title }}</span><small>{{ STEP_STATUS[step.status] || step.status }}</small>
                  </li>
                </ol>
                <div v-if="liveRun.thinking?.length" class="live-thinking">
                  <div class="thinking-label">正在思考 · 第{{ latestThinking(liveRun.thinking).round }}轮</div>
                  <div class="thinking-text">{{ latestThinking(liveRun.thinking).content }}</div>
                </div>
                <div v-if="liveRun.answer" class="live-answer">
                  <div class="thinking-label">正在回答（生成后会自动核对数字）</div>
                  <AnswerContent :content="liveRun.answer" :results="liveRun.results || []" />
                </div>
              </div>
              <div v-else class="message-bubble typing-bubble">
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
            <div class="composer-sources">
              <el-tooltip
                v-if="lingxingAvailable"
                content="勾选后本次提问可以查询领星ERP实时数据（只读）；不勾选只查本系统数据库"
                placement="top"
              >
                <el-checkbox v-model="useLingxing" :disabled="loading" size="small">领星MCP</el-checkbox>
              </el-tooltip>
              <span>Enter发送，Shift + Enter换行</span>
            </div>
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
    <AgentStatsPanel v-if="isAdmin" v-model="statsVisible" />
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import {
  confirmAiMemory,
  createAiConversation,
  deleteAiConversation,
  deleteAiMemory,
  getAgentRun,
  getAiAssistantStatus,
  getAiConversation,
  listAiConversations,
  listAiMemories,
  sendAgentFeedback,
  startAgentRun
} from '@/api/system/aiAssistant'
import {
  CALL_STATUS, STEP_STATUS, callSummary, toolTitle, formatCell, latestThinking, pendingMemories, planProgress,
  pollAgentRun, verificationNotice
} from './agentRun'
import AgentStatsPanel from './AgentStatsPanel.vue'
import AnswerContent from './AnswerContent.vue'
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
const statusProvider = ref('')
const statusKeyEnv = ref('')
const liveRun = ref(null)
const memories = ref([])
const memoriesLoading = ref(false)
const statsVisible = ref(false)
// 领星MCP：服务端配置了密钥才显示；默认不勾选，只有勾选的那次提问才会查询领星
const lingxingAvailable = ref(false)
const useLingxing = ref(false)

// 运行看板涵盖全体用户的提问，只对管理员显示（Java 接口同样限制为 admin 角色）。
const isAdmin = computed(() => (userStore.roles || []).includes('admin'))
const userDisplayName = computed(() => userStore.nickName || userStore.name || '我')
const userInitial = computed(() => userDisplayName.value.trim().slice(0, 1).toUpperCase() || '我')
const statusClass = computed(() => ({
  ready: 'online',
  unconfigured: 'warning',
  offline: 'offline',
  checking: 'checking'
}[statusState.value]))
const statusText = computed(() => {
  if (statusState.value === 'ready') {
    return ['已连接', statusProvider.value, statusModel.value].filter(Boolean).join(' · ')
  }
  if (statusState.value === 'unconfigured') return `等待配置 ${statusKeyEnv.value || 'API Key'}`
  if (statusState.value === 'offline') return 'Python服务不可用'
  return '正在检查服务'
})
const composerPlaceholder = computed(() => {
  if (statusState.value === 'ready') return '例如：10月综合绩效排名前5名，未分配有多少？'
  if (statusState.value === 'unconfigured') return `请先在Python服务的 .env 中配置 ${statusKeyEnv.value || '模型 API Key'}`
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
    statusProvider.value = data.providerLabel || ''
    statusKeyEnv.value = data.keyEnv || ''
    lingxingAvailable.value = Boolean(data.lingxingMcpConfigured)
    if (!lingxingAvailable.value) useLingxing.value = false
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
    const started = await startAgentRun({
      conversation_id: activeConversationId.value,
      message: content,
      data_sources: lingxingAvailable.value && useLingxing.value ? ['lingxing'] : [],
      page_context: {
        path: route.fullPath,
        title: route.meta?.title || document.title
      }
    }, createRequestId('agent-run'))
    const runId = started.data?.runId
    if (!runId) throw new Error('数据助手未返回任务编号')
    await followRun(runId)
  } catch (error) {
    const detail = error?.msg || error?.message || 'AI助手暂时无法回答，请稍后重试'
    messages.value.push(createMessage('assistant', detail, true))
  } finally {
    loading.value = false
    liveRun.value = null
    await scrollToBottom()
    nextTick(() => inputRef.value?.focus())
  }
}

/** 轮询一次运行直到结束：过程中展示计划、思考和正在生成的回答，结束后追加到消息列表。 */
async function followRun(runId) {
  const run = await pollAgentRun(runId, {
    fetchRun: async id => (await getAgentRun(id, createRequestId('agent-poll'))).data,
    onUpdate: value => {
      liveRun.value = value
      scrollToBottom()
    },
    // 思考模式下单次任务可能接近 5 分钟，留出余量
    timeoutMs: 420000
  })
  if (run.status === 'failed') {
    messages.value.push(createMessage('assistant', run.error || '数据助手执行失败', true))
  } else {
    const assistantMessage = createMessage('assistant', (run.answer || '').trim() || '没有得到有效回答')
    assistantMessage.run = {
      runId: run.runId, plan: run.plan || [], steps: run.steps || [], results: run.results || [],
      thinking: run.thinking || [], verification: run.verification || null, memories: run.memories || [],
      feedback: run.feedback || null
    }
    messages.value.push(assistantMessage)
  }
  await loadConversations(false)
}

async function sendFeedback(run, rating) {
  let comment = null
  if (rating < 0) {
    try {
      const { value } = await ElMessageBox.prompt('哪里不对？（选填，会帮助改进助手）', '没帮助', {
        confirmButtonText: '提交', cancelButtonText: '取消', inputMaxlength: 500
      })
      comment = value || null
    } catch (error) {
      return
    }
  }
  try {
    await sendAgentFeedback(run.runId, { rating, comment }, createRequestId('feedback'))
    run.feedback = { rating, comment }
    ElMessage.success('感谢反馈')
  } catch (error) {
    ElMessage.error(error?.msg || error?.message || '提交反馈失败')
  }
}

async function confirmMemory(memory, run) {
  try {
    await confirmAiMemory(memory.id, createRequestId('memory-confirm'))
    memory.status = 'active'
    if (run) run.memories = [...run.memories]
    memories.value = memories.value.map(item => (item.id === memory.id ? { ...item, status: 'active' } : item))
    ElMessage.success('已记住')
  } catch (error) {
    ElMessage.error(error?.msg || error?.message || '确认记忆失败')
  }
}

async function loadMemories() {
  memoriesLoading.value = true
  try {
    const response = await listAiMemories(createRequestId('memory-list'))
    memories.value = Array.isArray(response.data) ? response.data : []
  } catch (error) {
    memories.value = []
    ElMessage.error(error?.msg || error?.message || '加载助手记忆失败')
  } finally {
    memoriesLoading.value = false
  }
}

async function removeMemory(memory, run) {
  try {
    await deleteAiMemory(memory.id, createRequestId('memory-delete'))
    memories.value = memories.value.filter(item => item.id !== memory.id)
    if (run) run.memories = run.memories.filter(item => item.id !== memory.id)
  } catch (error) {
    ElMessage.error(error?.msg || error?.message || '删除记忆失败')
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

.answer-bubble { white-space: normal; }
.verification-notice {
  margin-top: 8px;
  padding: 6px 9px;
  border-radius: 6px;
  background: var(--el-color-warning-light-9, #fdf6ec);
  color: var(--el-color-warning-dark-2, #b88230);
  font-size: 12px;
}
.memory-suggestion {
  margin-top: 6px;
  color: var(--el-text-color-secondary, #909399);
  font-size: 12px;

  button { margin-left: 6px; border: 0; background: transparent; color: var(--el-text-color-secondary, #909399); cursor: pointer; }
  .confirm { color: var(--el-color-primary, #409eff); }
}
.feedback-bar {
  margin-top: 6px;
  display: flex;
  gap: 6px;

  button {
    height: 24px;
    padding: 0 9px;
    border: 1px solid var(--el-border-color-lighter, #ebeef5);
    border-radius: 12px;
    background: var(--el-bg-color, #fff);
    color: var(--el-text-color-secondary, #909399);
    font-size: 11.5px;
    cursor: pointer;

    &:hover, &.active { color: var(--el-color-primary, #409eff); border-color: var(--el-color-primary-light-5, #a0cfff); }
  }
}
.live-answer { margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--el-border-color-lighter, #ebeef5); }

.run-detail {
  margin-top: 8px;
  width: 100%;

  :deep(.el-collapse) { border-top: 0; }
  :deep(.el-collapse-item__header) { height: 34px; font-size: 12px; color: var(--el-text-color-secondary, #909399); }
}

.plan-list {
  margin: 4px 0 6px;
  padding-left: 18px;
  font-size: 12.5px;

  li {
    padding: 2px 0;
    color: var(--el-text-color-regular, #606266);

    span { margin-right: 8px; }
    small { color: var(--el-text-color-placeholder, #a8abb2); }
    &.completed span { color: var(--el-color-success, #67c23a); }
    &.in_progress span { color: var(--el-color-primary, #409eff); font-weight: 600; }
    &.skipped span { text-decoration: line-through; }
  }
}

.live-plan { min-width: 260px; white-space: normal; }
.live-thinking { margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--el-border-color-lighter, #ebeef5); }
.thinking-round + .thinking-round { margin-top: 8px; }
.thinking-label { margin-bottom: 2px; color: var(--el-text-color-secondary, #909399); font-size: 11px; }
.thinking-text {
  max-height: 220px;
  overflow-y: auto;
  color: var(--el-text-color-secondary, #909399);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}
.live-progress { margin-bottom: 4px; color: var(--el-color-primary, #409eff); font-size: 12.5px; }

.call-list { display: flex; flex-wrap: wrap; gap: 6px; }
.call-chip {
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--el-color-success-light-9, #f0f9eb);
  color: var(--el-color-success, #67c23a);
  font-size: 11px;

  &.failed, &.invalid { background: var(--el-color-warning-light-9, #fdf6ec); color: var(--el-color-warning, #e6a23c); }
  &.denied { background: var(--el-color-danger-light-9, #fef0f0); color: var(--el-color-danger, #f56c6c); }
}

.result-meta { margin-bottom: 6px; color: var(--el-text-color-secondary, #909399); font-size: 12px; }
.result-note { margin-bottom: 4px; color: var(--el-color-warning, #e6a23c); font-size: 12px; }

.memory-panel { font-size: 13px; }
.memory-title { margin-bottom: 8px; color: var(--el-text-color-secondary, #909399); font-size: 12px; }
.memory-empty { color: var(--el-text-color-placeholder, #a8abb2); }
.memory-item {
  padding: 6px 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  border-top: 1px solid var(--el-border-color-lighter, #ebeef5);

  button { flex: none; border: 0; background: transparent; color: var(--el-color-danger, #f56c6c); cursor: pointer; }
  .confirm { color: var(--el-color-primary, #409eff); }
}
.memory-actions { flex: none; display: flex; gap: 4px; }
.memory-pending {
  margin-right: 6px;
  padding: 0 5px;
  border-radius: 4px;
  background: var(--el-color-warning-light-9, #fdf6ec);
  color: var(--el-color-warning, #e6a23c);
  font-size: 11px;
  font-style: normal;
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

.composer-sources {
  display: flex;
  align-items: center;
  gap: 12px;

  :deep(.el-checkbox__label) { font-size: 12px; }
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

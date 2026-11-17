import request from '@/utils/request'

export function getAiAssistantStatus(requestId) {
  return request({
    url: '/system/ai-assistant/status',
    method: 'get',
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 15000
  })
}

export function chatWithAiAssistant(data, requestId) {
  return request({
    url: '/system/ai-assistant/chats',
    method: 'post',
    data,
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 210000
  })
}

export function listAiConversations(requestId) {
  return request({
    url: '/system/ai-assistant/conversations',
    method: 'get',
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 15000
  })
}

export function getAiConversation(conversationId, requestId) {
  return request({
    url: `/system/ai-assistant/conversations/${conversationId}`,
    method: 'get',
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 15000
  })
}

export function createAiConversation(data = {}, requestId) {
  return request({
    url: '/system/ai-assistant/conversations',
    method: 'post',
    data,
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 15000
  })
}

export function deleteAiConversation(conversationId, requestId) {
  return request({
    url: `/system/ai-assistant/conversations/${conversationId}`,
    method: 'delete',
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 15000
  })
}

export function startAgentRun(data, requestId) {
  return request({
    url: '/system/ai-assistant/agent-runs',
    method: 'post',
    data,
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 30000
  })
}

export function getAgentRun(runId, requestId) {
  return request({
    url: `/system/ai-assistant/agent-runs/${runId}`,
    method: 'get',
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 15000
  })
}

export function listAiMemories(requestId) {
  return request({
    url: '/system/ai-assistant/memories',
    method: 'get',
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 15000
  })
}

export function deleteAiMemory(memoryId, requestId) {
  return request({
    url: `/system/ai-assistant/memories/${memoryId}`,
    method: 'delete',
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 15000
  })
}

export function confirmAiMemory(memoryId, requestId) {
  return request({
    url: `/system/ai-assistant/memories/${memoryId}/confirm`,
    method: 'post',
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 15000
  })
}

export function sendAgentFeedback(runId, data, requestId) {
  return request({
    url: `/system/ai-assistant/agent-runs/${runId}/feedback`,
    method: 'post',
    data,
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 15000
  })
}

export function getAgentStats(days, requestId) {
  return request({
    url: '/system/ai-assistant/agent-stats',
    method: 'get',
    params: { days },
    headers: requestId ? { 'X-Request-ID': requestId } : undefined,
    timeout: 30000
  })
}

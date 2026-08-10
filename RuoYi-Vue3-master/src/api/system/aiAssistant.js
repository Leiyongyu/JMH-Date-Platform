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

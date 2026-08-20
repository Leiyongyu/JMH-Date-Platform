// 统一解析脚本最终访问地址，供卡片打开、新窗口打开、iframe 内嵌共用。

function isAbsoluteUrl(value) {
  return /^https?:\/\//i.test(String(value || '').trim())
}

/**
 * 解析脚本的最终访问地址。
 * @param {object} script 脚本注册表条目
 * @param {object} opts { imageProxyBase, erpSession, isDev }
 * @returns {string} 可用的完整 URL；无法解析时返回空字符串
 */
export function resolveScriptUrl(script, opts = {}) {
  const { imageProxyBase = '', erpSession = '', isDev = false } = opts
  const page = String(script?.page || '').trim()
  if (!page) return ''
  const openMode = String(script?.openMode || 'new_window').toLowerCase()

  // 新窗口 / 跳转：page 为绝对 URL 或相对 ERP 同源的根路径
  if (openMode !== 'embed') {
    if (isAbsoluteUrl(page)) return page
    return new URL(page, window.location.origin).toString()
  }

  // 内嵌：优先脚本自定义代理基址，其次 ERP 网关注入的代理基址，最后开发环境 devBase
  const custom = String(script?.proxyBase || '').trim().replace(/\/+$/, '')
  const configured = String(imageProxyBase || '').trim().replace(/\/+$/, '')
  const devBase = String(script?.devBase || '').trim().replace(/\/+$/, '')
  const base = custom || configured || (isDev ? devBase : '')
  if (!base) return ''

  const basePath = new URL(base, window.location.href).pathname.replace(/\/+$/, '')
  const query = new URLSearchParams({ api_base: basePath, embedded: '1' })
  if (script?.needSession !== false && erpSession) {
    query.set('erp_session', erpSession)
  }

  const normalizedPage = page.startsWith('/') ? page : `/${page}`
  return `${base}${normalizedPage}?${query.toString()}`
}

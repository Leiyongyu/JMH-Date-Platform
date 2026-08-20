// 统一解析脚本的新窗口访问地址。

function isAbsoluteUrl(value) {
  return /^https?:\/\//i.test(String(value || '').trim())
}

/**
 * transport=proxy：经 Java 安全代理访问 Python 组件，并携带临时 ERP 会话。
 * transport=direct：直接访问绝对地址或 ERP 同源地址。
 */
export function resolveScriptUrl(script, opts = {}) {
  const { imageProxyBase = '', erpSession = '', erpUserId = '', isDev = false } = opts
  const page = String(script?.page || '').trim()
  if (!page) return ''

  const transport = String(script?.transport || 'direct').toLowerCase()
  if (transport !== 'proxy') {
    if (isAbsoluteUrl(page)) return page
    return new URL(page, window.location.origin).toString()
  }

  const custom = String(script?.proxyBase || '').trim().replace(/\/+$/, '')
  const configured = String(imageProxyBase || '').trim().replace(/\/+$/, '')
  const devBase = String(script?.devBase || '').trim().replace(/\/+$/, '')
  const base = custom || configured || (isDev ? devBase : '')
  if (!base) return ''

  const basePath = new URL(base, window.location.href).pathname.replace(/\/+$/, '')
  const query = new URLSearchParams({ api_base: basePath })
  if (script?.needSession !== false && erpSession) query.set('erp_session', erpSession)
  if (erpUserId) query.set('erp_user_id', erpUserId)

  const normalizedPage = page.startsWith('/') ? page : `/${page}`
  return `${base}${normalizedPage}?${query.toString()}`
}

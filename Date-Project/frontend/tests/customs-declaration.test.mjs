import test from 'node:test'
import assert from 'node:assert/strict'
import scripts from '../src/scripts.js'
import { resolveScriptUrl } from '../src/scriptUrl.js'

test('customs declaration is registered as an authenticated proxy card', () => {
  const customs = scripts.find((script) => script.code === 'customs-declaration')
  assert.ok(customs)
  assert.equal(customs.permission, 'customs:declaration:query')
  assert.equal(customs.transport, 'proxy')
  assert.equal(customs.page, '/index.html')
  assert.equal(customs.proxyBase, '/sop/customs-declaration/proxy')
  assert.equal(customs.devBase, 'http://127.0.0.1:5000')
  assert.equal(customs.needSession, true)
})

test('customs declaration resolves to its ERP proxy instead of the ERP guide page', () => {
  const customs = scripts.find((script) => script.code === 'customs-declaration')
  globalThis.window = {
    location: {
      href: 'https://python.example:8010/script-tools/',
      origin: 'https://python.example:8010',
    },
  }
  try {
    const url = new URL(resolveScriptUrl(customs, {
      imageProxyBase: 'https://erp.example/prod-api/sop/image-sop/proxy',
      erpSession: 'workbench-ticket',
      erpUserId: '7',
    }))
    assert.equal(url.origin, 'https://erp.example')
    assert.equal(url.pathname, '/prod-api/sop/customs-declaration/proxy/index.html')
    assert.equal(url.searchParams.get('api_base'), '/prod-api/sop/customs-declaration/proxy')
    assert.equal(url.searchParams.get('erp_session'), 'workbench-ticket')
    assert.equal(url.searchParams.get('erp_user_id'), '7')
  } finally {
    delete globalThis.window
  }
})

test('customs declaration development fallback points to the existing port 5000 page', () => {
  const customs = scripts.find((script) => script.code === 'customs-declaration')
  globalThis.window = {
    location: {
      href: 'https://python.example:8010/script-tools/',
      origin: 'https://python.example:8010',
    },
  }
  try {
    const url = new URL(resolveScriptUrl(customs, { isDev: true }))
    assert.equal(url.origin, 'http://127.0.0.1:5000')
    assert.equal(url.pathname, '/index.html')
  } finally {
    delete globalThis.window
  }
})

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const projectEnv = loadEnv(mode, '..', '')
  const internalToken = process.env.PYTHON_INTERNAL_API_TOKEN || projectEnv.PYTHON_INTERNAL_API_TOKEN || ''

  return {
    plugins: [vue()],
    base: mode === 'production' ? '/script-tools/' : '/',
    server: {
      host: '0.0.0.0',
      port: 5174,
      strictPort: true,
      proxy: {
        '/ebay-tool': {
          target: 'http://127.0.0.1:8010',
          changeOrigin: true,
          configure: (proxy) => {
            if (internalToken) {
              proxy.on('proxyReq', (proxyReq) => {
                proxyReq.setHeader('X-Internal-Token', internalToken)
                proxyReq.setHeader('X-ERP-User-ID', '0')
                proxyReq.setHeader('X-ERP-Username-B64', 'ZGV2ZWxvcGVy')
              })
            }
          },
        },
        '/image-sop/api': {
          target: 'http://127.0.0.1:8010',
          changeOrigin: true,
          configure: (proxy) => {
            if (internalToken) {
              proxy.on('proxyReq', (proxyReq) => {
                proxyReq.setHeader('X-Internal-Token', internalToken)
                proxyReq.setHeader('X-ERP-User-ID', '0')
                proxyReq.setHeader('X-ERP-Username-B64', 'ZGV2ZWxvcGVy')
              })
            }
          },
        },
        '/api': {
          target: 'http://127.0.0.1:8010',
          changeOrigin: true,
          configure: (proxy) => {
            if (internalToken) {
              proxy.on('proxyReq', (proxyReq) => {
                proxyReq.setHeader('X-Internal-Token', internalToken)
                proxyReq.setHeader('X-ERP-User-ID', '0')
                proxyReq.setHeader('X-ERP-Username-B64', 'ZGV2ZWxvcGVy')
              })
            }
          },
        },
      },
    },
  }
})

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const internalToken = process.env.PYTHON_INTERNAL_API_TOKEN || ''

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        configure: (proxy) => {
          if (internalToken) {
            proxy.on('proxyReq', (proxyReq) => {
              proxyReq.setHeader('X-Internal-Token', internalToken)
            })
          }
        },
      },
    },
  },
})

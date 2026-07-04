import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const ADK = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/apps':      { target: ADK, changeOrigin: true, headers: { origin: ADK } },
      '/run_sse':   { target: ADK, changeOrigin: true, headers: { origin: ADK } },
      '/version':   { target: ADK, changeOrigin: true, headers: { origin: ADK } },
      '/list-apps': { target: ADK, changeOrigin: true, headers: { origin: ADK } },
    },
  },
})

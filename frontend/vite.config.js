import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'

// Self-signed TLS cert for serving the preview over HTTPS (required for mic access).
const httpsConfig = {
  key: fs.readFileSync('/root/Kontext-Agent/certs/kontext.key'),
  cert: fs.readFileSync('/root/Kontext-Agent/certs/kontext.crt'),
}

// Proxy API routes to the local FastAPI backend (keeps everything same-origin).
const backend = { target: 'http://127.0.0.1:8000', changeOrigin: true }
const backendWs = { ...backend, ws: true }

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  preview: {
    host: '0.0.0.0',
    port: 4173,
    https: httpsConfig,
    proxy: {
      '/auth': backend,
      '/chat': backend,
      '/docs': backend,
      '/metrics': backend,
      '/voice-chat': backend,
      '/meeting': backendWs,
    },
  },
})

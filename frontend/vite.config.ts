import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dashboard calls relative /api/* URLs; in dev Vite forwards them to FastAPI.
const API = process.env.MITRA_API_URL ?? 'http://127.0.0.1:8000'
// xfwd: tell the API who the visitor is, so shared links (other devices) are read-only.
const toApi = { target: API, xfwd: true }

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // allow the public link made by `start.sh --share` / `start.cmd -Share` (Cloudflare quick tunnel)
    allowedHosts: ['.trycloudflare.com'],
    proxy: {
      '/api': toApi,
      '/health': toApi,
    },
  },
})

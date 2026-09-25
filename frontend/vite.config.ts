import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dashboard calls relative /api/* URLs; in dev Vite forwards them to FastAPI.
const API = process.env.MITRA_API_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': API,
      '/health': API,
    },
  },
})

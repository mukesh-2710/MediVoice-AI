import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev the browser talks to Vite (5173); /api and /ws are proxied to FastAPI (8000).
// That keeps every API key on the backend and avoids CORS in development.
const target = process.env.VITE_BACKEND_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target, changeOrigin: true },
      '/ws': { target, ws: true, changeOrigin: true },
    },
  },
})

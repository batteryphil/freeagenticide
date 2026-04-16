import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy WS and API calls to Python backend in dev mode
      '/ws': {
        target: 'ws://127.0.0.1:7800',
        ws: true,
      },
      '/api': {
        target: 'http://127.0.0.1:7800',
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})

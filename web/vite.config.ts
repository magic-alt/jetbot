import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy API calls to the local FastAPI dev server so the SPA can run
      // standalone without CORS pain.
      '/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    target: 'es2020',
  },
})

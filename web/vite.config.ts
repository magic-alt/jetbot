import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

const apiTarget = 'http://127.0.0.1:8000'

// https://vitejs.dev/config/
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/ui/' : '/',
  plugins: [
    vue(),
    Components({
      dts: false,
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
    }),
  ],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy API calls to the local FastAPI dev server so the SPA can run
      // standalone without CORS pain. Use 127.0.0.1 instead of localhost
      // because some Windows setups resolve localhost:8000 to another app.
      '/v1': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/health': apiTarget,
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    target: 'es2020',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('markdown-it') || id.includes('dompurify')) {
            return 'reporting'
          }
          return undefined
        },
      },
    },
  },
}))

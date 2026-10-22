import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          // 把所有 pixi 相关包打到同一个 chunk，避免多实例导致 Live2D 渲染失败
          if (id.includes('pixi.js') || id.includes('pixi-live2d-display') || id.includes('@pixi/')) {
            return 'pixi-vendor'
          }
        },
      },
    },
  },
  server: {
    port: 5173,
    // 允许通过内网穿透域名访问（cpolar/ngrok 等隧道域名会被 Vite 默认的 Host 校验拦截）
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})

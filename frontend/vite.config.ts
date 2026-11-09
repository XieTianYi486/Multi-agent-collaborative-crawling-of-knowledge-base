import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { resolve } from 'path'

export default defineConfig({
  plugins: [
    vue(),
    // Element Plus 按需引入：模板里的组件与 API 自动导入，未用到的组件不再进包
    AutoImport({
      resolvers: [ElementPlusResolver()],
      dts: 'src/auto-imports.d.ts',
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      // v-loading 等指令需要开启解析，否则移除全局 app.use(ElementPlus) 后会失效
      directives: true,
      // 不生成全局组件类型声明：项目历史模板里有较多宽松写法，
      // 引入 Element Plus 强类型会一次性放大成大量无关类型错误
      dts: false,
    }),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
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
  build: {
    // 第三方依赖单独成包：业务代码更新时浏览器可继续用缓存的 vendor
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return
          if (id.includes('element-plus') || id.includes('@element-plus')) {
            return 'element-plus'
          }
          if (id.includes('echarts') || id.includes('zrender')) {
            return 'echarts'
          }
          return 'vendor'
        },
      },
    },
  },
})

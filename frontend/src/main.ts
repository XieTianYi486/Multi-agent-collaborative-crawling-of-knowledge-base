import { createApp } from 'vue'
import { createPinia } from 'pinia'
// Element Plus 已改为按需引入（vite.config.ts 自动解析），这里只补全局样式：
// 组件样式由插件按使用情况注入，消息/弹窗/通知/加载这类命令式组件需要显式引入
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/notification/style/css'
import 'element-plus/es/components/loading/style/css'
// Element Plus 官方暗色变量：html.dark 下组件自动切换到深色配色
import 'element-plus/theme-chalk/dark/css-vars.css'

import App from './App.vue'
import router from './router'
import { useAuthStore } from './store/auth'
import './styles/global.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

// 初始化认证状态后挂载
const authStore = useAuthStore()
authStore.initialize().then(() => {
  app.mount('#app')
})

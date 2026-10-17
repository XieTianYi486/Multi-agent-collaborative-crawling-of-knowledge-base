import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi } from '@/api/auth'
import router from '@/router'

export interface UserInfo {
  id: number
  username: string
  real_name: string | null
  email: string | null
  phone: string | null
  position: string | null
  avatar_url: string | null
  department: string | null
  role_id: number
  role_name: string | null
  status: number
  created_at: string
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const token = ref<string>(localStorage.getItem('access_token') || '')
  const loading = ref(false)

  /** 初始化：从 localStorage 恢复登录状态 */
  async function initialize() {
    if (!token.value) return
    try {
      const res = await authApi.getMe()
      user.value = res.data.data
    } catch {
      logout()
    }
  }

  /** 登录 */
  async function login(username: string, password: string, captcha?: { token?: string; code?: string }, identity?: string) {
    loading.value = true
    try {
      const res = await authApi.login({
        username,
        password,
        captcha_token: captcha?.token,
        captcha_code: captcha?.code,
        identity,
      })
      const data = res.data.data
      token.value = data.access_token
      user.value = data.user
      localStorage.setItem('access_token', data.access_token)
      // 按身份跳转：管理员进管理后台，学生/老师进智能问答
      router.push(isAdmin() ? '/admin/documents' : '/chat')
    } finally {
      loading.value = false
    }
  }

  /** 退出 */
  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('access_token')
    router.push('/login')
  }

  /** 检查是否为管理员 */
  const isAdmin = () => {
    return user.value?.role_name === '超级管理员' || user.value?.role_name === '知识库管理员'
  }

  const isSuperAdmin = () => {
    return user.value?.role_name === '超级管理员'
  }

  return { user, token, loading, initialize, login, logout, isAdmin, isSuperAdmin }
})

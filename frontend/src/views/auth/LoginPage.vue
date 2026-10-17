<template>
  <div class="login-page">
    <!-- 背景压暗层：右侧加深，保证玻璃卡片边界清晰 -->
    <div class="bg-veil" aria-hidden="true"></div>
    <!-- 装饰层：卡片光晕 + 浮动光球（位于滚动容器之外，不会被裁切） -->
    <div class="bg-decor" aria-hidden="true">
      <span class="card-glow"></span>
      <span class="orb orb-a"></span>
      <span class="orb orb-b"></span>
    </div>

    <div class="page-foot">人工智能学院 · 教学知识库</div>

    <!-- 右侧玻璃登录卡片 -->
    <div class="form-card">
      <div class="form-head">
        <div class="badge">人工智能学院 · 教学知识库</div>
        <h2>欢迎登录</h2>
        <p>登录后开始智能问答与资料检索</p>
      </div>

      <div class="identity-selector">
        <div
          v-for="item in identities"
          :key="item.value"
          class="identity-item"
          :class="{ active: form.identity === item.value }"
          @click="form.identity = item.value"
        >
          <el-icon :size="18"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </div>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="login-form"
        @submit.prevent="handleLogin"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            size="large"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            size="large"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item label="安全验证" prop="captcha" v-if="showCaptcha">
          <div class="captcha-row">
            <el-input
              v-model="form.captcha"
              placeholder="计算结果"
              size="large"
              class="captcha-input"
              @keyup.enter="handleLogin"
            />
            <button type="button" class="captcha-refresh" @click="loadCaptcha" title="点击刷新">
              <span>{{ captchaChallenge }}</span>
            </button>
          </div>
        </el-form-item>

        <el-button
          type="primary"
          size="large"
          :loading="authStore.loading"
          native-type="submit"
          class="login-btn"
        >
          {{ authStore.loading ? '登录中...' : '登 录' }}
        </el-button>

        <div class="sso-row" v-if="ssoEnabled">
          <el-button type="primary" plain size="default" class="goto-register-btn" @click="handleSSO">
            企业统一登录（SSO）
          </el-button>
        </div>

        <div class="form-footer">
          <span>还没有账号？</span>
          <router-link to="/register" class="register-link">
            <el-button type="primary" plain size="default" class="goto-register-btn">
              立即注册 <el-icon><ArrowRight /></el-icon>
            </el-button>
          </router-link>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { User, Lock, ArrowRight, Reading, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useAuthStore } from '@/store/auth'
import { useThemeStore } from '@/store/theme'
import { onMounted, onUnmounted } from 'vue'
import { authSecurity } from '@/api/security'

const authStore = useAuthStore()
const themeStore = useThemeStore()
const formRef = ref<FormInstance>()

// 登录页始终使用明亮模式的表单控件，但视觉上保持深色科技背景
let wasDark = false
onMounted(() => {
  wasDark = document.documentElement.classList.contains('dark')
  document.documentElement.classList.remove('dark')
  loadCaptcha()
  checkSSO()
})
onUnmounted(() => {
  if (wasDark) document.documentElement.classList.add('dark')
})

const form = reactive({
  username: '',
  password: '',
  captcha: '',
  identity: '',
})

const identities = [
  { label: '学生', value: 'student', icon: Reading },
  { label: '老师', value: 'teacher', icon: User },
  { label: '管理员', value: 'admin', icon: Setting },
]

const showCaptcha = ref(false)
const captchaChallenge = ref('')
const captchaToken = ref('')
const ssoEnabled = ref(false)

async function loadCaptcha() {
  try {
    const res = await authSecurity.captcha()
    const data = res.data.data
    captchaToken.value = data.token
    captchaChallenge.value = data.challenge
    showCaptcha.value = true
    form.captcha = ''
  } catch {
    showCaptcha.value = false
  }
}

async function checkSSO() {
  try {
    const res = await authSecurity.ssoStatus()
    ssoEnabled.value = !!res.data.data?.enabled
  } catch {
    ssoEnabled.value = false
  }
}

function handleSSO() {
  const serverUrl = import.meta.env?.VITE_SSO_SERVER || ''
  if (serverUrl) {
    window.location.href = serverUrl
  } else {
    ElMessage.info('企业 SSO 尚未配置，请联系管理员对接')
  }
}

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  captcha: [{ required: true, message: '请输入计算结果', trigger: 'blur' }],
}

async function handleLogin() {
  if (!form.identity) {
    ElMessage.warning('请先选择登录身份')
    return
  }
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  try {
    await authStore.login(form.username, form.password, {
      token: captchaToken.value,
      code: form.captcha,
    }, form.identity)
    ElMessage.success('登录成功')
  } catch (err: any) {
    const msg = err?.response?.data?.message || '登录失败，请检查用户名和密码'
    ElMessage.error(msg)
    // 失败后刷新验证码，防止连续暴力尝试
    loadCaptcha()
  }
}
</script>

<style scoped>
/* 页面配色取自背景图：深海军蓝玻璃 + 靛蓝 / 青色霓虹 */
.login-page {
  --auth-text: #eef3ff;
  --auth-text-dim: rgba(196, 210, 236, 0.72);
  --auth-line: rgba(140, 172, 255, 0.22);
  --auth-glass: rgba(255, 255, 255, 0.06);
  --auth-cyan: #7dd3fc;
  --auth-indigo: #818cf8;

  /* 固定为一屏高度：页面本身永不出现滚动条，溢出交给卡片自己吸收 */
  height: 100vh;
  box-sizing: border-box;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: clamp(24px, 4vh, 48px) clamp(24px, 6vw, 96px);
  background: url('@/assets/auth-bg.jpeg') center / cover no-repeat,
    #060e28;
  overflow: hidden;
}

/* 右侧轻微压暗，左侧保留图片原始亮度，让院徽完整露出 */
.bg-veil {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(
    100deg,
    rgba(4, 10, 30, 0) 0%,
    rgba(4, 10, 30, 0.14) 45%,
    rgba(4, 10, 30, 0.3) 70%,
    rgba(3, 8, 24, 0.44) 100%
  );
}

.bg-decor {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

/* 卡片光晕：贴着卡片位置，位于滚动容器之外所以不会被裁切 */
.card-glow {
  position: absolute;
  right: calc(clamp(24px, 6vw, 96px) - 70px);
  top: 50%;
  transform: translateY(-50%);
  width: 560px;
  height: 640px;
  border-radius: 50%;
  background:
    radial-gradient(circle at 62% 38%, rgba(99, 102, 241, 0.46), transparent 68%),
    radial-gradient(circle at 28% 80%, rgba(34, 211, 238, 0.26), transparent 66%);
  filter: blur(38px);
  animation: glow-breathe 12s ease-in-out infinite;
}

@keyframes glow-breathe {
  0%, 100% { opacity: 0.82; }
  50% { opacity: 1; }
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(40px);
}

.orb-a {
  width: 380px;
  height: 380px;
  right: -80px;
  top: 6%;
  background: radial-gradient(circle, rgba(124, 58, 237, 0.48), transparent 70%);
  animation: float-a 9s ease-in-out infinite;
}

.orb-b {
  width: 320px;
  height: 320px;
  right: 14%;
  bottom: -90px;
  background: radial-gradient(circle, rgba(34, 211, 238, 0.32), transparent 70%);
  animation: float-b 11s ease-in-out infinite;
}

@keyframes float-a {
  0%, 100% { transform: translate3d(0, 0, 0); }
  50% { transform: translate3d(0, 26px, 0); }
}

@keyframes float-b {
  0%, 100% { transform: translate3d(0, 0, 0); }
  50% { transform: translate3d(-18px, -22px, 0); }
}

.page-foot {
  position: absolute;
  left: clamp(24px, 6vw, 96px);
  bottom: 26px;
  z-index: 1;
  font-size: 13px;
  letter-spacing: 1px;
  color: rgba(203, 217, 243, 0.5);
  text-shadow: 0 1px 8px rgba(2, 6, 23, 0.6);
}

/* ==================== 深蓝玻璃卡片 ==================== */
.form-card {
  position: relative;
  z-index: 2;
  width: 452px;
  /* 只允许卡片自己吸收高度溢出（本页正常不会触发，兜底用） */
  max-height: 100%;
  overflow-y: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
  padding: 34px 34px 24px;
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(18, 30, 70, 0.78) 0%, rgba(8, 15, 40, 0.86) 100%);
  border: 1px solid var(--auth-line);
  box-shadow:
    0 30px 70px rgba(2, 6, 23, 0.55),
    0 10px 30px rgba(56, 110, 245, 0.2),
    inset 0 1px 0 rgba(190, 215, 255, 0.16);
  backdrop-filter: blur(26px) saturate(140%);
  -webkit-backdrop-filter: blur(26px) saturate(140%);
  animation: card-in 0.55s cubic-bezier(0.22, 0.68, 0.3, 1) both;
}

/* 滚动条隐藏：卡片是滚动容器，完全隐藏滚动条保持观感干净 */
.form-card::-webkit-scrollbar {
  display: none;
}

@keyframes card-in {
  from { opacity: 0; transform: translateY(18px) scale(0.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.form-head {
  text-align: center;
  margin-bottom: 22px;
}

.badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.32);
  color: var(--auth-cyan);
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}

.form-head h2 {
  margin: 0 0 8px;
  font-size: 30px;
  font-weight: 800;
  letter-spacing: 1px;
  color: var(--auth-text);
  text-shadow: 0 2px 16px rgba(99, 102, 241, 0.45);
}

.form-head p {
  margin: 0;
  font-size: 14px;
  color: var(--auth-text-dim);
}

/* ==================== 身份选择 ==================== */
.identity-selector {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.identity-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 11px 0;
  border: 1px solid var(--auth-line);
  border-radius: 12px;
  background: var(--auth-glass);
  cursor: pointer;
  color: rgba(196, 210, 236, 0.8);
  font-size: 14px;
  transition: all 0.2s ease;
}

.identity-item:hover {
  border-color: var(--auth-indigo);
  color: #c7d2fe;
  transform: translateY(-1px);
}

.identity-item.active {
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.42), rgba(79, 70, 229, 0.3));
  border-color: var(--auth-indigo);
  color: #e0e7ff;
  font-weight: 600;
  box-shadow:
    0 8px 20px rgba(79, 70, 229, 0.34),
    inset 0 0 0 1px rgba(129, 140, 248, 0.36);
}

/* ==================== 表单 ==================== */
.login-form :deep(.el-form-item__label) {
  font-weight: 600;
  color: rgba(214, 226, 245, 0.88);
  padding-bottom: 4px;
}

.login-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 12px;
  box-shadow: 0 0 0 1px var(--auth-line) inset;
  background: var(--auth-glass);
  padding: 5px 14px;
  transition: all 0.2s ease;
}

.login-form :deep(.el-input__inner) {
  color: var(--auth-text);
}

.login-form :deep(.el-input__inner::placeholder) {
  color: rgba(150, 168, 200, 0.7);
}

.login-form :deep(.el-input__prefix),
.login-form :deep(.el-input__suffix) {
  color: rgba(186, 202, 230, 0.72);
}

.login-form :deep(.el-input__wrapper:hover),
.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 1px var(--auth-indigo) inset,
    0 0 0 4px rgba(99, 102, 241, 0.16),
    0 8px 20px rgba(56, 110, 245, 0.22);
}

/* 验证码 */
.captcha-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.captcha-input {
  flex: 1;
}

.captcha-refresh {
  min-width: 118px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(56, 189, 248, 0.3);
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(34, 211, 238, 0.16), rgba(99, 102, 241, 0.2));
  color: var(--auth-cyan);
  font-weight: 700;
  font-size: 14px;
  letter-spacing: 1px;
  cursor: pointer;
  padding: 0 10px;
  white-space: nowrap;
  transition: all 0.2s ease;
}

.captcha-refresh:hover {
  border-color: var(--auth-cyan);
  background: linear-gradient(135deg, rgba(34, 211, 238, 0.26), rgba(99, 102, 241, 0.28));
}

.login-btn {
  width: 100%;
  margin-top: 4px;
  height: 46px;
  border: none;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 4px;
  color: #fff;
  background: linear-gradient(90deg, #4f46e5, #7c3aed);
  box-shadow: 0 12px 26px rgba(99, 102, 241, 0.42);
  transition: all 0.2s ease;
}

.login-btn:hover {
  filter: brightness(1.08);
  transform: translateY(-1px);
  box-shadow: 0 16px 32px rgba(124, 58, 237, 0.5);
}

.sso-row {
  margin-top: 10px;
  text-align: center;
}

.form-footer {
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid rgba(140, 172, 255, 0.16);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-size: 14px;
  color: var(--auth-text-dim);
}

.register-link {
  text-decoration: none;
}

.goto-register-btn {
  border-color: rgba(165, 180, 252, 0.5) !important;
  color: #a5b4fc !important;
  background: transparent !important;
}

.goto-register-btn:hover {
  border-color: var(--auth-cyan) !important;
  color: var(--auth-cyan) !important;
  background: rgba(56, 189, 248, 0.1) !important;
}

/* ==================== 响应式 ==================== */
@media (max-width: 900px) {
  .login-page {
    justify-content: center;
    background-position: 32% center;
  }
  .form-card {
    width: 100%;
    max-width: 452px;
  }
  .page-foot {
    display: none;
  }
}

/* 矮屏（1366x768 笔记本等）压缩布局：让内容在无需滚动的情况下放得下 */
@media (max-height: 820px) {
  .form-card {
    padding: 22px 30px 16px;
  }
  .form-head {
    margin-bottom: 12px;
  }
  .form-head h2 {
    font-size: 24px;
  }
  .form-head p {
    font-size: 13px;
  }
  .badge {
    margin-bottom: 8px;
  }
  .identity-selector {
    margin-bottom: 12px;
  }
  .identity-item {
    padding: 8px 0;
  }
  .login-form :deep(.el-form-item) {
    margin-bottom: 10px;
  }
  .login-btn {
    height: 42px;
  }
  .form-footer {
    margin-top: 12px;
    padding-top: 10px;
  }
}
</style>

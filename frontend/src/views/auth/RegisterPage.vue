<template>
  <div class="register-page">
    <!-- 背景压暗层 -->
    <div class="bg-veil" aria-hidden="true"></div>
    <!-- 装饰光晕 -->
    <div class="bg-decor" aria-hidden="true">
      <span class="card-glow"></span>
      <span class="orb orb-a"></span>
      <span class="orb orb-b"></span>
    </div>

    <div class="page-foot">人工智能学院 · 教学知识库</div>

    <!-- 右侧玻璃注册卡片 -->
    <div class="form-card">
      <div class="form-head">
        <div class="badge">人工智能学院 · 教学知识库</div>
        <h2>创建账号</h2>
        <p>注册后即可使用智能问答服务</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="register-form"
        @submit.prevent="handleRegister"
      >
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="用户名" prop="username">
              <el-input
                v-model="form.username"
                placeholder="请输入用户名"
                :prefix-icon="User"
                size="large"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="真实姓名" prop="real_name">
              <el-input
                v-model="form.real_name"
                placeholder="请输入真实姓名"
                :prefix-icon="UserFilled"
                size="large"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="身份" prop="role">
          <el-radio-group v-model="form.role" style="width: 100%">
            <el-radio-button style="width: 50%" value="student">学生</el-radio-button>
            <el-radio-button style="width: 50%" value="teacher">老师</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="所属部门" prop="department">
              <el-select
                v-model="form.department"
                placeholder="请选择所属部门"
                size="large"
                style="width: 100%"
                clearable
                popper-class="auth-select-popper"
              >
                <el-option
                  v-for="dept in departments"
                  :key="dept.id"
                  :label="dept.name"
                  :value="dept.name"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="邮箱">
              <el-input
                v-model="form.email"
                placeholder="请输入邮箱（选填）"
                :prefix-icon="Message"
                size="large"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="form.password"
                type="password"
                placeholder="请输入6-20位密码"
                :prefix-icon="Lock"
                size="large"
                show-password
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="确认密码" prop="confirmPassword">
              <el-input
                v-model="form.confirmPassword"
                type="password"
                placeholder="请再次输入密码"
                :prefix-icon="Lock"
                size="large"
                show-password
                @keyup.enter="handleRegister"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-button
          type="primary"
          size="large"
          :loading="loading"
          native-type="submit"
          class="register-btn"
        >
          {{ loading ? '正在注册...' : '创建账号' }}
        </el-button>

        <div class="form-footer">
          <span>已有账号？</span>
          <router-link to="/login" class="login-link">
            <el-button type="primary" plain size="default" class="goto-login-btn">
              立即登录 <el-icon><ArrowRight /></el-icon>
            </el-button>
          </router-link>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  User, UserFilled, Lock, Message, ArrowRight,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { authApi } from '@/api/auth'

const router = useRouter()
const formRef = ref<FormInstance>()
const loading = ref(false)

// 视觉保持深色科技背景
let wasDark = false
onMounted(() => {
  wasDark = document.documentElement.classList.contains('dark')
  document.documentElement.classList.remove('dark')
})
onUnmounted(() => {
  if (wasDark) document.documentElement.classList.add('dark')
})

const departments = ref<any[]>([])

// 身份 → 部门类型映射：学生→班级(class)，老师→教学单位(teaching)
const ROLE_TO_DEPT: Record<string, string> = { student: 'class', teacher: 'teaching' }

// 按身份拉取对应类型的部门列表
async function loadDepartments() {
  const deptType = ROLE_TO_DEPT[form.role] || 'class'
  try {
    const res = await fetch(`/api/v1/admin/departments/public?dept_type=${deptType}`)
    const data = await res.json()
    if (data.code === 0) departments.value = data.data || []
  } catch { /* public endpoint might not be accessible yet */ }
}
onMounted(loadDepartments)

const form = reactive({
  username: '',
  real_name: '',
  role: 'student',
  department: '',
  email: '',
  password: '',
  confirmPassword: '',
})

// 切换身份时清空部门选择并重新加载对应列表
watch(() => form.role, () => {
  form.department = ''
  loadDepartments()
})

const validateConfirm = (_rule: any, value: string, callback: any) => {
  if (value !== form.password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 30, message: '用户名需3-30个字符', trigger: 'blur' },
  ],
  real_name: [
    { required: true, message: '请输入真实姓名', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 20, message: '密码需6-20个字符', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}

async function handleRegister() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await authApi.register({
      username: form.username,
      password: form.password,
      real_name: form.real_name,
      email: form.email || undefined,
      department: form.department || undefined,
      role: form.role,
    })
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } catch (err: any) {
    const msg = err?.response?.data?.message || '注册失败'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* 页面配色取自背景图：深海军蓝玻璃 + 靛蓝 / 青色霓虹（与登录页一致） */
.register-page {
  --auth-text: #eef3ff;
  --auth-text-dim: rgba(196, 210, 236, 0.72);
  --auth-line: rgba(140, 172, 255, 0.22);
  --auth-glass: rgba(255, 255, 255, 0.06);
  --auth-cyan: #7dd3fc;
  --auth-indigo: #818cf8;

  height: 100vh;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: clamp(24px, 4vh, 48px) clamp(24px, 6vw, 96px);
  box-sizing: border-box;
  background: url('@/assets/auth-bg.jpeg') center / cover no-repeat,
    #060e28;
  overflow: hidden;
}

.bg-veil {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(
    100deg,
    rgba(4, 10, 30, 0) 0%,
    rgba(4, 10, 30, 0.16) 42%,
    rgba(4, 10, 30, 0.34) 68%,
    rgba(3, 8, 24, 0.48) 100%
  );
}

.bg-decor {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

/* 卡片光晕：贴着卡片位置，位于滚动容器之外所以不会被裁切、也不产生幻影滚动区 */
.card-glow {
  position: absolute;
  right: calc(clamp(24px, 6vw, 96px) - 70px);
  top: 50%;
  transform: translateY(-50%);
  width: 680px;
  height: 660px;
  border-radius: 50%;
  background:
    radial-gradient(circle at 62% 30%, rgba(99, 102, 241, 0.46), transparent 68%),
    radial-gradient(circle at 26% 84%, rgba(34, 211, 238, 0.26), transparent 66%);
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
  top: 4%;
  background: radial-gradient(circle, rgba(124, 58, 237, 0.48), transparent 70%);
  animation: float-a 9s ease-in-out infinite;
}

.orb-b {
  width: 320px;
  height: 320px;
  right: 16%;
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
  width: 560px;
  max-height: 100%;
  overflow-y: auto;
  /* 隐藏滚动条，保证卡片观感干净 */
  scrollbar-width: none;
  -ms-overflow-style: none;
  padding: 28px 32px 22px;
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

.form-card::-webkit-scrollbar {
  display: none;
}

/* 卡片光晕由 .bg-decor 层的 .card-glow 提供：卡片自身是滚动容器，
   在卡片内部放 ::before 光晕会被自身裁切不可见，还会撑出看不到内容的幻影滚动区 */

@keyframes card-in {
  from { opacity: 0; transform: translateY(18px) scale(0.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.form-head {
  text-align: center;
  margin-bottom: 16px;
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
  margin-bottom: 10px;
}

.form-head h2 {
  margin: 0 0 6px;
  font-size: 28px;
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

/* ==================== 表单 ==================== */
.register-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.register-form :deep(.el-form-item__label) {
  font-weight: 600;
  color: rgba(214, 226, 245, 0.88);
  padding-bottom: 4px;
}

.register-form :deep(.el-input__wrapper) {
  border-radius: 12px;
  box-shadow: 0 0 0 1px var(--auth-line) inset;
  background: var(--auth-glass);
  padding: 5px 14px;
  transition: all 0.2s ease;
}

.register-form :deep(.el-input__inner) {
  color: var(--auth-text);
}

.register-form :deep(.el-input__inner::placeholder) {
  color: rgba(150, 168, 200, 0.7);
}

.register-form :deep(.el-input__prefix),
.register-form :deep(.el-input__suffix) {
  color: rgba(186, 202, 230, 0.72);
}

.register-form :deep(.el-input__wrapper:hover),
.register-form :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 1px var(--auth-indigo) inset,
    0 0 0 4px rgba(99, 102, 241, 0.16),
    0 8px 20px rgba(56, 110, 245, 0.22);
}

/* 下拉框 */
.register-form :deep(.el-select__wrapper) {
  border-radius: 12px;
  box-shadow: 0 0 0 1px var(--auth-line) inset;
  background: var(--auth-glass);
  color: var(--auth-text);
}

.register-form :deep(.el-select__wrapper:hover),
.register-form :deep(.el-select__wrapper.is-focused) {
  box-shadow:
    0 0 0 1px var(--auth-indigo) inset,
    0 0 0 4px rgba(99, 102, 241, 0.16);
}

.register-form :deep(.el-select__placeholder) {
  color: rgba(150, 168, 200, 0.7);
}

/* 身份单选按钮 */
.register-form :deep(.el-radio-button__inner) {
  width: 100%;
  border-color: var(--auth-line);
  background: var(--auth-glass);
  color: rgba(196, 210, 236, 0.8);
  transition: all 0.2s ease;
}

.register-form :deep(.el-radio-button__inner:hover) {
  color: #c7d2fe;
}

.register-form :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.5), rgba(79, 70, 229, 0.4));
  border-color: var(--auth-indigo);
  color: #e0e7ff;
  box-shadow:
    -1px 0 0 0 var(--auth-indigo),
    0 8px 20px rgba(79, 70, 229, 0.34);
}

/* 注册按钮 */
.register-btn {
  width: 100%;
  margin-top: 4px;
  height: 46px;
  border: none;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 2px;
  color: #fff;
  background: linear-gradient(90deg, #4f46e5, #7c3aed);
  box-shadow: 0 12px 26px rgba(99, 102, 241, 0.42);
  transition: all 0.2s ease;
}

.register-btn:hover {
  filter: brightness(1.08);
  transform: translateY(-1px);
  box-shadow: 0 16px 32px rgba(124, 58, 237, 0.5);
}

.form-footer {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(140, 172, 255, 0.16);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-size: 14px;
  color: var(--auth-text-dim);
}

.login-link {
  text-decoration: none;
}

.goto-login-btn {
  border-color: rgba(165, 180, 252, 0.5) !important;
  color: #a5b4fc !important;
  background: transparent !important;
}

.goto-login-btn:hover {
  border-color: var(--auth-cyan) !important;
  color: var(--auth-cyan) !important;
  background: rgba(56, 189, 248, 0.1) !important;
}

/* ==================== 响应式 ==================== */
@media (max-width: 1000px) {
  .register-page {
    justify-content: center;
    background-position: 30% center;
  }
  .form-card {
    width: 100%;
    max-width: 560px;
  }
  .page-foot {
    display: none;
  }
}

@media (max-width: 640px) {
  .form-card {
    padding: 22px 18px 18px;
  }
  .register-form :deep(.el-form-item) {
    margin-bottom: 12px;
  }
}

/* 矮屏（笔记本常见 768px 高及以下）压缩布局：保证表单校验报错撑高后，
   创建账号按钮与底部链接仍完整落在卡片可视区内，无需滚动 */
@media (max-height: 800px) {
  .form-card {
    padding: 20px 28px 16px;
  }
  .form-head {
    margin-bottom: 10px;
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
  .register-form :deep(.el-form-item) {
    margin-bottom: 10px;
  }
  .form-footer {
    margin-top: 12px;
    padding-top: 12px;
  }
}
</style>

<style>
/* 部门下拉浮层（Teleport 到 body，需全局样式）：与卡片保持同一深蓝玻璃配色 */
.auth-select-popper.el-popper {
  background: rgba(13, 22, 52, 0.97) !important;
  border: 1px solid rgba(140, 172, 255, 0.24) !important;
  box-shadow: 0 18px 44px rgba(2, 6, 23, 0.6) !important;
  backdrop-filter: blur(16px);
}

.auth-select-popper .el-select-dropdown__item {
  color: rgba(214, 226, 245, 0.86);
}

.auth-select-popper .el-select-dropdown__item.is-hovering,
.auth-select-popper .el-select-dropdown__item:hover {
  background: rgba(99, 102, 241, 0.24);
  color: #e0e7ff;
}

.auth-select-popper .el-select-dropdown__item.is-selected {
  color: #a5b4fc;
  font-weight: 600;
  background: rgba(99, 102, 241, 0.18);
}

.auth-select-popper .el-popper__arrow::before {
  background: rgba(13, 22, 52, 0.97) !important;
  border-color: rgba(140, 172, 255, 0.24) !important;
}
</style>

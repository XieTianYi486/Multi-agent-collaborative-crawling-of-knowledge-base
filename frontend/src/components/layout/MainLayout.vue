<template>
  <div class="main-layout" :class="{ dark: themeStore.isDark }">
    <!-- 侧边栏 -->
    <aside class="sidebar" :class="{ collapsed: isCollapse, 'mobile-open': mobileMenuOpen }">
      <!-- Logo -->
      <div class="sidebar-logo">
        <el-icon :size="24" color="var(--color-primary)"><Reading /></el-icon>
        <span v-if="!isCollapse" class="logo-text">AI 学院教学知识库</span>
      </div>

      <!-- 菜单 -->
      <nav class="sidebar-nav" @click="mobileMenuOpen = false">
        <router-link to="/chat" class="nav-item" :class="{ active: currentRoute === '/chat' }">
          <el-icon :size="20"><ChatDotRound /></el-icon>
          <span v-if="!isCollapse" class="nav-label">智能问答</span>
        </router-link>

        <button type="button" class="nav-item nav-button" @click="openCounselor">
          <el-icon :size="20"><Service /></el-icon>
          <span v-if="!isCollapse" class="nav-label">AI 助手</span>
        </button>

        <router-link to="/documents" class="nav-item" :class="{ active: currentRoute === '/documents' }">
          <el-icon :size="20"><FolderOpened /></el-icon>
          <span v-if="!isCollapse" class="nav-label">知识库文档</span>
        </router-link>

        <router-link to="/videos" class="nav-item" :class="{ active: currentRoute === '/videos' }">
          <el-icon :size="20"><VideoCamera /></el-icon>
          <span v-if="!isCollapse" class="nav-label">视频专区</span>
        </router-link>

        <button type="button" class="nav-item nav-button nav-notif" @click="openNotifications">
          <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99">
            <el-icon :size="20"><Bell /></el-icon>
          </el-badge>
          <span v-if="!isCollapse" class="nav-label">消息通知</span>
        </button>

        <router-link to="/tickets" class="nav-item" :class="{ active: currentRoute === '/tickets' }">
          <el-icon :size="20"><Tickets /></el-icon>
          <span v-if="!isCollapse" class="nav-label">我的工单</span>
        </router-link>

        <router-link to="/my-collections" class="nav-item" :class="{ active: currentRoute === '/my-collections' }">
          <el-icon :size="20"><Refresh /></el-icon>
          <span v-if="!isCollapse" class="nav-label">我的补采</span>
        </router-link>

        <template v-if="authStore.isAdmin()">
          <div v-if="!isCollapse" class="nav-group-title">内容运营</div>

          <router-link to="/admin/documents" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/documents') }">
            <el-icon :size="20"><Document /></el-icon>
            <span v-if="!isCollapse" class="nav-label">文档管理</span>
          </router-link>

          <router-link to="/admin/categories" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/categories') }">
            <el-icon :size="20"><FolderOpened /></el-icon>
            <span v-if="!isCollapse" class="nav-label">分类管理</span>
          </router-link>

          <router-link to="/admin/videos" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/videos') }">
            <el-icon :size="20"><VideoCamera /></el-icon>
            <span v-if="!isCollapse" class="nav-label">视频管理</span>
          </router-link>

          <router-link to="/admin/review" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/review') }">
            <el-icon :size="20"><Stamp /></el-icon>
            <span v-if="!isCollapse" class="nav-label">知识审核</span>
            <span v-if="!isCollapse && reviewCount > 0" class="nav-badge">{{ reviewCount > 99 ? '99+' : reviewCount }}</span>
          </router-link>

          <router-link to="/admin/announcements" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/announcements') }">
            <el-icon :size="20"><Bell /></el-icon>
            <span v-if="!isCollapse" class="nav-label">公告管理</span>
          </router-link>

          <router-link to="/admin/tickets" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/tickets') }">
            <el-icon :size="20"><Tickets /></el-icon>
            <span v-if="!isCollapse" class="nav-label">工单管理</span>
          </router-link>

          <router-link to="/admin/stats" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/stats') }">
            <el-icon :size="20"><DataAnalysis /></el-icon>
            <span v-if="!isCollapse" class="nav-label">统计分析</span>
          </router-link>

          <router-link to="/admin/crawl" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/crawl') }">
            <el-icon :size="20"><Download /></el-icon>
            <span v-if="!isCollapse" class="nav-label">数据中心</span>
          </router-link>

          <router-link to="/admin/collection" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/collection') }">
            <el-icon :size="20"><Refresh /></el-icon>
            <span v-if="!isCollapse" class="nav-label">补采闭环</span>
          </router-link>

          <div v-if="!isCollapse" class="nav-group-title">系统管理</div>

          <router-link v-if="authStore.isSuperAdmin()" to="/admin/users" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/users') }">
            <el-icon :size="20"><User /></el-icon>
            <span v-if="!isCollapse" class="nav-label">用户管理</span>
          </router-link>

          <router-link v-if="authStore.isSuperAdmin()" to="/admin/roles" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/roles') }">
            <el-icon :size="20"><Avatar /></el-icon>
            <span v-if="!isCollapse" class="nav-label">角色管理</span>
          </router-link>

          <router-link v-if="authStore.isSuperAdmin()" to="/admin/departments" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/departments') }">
            <el-icon :size="20"><OfficeBuilding /></el-icon>
            <span v-if="!isCollapse" class="nav-label">部门管理</span>
          </router-link>

          <router-link to="/admin/logs" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/logs') }">
            <el-icon :size="20"><List /></el-icon>
            <span v-if="!isCollapse" class="nav-label">问答日志</span>
          </router-link>

          <router-link v-if="authStore.isSuperAdmin()" to="/admin/sensitive-words" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/sensitive-words') }">
            <el-icon :size="20"><Lock /></el-icon>
            <span v-if="!isCollapse" class="nav-label">敏感词管理</span>
          </router-link>

          <router-link v-if="authStore.isSuperAdmin()" to="/admin/audit-logs" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/audit-logs') }">
            <el-icon :size="20"><Tickets /></el-icon>
            <span v-if="!isCollapse" class="nav-label">审计日志</span>
          </router-link>
        </template>

        <router-link to="/profile" class="nav-item" :class="{ active: currentRoute === '/profile' }">
          <el-icon :size="20"><UserFilled /></el-icon>
          <span v-if="!isCollapse" class="nav-label">个人中心</span>
        </router-link>
      </nav>

      <!-- 底部操作 -->
      <div class="sidebar-footer">
        <button class="footer-btn collapse-btn" @click="isCollapse = !isCollapse" title="收起/展开">
          <el-icon :size="18"><component :is="isCollapse ? 'Expand' : 'Fold'" /></el-icon>
        </button>
        <button class="footer-btn" @click="themeStore.toggle()" title="切换主题">
          <el-icon :size="18"><component :is="themeStore.isDark ? 'Sunny' : 'Moon'" /></el-icon>
        </button>
        <button v-if="!isCollapse" class="footer-btn logout-btn" @click="authStore.logout()" title="退出登录">
          <el-icon :size="18"><SwitchButton /></el-icon>
          <span class="nav-label">退出</span>
        </button>
      </div>
    </aside>

    <!-- 移动端导航抽屉遮罩 -->
    <div v-if="isMobile && mobileMenuOpen" class="mobile-backdrop" @click="mobileMenuOpen = false"></div>

    <!-- 主内容 -->
    <div class="layout-body">
      <!-- 移动端顶栏 -->
      <header class="mobile-bar">
        <button class="mobile-bar-btn" aria-label="打开导航" @click="mobileMenuOpen = true">
          <el-icon :size="20"><Expand /></el-icon>
        </button>
        <span class="mobile-bar-title">{{ pageTitle }}</span>
        <button class="mobile-bar-btn" aria-label="切换主题" @click="themeStore.toggle()">
          <el-icon :size="18"><component :is="themeStore.isDark ? 'Sunny' : 'Moon'" /></el-icon>
        </button>
      </header>

      <main class="main-content">
        <router-view />
      </main>
    </div>

    <!-- AI 助手悬浮入口（后端由 COUNSELOR_ENABLED 开关控制） -->
    <FloatingCounselor ref="counselorRef" />

    <!-- 消息通知 -->
    <el-dialog v-model="notificationOpen" title="消息通知" width="560px" class="notif-dialog">
      <div class="notif-toolbar">
        <el-button v-if="unreadCount > 0" link type="primary" @click="markAllRead">全部标为已读</el-button>
      </div>
      <el-empty v-if="!notifications.length" description="暂无消息" :image-size="70" />
      <div v-else v-loading="notifLoading" class="notif-list">
        <div
          v-for="n in notifications"
          :key="n.id"
          class="notif-item"
          :class="{ unread: !n.is_read }"
          @click="openNotification(n)"
        >
          <div class="notif-head">
            <span class="notif-title">{{ n.title }}</span>
            <span class="notif-time">{{ formatNotifTime(n.created_at) }}</span>
          </div>
          <div class="notif-content">{{ n.content }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { useThemeStore } from '@/store/theme'
import { reviewApi } from '@/api/security'
import { notificationApi } from '@/api/notification'
import type { NotificationItem } from '@/api/notification'
import FloatingCounselor from '@/components/counselor/FloatingCounselor.vue'
import {
  Expand, Fold, Sunny, Moon, Reading, SwitchButton,
  ChatDotRound, Document, User, List, DataAnalysis, UserFilled,
  FolderOpened, Avatar, OfficeBuilding, Bell, Tickets, Stamp, Lock, Download, Refresh,
  Service, VideoCamera,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const isCollapse = ref(false)
const reviewCount = ref(0)
const counselorRef = ref<InstanceType<typeof FloatingCounselor> | null>(null)

// ==================== 消息通知 ====================
const notificationOpen = ref(false)
const notifications = ref<NotificationItem[]>([])
const unreadCount = ref(0)
const notifLoading = ref(false)
let notifTimer: ReturnType<typeof setInterval> | undefined

async function loadUnreadCount() {
  try {
    const res = await notificationApi.unreadCount()
    unreadCount.value = res.data.data?.count || 0
  } catch {
    unreadCount.value = 0
  }
}

async function loadNotifications() {
  notifLoading.value = true
  try {
    const res = await notificationApi.list({ page: 1, page_size: 30 })
    notifications.value = res.data.data?.items || []
  } catch {
    notifications.value = []
  } finally {
    notifLoading.value = false
  }
}

function openNotifications() {
  notificationOpen.value = true
  loadNotifications()
  loadUnreadCount()
}

async function markAllRead() {
  try {
    await notificationApi.markAllRead()
    notifications.value.forEach((n) => { n.is_read = true })
    unreadCount.value = 0
  } catch {
    // 静默失败，下次打开弹窗会刷新
  }
}

async function openNotification(n: NotificationItem) {
  if (!n.is_read) {
    try {
      await notificationApi.markRead(n.id)
      n.is_read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    } catch {
      // 忽略标记失败，仍允许跳转
    }
  }
  notificationOpen.value = false
  if (n.link) router.push(n.link)
}

function formatNotifTime(value: string | null) {
  if (!value) return ''
  return value.replace('T', ' ').slice(0, 16)
}

function openCounselor() {
  counselorRef.value?.openPanel()
}

// ==================== 移动端适配 ====================
const isMobile = ref(false)
const mobileMenuOpen = ref(false)

function updateViewportMode() {
  isMobile.value = window.innerWidth <= 768
  if (isMobile.value) {
    // 移动端抽屉始终展示完整菜单，不沿用桌面端的折叠状态
    isCollapse.value = false
  } else {
    mobileMenuOpen.value = false
  }
}

const pageTitle = computed(() => (route.meta.title as string) || 'AI 学院教学知识库')

// 路由切换后自动关闭导航抽屉
watch(() => route.path, () => {
  mobileMenuOpen.value = false
})

// 拉取待审核文档数量（侧边栏红色角标）
async function loadReviewCount() {
  try {
    const res = await reviewApi.queue({ review_status: 1, page: 1, page_size: 1 })
    reviewCount.value = res.data.data?.total || 0
  } catch {
    reviewCount.value = 0
  }
}
onMounted(() => {
  updateViewportMode()
  window.addEventListener('resize', updateViewportMode)
  loadReviewCount()
  loadUnreadCount()
  notifTimer = setInterval(loadUnreadCount, 60000)
})
onUnmounted(() => {
  window.removeEventListener('resize', updateViewportMode)
  if (notifTimer) clearInterval(notifTimer)
})

const currentRoute = computed(() => {
  const path = route.path
  if (path.startsWith('/admin/documents')) return '/admin/documents'
  if (path.startsWith('/admin/categories')) return '/admin/categories'
  if (path.startsWith('/admin/videos')) return '/admin/videos'
  if (path.startsWith('/admin/users')) return '/admin/users'
  if (path.startsWith('/admin/roles')) return '/admin/roles'
  if (path.startsWith('/admin/departments')) return '/admin/departments'
  if (path.startsWith('/admin/logs')) return '/admin/logs'
  if (path.startsWith('/admin/stats')) return '/admin/stats'
  if (path.startsWith('/admin/crawl')) return '/admin/crawl'
  if (path.startsWith('/admin/collection')) return '/admin/collection'
  if (path.startsWith('/admin/announcements')) return '/admin/announcements'
  if (path.startsWith('/admin/tickets')) return '/admin/tickets'
  if (path.startsWith('/admin/review')) return '/admin/review'
  if (path.startsWith('/admin/sensitive-words')) return '/admin/sensitive-words'
  if (path.startsWith('/admin/audit-logs')) return '/admin/audit-logs'
  if (path.startsWith('/documents')) return '/documents'
  if (path.startsWith('/videos')) return '/videos'
  if (path.startsWith('/tickets')) return '/tickets'
  if (path.startsWith('/my-collections')) return '/my-collections'
  if (path.startsWith('/chat')) return '/chat'
  if (path.startsWith('/profile')) return '/profile'
  return '/chat'
})
</script>

<style scoped>
/* ========== 消息通知 ========== */
.nav-notif {
  position: relative;
}
.nav-notif :deep(.el-badge__content) {
  top: 2px;
  right: 8px;
}
.notif-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.notif-list {
  max-height: 60vh;
  overflow-y: auto;
}
.notif-item {
  padding: 12px 14px;
  margin-bottom: 8px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-bg-card);
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease;
}
.notif-item:hover {
  border-color: var(--color-primary);
}
.notif-item.unread {
  background: var(--color-primary-light);
  border-color: var(--color-primary);
}
.notif-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}
.notif-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.notif-time {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.notif-content {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-secondary);
  word-break: break-word;
}

/* ========== 布局 ========== */
.main-layout {
  display: flex;
  height: 100vh;
  height: 100dvh;
  background: var(--color-bg-page);
  color: var(--color-text-body);
}

/* 移动端顶栏 + 主内容 */
.layout-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100%;
}
.mobile-bar { display: none; }
.mobile-bar-btn {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border: none;
  background: transparent;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
}
.mobile-bar-btn:active { background: var(--color-bg-hover); }
.mobile-bar-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* ========== 侧边栏 ========== */
.sidebar {
  width: 220px;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-card);
  border-right: 1px solid var(--color-border);
  transition: width 0.25s ease;
  flex-shrink: 0;
  overflow: hidden;
  z-index: 10;
}
.sidebar.collapsed { width: 64px; }

/* Logo */
.sidebar-logo {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 10px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.sidebar.collapsed .sidebar-logo { justify-content: center; padding: 0; }

.logo-text {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary);
  white-space: nowrap;
}

/* 导航 */
.sidebar-nav {
  flex: 1;
  padding: 12px 8px;
  overflow-y: auto;
  overflow-x: hidden;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  color: var(--color-text-secondary);
  text-decoration: none;
  font-size: 14px;
  transition: all 0.15s;
  margin-bottom: 2px;
  white-space: nowrap;
}
.nav-item:hover { background: var(--color-primary-light); color: var(--color-primary); }
.nav-item.active { background: var(--color-primary-light); color: var(--color-primary); font-weight: 600; }

/* 按钮形态的导航项（如 AI 助手），与 router-link 保持一致的视觉 */
.nav-button {
  width: 100%;
  border: 0;
  background: transparent;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
}

.nav-group-title {
  margin: 16px 12px 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--color-text-secondary);
  opacity: 0.75;
  white-space: nowrap;
}

.sidebar.collapsed .nav-item {
  justify-content: center;
  padding: 10px;
  gap: 0;
}

.nav-label {
  white-space: nowrap;
}
.nav-badge {
  min-width: 18px;
  height: 18px;
  margin-left: auto;
  padding: 0 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  background: #f56c6c;
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  font-weight: 600;
}

/* 底部 */
.sidebar-footer {
  padding: 8px;
  border-top: 1px solid var(--color-border);
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: center;
}

.sidebar.collapsed .sidebar-footer {
  flex-direction: column;
  align-items: center;
}

.footer-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  transition: all 0.15s;
}
.footer-btn:hover { background: var(--color-primary-light); color: var(--color-primary); }
.logout-btn {
  width: auto;
  padding: 0 12px;
  gap: 6px;
  font-size: 13px;
}
.logout-btn:hover { color: var(--color-danger) !important; background: #FEF2F2; }
.main-layout.dark .logout-btn:hover { background: rgba(239, 68, 68, 0.15); }

/* ========== 主内容区 ========== */
.main-content {
  flex: 1;
  overflow-y: auto;
  background: var(--color-bg-page);
  min-width: 0;
  min-height: 0;
}

/* ========== 移动端 ========== */
@media (max-width: 768px) {
  /* 侧栏改为抽屉，不再挤占内容宽度 */
  .sidebar {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    width: min(80vw, 280px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
    transform: translateX(-100%);
    transition: transform 0.25s ease;
    z-index: 2200;
    box-shadow: 8px 0 40px rgba(15, 23, 42, 0.28);
  }
  .sidebar.collapsed { width: min(80vw, 280px); }
  .sidebar.mobile-open { transform: translateX(0); }
  .mobile-backdrop {
    position: fixed;
    inset: 0;
    z-index: 2199;
    background: rgba(15, 23, 42, 0.45);
  }

  .mobile-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 48px;
    flex-shrink: 0;
    padding: 0 8px;
    background: var(--color-bg-card);
    border-bottom: 1px solid var(--color-border);
  }

  .collapse-btn { display: none; }
  .logout-btn { width: auto; }
}
</style>

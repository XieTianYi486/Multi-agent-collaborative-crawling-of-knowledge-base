<template>
  <div class="main-layout" :class="{ dark: themeStore.isDark }">
    <!-- 侧边栏 -->
    <aside class="sidebar" :class="{ collapsed: isCollapse }">
      <!-- Logo -->
      <div class="sidebar-logo">
        <el-icon :size="24" color="var(--color-primary)"><Reading /></el-icon>
        <span v-if="!isCollapse" class="logo-text">AI 学院教学知识库</span>
      </div>

      <!-- 菜单 -->
      <nav class="sidebar-nav">
        <router-link to="/chat" class="nav-item" :class="{ active: currentRoute === '/chat' }">
          <el-icon :size="20"><ChatDotRound /></el-icon>
          <span v-if="!isCollapse" class="nav-label">智能问答</span>
        </router-link>

        <router-link to="/documents" class="nav-item" :class="{ active: currentRoute === '/documents' }">
          <el-icon :size="20"><FolderOpened /></el-icon>
          <span v-if="!isCollapse" class="nav-label">知识库文档</span>
        </router-link>

        <router-link to="/tickets" class="nav-item" :class="{ active: currentRoute === '/tickets' }">
          <el-icon :size="20"><Tickets /></el-icon>
          <span v-if="!isCollapse" class="nav-label">我的工单</span>
        </router-link>

        <template v-if="authStore.isAdmin()">
          <router-link to="/admin/documents" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/documents') }">
            <el-icon :size="20"><Document /></el-icon>
            <span v-if="!isCollapse" class="nav-label">文档管理</span>
          </router-link>

          <router-link to="/admin/categories" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/categories') }">
            <el-icon :size="20"><FolderOpened /></el-icon>
            <span v-if="!isCollapse" class="nav-label">分类管理</span>
          </router-link>

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

          <router-link to="/admin/stats" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/stats') }">
            <el-icon :size="20"><DataAnalysis /></el-icon>
            <span v-if="!isCollapse" class="nav-label">统计分析</span>
          </router-link>

          <router-link to="/admin/crawl" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/crawl') }">
            <el-icon :size="20"><Download /></el-icon>
            <span v-if="!isCollapse" class="nav-label">数据中心</span>
          </router-link>

          <router-link to="/admin/announcements" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/announcements') }">
            <el-icon :size="20"><Bell /></el-icon>
            <span v-if="!isCollapse" class="nav-label">公告管理</span>
          </router-link>

          <router-link to="/admin/tickets" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/tickets') }">
            <el-icon :size="20"><Tickets /></el-icon>
            <span v-if="!isCollapse" class="nav-label">工单管理</span>
          </router-link>

          <router-link to="/admin/review" class="nav-item" :class="{ active: currentRoute.startsWith('/admin/review') }">
            <el-icon :size="20"><Stamp /></el-icon>
            <span v-if="!isCollapse" class="nav-label">知识审核</span>
            <span v-if="!isCollapse && reviewCount > 0" class="nav-badge">{{ reviewCount > 99 ? '99+' : reviewCount }}</span>
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
        <button class="footer-btn" @click="isCollapse = !isCollapse" title="收起/展开">
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

    <!-- 主内容 -->
    <main class="main-content">
      <router-view />
    </main>

    <!-- AI 导员悬浮入口 -->
    <FloatingCounselor />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { useThemeStore } from '@/store/theme'
import { reviewApi } from '@/api/security'
import FloatingCounselor from '@/components/counselor/FloatingCounselor.vue'
import {
  Expand, Fold, Sunny, Moon, Reading, SwitchButton,
  ChatDotRound, Document, User, List, DataAnalysis, UserFilled,
  FolderOpened, Avatar, OfficeBuilding, Bell, Tickets, Stamp, Lock, Download,
} from '@element-plus/icons-vue'

const route = useRoute()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const isCollapse = ref(false)
const reviewCount = ref(0)

// 拉取待审核文档数量（侧边栏红色角标）
async function loadReviewCount() {
  try {
    const res = await reviewApi.queue({ review_status: 1, page: 1, page_size: 1 })
    reviewCount.value = res.data.data?.total || 0
  } catch {
    reviewCount.value = 0
  }
}
onMounted(loadReviewCount)

const currentRoute = computed(() => {
  const path = route.path
  if (path.startsWith('/admin/documents')) return '/admin/documents'
  if (path.startsWith('/admin/categories')) return '/admin/categories'
  if (path.startsWith('/admin/users')) return '/admin/users'
  if (path.startsWith('/admin/roles')) return '/admin/roles'
  if (path.startsWith('/admin/departments')) return '/admin/departments'
  if (path.startsWith('/admin/logs')) return '/admin/logs'
  if (path.startsWith('/admin/stats')) return '/admin/stats'
  if (path.startsWith('/admin/crawl')) return '/admin/crawl'
  if (path.startsWith('/admin/announcements')) return '/admin/announcements'
  if (path.startsWith('/admin/tickets')) return '/admin/tickets'
  if (path.startsWith('/admin/review')) return '/admin/review'
  if (path.startsWith('/admin/sensitive-words')) return '/admin/sensitive-words'
  if (path.startsWith('/admin/audit-logs')) return '/admin/audit-logs'
  if (path.startsWith('/documents')) return '/documents'
  if (path.startsWith('/tickets')) return '/tickets'
  if (path.startsWith('/chat')) return '/chat'
  if (path.startsWith('/profile')) return '/profile'
  return '/chat'
})
</script>

<style scoped>
/* ========== 布局 ========== */
.main-layout {
  display: flex;
  height: 100vh;
  background: var(--color-bg-page);
  color: var(--color-text-body);
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

/* ========== 主内容区 ========== */
.main-content {
  flex: 1;
  overflow-y: auto;
  background: var(--color-bg-page);
  min-width: 0;
}
</style>

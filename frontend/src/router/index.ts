import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/auth/LoginPage.vue'),
      meta: { guest: true },
    },
    {
      path: '/register',
      name: 'Register',
      component: () => import('@/views/auth/RegisterPage.vue'),
      meta: { guest: true },
    },
    {
      path: '/',
      component: () => import('@/components/layout/MainLayout.vue'),
      children: [
        {
          path: '',
          redirect: '/chat',
        },
        {
          path: 'chat',
          name: 'Chat',
          component: () => import('@/views/chat/ChatPage.vue'),
          meta: { title: '智能问答' },
        },
        {
          path: 'chat/:sessionId',
          name: 'ChatSession',
          component: () => import('@/views/chat/ChatPage.vue'),
          meta: { title: '智能问答' },
        },
        {
          path: 'documents',
          name: 'Documents',
          component: () => import('@/views/documents/BrowsePage.vue'),
          meta: { title: '知识库文档' },
        },
        {
          path: 'tickets',
          name: 'MyTickets',
          component: () => import('@/views/tickets/MyTicketsPage.vue'),
          meta: { title: '我的工单' },
        },
        {
          path: 'admin',
          redirect: '/admin/documents',
        },
        {
          path: 'admin/documents',
          name: 'AdminDocuments',
          component: () => import('@/views/admin/DocumentPage.vue'),
          meta: { title: '文档管理', admin: true },
        },
        {
          path: 'admin/categories',
          name: 'AdminCategories',
          component: () => import('@/views/admin/CategoryPage.vue'),
          meta: { title: '分类管理', admin: true },
        },
        {
          path: 'admin/users',
          name: 'AdminUsers',
          component: () => import('@/views/admin/UserPage.vue'),
          meta: { title: '用户管理', admin: true, superAdmin: true },
        },
        {
          path: 'admin/roles',
          name: 'AdminRoles',
          component: () => import('@/views/admin/RolePage.vue'),
          meta: { title: '角色管理', admin: true, superAdmin: true },
        },
        {
          path: 'admin/departments',
          name: 'AdminDepartments',
          component: () => import('@/views/admin/DeptPage.vue'),
          meta: { title: '部门管理', admin: true, superAdmin: true },
        },
        {
          path: 'admin/logs',
          name: 'AdminLogs',
          component: () => import('@/views/admin/LogPage.vue'),
          meta: { title: '问答日志', admin: true },
        },
        {
          path: 'admin/stats',
          name: 'AdminStats',
          component: () => import('@/views/admin/StatsPage.vue'),
          meta: { title: '统计分析', admin: true },
        },
        {
          path: 'admin/crawl',
          name: 'AdminCrawl',
          component: () => import('@/views/admin/CrawlPage.vue'),
          meta: { title: '数据中心', admin: true },
        },
        {
          path: 'admin/announcements',
          name: 'AdminAnnouncements',
          component: () => import('@/views/admin/AnnouncePage.vue'),
          meta: { title: '公告管理', admin: true },
        },
        {
          path: 'admin/tickets',
          name: 'AdminTickets',
          component: () => import('@/views/admin/TicketAdminPage.vue'),
          meta: { title: '工单管理', admin: true },
        },
        {
          path: 'admin/review',
          name: 'Review',
          component: () => import('@/views/admin/ReviewPage.vue'),
          meta: { title: '知识审核', admin: true },
        },
        {
          path: 'admin/sensitive-words',
          name: 'SensitiveWords',
          component: () => import('@/views/admin/SensitiveWordPage.vue'),
          meta: { title: '敏感词管理', admin: true },
        },
        {
          path: 'admin/audit-logs',
          name: 'AuditLogs',
          component: () => import('@/views/admin/AuditLogPage.vue'),
          meta: { title: '审计日志', admin: true },
        },
        {
          path: 'profile',
          name: 'Profile',
          component: () => import('@/views/auth/ProfilePage.vue'),
          meta: { title: '个人中心' },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: () => import('@/views/auth/NotFoundPage.vue'),
    },
  ],
})

// 路由守卫
router.beforeEach(async (to, _from, next) => {
  const token = localStorage.getItem('access_token')

  // 已登录用户访问登录/注册页 → 跳转到聊天页
  if (to.meta.guest && token) {
    next('/chat')
    return
  }

  // 未登录用户访问需要认证的页面 → 跳转到登录页
  if (!to.meta.guest && !token) {
    next('/login')
    return
  }

  // 管理员页面权限检查
  if (to.meta.admin && token) {
    try {
      // 从 JWT payload 解析角色（不发起网络请求）
      const payload = JSON.parse(atob(token.split('.')[1]))
      const roleName = payload.role_name || ''
      const isAdminUser = roleName === '超级管理员' || roleName === '知识库管理员'
      const isSuperAdminUser = roleName === '超级管理员'

      if (to.meta.superAdmin && !isSuperAdminUser) {
        next('/chat')
        return
      }
      if (!isAdminUser) {
        next('/chat')
        return
      }
    } catch {
      next('/chat')
      return
    }
  }

  next()
})

export default router

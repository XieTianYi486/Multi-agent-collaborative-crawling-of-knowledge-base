<template>
  <div class="help-page">
    <header class="help-topbar">
      <div class="topbar-brand">
        <el-icon :size="20" class="topbar-icon"><Reading /></el-icon>
        <span>人工智能学院 · 教学知识库</span>
      </div>
      <el-button v-if="!isLoggedIn" type="primary" size="small" @click="goLogin">去登录</el-button>
      <el-button v-else text size="small" @click="backToApp">返回系统</el-button>
    </header>

    <div class="page-header">
      <div class="header-left">
        <el-icon class="header-icon" :size="22"><QuestionFilled /></el-icon>
        <h2>使用帮助</h2>
        <el-tag v-if="currentRoleName" effect="plain" type="primary">{{ currentRoleName }}</el-tag>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="登录后侧边栏只会显示你有权限使用的菜单。下面按角色说明每个功能的用途与入口，先找到自己的角色即可；未登录也可先预览。"
      class="hint"
    />

    <el-tabs v-model="activeRole" class="role-tabs">
      <el-tab-pane v-for="role in roleGuides" :key="role.key" :label="role.label" :name="role.key">
        <div class="role-summary">
          <el-icon :size="18"><InfoFilled /></el-icon>
          <span>{{ role.summary }}</span>
        </div>

        <h3 class="section-title">我能做什么</h3>
        <div class="capability-grid">
          <div v-for="cap in role.capabilities" :key="cap.title" class="capability-card">
            <div class="capability-icon">
              <el-icon :size="18"><component :is="cap.icon" /></el-icon>
            </div>
            <div class="capability-body">
              <div class="capability-title">{{ cap.title }}</div>
              <div class="capability-desc">{{ cap.desc }}</div>
            </div>
            <el-button
              v-if="cap.path"
              class="capability-action"
              size="small"
              text
              type="primary"
              @click="go(cap.path)"
            >
              去看看<el-icon :size="12"><ArrowRight /></el-icon>
            </el-button>
          </div>
        </div>

        <h3 class="section-title">第一步怎么做</h3>
        <ol class="step-list">
          <li v-for="(step, i) in role.steps" :key="step">
            <span class="step-index">{{ i + 1 }}</span>
            <span class="step-text">{{ step }}</span>
          </li>
        </ol>

        <h3 v-if="role.faqs.length" class="section-title">常见问题</h3>
        <el-collapse v-if="role.faqs.length" class="faq-collapse">
          <el-collapse-item v-for="faq in role.faqs" :key="faq.q" :title="faq.q">
            <div class="faq-answer">{{ faq.a }}</div>
          </el-collapse-item>
        </el-collapse>
      </el-tab-pane>
    </el-tabs>

    <h3 class="section-title common-title">问答小技巧（所有角色通用）</h3>
    <div class="tips-grid">
      <div v-for="tip in commonTips" :key="tip.title" class="tip-card">
        <div class="tip-title">
          <el-icon :size="16"><component :is="tip.icon" /></el-icon>
          <span>{{ tip.title }}</span>
        </div>
        <div class="tip-desc">{{ tip.desc }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { Component } from 'vue'
import { useAuthStore } from '@/store/auth'
import {
  QuestionFilled, InfoFilled, ArrowRight,
  ChatDotRound, Service, FolderOpened, VideoCamera, Tickets, Refresh, Avatar,
  Document, Stamp, Bell, DataAnalysis, Download, User, Lock, OfficeBuilding,
  List, UploadFilled, Search, Reading, Setting,
} from '@element-plus/icons-vue'

interface Capability {
  icon: Component
  title: string
  desc: string
  path?: string
}

interface RoleGuide {
  key: string
  label: string
  summary: string
  capabilities: Capability[]
  steps: string[]
  faqs: { q: string; a: string }[]
}

const router = useRouter()
const authStore = useAuthStore()

/** 侧边栏通用入口（学生/老师/访客共用的检索与浏览能力） */
const learnerCapabilities: Capability[] = [
  {
    icon: ChatDotRound,
    title: '智能问答',
    desc: '用自然语言描述问题，系统从已入库资料中检索答案并标注来源。',
    path: '/chat',
  },
  {
    icon: Service,
    title: 'AI 助手',
    desc: '侧边栏「AI 助手」或右下角悬浮球，可在任意页面随时唤起对话。',
  },
  {
    icon: FolderOpened,
    title: '知识库文档',
    desc: '按分类浏览全部教学资料，支持搜索与在线阅读。',
    path: '/documents',
  },
  {
    icon: VideoCamera,
    title: '视频专区',
    desc: '嵌入式、AI 应用开发等方向的精选 B 站课程，可按关键词与难度筛选。',
    path: '/videos',
  },
  {
    icon: Refresh,
    title: '我的补采',
    desc: '问答没找到答案时提交补采需求，管理员处理后可在这里看进度。',
    path: '/my-collections',
  },
  {
    icon: Tickets,
    title: '我的工单',
    desc: '账号、资料等问题提交工单，处理进展会通过消息通知提醒。',
    path: '/tickets',
  },
]

const roleGuides: RoleGuide[] = [
  {
    key: 'student',
    label: '学生 / 访客',
    summary: '核心用法只有一个：把问题讲清楚，剩下的交给检索。系统只基于入库资料回答，并给出原文出处。',
    capabilities: learnerCapabilities,
    steps: [
      '进入「智能问答」，直接描述现象或知识点，不要只丢一个关键词。',
      '答案下方展开「查看来源」，核对文档名称、章节与原文链接。',
      '没有找到答案时点击「提交补采」，管理员补充资料后可回来复查。',
    ],
    faqs: [
      {
        q: '为什么有些问题系统直接拒答？',
        a: '系统只基于知识库收录的资料回答，不调用模型自身知识。资料没覆盖时会主动拒答，避免编造答案。',
      },
      {
        q: '我的提问会被别人看到吗？',
        a: '提问会记录到问答日志用于改进知识库，管理端不展示与教学无关的个人隐私信息。',
      },
    ],
  },
  {
    key: 'teacher',
    label: '老师',
    summary: '在教学资料检索之外，老师可以把课程资料投稿进知识库，并查看所带班级学生的使用情况。',
    capabilities: [
      ...learnerCapabilities,
      {
        icon: UploadFilled,
        title: '投稿教学资料',
        desc: '在「知识库文档」上传 PDF / Word / Excel / Markdown / TXT，审核通过后自动入库。',
        path: '/documents',
      },
      {
        icon: Avatar,
        title: '我的学生',
        desc: '查看所带班级与学生名单，了解学生的问答情况。',
        path: '/my-students',
      },
    ],
    steps: [
      '打开「知识库文档」，使用上传入口提交教学资料并等待审核。',
      '审核通过后资料会自动分块、向量化，随后即可被智能问答检索到。',
      '在「我的学生」关注学生高频问题，有针对性地补充资料。',
    ],
    faqs: [
      {
        q: '上传的文档多久能被检索到？',
        a: '需要经过解析、分块、向量化和管理员审核，审核通过后生效；扫描版 PDF 会先走 OCR 识别。',
      },
      {
        q: '支持哪些文件格式？',
        a: 'PDF、Word（docx）、Excel（xlsx）、Markdown、纯文本。',
      },
    ],
  },
  {
    key: 'dept_admin',
    label: '院系管理员',
    summary: '以院系资料查阅为主。当前版本的管理后台入口仅开放给知识库管理员与超级管理员，院系维度的报表可由知识库管理员协助导出。',
    capabilities: learnerCapabilities,
    steps: [
      '使用「智能问答」和「知识库文档」查阅院系教学资料。',
      '需要院系维度的问答统计报表时，联系知识库管理员导出。',
      '发现资料缺失，通过「我的补采」提交需求。',
    ],
    faqs: [
      {
        q: '为什么我看不到管理菜单？',
        a: '当前前端只向知识库管理员和超级管理员开放管理入口，院系管理员以资料查阅为主，避免误操作影响全校知识库。',
      },
    ],
  },
  {
    key: 'knowledge_admin',
    label: '知识库管理员',
    summary: '负责内容运营：文档、分类、视频、审核、公告、工单、统计，以及爬取数据中心和补采闭环。',
    capabilities: [
      {
        icon: Document,
        title: '文档管理',
        desc: '上传、编辑、删除文档，调整密级与分类，查看处理状态。',
        path: '/admin/documents',
      },
      {
        icon: FolderOpened,
        title: '分类管理',
        desc: '维护知识库分类树，爬虫打标结果会映射到这里的分类。',
        path: '/admin/categories',
      },
      {
        icon: VideoCamera,
        title: '视频管理',
        desc: '新增、编辑、排序、上下架视频专区的课程条目。',
        path: '/admin/videos',
      },
      {
        icon: Stamp,
        title: '知识审核',
        desc: '审核待发布文档，侧边栏红色角标就是待审核数量。',
        path: '/admin/review',
      },
      {
        icon: Bell,
        title: '公告管理',
        desc: '发布首页公告，用户会在智能问答页顶部看到。',
        path: '/admin/announcements',
      },
      {
        icon: Tickets,
        title: '工单管理',
        desc: '处理用户提交的工单并回复，回复会触发消息通知。',
        path: '/admin/tickets',
      },
      {
        icon: DataAnalysis,
        title: '统计分析',
        desc: '问答量趋势、高频问题、未命中问题与满意度统计。',
        path: '/admin/stats',
      },
      {
        icon: Download,
        title: '数据中心',
        desc: '站点采集状态、爬取流水线实时进度、LLM 成本账本，可手动触发采集。',
        path: '/admin/crawl',
      },
      {
        icon: Refresh,
        title: '补采闭环',
        desc: '集中处理用户提交的补采需求，触发补充采集或标记已解决。',
        path: '/admin/collection',
      },
      {
        icon: List,
        title: '问答日志',
        desc: '查看每次提问的答案、来源、耗时与用户反馈。',
        path: '/admin/logs',
      },
    ],
    steps: [
      '先看侧边栏「知识审核」的红色角标，处理待审核文档。',
      '在「数据中心」查看站点采集状态，必要时手动触发爬取流水线。',
      '在「补采闭环」处理用户提交的补采需求，形成"提问→补采→入库"闭环。',
    ],
    faqs: [
      {
        q: '审核通过后多久能在问答里检索到？',
        a: '审核通过会触发解析与向量化，完成后即可被检索；大批量导入时请等待处理状态变为已完成。',
      },
      {
        q: '爬取流水线怎么手动运行？',
        a: '「数据中心」页面点击立即运行即可，也可以在后端执行 python run_crawl_daily.py。',
      },
      {
        q: 'LLM 花费在哪里看？',
        a: '「数据中心」提供成本账本与每日预算闸门，超出预算后 LLM 步骤会自动降级为规则管线。',
      },
    ],
  },
  {
    key: 'super_admin',
    label: '超级管理员',
    summary: '拥有全部权限，并额外负责用户、角色、部门与系统安全配置。',
    capabilities: [
      {
        icon: User,
        title: '用户管理',
        desc: '新增用户、分配角色与部门、启用或禁用账号。',
        path: '/admin/users',
      },
      {
        icon: Avatar,
        title: '角色管理',
        desc: '维护角色及其权限项，控制各角色可见的功能范围。',
        path: '/admin/roles',
      },
      {
        icon: OfficeBuilding,
        title: '部门管理',
        desc: '维护院系与部门结构，注册时可选择所属部门。',
        path: '/admin/departments',
      },
      {
        icon: Lock,
        title: '敏感词管理',
        desc: '维护问答的敏感词库，命中后会被拦截或替换。',
        path: '/admin/sensitive-words',
      },
      {
        icon: Tickets,
        title: '审计日志',
        desc: '查看关键管理操作与登录行为的审计记录。',
        path: '/admin/audit-logs',
      },
    ],
    steps: [
      '在「用户管理」为师生分配正确角色和部门，角色决定他们能看到哪些菜单。',
      '在「角色管理」核对权限项，避免误把管理权限开放给无关角色。',
      '定期查看「审计日志」和「敏感词管理」，并修改默认管理员密码。',
    ],
    faqs: [
      {
        q: '怎么给别人开通管理员权限？',
        a: '在「用户管理」把该用户的角色改为知识库管理员或超级管理员，重新登录后即可看到管理菜单。',
      },
      {
        q: '默认管理员密码在哪里修改？',
        a: '修改 backend/.env 中的 ADMIN_PASSWORD 并重启后端。生产环境必须修改默认密码和 JWT_SECRET_KEY。',
      },
    ],
  },
]

const commonTips = [
  {
    icon: ChatDotRound,
    title: '描述现象，而不是只给关键词',
    desc: '例如"ESP32 烧录后串口一直重启"比"ESP32 重启"更容易命中资料。',
  },
  {
    icon: Search,
    title: '一次问一个问题',
    desc: '把多个问题拆开问，检索更精准，来源也更清楚。',
  },
  {
    icon: Reading,
    title: '一定展开「查看来源」',
    desc: '答案中的编号对应文档名称、章节、页码和原文链接，核对后再使用。',
  },
  {
    icon: InfoFilled,
    title: '被拒答不是系统坏了',
    desc: '说明知识库还没收录相关内容，可以提交补采，或在知识库文档里搜同义词再试。',
  },
  {
    icon: Setting,
    title: '多轮追问会带上上下文',
    desc: '在同一会话里继续追问，系统会结合上文理解指代。',
  },
]

const ROLE_TO_TAB: Record<string, string> = {
  学生: 'student',
  访客: 'student',
  老师: 'teacher',
  院系管理员: 'dept_admin',
  知识库管理员: 'knowledge_admin',
  超级管理员: 'super_admin',
}

const currentRoleName = computed(() => authStore.user?.role_name || '')
const isLoggedIn = computed(() => !!authStore.token)
const activeRole = ref(ROLE_TO_TAB[currentRoleName.value] || 'student')

/** 未登录时只做预览，点功能入口统一引导到登录页 */
function go(path?: string) {
  if (!path) return
  router.push(isLoggedIn.value ? path : '/login')
}

function goLogin() {
  router.push('/login')
}

function backToApp() {
  router.push('/chat')
}
</script>

<style scoped>
.help-page {
  padding: 24px;
  min-height: 100vh;
  background: var(--color-bg-page);
}
.help-topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 24px;
  margin: -24px -24px 20px;
  background: var(--color-bg-card);
  border-bottom: 1px solid var(--color-border);
}
.topbar-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.topbar-icon {
  color: var(--color-primary);
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.header-left h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.header-icon {
  color: var(--color-primary);
}
.hint {
  margin-bottom: 16px;
}

.role-tabs :deep(.el-tabs__content) {
  overflow: visible;
}

.role-summary {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px 14px;
  margin-bottom: 20px;
  border-left: 3px solid var(--color-primary);
  border-radius: var(--radius-btn);
  background: var(--color-primary-light);
  color: var(--color-text-body);
  font-size: 13px;
  line-height: 1.7;
}
.role-summary .el-icon {
  margin-top: 2px;
  flex-shrink: 0;
  color: var(--color-primary);
}

.section-title {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.common-title {
  margin-top: 28px;
}

.capability-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.capability-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-bg-card);
  transition: border-color 0.18s ease, transform 0.18s ease;
}
.capability-card:hover {
  border-color: var(--color-primary);
}
.capability-icon {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: var(--color-primary-light);
  color: var(--color-primary);
}
.capability-body {
  flex: 1;
  min-width: 0;
}
.capability-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.capability-desc {
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-secondary);
}
.capability-action {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.step-list {
  margin: 0 0 24px;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
  counter-reset: step;
}
.step-list li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text-body);
}
.step-index {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--color-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.step-text {
  padding-top: 1px;
}

.faq-collapse {
  border: none;
  background: transparent;
}
.faq-collapse :deep(.el-collapse-item__header),
.faq-collapse :deep(.el-collapse-item__wrap) {
  background: transparent;
  border-color: var(--color-border);
  color: var(--color-text-primary);
  font-size: 13px;
}
.faq-answer {
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text-secondary);
  padding-bottom: 4px;
}

.tips-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.tip-card {
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-bg-card);
}
.tip-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.tip-title .el-icon {
  color: var(--color-primary);
}
.tip-desc {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--color-text-secondary);
}

@media (max-width: 768px) {
  .help-page {
    padding: 16px 12px;
  }
  .help-topbar {
    margin: -16px -12px 16px;
    padding: 0 12px;
    height: 52px;
  }
  .capability-grid,
  .tips-grid {
    grid-template-columns: 1fr;
  }
  .capability-action {
    display: none;
  }
}
</style>

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

    <!-- ==================== AI 助手使用指南 ==================== -->
    <section class="assistant-guide">
      <div class="assistant-head">
        <div class="assistant-head-left">
          <div class="assistant-logo">
            <el-icon :size="20"><Service /></el-icon>
          </div>
          <div>
            <h3 class="assistant-title">AI 助手怎么用（不只是问答）</h3>
            <p class="assistant-sub">全角色通用 · 登录后任意页面随时唤起</p>
          </div>
        </div>
        <el-tag effect="plain" type="success" size="small">能查 · 能办 · 有确认</el-tag>
      </div>

      <p class="assistant-lead">
        侧边栏的「智能问答」只负责翻资料回答；「AI 助手」则会调用检索、资料、班级、运营等工具：
        帮你找课件视频、查补采与工单进度、看班级学情和平台数据，还能替你把补采需求、工单提交出去。
        知识性问题仍然只基于入库资料回答并标注来源，资料没覆盖时会明确告诉你，不会凭空编造。
      </p>

      <h4 class="sub-title">第一次使用：按这 4 步来</h4>
      <ol class="step-list">
        <li v-for="(step, i) in assistantSteps" :key="step">
          <span class="step-index">{{ i + 1 }}</span>
          <span class="step-text">{{ step }}</span>
        </li>
      </ol>

      <h4 class="sub-title">它比普通问答多做什么</h4>
      <div class="capability-grid">
        <div v-for="cap in assistantAbilities" :key="cap.title" class="capability-card">
          <div class="capability-icon">
            <el-icon :size="18"><component :is="cap.icon" /></el-icon>
          </div>
          <div class="capability-body">
            <div class="capability-title">{{ cap.title }}</div>
            <div class="capability-desc">{{ cap.desc }}</div>
          </div>
        </div>
      </div>

      <h4 class="sub-title">不同身份可以这样问</h4>
      <div class="ask-grid">
        <div v-for="group in assistantAsks" :key="group.role" class="ask-card">
          <div class="ask-role">
            <el-icon :size="16"><component :is="group.icon" /></el-icon>
            <span>{{ group.role }}</span>
          </div>
          <div v-for="q in group.examples" :key="q" class="ask-example">“{{ q }}”</div>
        </div>
      </div>

      <h4 class="sub-title">和「智能问答」的区别</h4>
      <div class="compare-wrap">
        <table class="compare-table">
          <thead>
            <tr>
              <th>对比项</th>
              <th>智能问答</th>
              <th>AI 助手</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in assistantCompare" :key="row.item">
              <td class="compare-item">{{ row.item }}</td>
              <td>{{ row.chat }}</td>
              <td class="compare-strong">{{ row.assistant }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h4 class="sub-title">这些细节很好用</h4>
      <div class="tips-grid">
        <div v-for="tip in assistantTips" :key="tip.title" class="tip-card">
          <div class="tip-title">
            <el-icon :size="16"><component :is="tip.icon" /></el-icon>
            <span>{{ tip.title }}</span>
          </div>
          <div class="tip-desc">{{ tip.desc }}</div>
        </div>
      </div>
    </section>

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
  Microphone, Clock, Rank, VideoPause,
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
    title: 'AI 助手（不只是问答）',
    desc: '任意页面右下角悬浮球或侧边栏「AI 助手」唤起：找课件视频、查补采/工单/通知，教师查班级学情，管理员查运营数据；还能代你提交补采与工单（需确认）。',
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

/** ==================== AI 助手使用指南（全角色通用） ==================== */
const assistantSteps = [
  '登录后，在任意页面点右下角悬浮球（桌面端可拖到顺手的位置），或点侧边栏「AI 助手」打开对话面板。',
  '直接说清「对象 + 目的」，例如“帮我找 FreeRTOS 任务调度的资料”“我班最近都在问什么”，不要只丢一个关键词。',
  '看执行步骤与结果：资料卡片点一下直达文档/视频；知识性回答展开「参考来源」核对原文。',
  '涉及补采或工单时，先在确认卡片里核对内容，点「确认执行」才会真正提交。',
]

const assistantAbilities: Capability[] = [
  {
    icon: ChatDotRound,
    title: '知识问答带来源',
    desc: '基于学院教学资料作答，答案下方可展开「参考来源」核对原文；资料没覆盖时会明确说明，不凭空编造。',
  },
  {
    icon: Search,
    title: '找资料直达',
    desc: '说“帮我找 ESP32 I2C 的课件/视频”，返回可点击的资料卡片，一键跳转文档或视频专区，并自动带上关键词检索。',
  },
  {
    icon: Tickets,
    title: '查个人事项',
    desc: '一句话查我的补采进度、我的工单与老师回复、未读通知，不用自己逐个菜单翻找。',
  },
  {
    icon: Refresh,
    title: '代你提交补采 / 工单',
    desc: '把知识库没覆盖的问题转成补采需求，或把需要人工处理的问题转成工单；先出确认卡片，点「确认执行」才真正提交。',
  },
  {
    icon: Avatar,
    title: '教师学情分析（老师）',
    desc: '查任教班级、班级提问热点、知识库答不上的问题、学生学习画像，还能直接生成班级学情周报。',
  },
  {
    icon: DataAnalysis,
    title: '运营与安全数据（管理员）',
    desc: '查待办概览、待审核文档、补采与工单积压、知识缺口、平台使用统计、账号分布与审计摘要。',
  },
]

const assistantAsks = [
  {
    role: '学生 / 访客',
    icon: Reading,
    examples: [
      'ESP32 烧录失败有哪些常见原因？',
      '帮我找一下 FreeRTOS 任务调度的资料',
      '我提交的补采有进度了吗？',
      '这个问题知识库没有，帮我提交补采：……',
    ],
  },
  {
    role: '老师',
    icon: User,
    examples: [
      '我教哪些班级？',
      '我班最近都在问什么？',
      '我班哪些问题知识库答不上来？',
      '帮我生成本周班级学情周报',
    ],
  },
  {
    role: '管理员',
    icon: Setting,
    examples: [
      '今天有哪些待办需要处理？',
      '有哪些文档待审核？积压多久了？',
      '最近补采需求和工单积压多少？',
      '近期有没有异常操作或敏感词命中？',
    ],
  },
]

const assistantCompare = [
  {
    item: '定位',
    chat: '专门做知识库检索问答',
    assistant: '会调用工具的智能体，既能查资料也能办事',
  },
  {
    item: '入口',
    chat: '侧边栏「智能问答」，整页使用',
    assistant: '任意页面：右下角悬浮球，或侧边栏「AI 助手」',
  },
  {
    item: '典型结果',
    chat: '答案 + 参考来源',
    assistant: '答案 + 来源 + 执行步骤 + 可点击资料卡片（必要时附操作确认卡片）',
  },
  {
    item: '查个人数据',
    chat: '不支持，需要到对应菜单查看',
    assistant: '一句话查补采、工单、通知；老师查班级学情，管理员查运营数据',
  },
  {
    item: '代提交事项',
    chat: '未命中时可在答案下方点「提交补采」',
    assistant: '补采和工单都能代提交，都要在卡片中点「确认执行」',
  },
  {
    item: '语音播报',
    chat: '无',
    assistant: '自动朗读回答，可关闭，也可切换音色',
  },
]

const assistantTips = [
  {
    icon: Rank,
    title: '悬浮球和面板都能拖',
    desc: '拖动悬浮球可换位置；打开面板后按住顶部标题栏拖动，避开正在看的内容。',
  },
  {
    icon: Microphone,
    title: '语音播报可开关、可换音色',
    desc: '回答会自动朗读，点麦克风图标关闭或开启；点旁边下拉箭头选择音色，选完立即试听。',
  },
  {
    icon: Clock,
    title: '历史对话会保留',
    desc: '点时钟图标查看历史会话并继续追问；点「+」开新对话，垃圾桶图标可删除不需要的会话。',
  },
  {
    icon: VideoPause,
    title: '随时打断、回车发送',
    desc: '生成过程中点停止按钮可中断回答；回车发送，Shift + 回车换行。',
  },
  {
    icon: List,
    title: '执行过程看得见',
    desc: '回答上方会列出「检索知识库」「查找资料」「班级提问热点」等实际执行步骤，失败步骤会标红。',
  },
  {
    icon: Search,
    title: '不知道问什么就先点预设问题',
    desc: '欢迎页会按你的身份给出 4 条可点击的示例问题，点「换一批」还能看到更多问法。',
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

/* ==================== AI 助手使用指南 ==================== */
.assistant-guide {
  margin-top: 8px;
  padding: 20px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: linear-gradient(180deg, var(--color-bg-card), var(--color-primary-light));
}
.assistant-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}
.assistant-head-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.assistant-logo {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 8px 18px rgba(79, 70, 229, 0.28);
}
.assistant-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.assistant-sub {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--color-text-placeholder);
}
.assistant-lead {
  margin: 0 0 18px;
  padding: 12px 14px;
  border-left: 3px solid var(--color-primary);
  border-radius: var(--radius-btn);
  background: var(--color-bg-card);
  font-size: 13px;
  line-height: 1.8;
  color: var(--color-text-body);
}
.sub-title {
  margin: 22px 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.assistant-guide .step-list {
  margin-bottom: 0;
}
.ask-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}
.ask-card {
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-bg-card);
}
.ask-role {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.ask-role .el-icon {
  color: var(--color-primary);
}
.ask-example {
  padding: 7px 10px;
  margin-bottom: 8px;
  border-radius: 8px;
  background: var(--color-primary-light);
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--color-text-body);
}
.ask-example:last-child {
  margin-bottom: 0;
}
.compare-wrap {
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
}
.compare-table {
  width: 100%;
  min-width: 620px;
  border-collapse: collapse;
  background: var(--color-bg-card);
  font-size: 13px;
}
.compare-table th,
.compare-table td {
  padding: 10px 14px;
  text-align: left;
  vertical-align: top;
  line-height: 1.65;
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-body);
}
.compare-table thead th {
  background: var(--color-primary-light);
  color: var(--color-text-primary);
  font-weight: 600;
}
.compare-table tbody tr:last-child td {
  border-bottom: none;
}
.compare-item {
  white-space: nowrap;
  font-weight: 500;
  color: var(--color-text-primary) !important;
}
.compare-strong {
  color: var(--color-primary) !important;
}
.assistant-guide .tips-grid {
  margin-top: 0;
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
  .assistant-guide {
    padding: 14px;
  }
  .assistant-head {
    align-items: flex-start;
  }
  .capability-action {
    display: none;
  }
}
</style>

<template>
  <div class="counselor-root">
    <!-- 悬浮入口（可拖动：拖动>5px 视为移动，否则视为点击展开） -->
    <transition name="cp-pop">
      <button
        v-if="!open"
        ref="fabEl"
        class="cp-fab"
        title="AI 助手（可拖动）"
        :style="fabStyle"
        @pointerdown="onFabDown"
        @dragstart.prevent
        @click="onFabClick"
      >
        <span class="cp-fab-core">
          <img class="cp-fab-img" :src="counselorAvatar" alt="AI 助手" draggable="false" />
        </span>
        <span class="cp-fab-tip">AI 助手在线</span>
      </button>
    </transition>

    <!-- 对话面板 -->
    <transition name="cp-rise">
      <section v-if="open" ref="panelEl" class="cp-panel" :style="panelStyle">
        <header class="cp-head" title="按住此处可拖动窗口" @pointerdown="onHeadDown" @dragstart.prevent>
          <div class="cp-avatar">
            <img class="cp-avatar-img" :src="counselorAvatar" alt="AI 助手" draggable="false" />
          </div>
          <div class="cp-title">
            <div class="cp-name">AI 助手</div>
            <div class="cp-sub">智能问答 · 随时为你答疑</div>
          </div>
          <div class="cp-actions">
            <div class="cp-voice-wrap">
              <button class="cp-icon-btn cp-mic-btn" :class="{ muted: !voiceEnabled }" :title="voiceEnabled ? '关闭语音' : '开启语音'" @click="toggleVoice">
                <el-icon class="cp-voice-icon" :class="{ off: !voiceEnabled }"><Microphone /></el-icon>
                <span v-if="!voiceEnabled" class="cp-mic-slash"></span>
              </button>
              <!-- 加载指示器：正在生成回复且尚未开始说话时显示 -->
              <div v-if="streaming && !speaking" class="cp-loading-spinner" title="AI 助手正在思考中…">
                <svg viewBox="0 0 24 24" width="18" height="18">
                  <circle cx="12" cy="12" r="9" fill="none" stroke="rgba(79,70,229,0.25)" stroke-width="3"/>
                  <circle cx="12" cy="12" r="9" fill="none" stroke="#4F46E5" stroke-width="3" stroke-linecap="round"
                    stroke-dasharray="14 42" transform="rotate(0 12 12)">
                    <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="0.8s" repeatCount="indefinite"/>
                  </circle>
                </svg>
              </div>
              <!-- 音色选择下拉 -->
              <button
                v-if="edgeVoices.length"
                class="cp-icon-btn cp-voice-sel"
                title="选择音色"
                @click.stop="voiceMenuOpen = !voiceMenuOpen"
              >
                <el-icon><CaretBottom /></el-icon>
              </button>
              <transition name="cp-fade">
                <div v-if="voiceMenuOpen" class="cp-voice-menu" @click.stop>
                  <div class="cp-voice-menu-title">选择音色</div>
                  <div
                    v-for="v in edgeVoices"
                    :key="v.short_name"
                    class="cp-voice-item"
                    :class="{ active: v.short_name === selectedVoice }"
                    @click="selectVoice(v.short_name)"
                  >
                    <span class="cp-voice-name">{{ v.name }}</span>
                    <span class="cp-voice-lang">{{ v.desc }}</span>
                  </div>
                  <div v-if="!edgeVoices.length" class="cp-voice-empty">暂无可用音色</div>
                </div>
              </transition>
            </div>
            <button class="cp-icon-btn" title="历史对话" @click="toggleHistory">
              <el-icon><Clock /></el-icon>
            </button>
            <button class="cp-icon-btn" title="开始新对话" @click="newChat">
              <el-icon><Plus /></el-icon>
            </button>
            <button class="cp-icon-btn" title="收起" @click="closePanel">
              <el-icon><Close /></el-icon>
            </button>
          </div>
        </header>

        <!-- 历史会话 -->
        <transition name="cp-fade">
          <div v-if="showHistory" class="cp-history">
            <div v-if="!sessions.length" class="cp-history-empty">还没有历史对话哦～</div>
            <div
              v-for="s in sessions"
              :key="s.id"
              class="cp-history-item"
              :class="{ active: s.id === sessionId }"
              @click="loadSession(s.id)"
            >
              <span class="cp-history-title">{{ s.title }}</span>
              <button class="cp-history-del" title="删除" @click.stop="removeSession(s.id)">
                <el-icon><Delete /></el-icon>
              </button>
            </div>
          </div>
        </transition>

        <!-- 消息区 -->
        <div ref="listEl" class="cp-body">
          <div v-if="!messages.length && !streaming" class="cp-welcome">
            <div class="cp-welcome-bot">
              <img class="cp-welcome-bot-img" :src="counselorAvatar" alt="AI 助手" draggable="false" />
            </div>
            <p class="cp-welcome-text">
              你好呀，我是你的 AI 助手～<br />
              嵌入式开发学习中的问题（ESP32 / ESP-IDF / 树莓派 / 电子电路），或是想查找教学资料，都可以问我。
            </p>
            <div class="cp-quick">
              <button v-for="q in quickPrompts" :key="q" class="cp-quick-btn" @click="askQuick(q)">
                {{ q }}
              </button>
            </div>
            <div class="cp-welcome-tools">
              <button class="cp-quick-refresh" title="换一批问题" @click="refreshPrompts">
                <el-icon :class="{ spinning: refreshing }"><Refresh /></el-icon>
                <span>换一批</span>
              </button>
            </div>
          </div>

          <div v-for="m in messages" :key="m.id" class="cp-row" :class="m.role">
            <div class="cp-bubble">
              <span v-if="m.role === 'assistant' && m.mode" class="cp-mode-tag" :class="m.mode">
                {{ m.mode === 'knowledge' ? '知识库依据' : '智能回答' }}
              </span>
              <!-- AI 助手回答是 Markdown（含表格/加粗/分点），需渲染后展示，否则原文符号会直接暴露给用户 -->
              <div class="cp-text" v-html="renderMarkdown(m.content)"></div>
              <!-- 资料卡片：助手检索到的文档/视频，点击直接跳转到对应页面 -->
              <div v-if="m.resources && m.resources.length" class="cp-resources">
                <div class="cp-resources-title">为你找到的资料（点击打开）</div>
                <button
                  v-for="r in m.resources"
                  :key="`${r.type}-${r.id}`"
                  class="cp-resource"
                  @click="openResource(r)"
                >
                  <span class="cp-resource-icon" :class="r.type">
                    {{ r.type === 'video' ? '▶' : '文' }}
                  </span>
                  <span class="cp-resource-body">
                    <span class="cp-resource-title">{{ r.title }}</span>
                    <span v-if="r.subtitle" class="cp-resource-sub">{{ r.subtitle }}</span>
                  </span>
                  <span class="cp-resource-arrow">→</span>
                </button>
              </div>
              <div v-if="m.sources && m.sources.length" class="cp-sources">
                <div class="cp-sources-title">参考来源（点击展开原文）</div>
                <div
                  v-for="(s, i) in m.sources"
                  :key="i"
                  class="cp-source"
                  :class="{ open: isSourceOpen(m.id, i) }"
                >
                  <button class="cp-source-head" @click="toggleSource(m.id, i)">
                    <span class="cp-source-dot"></span>
                    <span class="cp-source-label">{{ s.document_name }}<template v-if="s.chapter"> · {{ s.chapter }}</template></span>
                    <span class="cp-source-arrow">▾</span>
                  </button>
                  <div v-if="isSourceOpen(m.id, i)" class="cp-source-text">
                    {{ s.snippet || '暂无原文片段' }}
                    <a
                      v-if="isHttpUrl(s.source_url)"
                      :href="s.source_url ?? undefined"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="cp-source-link"
                      @click.stop
                    >查看原文 ↗</a>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="streaming" class="cp-row assistant">
            <div class="cp-bubble">
              <div v-if="streamContent && minLoadingDone" class="cp-text" v-html="renderMarkdown(streamContent)"></div>
              <div v-else class="cp-loading">
                <div class="cp-typing"><i></i><i></i><i></i></div>
                <span class="cp-loading-text">AI 助手正在思考中…</span>
              </div>
            </div>
          </div>

          <div v-if="loadingHistory && !streaming" class="cp-row assistant">
            <div class="cp-bubble">
              <div class="cp-loading">
                <div class="cp-typing"><i></i><i></i><i></i></div>
                <span class="cp-loading-text">加载对话中…</span>
              </div>
            </div>
          </div>

          <div v-if="notice" class="cp-notice">你的消息中包含不合适的内容，AI 助手已为你调整措辞。</div>
          <div v-if="errorMsg" class="cp-notice error">{{ errorMsg }}</div>
        </div>

        <!-- 输入区 -->
        <footer class="cp-foot">
          <textarea
            ref="inputEl"
            v-model="input"
            class="cp-input"
            rows="1"
            placeholder="和 AI 助手聊聊你的问题…"
            @input="autoResizeInput"
            @keydown.enter.exact="onEnter"
          />
          <button v-if="streaming" class="cp-send stop" title="停止" @click="stop">
            <el-icon><Close /></el-icon>
          </button>
          <button v-else class="cp-send" :disabled="!input.trim()" title="发送" @click="send">
            <el-icon><Promotion /></el-icon>
          </button>
        </footer>
      </section>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { Close, Plus, Clock, Delete, Promotion, Refresh, Microphone, CaretBottom } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'
import { counselorApi, counselorStream } from '@/api/counselor'
import type { CounselorSource, CounselorSession, CounselorResource } from '@/api/counselor'
import { useRouter } from 'vue-router'

// html: false —— 禁止原始 HTML 透传，避免模型输出带标签时触发 XSS
const md = new MarkdownIt({ breaks: true, linkify: true, html: false })

function renderMarkdown(text: string) {
  return md.render(text || '')
}

// 参考条款展开状态：key 为 `${消息id}:${条款序号}`，仅记录已展开的条目
const expandedSources = ref<Set<string>>(new Set())

function isSourceOpen(messageId: number, index: number) {
  return expandedSources.value.has(`${messageId}:${index}`)
}

function toggleSource(messageId: number, index: number) {
  const key = `${messageId}:${index}`
  if (expandedSources.value.has(key)) expandedSources.value.delete(key)
  else expandedSources.value.add(key)
}

/** source_url 可能是网址，也可能是"某某部门文件（2025年8月）"这类说明文字，只有真网址才渲染成链接 */
function isHttpUrl(url?: string | null) {
  return !!url && /^https?:\/\//i.test(url.trim())
}

// AI 助手形象（静态资源，置于 public 目录，避免为图片导入引入额外类型声明）
const counselorAvatar = '/ai-assistant.jpg?v=2'

interface LocalMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  mode?: string | null
  sources?: CounselorSource[] | null
  resources?: CounselorResource[] | null
}

const open = ref(false)
const input = ref('')
const messages = ref<LocalMessage[]>([])
const streaming = ref(false)
const loadingHistory = ref(false)   // 正在加载会话历史消息
const streamContent = ref('')
const minLoadingDone = ref(false)   // 加载状态最小显示时间已过
const sessionId = ref<string | null>(null)
const sessions = ref<CounselorSession[]>([])
const showHistory = ref(false)
const notice = ref('')
const errorMsg = ref('')
const listEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLTextAreaElement | null>(null)

const router = useRouter()

/** 打开资料卡片：跳转到文档页或视频专区，并收起助手面板 */
function openResource(resource: CounselorResource) {
  if (!resource?.url) return
  open.value = false
  router.push(resource.url)
}

// ==================== 语音播报（Edge TTS - 分段合成降低延迟） ====================
const voiceEnabled = ref(true)                               // 是否开启语音
const speaking = ref(false)                                   // 是否正在播报（用于嘴型同步）
const voiceMenuOpen = ref(false)                              // 音色选择菜单
const selectedVoice = ref(localStorage.getItem('counselor_voice') || 'zh-CN-XiaoxiaoNeural') // 用户选中的 Edge TTS 音色

// 当前播放的音频元素和分段队列
let currentAudio: HTMLAudioElement | null = null
let segmentQueue: string[] = []          // 待播放的文本分段
let segmentIndex = 0                     // 当前播放到第几段
let cancelled = false                    // 是否被取消（stopSpeak）

// Edge TTS 音色列表（从后端获取）
interface EdgeVoice {
  short_name: string
  name: string
  gender: string
  desc: string
}
const edgeVoices = ref<EdgeVoice[]>([])

async function loadEdgeVoices() {
  try {
    const token = localStorage.getItem('access_token')
    const res = await fetch('/api/v1/counselor/tts/voices', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    const json = await res.json()
    if (json.code === 0 && Array.isArray(json.data)) {
      edgeVoices.value = json.data
    }
  } catch (e) {
    // 失败时不影响使用，音色列表为空
  }
}

function selectVoice(shortName: string) {
  selectedVoice.value = shortName
  localStorage.setItem('counselor_voice', shortName)
  voiceMenuOpen.value = false
  // 切换音色后试听一句（无论语音是否开启，都播放试听让用户确认）
  stopSpeak()
  speak('你好呀，我是你的AI 助手，这是我的新声音。')
}

// 按标点把长文本切成短句，每段不超过 80 字，降低单段合成延迟
function splitText(text: string): string[] {
  // 先按句号、问号、感叹号切分，保留标点
  const sentences = text.match(/[^。！？.!?]+[。！？.!?]?/g) || [text]
  const segments: string[] = []
  for (const s of sentences) {
    const trimmed = s.trim()
    if (!trimmed) continue
    // 长句再按逗号切分
    if (trimmed.length > 80) {
      const parts = trimmed.match(/[^，,；;]+[，,；;]?/g) || [trimmed]
      for (const p of parts) {
        const pt = p.trim()
        if (pt) segments.push(pt)
      }
    } else {
      segments.push(trimmed)
    }
  }
  return segments.length ? segments : [text]
}

// 请求单段音频，返回 blob url
async function fetchSegmentAudio(segment: string): Promise<string> {
  const token = localStorage.getItem('access_token')
  const url = `/api/v1/counselor/tts?text=${encodeURIComponent(segment)}&voice=${encodeURIComponent(selectedVoice.value)}`
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`TTS 请求失败: ${res.status}`)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

// 播放分段队列：当前段播放时，后台预取下一段
async function playSegments(segments: string[]) {
  segmentQueue = segments
  segmentIndex = 0
  cancelled = false
  speaking.value = true

  let nextAudioUrl: string | null = null

  for (let i = 0; i < segments.length; i++) {
    if (cancelled) break
    segmentIndex = i

    let audioUrl: string
    if (nextAudioUrl) {
      // 使用上一轮预取的结果
      audioUrl = nextAudioUrl
      nextAudioUrl = null
    } else {
      audioUrl = await fetchSegmentAudio(segments[i])
    }

    // 后台预取下一段（不等待）
    const prefetchPromise = (i + 1 < segments.length)
      ? fetchSegmentAudio(segments[i + 1]).then(url => { nextAudioUrl = url }).catch(() => { nextAudioUrl = null })
      : null

    // 播放当前段
    await new Promise<void>((resolve) => {
      if (cancelled) { resolve(); return }
      const audio = new Audio(audioUrl)
      currentAudio = audio
      audio.onended = () => {
        URL.revokeObjectURL(audioUrl)
        currentAudio = null
        resolve()
      }
      audio.onerror = () => {
        URL.revokeObjectURL(audioUrl)
        currentAudio = null
        resolve()
      }
      audio.play().catch(() => resolve())
    })

    // 等待预取完成（如果有）
    if (prefetchPromise) await prefetchPromise.catch(() => {})
  }

  if (!cancelled) {
    speaking.value = false
  }
  currentAudio = null
}

function stopSpeak() {
  cancelled = true
  segmentQueue = []
  if (currentAudio) {
    currentAudio.pause()
    currentAudio.currentTime = 0
    currentAudio = null
  }
  speaking.value = false
}

async function speak(text: string) {
  stopSpeak()
  if (!voiceEnabled.value || !text) return
  // 去掉 markdown 标记和超长文本，只朗读前 500 字
  const clean = text.replace(/```[\s\S]*?```/g, ' ').replace(/[#*`>\-]/g, ' ').replace(/\s+/g, ' ').trim()
  if (!clean) return
  const toRead = clean.slice(0, 500)

  // 按标点切分成短句，逐段合成播放，降低首音延迟
  const segments = splitText(toRead)
  playSegments(segments)
}

function toggleVoice() {
  voiceEnabled.value = !voiceEnabled.value
  if (!voiceEnabled.value) {
    stopSpeak()
  } else {
    // 开启语音时，朗读最后一条 AI 消息；没有则朗读问候语
    const lastAssistant = [...messages.value].reverse().find(m => m.role === 'assistant')
    if (lastAssistant?.content) {
      speak(lastAssistant.content)
    } else {
      speak('你好呀，我是你的AI 助手，有什么可以帮你的吗？')
    }
  }
}

// 点击页面其他地方关闭音色菜单
function closeVoiceMenu(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.cp-voice-wrap')) voiceMenuOpen.value = false
}

// ==================== 移动端适配 ====================
const MOBILE_MAX_WIDTH = 768
const isMobile = ref(false)
// iOS 键盘弹出时 visualViewport 会收缩，需要把底部面板抬到键盘上方
const keyboardOffset = ref(0)

function updateViewportMode() {
  isMobile.value = window.innerWidth <= MOBILE_MAX_WIDTH
}

function syncKeyboardOffset() {
  const vv = window.visualViewport
  if (!isMobile.value || !vv) {
    keyboardOffset.value = 0
    return
  }
  // 键盘高度 ≈ 布局视口高度 - 可视视口高度 - 可视视口顶部偏移
  keyboardOffset.value = Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop))
}

// ==================== 拖动 ====================
const FAB_SIZE = 58      // 悬浮按钮边长
const PANEL_GAP = 14     // 面板与按钮之间的间距
const EDGE_MARGIN = 8    // 距视口边缘的最小留白
const DRAG_THRESHOLD = 5 // 移动超过该像素数视为拖动，否则视为点击

const fabEl = ref<HTMLElement | null>(null)
const panelEl = ref<HTMLElement | null>(null)

function clamp(value: number, max: number) {
  return Math.min(Math.max(value, EDGE_MARGIN), Math.max(EDGE_MARGIN, max))
}

// 初始位置：与原来的 right/bottom 28px 对齐
const fabPos = ref({
  x: clamp(window.innerWidth - FAB_SIZE - 28, window.innerWidth - FAB_SIZE - EDGE_MARGIN),
  y: clamp(window.innerHeight - FAB_SIZE - 28, window.innerHeight - FAB_SIZE - EDGE_MARGIN),
})
const panelPos = ref({ x: 0, y: 0 })

// 移动端交给 CSS 定位（FAB 固定右下、面板固定底部），避免拖拽坐标与安全区打架
const fabStyle = computed(() => (isMobile.value
  ? {}
  : { left: `${fabPos.value.x}px`, top: `${fabPos.value.y}px` }))

const panelStyle = computed(() => {
  if (!isMobile.value) {
    return { left: `${panelPos.value.x}px`, top: `${panelPos.value.y}px` }
  }
  // 键盘弹出时整体上移并同步压缩高度，保证输入框不被键盘遮挡；
  // 键盘收起时把高度交还给 CSS，便于横竖屏使用不同高度
  const offset = keyboardOffset.value
  return offset > 0
    ? { bottom: `${offset}px`, height: `calc(80dvh - ${offset}px)` }
    : { bottom: '0px' }
})

let movedDistance = 0 // 本次指针交互累计位移，用于区分点击与拖动

function startDrag(e: PointerEvent, target: 'fab' | 'panel') {
  // 移动端 FAB 固定右下、面板为底部抽屉，均不参与拖拽
  if (isMobile.value) {
    movedDistance = 0
    return
  }
  const el = target === 'fab' ? fabEl.value : panelEl.value
  if (!el || e.button !== 0) return

  // 把后续的 pointermove/pointerup 锁定到本次按下的把手元素上，
  // 避免事件在半途改投其他元素而丢失（触屏/某些浏览器会对按下元素做隐式指针捕获）
  const handle = e.currentTarget as HTMLElement | null
  try {
    handle?.setPointerCapture?.(e.pointerId)
  } catch {
    /* 捕获失败不影响 window 兜底监听 */
  }

  const startX = e.clientX
  const startY = e.clientY
  // 直接读取自身内联定位值，与写回时使用同一坐标系，避免 transform 干扰
  const startLeft = parseFloat(getComputedStyle(el).left) || 0
  const startTop = parseFloat(getComputedStyle(el).top) || 0
  const w = el.offsetWidth
  const h = el.offsetHeight

  movedDistance = 0
  document.body.classList.add('cp-dragging')

  const onMove = (ev: PointerEvent) => {
    if (ev.pointerId !== e.pointerId) return
    const dx = ev.clientX - startX
    const dy = ev.clientY - startY
    movedDistance = Math.max(movedDistance, Math.hypot(dx, dy))
    // 拖动过程中直接写 DOM 样式，不经过 Vue 的渲染调度，保证逐帧跟手
    el.style.left = `${clamp(startLeft + dx, window.innerWidth - w - EDGE_MARGIN)}px`
    el.style.top = `${clamp(startTop + dy, window.innerHeight - h - EDGE_MARGIN)}px`
  }

  const onUp = (ev: PointerEvent) => {
    if (ev.pointerId !== e.pointerId) return
    document.body.classList.remove('cp-dragging')
    // 把最终位置同步回响应式状态，供展开/收起/窗口缩放复用
    const finalPos = {
      x: parseFloat(el.style.left) || startLeft,
      y: parseFloat(el.style.top) || startTop,
    }
    if (target === 'fab') fabPos.value = finalPos
    else panelPos.value = finalPos

    try {
      if (handle?.hasPointerCapture?.(e.pointerId)) handle.releasePointerCapture(e.pointerId)
    } catch {
      /* 忽略 */
    }
    window.removeEventListener('pointermove', onMove, true)
    window.removeEventListener('pointerup', onUp, true)
    window.removeEventListener('pointercancel', onUp, true)
  }

  // 捕获模式监听：即使事件被重定向到把手元素，也能稳定收到
  window.addEventListener('pointermove', onMove, true)
  window.addEventListener('pointerup', onUp, true)
  window.addEventListener('pointercancel', onUp, true)
}

function onFabDown(e: PointerEvent) {
  startDrag(e, 'fab')
}

function onFabClick() {
  // 刚才是拖动而非点击，不展开面板
  if (movedDistance > DRAG_THRESHOLD) {
    movedDistance = 0
    return
  }
  openPanel()
}

function onHeadDown(e: PointerEvent) {
  // 头部右侧的操作按钮不触发拖动
  if ((e.target as HTMLElement).closest('.cp-icon-btn')) return
  startDrag(e, 'panel')
}

function onWindowResize() {
  updateViewportMode()
  syncKeyboardOffset()
  if (isMobile.value) return
  fabPos.value = {
    x: clamp(fabPos.value.x, window.innerWidth - FAB_SIZE - EDGE_MARGIN),
    y: clamp(fabPos.value.y, window.innerHeight - FAB_SIZE - EDGE_MARGIN),
  }
  if (open.value && panelEl.value) {
    // 等 CSS 断点切换完成后再读取尺寸，避免沿用移动端底部抽屉的宽高
    requestAnimationFrame(() => {
      if (!panelEl.value || isMobile.value) return
      const w = panelEl.value.offsetWidth
      const h = panelEl.value.offsetHeight
      // panelPos 为 0 表示此前处于移动端抽屉模式、尚未初始化桌面坐标，按 FAB 重新吸附
      const baseX = panelPos.value.x || fabPos.value.x + FAB_SIZE - w
      const baseY = panelPos.value.y || fabPos.value.y - PANEL_GAP - h
      panelPos.value = {
        x: clamp(baseX, window.innerWidth - w - EDGE_MARGIN),
        y: clamp(baseY, window.innerHeight - h - EDGE_MARGIN),
      }
    })
  }
}

onMounted(() => {
  updateViewportMode()
  syncKeyboardOffset()
  window.addEventListener('resize', onWindowResize)
  window.addEventListener('orientationchange', onWindowResize)
  // visualViewport 变化用于感知移动端软键盘弹出/收起
  window.visualViewport?.addEventListener('resize', syncKeyboardOffset)
  window.visualViewport?.addEventListener('scroll', syncKeyboardOffset)
  document.addEventListener('click', closeVoiceMenu)
  autoResizeInput()
})
onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize)
  window.removeEventListener('orientationchange', onWindowResize)
  window.visualViewport?.removeEventListener('resize', syncKeyboardOffset)
  window.visualViewport?.removeEventListener('scroll', syncKeyboardOffset)
  document.removeEventListener('click', closeVoiceMenu)
  document.body.classList.remove('cp-dragging')
  stopSpeak()
})

let controller: AbortController | null = null
let seq = 0

/** 预设问题池：每次随机抽 4 条展示，点"换一批"重新抽取，避免只看到固定几条 */
const QUICK_POOL = [
  'ESP32 如何配置 GPIO 中断？',
  'ESP-IDF 工程编译报错怎么排查？',
  'ESP32 烧录失败有哪些常见原因？',
  '树莓派如何连接 I2C 传感器？',
  'FreeRTOS 任务优先级怎么设置？',
  'ESP32 的 UART 有几个，如何配置？',
  'MQTT 连接阿里云物联网平台怎么做？',
  '电子电路里上拉电阻的作用是什么？',
  'ESP32 低功耗模式怎么使用？',
  'APA102 灯带的 SPI 时序是怎样的？',
]

const QUICK_COUNT = 4

/** Fisher-Yates 洗牌后取前 N 条，保证每次分布均匀且不重复 */
function pickPrompts(): string[] {
  const pool = [...QUICK_POOL]
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[pool[i], pool[j]] = [pool[j], pool[i]]
  }
  return pool.slice(0, QUICK_COUNT)
}

const quickPrompts = ref<string[]>(pickPrompts())
const refreshing = ref(false)

/** 换一批：重新抽取；若与原集合完全重合则再抽一次，避免点了没变化 */
function refreshPrompts() {
  const before = quickPrompts.value.join('|')
  let next = pickPrompts()
  if (next.join('|') === before) next = pickPrompts()
  quickPrompts.value = next

  refreshing.value = true
  setTimeout(() => (refreshing.value = false), 400)
}

function scrollToBottom() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

// 输入框随内容自动增高（上限 96px），避免多行输入时过早出现内部滚动条
function autoResizeInput() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  // scrollHeight 不含边框，而元素是 border-box、且有 1px 边框，
  // 直接用 scrollHeight 作高度会差 2px 触发滚动条，这里补回上下边框宽度
  const fullHeight = el.scrollHeight + (el.offsetHeight - el.clientHeight)
  const overflow = fullHeight > 96
  el.style.height = `${overflow ? 96 : fullHeight}px`
  // 内容未超出上限时强制隐藏滚动条，规避亚像素舍入导致的残留滚动条
  el.style.overflowY = overflow ? 'auto' : 'hidden'
}

async function openPanel() {
  open.value = true
  await nextTick()
  // 桌面端面板吸附在按钮左上方（右边缘对齐）；移动端由 CSS 固定在底部，无需计算坐标
  if (!isMobile.value) {
    const w = panelEl.value?.offsetWidth || 390
    const h = panelEl.value?.offsetHeight || 580
    panelPos.value = {
      x: clamp(fabPos.value.x + FAB_SIZE - w, window.innerWidth - w - EDGE_MARGIN),
      y: clamp(fabPos.value.y - PANEL_GAP - h, window.innerHeight - h - EDGE_MARGIN),
    }
  }
  loadSessions()
  loadEdgeVoices()
  scrollToBottom()
  autoResizeInput()
}

function closePanel() {
  // 收起后按钮直接回到展开前的原始位置：面板打开期间按钮被隐藏、位置不会被改写，
  // 因此无需用面板位置反向推导，避免"拖到上方→展开（面板被 clamp 到顶部）→收起后按钮掉到下方"的位置漂移
  open.value = false
  showHistory.value = false
  stopSpeak()
}

function toggleHistory() {
  showHistory.value = !showHistory.value
}

async function loadSessions() {
  try {
    const res = await counselorApi.listSessions()
    sessions.value = res.data?.data || res.data || []
  } catch {
    /* 忽略 */
  }
}

async function loadSession(id: string) {
  if (streaming.value) stop()
  sessionId.value = id
  showHistory.value = false
  loadingHistory.value = true
  try {
    const res = await counselorApi.getMessages(id)
    const items = res.data?.data?.items || []
    messages.value = items.map((m: any) => ({
      id: ++seq,
      role: m.role,
      content: m.content,
      mode: m.mode,
      sources: m.sources || null,
    }))
    scrollToBottom()
  } catch {
    messages.value = []
  } finally {
    loadingHistory.value = false
  }
}

async function removeSession(id: string) {
  try {
    await counselorApi.deleteSession(id)
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (sessionId.value === id) newChat()
  } catch {
    /* 忽略 */
  }
}

function newChat() {
  if (streaming.value) stop()
  sessionId.value = null
  messages.value = []
  streamContent.value = ''
  notice.value = ''
  errorMsg.value = ''
  showHistory.value = false
}

function askQuick(q: string) {
  input.value = q
  send()
}

/** 回车发送；移动端中文输入法组词过程中的回车不触发发送 */
function onEnter(e: KeyboardEvent) {
  if (e.isComposing) return
  e.preventDefault()
  send()
}

function send() {
  const question = input.value.trim()
  if (!question || streaming.value) return

  input.value = ''
  // 清空输入框后把高度复位，避免残留之前的增高
  nextTick(autoResizeInput)
  notice.value = ''
  errorMsg.value = ''
  stopSpeak()
  messages.value.push({ id: ++seq, role: 'user', content: question })

  streaming.value = true
  streamContent.value = ''
  minLoadingDone.value = false
  // 加载状态至少显示 500ms，避免 AI 回复太快看不到
  setTimeout(() => { minLoadingDone.value = true }, 500)
  scrollToBottom()

  let pendingSources: CounselorSource[] = []

  controller = counselorStream(question, sessionId.value, {
    onToken: (t) => {
      streamContent.value += t
      scrollToBottom()
    },
    onSources: (s) => {
      pendingSources = s || []
    },
    onSensitive: (masked) => {
      streamContent.value = masked
      notice.value = 'sensitive'
    },
    onDone: (result) => {
      if (result.session_id) sessionId.value = result.session_id
      const answer = result.full_answer || streamContent.value
      messages.value.push({
        id: ++seq,
        role: 'assistant',
        content: answer,
        mode: result.mode,
        sources: result.sources?.length ? result.sources : pendingSources,
        resources: result.resources?.length ? result.resources : null,
      })
      streamContent.value = ''
      streaming.value = false
      loadSessions()
      scrollToBottom()
      // 朗读回复内容
      speak(answer)
    },
    onError: (err) => {
      streaming.value = false
      streamContent.value = ''
      errorMsg.value = `AI 助手暂时没能回应：${err}`
      scrollToBottom()
    },
  })
}

function stop() {
  controller?.abort()
  stopSpeak()
  if (streamContent.value) {
    messages.value.push({
      id: ++seq,
      role: 'assistant',
      content: streamContent.value + ' [已停止]',
      mode: null,
      sources: null,
    })
  }
  streamContent.value = ''
  streaming.value = false
}

// 供侧边栏「AI 助手」导航项唤起面板
defineExpose({ openPanel })
</script>

<style scoped>
/* ================= 悬浮入口 ================= */
.cp-fab {
  position: fixed;
  width: 58px;
  height: 58px;
  border: none;
  border-radius: 50%;
  padding: 0;
  cursor: grab;
  background: transparent;
  touch-action: none;
  z-index: 2000;
}

.cp-fab-core {
  position: relative;
  z-index: 2;
  width: 58px;
  height: 58px;
  box-sizing: border-box;
  padding: 0;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, rgba(0, 0, 0, 0.08));
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.18);
  transition: transform 0.22s ease, box-shadow 0.22s ease;
}

/* AI 助手头像：保留原图白底，避免抠图边缘发脏 */
.cp-fab-img {
  width: 100%;
  height: 100%;
  display: block;
  border-radius: 50%;
  object-fit: cover;
  /* 关键：禁用图片默认的原生拖拽，否则按住头像会触发 HTML5 dragstart，
     拖动期间 pointermove 被浏览器吞掉，导致图标只在松手后才跳位 */
  -webkit-user-drag: none;
  user-select: none;
  pointer-events: none;
}
.cp-fab:hover .cp-fab-core {
  transform: translateY(-2px) scale(1.04);
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.24);
}

/* 悬停提示 */
.cp-fab-tip {
  position: absolute;
  right: 70px;
  top: 50%;
  transform: translateY(-50%) translateX(6px);
  white-space: nowrap;
  padding: 7px 12px;
  border-radius: 10px;
  font-size: 13px;
  color: #fff;
  background: rgba(30, 30, 46, 0.9);
  opacity: 0;
  pointer-events: none;
  transition: all 0.2s ease;
}
.cp-fab:hover .cp-fab-tip {
  opacity: 1;
  transform: translateY(-50%) translateX(0);
}

/* ================= 对话面板 ================= */
.cp-panel {
  position: fixed;
  width: 390px;
  height: 580px;
  max-height: calc(100vh - 140px);
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  overflow: hidden;
  z-index: 2001;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, rgba(0, 0, 0, 0.08));
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.16);
  backdrop-filter: blur(14px);
}

/* 头部（同时是拖动把手）：与项目卡片一致，浅色底 + 细边框 */
.cp-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 14px 14px 16px;
  background: var(--color-bg-card, #fff);
  border-bottom: 1px solid var(--color-border, rgba(0, 0, 0, 0.08));
  color: var(--color-text-primary, #0f172a);
  flex-shrink: 0;
  cursor: grab;
  touch-action: none;
  user-select: none;
}
:global(body.cp-dragging) { user-select: none; }
:global(body.cp-dragging .cp-head),
:global(body.cp-dragging .cp-fab) { cursor: grabbing; }
/* 拖动期间禁用过渡，避免 left/top 变化被动画拖慢而显得不跟手 */
:global(body.cp-dragging .cp-fab),
:global(body.cp-dragging .cp-panel) { transition: none !important; }
.cp-avatar {
  width: 46px;
  height: 46px;
  box-sizing: border-box;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 0;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, rgba(0, 0, 0, 0.08));
  flex-shrink: 0;
}

.cp-avatar-img {
  width: 100%;
  height: 100%;
  display: block;
  border-radius: 50%;
  object-fit: cover;
  /* 禁用原生图片拖拽，保证面板头部拖动手感 */
  -webkit-user-drag: none;
  user-select: none;
}
.cp-title { flex: 1; min-width: 0; }
.cp-name { font-size: 15px; font-weight: 600; line-height: 1.3; color: var(--color-text-primary, #0f172a); }
.cp-sub { font-size: 11.5px; color: var(--color-text-secondary, #64748b); margin-top: 3px; }

.cp-actions { display: flex; gap: 2px; }
.cp-icon-btn {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--color-text-secondary, #64748b);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease, color 0.15s ease;
}
.cp-icon-btn:hover {
  background: var(--color-bg-hover, #f1f5f9);
  color: var(--color-primary, #4f46e5);
}
.cp-voice-icon.off { opacity: 0.5; }
/* 闭麦状态：麦克风按钮变灰 + 红色禁止斜杠 */
.cp-mic-btn.muted { background: var(--color-bg-hover, #f1f5f9); }
.cp-mic-btn { position: relative; }
.cp-mic-slash {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 26px;
  height: 2.5px;
  background: #ff4d4f;
  border-radius: 2px;
  transform: translate(-50%, -50%) rotate(-45deg);
  pointer-events: none;
  box-shadow: 0 0 2px rgba(0,0,0,0.3);
}

/* 音色选择 */
.cp-voice-wrap { position: relative; display: flex; align-items: center; gap: 2px; }
.cp-loading-spinner {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
}
.cp-voice-sel { font-size: 12px; }
.cp-voice-menu {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 6px;
  min-width: 200px;
  max-height: 260px;
  overflow-y: auto;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, rgba(0, 0, 0, 0.08));
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
  padding: 6px;
  z-index: 1000;
}
.cp-voice-menu-title {
  font-size: 12px;
  color: var(--color-text-secondary, #64748b);
  padding: 6px 10px 4px;
}
.cp-voice-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.cp-voice-item:hover { background: var(--color-bg-hover, #f1f5f9); }
.cp-voice-item.active {
  background: var(--color-primary-light, #e0e7ff);
}
.cp-voice-item.active .cp-voice-name {
  color: var(--color-primary, #4f46e5);
  font-weight: 600;
}
.cp-voice-name {
  font-size: 13px;
  color: var(--color-text-body, #334155);
}
.cp-voice-lang {
  font-size: 11px;
  color: var(--color-text-secondary, #64748b);
}
.cp-voice-empty {
  padding: 12px 10px;
  font-size: 13px;
  color: var(--color-text-secondary, #64748b);
  text-align: center;
}

/* 历史 */
.cp-history {
  max-height: 180px;
  overflow-y: auto;
  padding: 8px;
  border-bottom: 1px solid var(--color-border, rgba(0, 0, 0, 0.08));
  background: var(--color-bg-card, #fff);
  flex-shrink: 0;
}
.cp-history-empty {
  padding: 12px;
  font-size: 12.5px;
  color: var(--color-text-secondary, #8b90a6);
  text-align: center;
}
.cp-history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 9px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.cp-history-item:hover { background: var(--color-bg-hover, #f1f5f9); }
.cp-history-item.active {
  background: var(--color-primary-light, #e0e7ff);
}
.cp-history-item.active .cp-history-title { color: var(--color-primary, #4f46e5); }
.cp-history-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--color-text-body, #3b3f52);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cp-history-del {
  border: none;
  background: transparent;
  color: var(--color-text-secondary, #97a0b5);
  cursor: pointer;
  padding: 2px;
  border-radius: 6px;
  opacity: 0;
  transition: opacity 0.15s ease, color 0.15s ease;
}
.cp-history-item:hover .cp-history-del { opacity: 1; }
.cp-history-del:hover { color: var(--color-danger, #f56c6c); }

/* 消息区 */
.cp-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--color-bg-page, #f6f7fb);
}
.cp-body::-webkit-scrollbar { width: 6px; }
.cp-body::-webkit-scrollbar-thumb {
  background: var(--color-border, rgba(0, 0, 0, 0.14));
  border-radius: 3px;
}

/* 欢迎态 */
.cp-welcome {
  margin: auto 0;
  text-align: center;
  padding: 6px 4px;
}
/* 欢迎态：与 ChatPage 首页的机器人展示保持一致 */
.cp-welcome-bot {
  width: 56px;
  height: 56px;
  margin: 0 auto;
  border-radius: 50%;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  box-sizing: border-box;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, rgba(0, 0, 0, 0.08));
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.14);
}
.cp-welcome-bot-img {
  width: 100%;
  height: 100%;
  display: block;
  border-radius: 50%;
  object-fit: cover;
  -webkit-user-drag: none;
  user-select: none;
}
.cp-welcome-text {
  margin: 12px 0 16px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--color-text-secondary, #64748b);
}
.cp-quick {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}
.cp-quick-btn {
  border: 1px solid var(--color-border, rgba(79, 70, 229, 0.2));
  background: var(--color-bg-card, #fff);
  color: var(--color-text-body, #334155);
  font-size: 12.5px;
  padding: 7px 12px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.18s ease;
}
.cp-quick-btn:hover {
  color: var(--color-primary, #4f46e5);
  background: var(--color-primary-light, rgba(79, 70, 229, 0.1));
  border-color: var(--color-primary, #4f46e5);
  transform: translateY(-1px);
}
/* 换一批：弱化的文字按钮，不与问题胶囊抢视觉焦点 */
.cp-quick-refresh {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 10px;
  padding: 4px 10px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--color-text-secondary, #8a90a8);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.18s ease;
}
.cp-quick-refresh:hover {
  color: var(--color-primary, #4f46e5);
  background: var(--color-primary-light, rgba(79, 70, 229, 0.08));
}
.cp-quick-refresh .el-icon {
  font-size: 13px;
  transition: transform 0.4s ease;
}
.cp-quick-refresh .el-icon.spinning {
  transform: rotate(360deg);
}

/* 首屏工具行：换一批 */
.cp-welcome-tools {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 4px;
}
.cp-welcome-tools .cp-quick-refresh {
  margin-top: 10px;
}

/* 气泡 */
.cp-row { display: flex; }
.cp-row.user { justify-content: flex-end; }
.cp-row.assistant { justify-content: flex-start; }

.cp-bubble {
  max-width: 84%;
  padding: 12px 14px;
  border-radius: 16px;
  font-size: 13.5px;
  line-height: 1.75;
  word-break: break-word;
  white-space: pre-wrap;
}
.cp-row.user .cp-bubble {
  background: linear-gradient(135deg, var(--color-primary, #4f46e5), var(--color-primary-hover, #4338ca));
  color: #fff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.2);
}
.cp-row.assistant .cp-bubble {
  background: var(--color-bg-card, #fff);
  color: var(--color-text-body, #334155);
  border: 1px solid var(--color-border, rgba(0, 0, 0, 0.07));
  border-bottom-left-radius: 4px;
}
.cp-text { white-space: normal; }

/* 资料卡片：与项目浅色卡片风格一致 */
.cp-resources { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.cp-resources-title {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 2px;
}
.cp-resource {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  text-align: left;
  cursor: pointer;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-page);
  color: var(--color-text-primary);
  transition: border-color 0.16s, background 0.16s;
}
.cp-resource:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
}
.cp-resource-icon {
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-size: 11px;
  color: #fff;
  background: var(--color-primary);
}
.cp-resource-icon.video { background: var(--color-warning); }
.cp-resource-body { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.cp-resource-title {
  font-size: 13px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cp-resource-sub {
  font-size: 11px;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cp-resource-arrow { flex: 0 0 auto; color: var(--color-primary); font-size: 13px; }
/* Markdown 渲染后的排版（v-html 内容需 :deep 才能命中 scoped 样式） */
.cp-text :deep(p) { margin: 0 0 8px; }
.cp-text :deep(p:last-child) { margin-bottom: 0; }
.cp-text :deep(ul),
.cp-text :deep(ol) { margin: 4px 0 8px; padding-left: 18px; }
.cp-text :deep(li) { margin: 2px 0; }
.cp-text :deep(strong) { font-weight: 600; }
.cp-text :deep(h1),
.cp-text :deep(h2),
.cp-text :deep(h3),
.cp-text :deep(h4) {
  margin: 10px 0 6px;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
}
.cp-text :deep(h1:first-child),
.cp-text :deep(h2:first-child),
.cp-text :deep(h3:first-child) { margin-top: 0; }
/* 表格：窄气泡里容易撑破，改为可横向滚动的块级容器 */
.cp-text :deep(table) {
  display: block;
  width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 12.5px;
}
.cp-text :deep(th),
.cp-text :deep(td) {
  border: 1px solid var(--color-border, rgba(0, 0, 0, 0.1));
  padding: 4px 8px;
  text-align: left;
  white-space: nowrap;
}
.cp-text :deep(th) {
  background: var(--color-bg-hover, rgba(79, 70, 229, 0.06));
  font-weight: 600;
}
.cp-text :deep(code) {
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--color-bg-hover, rgba(79, 70, 229, 0.08));
  font-size: 12px;
}
.cp-text :deep(blockquote) {
  margin: 8px 0;
  padding: 2px 0 2px 10px;
  border-left: 3px solid var(--color-border, rgba(79, 70, 229, 0.25));
  color: var(--color-text-secondary, #6b7290);
}
.cp-text :deep(a) { color: var(--color-primary, #4f46e5); }
.cp-text :deep(hr) {
  margin: 10px 0;
  border: none;
  border-top: 1px dashed var(--color-border, rgba(0, 0, 0, 0.12));
}

.cp-mode-tag {
  display: inline-block;
  font-size: 11px;
  line-height: 1;
  padding: 3px 7px;
  border-radius: 999px;
  margin-bottom: 7px;
}
.cp-mode-tag.knowledge {
  color: var(--color-success, #10b981);
  background: rgba(16, 185, 129, 0.12);
}
.cp-mode-tag.persona {
  color: var(--color-primary, #4f46e5);
  background: var(--color-primary-light, #e0e7ff);
}

/* 来源 */
.cp-sources {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed var(--color-border, rgba(0, 0, 0, 0.1));
}
.cp-sources-title {
  font-size: 11.5px;
  color: var(--color-text-secondary, #8b90a6);
  margin-bottom: 5px;
}
.cp-source {
  display: block;
  font-size: 12px;
  color: var(--color-text-secondary, #6b7290);
  line-height: 1.9;
}
/* 条款标题行做成按钮：整行可点，展开原文 */
.cp-source-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 0;
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.cp-source-head:hover { color: var(--color-primary, #4f46e5); }
.cp-source-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cp-source-arrow {
  flex-shrink: 0;
  font-size: 10px;
  opacity: 0.55;
  transition: transform 0.18s ease;
}
.cp-source.open .cp-source-arrow { transform: rotate(180deg); }
.cp-source-text {
  margin: 2px 0 8px 11px;
  padding: 7px 9px;
  border-radius: 8px;
  background: var(--color-bg-hover, rgba(79, 70, 229, 0.05));
  color: var(--color-text-body, #3b3f52);
  font-size: 12px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}
.cp-source-link {
  display: inline-block;
  margin-left: 4px;
  color: var(--color-primary, #4f46e5);
  text-decoration: none;
}
.cp-source-link:hover { text-decoration: underline; }
.cp-source-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--color-primary, #4f46e5);
  flex-shrink: 0;
}

/* 打字指示 */
.cp-typing { display: flex; gap: 4px; align-items: center; height: 18px; }
.cp-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
}
.cp-loading-text {
  font-size: 13px;
  color: var(--color-text-secondary, #64748b);
}
.cp-typing i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-primary, #4f46e5);
  opacity: 0.5;
  animation: cp-typing 1.1s infinite ease-in-out;
}
.cp-typing i:nth-child(2) { animation-delay: 0.18s; }
.cp-typing i:nth-child(3) { animation-delay: 0.36s; }
@keyframes cp-typing {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.35; }
  40% { transform: translateY(-4px); opacity: 1; }
}

/* 提示条 */
.cp-notice {
  align-self: center;
  font-size: 12px;
  padding: 6px 12px;
  border-radius: 8px;
  color: #b45309;
  background: rgba(245, 158, 11, 0.13);
}
.cp-notice.error { color: var(--color-danger, #f56c6c); background: rgba(245, 108, 108, 0.12); }

/* 输入区 */
.cp-foot {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 10px 12px 12px;
  border-top: 1px solid var(--color-border, rgba(0, 0, 0, 0.08));
  background: var(--color-bg-card, #fff);
  flex-shrink: 0;
}
.cp-input {
  flex: 1;
  resize: none;
  min-height: 40px;
  max-height: 96px;
  overflow-y: hidden;
  /* 隐藏滚动条外观，仅保留溢出的滚动能力，避免出现多余上下移动的条 */
  scrollbar-width: none;
  padding: 10px 12px;
  font-size: 13.5px;
  font-family: inherit;
  line-height: 1.5;
  border-radius: 12px;
  border: 1px solid var(--color-border, rgba(0, 0, 0, 0.12));
  background: var(--color-bg-page, #f6f7fb);
  color: var(--color-text-body, #3b3f52);
  outline: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
.cp-input::-webkit-scrollbar { display: none; }
.cp-input::-webkit-scrollbar-thumb { display: none; }
.cp-input:focus {
  border-color: var(--color-primary, #4f46e5);
  box-shadow: 0 0 0 2px var(--color-primary-light, #e0e7ff);
}
.cp-send {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: var(--color-primary, #4f46e5);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.24);
  transition: transform 0.15s ease, background 0.15s ease, opacity 0.15s ease;
}
.cp-send:hover:not(:disabled) {
  background: var(--color-primary-hover, #4338ca);
  transform: translateY(-1px);
}
.cp-send:disabled { opacity: 0.45; cursor: not-allowed; box-shadow: none; }
.cp-send.stop { background: var(--color-danger, #ef4444); box-shadow: none; }
.cp-send.stop:hover { background: var(--color-danger, #ef4444); }

/* ================= 动效 ================= */
.cp-pop-enter-active, .cp-pop-leave-active { transition: all 0.2s ease; }
.cp-pop-enter-from, .cp-pop-leave-to { opacity: 0; transform: scale(0.85); }

.cp-rise-enter-active { transition: all 0.26s cubic-bezier(0.22, 1, 0.36, 1); }
.cp-rise-leave-active { transition: all 0.18s ease; }
.cp-rise-enter-from, .cp-rise-leave-to { opacity: 0; transform: translateY(16px) scale(0.97); }

.cp-fade-enter-active, .cp-fade-leave-active { transition: opacity 0.18s ease; }
.cp-fade-enter-from, .cp-fade-leave-to { opacity: 0; }

/* ================= 移动端：底部抽屉 ================= */
@media (max-width: 768px) {
  /* 入口固定右下，抬到聊天输入区上方，避开 iOS 底部安全区；移动端不可拖动 */
  .cp-fab {
    left: auto;
    top: auto;
    right: 12px;
    bottom: calc(104px + env(safe-area-inset-bottom, 0px));
    width: 52px;
    height: 52px;
  }
  .cp-fab-core { width: 52px; height: 52px; }
  .cp-fab-tip { display: none; }

  /* 面板改为贴底抽屉，定位由 CSS 接管 */
  .cp-panel {
    left: 0;
    top: auto;
    bottom: 0;
    width: 100%;
    height: 82vh;
    height: 82dvh;
    max-height: 82dvh;
    border-radius: 16px 16px 0 0;
    border-left: none;
    border-right: none;
    border-bottom: none;
    box-shadow: 0 -8px 30px rgba(15, 23, 42, 0.18);
    /* 移动端 GPU 上毛玻璃开销大，改用纯色背景 */
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }

  .cp-head {
    padding: 12px 8px 12px 14px;
    cursor: default;
    touch-action: auto;
  }
  .cp-avatar { width: 40px; height: 40px; padding: 2px; }
  .cp-sub { display: none; }
  .cp-actions { gap: 0; }
  .cp-icon-btn { width: 34px; height: 34px; }
  /* 音色菜单锚定右侧，避免在窄屏上向右溢出 */
  .cp-voice-menu { left: auto; right: 0; }

  .cp-history { max-height: 35vh; }
  /* 触屏没有 hover，删除按钮必须常显 */
  .cp-history-del { opacity: 1; }

  .cp-body {
    padding: 12px 10px;
    gap: 10px;
    overscroll-behavior: contain;
  }
  .cp-welcome-text { font-size: 14px; }
  .cp-bubble { max-width: 90%; font-size: 14px; }

  .cp-foot {
    gap: 6px;
    padding: 8px 10px calc(8px + env(safe-area-inset-bottom, 0px));
  }
  /* iOS 输入框字号小于 16px 会自动放大整个页面 */
  .cp-input {
    font-size: 16px;
    min-height: 44px;
  }
}

/* 手机横屏：高度优先，铺满整个可视区 */
@media (max-width: 768px) and (orientation: landscape) {
  .cp-panel {
    height: 100vh;
    height: 100dvh;
    max-height: 100dvh;
    border-radius: 0;
  }
}
</style>

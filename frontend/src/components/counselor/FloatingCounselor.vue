<template>
  <div class="counselor-root">
    <!-- 悬浮入口（可拖动：拖动>5px 视为移动，否则视为点击展开） -->
    <transition name="cp-pop">
      <button
        v-if="!open"
        ref="fabEl"
        class="cp-fab"
        title="AI 导员（可拖动）"
        :style="fabStyle"
        @pointerdown="onFabDown"
        @dragstart.prevent
        @click="onFabClick"
      >
        <span class="cp-fab-ring"></span>
        <span class="cp-fab-core">
          <img class="cp-fab-img" :src="counselorAvatar" alt="AI 导员" draggable="false" />
        </span>
        <span class="cp-fab-tip">AI 导员在线</span>
      </button>
    </transition>

    <!-- 对话面板 -->
    <transition name="cp-rise">
      <section v-if="open" ref="panelEl" class="cp-panel" :style="panelStyle">
        <header class="cp-head" title="按住此处可拖动窗口" @pointerdown="onHeadDown" @dragstart.prevent>
          <div class="cp-avatar">
            <img class="cp-avatar-img" :src="counselorAvatar" alt="AI 导员" draggable="false" />
          </div>
          <div class="cp-title">
            <div class="cp-name">AI 导员</div>
            <div class="cp-sub">温柔耐心 · 随时陪你聊聊</div>
          </div>
          <div class="cp-actions">
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
            <div class="cp-welcome-emoji">🌿</div>
            <p class="cp-welcome-text">
              你好呀，我是你的导员～<br />
              学习上的困惑、生活里的烦恼，或是想了解学校的相关规定，都可以慢慢跟我说。
            </p>
            <div class="cp-quick">
              <button v-for="q in quickPrompts" :key="q" class="cp-quick-btn" @click="askQuick(q)">
                {{ q }}
              </button>
            </div>
          </div>

          <div v-for="m in messages" :key="m.id" class="cp-row" :class="m.role">
            <div class="cp-bubble">
              <span v-if="m.role === 'assistant' && m.mode" class="cp-mode-tag" :class="m.mode">
                {{ m.mode === 'knowledge' ? '依据校规' : '陪伴模式' }}
              </span>
              <div class="cp-text">{{ m.content }}</div>
              <div v-if="m.sources && m.sources.length" class="cp-sources">
                <div class="cp-sources-title">参考条款</div>
                <div v-for="(s, i) in m.sources" :key="i" class="cp-source">
                  <span class="cp-source-dot"></span>
                  <span>《{{ s.source_title }}》{{ s.article_no }}</span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="streaming" class="cp-row assistant">
            <div class="cp-bubble">
              <div v-if="streamContent" class="cp-text">{{ streamContent }}</div>
              <div v-else class="cp-typing"><i></i><i></i><i></i></div>
            </div>
          </div>

          <div v-if="notice" class="cp-notice">你的消息中包含不合适的内容，导员已为你调整措辞。</div>
          <div v-if="errorMsg" class="cp-notice error">{{ errorMsg }}</div>
        </div>

        <!-- 输入区 -->
        <footer class="cp-foot">
          <textarea
            ref="inputEl"
            v-model="input"
            class="cp-input"
            rows="1"
            placeholder="和导员说说你的心事或疑问…"
            @input="autoResizeInput"
            @keydown.enter.exact.prevent="send"
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
import { Close, Plus, Clock, Delete, Promotion } from '@element-plus/icons-vue'
import { counselorApi, counselorStream } from '@/api/counselor'
import type { CounselorSource, CounselorSession } from '@/api/counselor'

// 导员形象（静态资源，置于 public 目录，避免为图片导入引入额外类型声明）
const counselorAvatar = '/counselor-avatar.jpeg'

interface LocalMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  mode?: string | null
  sources?: CounselorSource[] | null
}

const open = ref(false)
const input = ref('')
const messages = ref<LocalMessage[]>([])
const streaming = ref(false)
const streamContent = ref('')
const sessionId = ref<string | null>(null)
const sessions = ref<CounselorSession[]>([])
const showHistory = ref(false)
const notice = ref('')
const errorMsg = ref('')
const listEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLTextAreaElement | null>(null)

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

const fabStyle = computed(() => ({ left: `${fabPos.value.x}px`, top: `${fabPos.value.y}px` }))
const panelStyle = computed(() => ({ left: `${panelPos.value.x}px`, top: `${panelPos.value.y}px` }))

let movedDistance = 0 // 本次指针交互累计位移，用于区分点击与拖动

function startDrag(e: PointerEvent, target: 'fab' | 'panel') {
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
  fabPos.value = {
    x: clamp(fabPos.value.x, window.innerWidth - FAB_SIZE - EDGE_MARGIN),
    y: clamp(fabPos.value.y, window.innerHeight - FAB_SIZE - EDGE_MARGIN),
  }
  if (open.value && panelEl.value) {
    const w = panelEl.value.offsetWidth
    const h = panelEl.value.offsetHeight
    panelPos.value = {
      x: clamp(panelPos.value.x, window.innerWidth - w - EDGE_MARGIN),
      y: clamp(panelPos.value.y, window.innerHeight - h - EDGE_MARGIN),
    }
  }
}

onMounted(() => {
  window.addEventListener('resize', onWindowResize)
  autoResizeInput()
})
onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize)
  document.body.classList.remove('cp-dragging')
})

let controller: AbortController | null = null
let seq = 0

const quickPrompts = [
  '旷课多少学时会被处分？',
  '论文抄袭会怎么处理？',
  '宿舍能不能养猫？',
  '我最近心情不太好…',
]

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
  // 面板吸附在按钮的左上方（右边缘对齐），整体拖到哪就从哪里展开
  const w = panelEl.value?.offsetWidth || 390
  const h = panelEl.value?.offsetHeight || 580
  panelPos.value = {
    x: clamp(fabPos.value.x + FAB_SIZE - w, window.innerWidth - w - EDGE_MARGIN),
    y: clamp(fabPos.value.y - PANEL_GAP - h, window.innerHeight - h - EDGE_MARGIN),
  }
  loadSessions()
  scrollToBottom()
  autoResizeInput()
}

function closePanel() {
  // 收起后按钮直接回到展开前的原始位置：面板打开期间按钮被隐藏、位置不会被改写，
  // 因此无需用面板位置反向推导，避免"拖到上方→展开（面板被 clamp 到顶部）→收起后按钮掉到下方"的位置漂移
  open.value = false
  showHistory.value = false
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

function send() {
  const question = input.value.trim()
  if (!question || streaming.value) return

  input.value = ''
  // 清空输入框后把高度复位，避免残留之前的增高
  nextTick(autoResizeInput)
  notice.value = ''
  errorMsg.value = ''
  messages.value.push({ id: ++seq, role: 'user', content: question })

  streaming.value = true
  streamContent.value = ''
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
      messages.value.push({
        id: ++seq,
        role: 'assistant',
        content: result.full_answer || streamContent.value,
        mode: result.mode,
        sources: result.sources?.length ? result.sources : pendingSources,
      })
      streamContent.value = ''
      streaming.value = false
      loadSessions()
      scrollToBottom()
    },
    onError: (err) => {
      streaming.value = false
      streamContent.value = ''
      errorMsg.value = `导员暂时没能回应：${err}`
      scrollToBottom()
    },
  })
}

function stop() {
  controller?.abort()
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
  padding: 2.5px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: linear-gradient(135deg, var(--color-primary, #4f46e5), #7c8cf8);
  box-shadow: 0 10px 26px rgba(79, 70, 229, 0.42);
  transition: transform 0.22s ease, box-shadow 0.22s ease;
}

/* 导员头像：圆形裁切并略微放大，让面部更清晰 */
.cp-fab-img {
  width: 100%;
  height: 100%;
  display: block;
  border-radius: 50%;
  object-fit: cover;
  object-position: 50% 36%;
  transform-origin: 50% 36%;
  transform: scale(1.18);
  /* 关键：禁用图片默认的原生拖拽，否则按住头像会触发 HTML5 dragstart，
     拖动期间 pointermove 被浏览器吞掉，导致图标只在松手后才跳位 */
  -webkit-user-drag: none;
  user-select: none;
  pointer-events: none;
}
.cp-fab:hover .cp-fab-core {
  transform: translateY(-2px) scale(1.05);
  box-shadow: 0 14px 32px rgba(79, 70, 229, 0.55);
}

/* 呼吸光环 */
.cp-fab-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: rgba(79, 70, 229, 0.35);
  animation: cp-pulse 2.4s ease-out infinite;
}
@keyframes cp-pulse {
  0% { transform: scale(1); opacity: 0.7; }
  70% { transform: scale(1.6); opacity: 0; }
  100% { transform: scale(1.6); opacity: 0; }
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
  border-radius: 18px;
  overflow: hidden;
  z-index: 2001;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, rgba(0, 0, 0, 0.08));
  box-shadow: 0 24px 60px rgba(24, 26, 54, 0.22);
  backdrop-filter: blur(14px);
}

/* 头部（同时是拖动把手） */
.cp-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 14px 14px 16px;
  background: linear-gradient(135deg, var(--color-primary, #4f46e5), #7c8cf8);
  color: #fff;
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
  width: 40px;
  height: 40px;
  box-sizing: border-box;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.22);
  border: 1.5px solid rgba(255, 255, 255, 0.65);
  flex-shrink: 0;
}

.cp-avatar-img {
  width: 100%;
  height: 100%;
  display: block;
  border-radius: 50%;
  object-fit: cover;
  object-position: 50% 36%;
  transform-origin: 50% 36%;
  transform: scale(1.18);
  /* 同上：禁用原生图片拖拽，保证面板头部拖动手感 */
  -webkit-user-drag: none;
  user-select: none;
}
.cp-title { flex: 1; min-width: 0; }
.cp-name { font-size: 15px; font-weight: 700; line-height: 1.3; }
.cp-sub { font-size: 11.5px; opacity: 0.85; margin-top: 2px; }

.cp-actions { display: flex; gap: 2px; }
.cp-icon-btn {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease;
}
.cp-icon-btn:hover { background: rgba(255, 255, 255, 0.2); }

/* 历史 */
.cp-history {
  max-height: 180px;
  overflow-y: auto;
  padding: 8px;
  border-bottom: 1px solid var(--color-border, rgba(0, 0, 0, 0.08));
  background: var(--color-bg-page, #f6f7fb);
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
.cp-history-item:hover { background: var(--color-primary-light, rgba(79, 70, 229, 0.08)); }
.cp-history-item.active { background: var(--color-primary-light, rgba(79, 70, 229, 0.12)); }
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
  background: rgba(0, 0, 0, 0.14);
  border-radius: 3px;
}

/* 欢迎态 */
.cp-welcome {
  margin: auto 0;
  text-align: center;
  padding: 6px 4px;
}
.cp-welcome-emoji { font-size: 30px; }
.cp-welcome-text {
  margin: 10px 0 16px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--color-text-secondary, #6b7290);
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
  color: var(--color-primary, #4f46e5);
  font-size: 12.5px;
  padding: 7px 12px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.18s ease;
}
.cp-quick-btn:hover {
  background: var(--color-primary-light, rgba(79, 70, 229, 0.1));
  border-color: var(--color-primary, #4f46e5);
  transform: translateY(-1px);
}

/* 气泡 */
.cp-row { display: flex; }
.cp-row.user { justify-content: flex-end; }
.cp-row.assistant { justify-content: flex-start; }

.cp-bubble {
  max-width: 84%;
  padding: 10px 13px;
  border-radius: 14px;
  font-size: 13.5px;
  line-height: 1.75;
  word-break: break-word;
  white-space: pre-wrap;
}
.cp-row.user .cp-bubble {
  background: linear-gradient(135deg, var(--color-primary, #4f46e5), #7c8cf8);
  color: #fff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 6px 16px rgba(79, 70, 229, 0.24);
}
.cp-row.assistant .cp-bubble {
  background: var(--color-bg-card, #fff);
  color: var(--color-text-body, #3b3f52);
  border: 1px solid var(--color-border, rgba(0, 0, 0, 0.07));
  border-bottom-left-radius: 4px;
}
.cp-text { white-space: pre-wrap; }

.cp-mode-tag {
  display: inline-block;
  font-size: 11px;
  line-height: 1;
  padding: 3px 7px;
  border-radius: 999px;
  margin-bottom: 7px;
}
.cp-mode-tag.knowledge {
  color: #0f9d8a;
  background: rgba(16, 185, 129, 0.12);
}
.cp-mode-tag.persona {
  color: #8b7cf6;
  background: rgba(139, 124, 246, 0.13);
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
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-secondary, #6b7290);
  line-height: 1.9;
}
.cp-source-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--color-primary, #4f46e5);
  flex-shrink: 0;
}

/* 打字指示 */
.cp-typing { display: flex; gap: 4px; align-items: center; height: 18px; }
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
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.12);
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
  background: linear-gradient(135deg, var(--color-primary, #4f46e5), #7c8cf8);
  box-shadow: 0 6px 14px rgba(79, 70, 229, 0.28);
  transition: transform 0.15s ease, opacity 0.15s ease;
}
.cp-send:hover:not(:disabled) { transform: translateY(-1px); }
.cp-send:disabled { opacity: 0.45; cursor: not-allowed; box-shadow: none; }
.cp-send.stop { background: rgba(107, 114, 128, 0.85); box-shadow: none; }

/* ================= 动效 ================= */
.cp-pop-enter-active, .cp-pop-leave-active { transition: all 0.2s ease; }
.cp-pop-enter-from, .cp-pop-leave-to { opacity: 0; transform: scale(0.85); }

.cp-rise-enter-active { transition: all 0.26s cubic-bezier(0.22, 1, 0.36, 1); }
.cp-rise-leave-active { transition: all 0.18s ease; }
.cp-rise-enter-from, .cp-rise-leave-to { opacity: 0; transform: translateY(16px) scale(0.97); }

.cp-fade-enter-active, .cp-fade-leave-active { transition: opacity 0.18s ease; }
.cp-fade-enter-from, .cp-fade-leave-to { opacity: 0; }

/* 移动端适配（定位由拖动逻辑以 left/top 内联控制） */
@media (max-width: 640px) {
  .cp-panel {
    width: calc(100vw - 24px);
    height: 68vh;
  }
}
</style>

/**
 * AI 助手 API 封装
 * 与教学问答（chat.ts）共用主知识库 RAG，接口路径沿用 /api/v1/counselor/*
 */

export interface CounselorSource {
  document_id?: number
  document_name: string
  chapter?: string | null
  page?: number | null
  source_url?: string | null
  snippet?: string
  score?: number
}

export interface CounselorSession {
  id: string
  title: string
  message_count: number
  last_message_at: string | null
  created_at: string
}

export interface CounselorMessage {
  id: number
  session_id: string
  role: 'user' | 'assistant'
  content: string
  mode: string | null
  sources: CounselorSource[] | null
  token_count: number | null
  created_at: string
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token')
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: authHeaders() })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function send<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: authHeaders(),
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export const counselorApi = {
  /** 会话列表 */
  listSessions: () => get<any>('/api/v1/counselor/sessions'),
  /** 创建会话 */
  createSession: (title?: string) =>
    send<any>('POST', '/api/v1/counselor/sessions', { title }),
  /** 重命名会话 */
  updateSession: (sessionId: string, title: string) =>
    send<any>('PATCH', `/api/v1/counselor/sessions/${sessionId}`, { title }),
  /** 删除会话 */
  deleteSession: (sessionId: string) =>
    send<any>('DELETE', `/api/v1/counselor/sessions/${sessionId}`),
  /** 会话消息 */
  getMessages: (sessionId: string, page = 1, pageSize = 100) =>
    get<any>(
      `/api/v1/counselor/sessions/${sessionId}/messages?page=${page}&page_size=${pageSize}`,
    ),
  /** 提交反馈 */
  feedback: (sessionId: string, feedback: number, reason?: string) =>
    send<any>('POST', '/api/v1/counselor/feedback', {
      session_id: sessionId,
      feedback,
      reason: reason || null,
    }),
  /** 确认执行助手提议的写操作（提交补采 / 创建工单） */
  confirmAction: (actionToken: string) =>
    send<any>('POST', '/api/v1/counselor/actions/confirm', {
      action_token: actionToken,
    }),
}

/** AI 助手检索到的可跳转资料（文档 / 视频） */
export interface CounselorResource {
  type: 'document' | 'video'
  id: number
  title: string
  subtitle?: string
  file_type?: string
  url: string
}

/** 助手工具调用步骤 */
export interface CounselorToolStep {
  id?: string
  name: string
  label: string
  ok?: boolean
  summary?: string
  args?: Record<string, any>
  data?: Record<string, any>
}

/** 待用户确认的写操作 */
export interface CounselorAction {
  tool: string
  label: string
  args: Record<string, any>
  action_token: string
  expires_in: number
  loading?: boolean
  done?: boolean
  ok?: boolean
  resultText?: string
  error?: string
}

interface CounselorStreamCallbacks {
  onToken: (token: string) => void
  onSources: (sources: CounselorSource[]) => void
  onSensitive?: (masked: string, hits: any[]) => void
  onToolCall?: (step: CounselorToolStep) => void
  onToolResult?: (step: CounselorToolStep) => void
  onConfirmation?: (action: CounselorAction) => void
  onDone: (result: {
    full_answer: string
    mode: string
    sources: CounselorSource[]
    resources?: CounselorResource[]
    session_id?: string
    tool_trace?: CounselorToolStep[]
  }) => void
  onError: (error: string) => void
}

/**
 * AI 助手流式提问（SSE）
 * events: token / sources / tool_call / tool_result / confirmation_required / done / error / sensitive
 */
export function counselorStream(
  question: string,
  sessionId: string | null,
  cb: CounselorStreamCallbacks,
): AbortController {
  const controller = new AbortController()

  fetch('/api/v1/counselor/stream', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ question, session_id: sessionId }),
    signal: controller.signal,
  })
    .then(async (response) => {
      // 5xx 多为后端刚重启还没就绪，直接抛状态码用户看不懂，这里给出可操作提示
      if (!response.ok) {
        throw new Error(
          response.status >= 500
            ? `AI 助手服务暂时不可用（HTTP ${response.status}），可能正在启动或重启，请等几秒再试`
            : `HTTP ${response.status}`,
        )
      }
      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''
      let terminalSeen = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const data = line.slice(6).trim()
            if (!data) continue
            try {
              const parsed = JSON.parse(data)
              switch (currentEvent) {
                case 'token':
                  cb.onToken(parsed.token)
                  break
                case 'sources':
                  cb.onSources(parsed)
                  break
                case 'tool_call':
                  cb.onToolCall?.(parsed)
                  break
                case 'tool_result':
                  cb.onToolResult?.(parsed)
                  break
                case 'confirmation_required':
                  cb.onConfirmation?.(parsed)
                  break
                case 'sensitive':
                  cb.onSensitive?.(parsed.full_answer, parsed.hits || [])
                  break
                case 'done':
                  terminalSeen = true
                  cb.onDone(parsed)
                  break
                case 'error':
                  terminalSeen = true
                  cb.onError(parsed.message || '未知错误')
                  break
              }
            } catch {
              // 非 JSON 数据，忽略
            }
          }
        }
      }

      // 连接被代理/超时截断等场景：流正常结束但没有 done/error，
      // 必须主动收尾，否则前端会永远停在"生成中"
      if (!terminalSeen) {
        cb.onError('连接中断，回答未完整返回，请重试')
      }
    })
    .catch((err) => {
      if (err.name === 'AbortError') return
      cb.onError(err.message || '网络请求失败')
    })

  return controller
}

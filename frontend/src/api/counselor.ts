/**
 * AI 导员 API 封装
 * 与教学问答（chat.ts）完全独立，走 /api/v1/counselor/*
 */

export interface CounselorSource {
  source_title: string
  article_no: string
  chapter: string
  source_url: string
  snippet: string
  score: number
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
}

interface CounselorStreamCallbacks {
  onToken: (token: string) => void
  onSources: (sources: CounselorSource[]) => void
  onSensitive?: (masked: string, hits: any[]) => void
  onDone: (result: {
    full_answer: string
    mode: string
    sources: CounselorSource[]
    session_id?: string
  }) => void
  onError: (error: string) => void
}

/**
 * 导员流式提问（SSE）
 * events: token / sources / done / error / sensitive
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
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''

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
                case 'sensitive':
                  cb.onSensitive?.(parsed.full_answer, parsed.hits || [])
                  break
                case 'done':
                  cb.onDone(parsed)
                  break
                case 'error':
                  cb.onError(parsed.message || '未知错误')
                  break
              }
            } catch {
              // 非 JSON 数据，忽略
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name === 'AbortError') return
      cb.onError(err.message || '网络请求失败')
    })

  return controller
}

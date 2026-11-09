// ============================================================
// 补采闭环 API 封装
// 未命中问题候选 → 补采需求 → 触发采集流水线
// ============================================================

import client from './client'

export interface CollectionCandidate {
  question: string
  count: number
  last_at: string | null
  missed_count: number
  negative_count: number
  reasons: string[]
}

export interface CollectionRequestRow {
  id: number
  question: string
  reason: string
  status: number
  status_label: string
  category_id: number | null
  chat_log_id: number | null
  note: string | null
  created_by: number
  creator_name: string | null
  created_at: string | null
  updated_at: string | null
}

export const COLLECTION_STATUS: Record<number, string> = {
  0: '待处理',
  1: '已触发采集',
  2: '已完成',
  3: '已忽略',
}

export const REASON_LABELS: Record<string, string> = {
  missed: '未命中',
  negative_feedback: '点踩',
}

export const collectionApi = {
  candidates: (params: { days?: number; limit?: number }) =>
    client.get('/collection/candidates', { params }),
  createRequest: (data: {
    question: string
    reason?: string
    category_id?: number | null
    chat_log_id?: number | null
    note?: string
  }) => client.post('/collection/requests', data),
  listRequests: (params: {
    page?: number
    page_size?: number
    status?: number
    keyword?: string
  }) => client.get('/collection/requests', { params }),
  myRequests: (params: {
    page?: number
    page_size?: number
    status?: number
  }) => client.get('/collection/requests/mine', { params }),
  stats: () => client.get('/collection/requests/stats'),
  updateRequest: (id: number, data: { status?: number; note?: string }) =>
    client.put(`/collection/requests/${id}`, data),
  runRequest: (id: number) => client.post(`/collection/requests/${id}/run`),
}

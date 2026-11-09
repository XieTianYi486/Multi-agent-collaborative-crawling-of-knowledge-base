import client from './client'

export interface VideoItem {
  id: number
  title: string
  bvid: string
  url: string
  cover_url: string
  up_name: string
  duration: number
  play_count: number
  category: string
  difficulty: string
  description: string
  tags: string[]
  sort_order: number
  status: number
  created_at?: string
  updated_at?: string
}

export interface VideoPayload {
  title: string
  bvid: string
  cover_url?: string
  up_name?: string
  duration?: number
  play_count?: number
  category?: string
  difficulty?: string
  description?: string
  tags?: string[]
  sort_order?: number
  status?: number
}

// 学生端
export const videoApi = {
  list: (params: {
    keyword?: string
    category?: string
    difficulty?: string
    page?: number
    page_size?: number
  }) => client.get('/videos', { params }),
  categories: () => client.get('/videos/categories'),
  detail: (id: number) => client.get(`/videos/${id}`),
}

// 管理端
export const videoAdminApi = {
  list: (params: {
    keyword?: string
    category?: string
    status?: number
    page?: number
    page_size?: number
  }) => client.get('/admin/videos', { params }),
  create: (data: VideoPayload) => client.post('/admin/videos', data),
  update: (id: number, data: Partial<VideoPayload>) => client.put(`/admin/videos/${id}`, data),
  setStatus: (id: number, status: number) =>
    client.put(`/admin/videos/${id}/status`, null, { params: { status } }),
  remove: (id: number) => client.delete(`/admin/videos/${id}`),
}

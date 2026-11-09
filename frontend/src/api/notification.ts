import client from './client'

export interface NotificationItem {
  id: number
  type: string
  title: string
  content: string | null
  link: string | null
  is_read: boolean
  created_at: string | null
}

export const notificationApi = {
  list: (params: { page?: number; page_size?: number; unread_only?: boolean }) =>
    client.get('/notifications', { params }),
  unreadCount: () => client.get('/notifications/unread-count'),
  markRead: (id: number) => client.put(`/notifications/${id}/read`),
  markAllRead: () => client.put('/notifications/read-all'),
}

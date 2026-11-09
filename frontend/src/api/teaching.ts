// ============================================================
// 教学关系 API：老师 ↔ 班级 ↔ 学生
// ============================================================

import client from './client'

export interface TeachingAssignmentRow {
  id: number
  teacher_id: number
  teacher_name: string | null
  teacher_username: string | null
  teacher_department: string | null
  class_id: number
  subject: string | null
  created_at: string | null
}

export interface MyClassRow {
  class_id: number
  class_name: string
  subject: string | null
  student_count: number
}

export interface StudentRow {
  id: number
  username: string
  real_name: string | null
  gender: string | null
  department: string | null
  created_at: string | null
  chat_count: number
  last_ask_at: string | null
  doc_count: number
  collection_count: number
}

export const teachingApi = {
  teachers: (keyword?: string) =>
    client.get('/teaching/teachers', { params: { keyword } }),
  assignments: (params?: { class_id?: number; teacher_id?: number }) =>
    client.get('/teaching/assignments', { params }),
  createAssignment: (data: { teacher_id: number; class_id: number; subject?: string }) =>
    client.post('/teaching/assignments', data),
  removeAssignment: (id: number) => client.delete(`/teaching/assignments/${id}`),
  myClasses: () => client.get('/teaching/my-classes'),
  classStudents: (classId: number, params: { page?: number; page_size?: number; keyword?: string }) =>
    client.get(`/teaching/my-classes/${classId}/students`, { params }),
}

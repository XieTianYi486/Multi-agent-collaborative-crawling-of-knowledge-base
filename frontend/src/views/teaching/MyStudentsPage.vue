<template>
  <div class="student-page">
    <div class="page-header">
      <div class="header-left">
        <el-icon class="header-icon" :size="22"><UserFilled /></el-icon>
        <h2>我的学生</h2>
        <el-tag v-if="classes.length" effect="plain">{{ classes.length }} 个班级</el-tag>
      </div>
    </div>

    <el-empty
      v-if="!loadingClasses && classes.length === 0"
      description="还没有任课班级，请联系管理员在「部门管理」中为你分配班级"
    />

    <div v-else class="student-layout">
      <aside v-loading="loadingClasses" class="class-list">
        <button
          v-for="c in classes"
          :key="c.class_id"
          type="button"
          class="class-item"
          :class="{ active: c.class_id === activeClassId }"
          @click="selectClass(c.class_id)"
        >
          <span class="class-name">{{ c.class_name }}</span>
          <span class="class-meta">
            {{ c.subject || '未标注学科' }} · {{ c.student_count }} 人
          </span>
        </button>
      </aside>

      <section class="student-panel">
        <div class="panel-toolbar">
          <el-input
            v-model="keyword"
            placeholder="搜索姓名或账号"
            clearable
            :prefix-icon="Search"
            class="search-input"
            @keyup.enter="loadStudents(1)"
            @clear="loadStudents(1)"
          />
          <el-button :icon="Search" @click="loadStudents(1)">查询</el-button>
          <span class="panel-count">共 {{ total }} 名学生</span>
        </div>

        <el-table v-loading="loadingStudents" :data="students" class="student-table">
          <el-table-column label="学生" min-width="140">
            <template #default="{ row }">
              <div class="student-name">{{ row.real_name || '未填写姓名' }}</div>
              <div class="student-username">{{ row.username }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="gender" label="性别" width="70">
            <template #default="{ row }">{{ row.gender || '—' }}</template>
          </el-table-column>
          <el-table-column label="班级" min-width="110">
            <template #default="{ row }">{{ row.department || '—' }}</template>
          </el-table-column>
          <el-table-column label="注册时间" width="120">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="问答次数" width="96" align="center">
            <template #default="{ row }">
              <el-tag size="small" type="info" effect="plain">{{ row.chat_count }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="最近提问" width="130">
            <template #default="{ row }">{{ formatDateTime(row.last_ask_at) }}</template>
          </el-table-column>
          <el-table-column label="投稿" width="76" align="center">
            <template #default="{ row }">{{ row.doc_count }}</template>
          </el-table-column>
          <el-table-column label="补采" width="76" align="center">
            <template #default="{ row }">{{ row.collection_count }}</template>
          </el-table-column>
        </el-table>

        <div v-if="total > pageSize" class="pagination">
          <el-pagination
            v-model:current-page="page"
            :page-size="pageSize"
            :total="total"
            layout="total, prev, pager, next"
            @current-change="loadStudents(page)"
          />
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { UserFilled, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { teachingApi } from '@/api/teaching'
import type { MyClassRow, StudentRow } from '@/api/teaching'

const classes = ref<MyClassRow[]>([])
const activeClassId = ref<number | null>(null)
const students = ref<StudentRow[]>([])
const loadingClasses = ref(false)
const loadingStudents = ref(false)
const keyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

async function loadClasses() {
  loadingClasses.value = true
  try {
    const res = await teachingApi.myClasses()
    classes.value = res.data.data || []
    if (classes.value.length && activeClassId.value === null) {
      selectClass(classes.value[0].class_id)
    }
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '班级加载失败')
  } finally {
    loadingClasses.value = false
  }
}

function selectClass(classId: number) {
  if (activeClassId.value === classId) return
  activeClassId.value = classId
  keyword.value = ''
  loadStudents(1)
}

async function loadStudents(targetPage = 1) {
  if (activeClassId.value === null) return
  page.value = targetPage
  loadingStudents.value = true
  try {
    const res = await teachingApi.classStudents(activeClassId.value, {
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    })
    const data = res.data.data || {}
    students.value = data.items || []
    total.value = data.total || 0
  } catch (err: any) {
    students.value = []
    total.value = 0
    ElMessage.error(err?.response?.data?.detail || '学生列表加载失败')
  } finally {
    loadingStudents.value = false
  }
}

function formatDate(value: string | null) {
  if (!value) return '—'
  return value.slice(0, 10)
}

function formatDateTime(value: string | null) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

onMounted(loadClasses)
</script>

<style scoped>
.student-page { padding: 24px 32px; max-width: 1180px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.header-left { display: flex; align-items: center; gap: 10px; }
.header-icon { color: var(--color-primary); }
.header-left h2 { font-size: 20px; font-weight: 700; color: var(--color-text-primary); margin: 0; }

.student-layout { display: flex; gap: 16px; align-items: flex-start; }

.class-list { width: 210px; flex: 0 0 210px; display: flex; flex-direction: column; gap: 8px; }
.class-item {
  display: flex; flex-direction: column; gap: 4px; width: 100%;
  padding: 12px 14px; text-align: left; cursor: pointer;
  background: var(--color-bg-card); border: 1px solid var(--color-border);
  border-radius: 10px; transition: all .18s;
}
.class-item:hover { border-color: var(--color-primary); }
.class-item.active {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
}
.class-name { font-size: 14px; font-weight: 600; color: var(--color-text-primary); }
.class-meta { font-size: 12px; color: var(--color-text-secondary); }

.student-panel {
  flex: 1; min-width: 0;
  background: var(--color-bg-card); border: 1px solid var(--color-border);
  border-radius: 12px; padding: 16px 18px;
}
.panel-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.search-input { width: 240px; }
.panel-count { margin-left: auto; font-size: 13px; color: var(--color-text-secondary); }

.student-name { font-weight: 600; color: var(--color-text-primary); }
.student-username { font-size: 12px; color: var(--color-text-secondary); margin-top: 2px; }

.pagination { display: flex; justify-content: flex-end; margin-top: 14px; }

@media (max-width: 860px) {
  .student-layout { flex-direction: column; }
  .class-list { width: 100%; flex: 1 1 auto; flex-direction: row; overflow-x: auto; }
  .class-item { min-width: 160px; }
}
</style>

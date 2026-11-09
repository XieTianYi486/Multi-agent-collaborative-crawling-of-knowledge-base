<template>
  <div class="admin-page">
    <div class="page-header">
      <div class="header-left">
        <el-icon class="header-icon" :size="24"><OfficeBuilding /></el-icon>
        <h2>部门管理</h2>
        <el-tag size="small" round type="info">{{ filteredDepartments.length }} 个部门</el-tag>
      </div>
      <el-button type="primary" :icon="Plus" @click="showCreateDialog">新建部门</el-button>
    </div>

    <el-tabs v-model="activeType" class="dept-tabs">
      <el-tab-pane label="全部部门" name="all" />
      <el-tab-pane label="教学单位" name="teaching" />
      <el-tab-pane label="班级" name="class" />
    </el-tabs>

    <div v-loading="loading" class="dept-grid">
      <template v-if="filteredDepartments.length > 0">
        <div v-for="dept in filteredDepartments" :key="dept.id" class="dept-card">
          <div class="dept-avatar">
            <el-icon :size="24"><OfficeBuilding /></el-icon>
          </div>
          <div class="dept-body">
            <div class="dept-name">{{ dept.name }}</div>
            <div class="dept-desc">{{ dept.description || '暂无描述' }}</div>
            <div class="dept-meta">
              <span class="meta-item">
                <el-icon :size="14"><User /></el-icon>
                {{ dept.manager_name || '未设置' }}
              </span>
              <span class="meta-tags">
                <el-tag size="small" round :type="dept.dept_type === 'class' ? 'warning' : 'primary'">
                  {{ dept.dept_type === 'class' ? '班级' : '教学单位' }}
                </el-tag>
                <el-tag size="small" round type="info">{{ dept.member_count ?? 0 }} 人</el-tag>
              </span>
            </div>
            <div v-if="dept.dept_type === 'class'" class="teacher-row">
              <span class="teacher-label">任课老师</span>
              <div class="teacher-tags">
                <el-tag
                  v-for="a in assignmentsByClass(dept.id)"
                  :key="a.id"
                  size="small"
                  round
                  closable
                  @close="handleRemoveAssignment(a)"
                >
                  {{ a.teacher_name || a.teacher_username }}<span v-if="a.subject"> · {{ a.subject }}</span>
                </el-tag>
                <el-button text size="small" :icon="Plus" @click="openAssignDialog(dept)">分配</el-button>
              </div>
            </div>
          </div>
          <div class="dept-actions">
            <el-button text size="small" :icon="Edit" @click="showEditDialog(dept)">编辑</el-button>
            <el-popconfirm title="确定删除此部门？" @confirm="handleDelete(dept.id)">
              <template #reference>
                <el-button text type="danger" size="small" :icon="Delete">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </template>
      <el-empty v-else description="暂无部门，点击上方按钮创建" class="empty-state">
        <el-button type="primary" @click="showCreateDialog">新建部门</el-button>
      </el-empty>
    </div>

    <!-- 创建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑部门' : '新建部门'" width="460px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="72px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="部门名称" maxlength="20" show-word-limit />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="部门描述（选填）" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="类型" prop="dept_type">
          <el-radio-group v-model="form.dept_type">
            <el-radio-button value="teaching">教学单位（老师）</el-radio-button>
            <el-radio-button value="class">班级（学生）</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">
          {{ editingId ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 分配任课老师 -->
    <el-dialog v-model="assignVisible" title="分配任课老师" width="440px" destroy-on-close>
      <div class="assign-target">
        <el-icon :size="16"><OfficeBuilding /></el-icon>
        <span>{{ assignClass?.name }}</span>
      </div>
      <el-form label-width="64px">
        <el-form-item label="教师">
          <el-select
            v-model="assignForm.teacher_id"
            filterable
            clearable
            placeholder="选择教师（可搜索姓名或账号）"
            style="width: 100%"
          >
            <el-option
              v-for="t in teachers"
              :key="t.id"
              :label="`${t.real_name || t.username}（${t.username}）`"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="学科">
          <el-input v-model="assignForm.subject" placeholder="选填，如 数据结构" maxlength="64" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" :loading="assigning" @click="handleAssign">确认分配</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, OfficeBuilding, User, Edit, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import client from '@/api/client'
import { teachingApi } from '@/api/teaching'
import type { TeachingAssignmentRow } from '@/api/teaching'

const loading = ref(false)
const saving = ref(false)
const departments = ref<any[]>([])
const activeType = ref<'all' | 'teaching' | 'class'>('all')
const filteredDepartments = computed(() => {
  if (activeType.value === 'all') return departments.value
  return departments.value.filter((d) => (d.dept_type || 'teaching') === activeType.value)
})
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()

const form = reactive({ name: '', description: '', dept_type: 'teaching' })
const rules: FormRules = {
  name: [{ required: true, message: '请输入部门名称', trigger: 'blur' }],
}

// ==================== 任课老师分配 ====================
const assignments = ref<TeachingAssignmentRow[]>([])
const teachers = ref<any[]>([])
const assignVisible = ref(false)
const assigning = ref(false)
const assignClass = ref<any | null>(null)
const assignForm = reactive<{ teacher_id: number | undefined; subject: string }>({
  teacher_id: undefined,
  subject: '',
})

function assignmentsByClass(classId: number) {
  return assignments.value.filter((a) => a.class_id === classId)
}

async function loadAssignments() {
  try {
    const res = await teachingApi.assignments()
    assignments.value = res.data.data || []
  } catch {
    assignments.value = []
  }
}

async function loadTeachers() {
  try {
    const res = await teachingApi.teachers()
    teachers.value = res.data.data || []
  } catch {
    teachers.value = []
  }
}

function openAssignDialog(dept: any) {
  assignClass.value = dept
  assignForm.teacher_id = undefined
  assignForm.subject = ''
  assignVisible.value = true
}

async function handleAssign() {
  if (!assignForm.teacher_id || !assignClass.value) {
    ElMessage.warning('请选择教师')
    return
  }
  assigning.value = true
  try {
    await teachingApi.createAssignment({
      teacher_id: assignForm.teacher_id,
      class_id: assignClass.value.id,
      subject: assignForm.subject || undefined,
    })
    ElMessage.success('已分配任课老师')
    assignVisible.value = false
    await loadAssignments()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '分配失败')
  } finally {
    assigning.value = false
  }
}

async function handleRemoveAssignment(a: TeachingAssignmentRow) {
  try {
    await ElMessageBox.confirm(
      `确定取消「${a.teacher_name || a.teacher_username}」在班级中的授课关系？`,
      '取消授课关系',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await teachingApi.removeAssignment(a.id)
    ElMessage.success('已取消')
    await loadAssignments()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '操作失败')
  }
}

async function loadData() {
  loading.value = true
  try {
    const res = await client.get('/admin/departments')
    departments.value = res.data.data || []
  } catch { /* ignore */ } finally { loading.value = false }
}

function showCreateDialog() {
  editingId.value = null
  form.name = ''
  form.description = ''
  form.dept_type = activeType.value === 'class' ? 'class' : 'teaching'
  dialogVisible.value = true
}

function showEditDialog(row: any) {
  editingId.value = row.id
  form.name = row.name
  form.description = row.description || ''
  form.dept_type = row.dept_type || 'teaching'
  dialogVisible.value = true
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    if (editingId.value) {
      await client.put(`/admin/departments/${editingId.value}`, null, {
        params: { name: form.name, description: form.description || undefined, dept_type: form.dept_type },
      })
      ElMessage.success('部门已更新')
    } else {
      await client.post('/admin/departments', null, {
        params: { name: form.name, description: form.description || undefined, dept_type: form.dept_type },
      })
      ElMessage.success('部门已创建')
    }
    dialogVisible.value = false
    loadData()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '操作失败')
  } finally { saving.value = false }
}

async function handleDelete(id: number) {
  try {
    await client.delete(`/admin/departments/${id}`)
    ElMessage.success('部门已删除')
    loadData()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '删除失败')
  }
}

onMounted(() => {
  loadData()
  loadAssignments()
  loadTeachers()
})
</script>

<style scoped>
.admin-page { padding: 24px 32px; max-width: 1000px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.header-left { display: flex; align-items: center; gap: 10px; }
.header-icon { color: var(--color-primary); }
.header-left h2 { font-size: 20px; font-weight: 700; color: var(--color-text-primary); margin: 0; }

.dept-tabs { margin-bottom: 16px; }
.dept-tabs :deep(.el-tabs__header) { margin-bottom: 16px; }

.dept-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.empty-state { grid-column: 1 / -1; }

.dept-card {
  background: var(--color-bg-card); border: 1px solid var(--color-border);
  border-radius: 10px; padding: 20px; display: flex; flex-direction: column; gap: 14px;
  transition: box-shadow .2s; box-shadow: 0 1px 3px rgba(0,0,0,.04);
}
.dept-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,.08); }

.dept-avatar {
  width: 44px; height: 44px; border-radius: 10px;
  background: linear-gradient(135deg, var(--color-primary-light-8, #d9ecff), var(--color-primary-light-5, #a0cfff));
  display: flex; align-items: center; justify-content: center; color: var(--color-primary);
}
.dept-body { flex: 1; }
.dept-name { font-size: 16px; font-weight: 600; color: var(--color-text-primary); }
.dept-desc { font-size: 13px; color: var(--color-text-placeholder); margin-top: 4px; min-height: 18px; }
.dept-meta { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; }
.meta-item { display: flex; align-items: center; gap: 4px; font-size: 13px; color: var(--color-text-secondary); }
.meta-tags { display: flex; align-items: center; gap: 6px; }
.teacher-row { display: flex; align-items: flex-start; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--color-border); }
.teacher-label { font-size: 12px; color: var(--color-text-secondary); white-space: nowrap; line-height: 24px; }
.teacher-tags { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.assign-target { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; padding: 10px 12px; border-radius: 8px; background: var(--color-primary-light); color: var(--color-primary); font-weight: 600; }
.dept-actions { display: flex; justify-content: flex-end; gap: 2px; border-top: 1px solid var(--color-border); padding-top: 12px; }
</style>
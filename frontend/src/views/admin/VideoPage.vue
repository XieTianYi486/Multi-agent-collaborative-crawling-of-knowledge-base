<template>
  <div class="admin-page">
    <div class="page-header">
      <div>
        <h2>视频管理</h2>
        <p class="page-sub">维护视频专区的 B 站精选内容，只存元数据，播放由 B 站官方播放器提供；播放量与封面为手动维护的快照，不会自动刷新</p>
      </div>
      <el-button type="primary" @click="openCreate">新增视频</el-button>
    </div>

    <el-card>
      <!-- 筛选 -->
      <div class="filter-row">
        <el-input
          v-model="filters.keyword"
          placeholder="搜索标题 / BV 号 / UP 主"
          clearable
          :prefix-icon="Search"
          class="filter-item keyword"
          @input="onSearch"
        />
        <el-select v-model="filters.category" clearable placeholder="全部分类" class="filter-item" @change="reload">
          <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="全部状态" class="filter-item" @change="reload">
          <el-option label="已上架" :value="1" />
          <el-option label="已下架" :value="0" />
        </el-select>
      </div>

      <el-table :data="videos" stripe v-loading="loading">
        <el-table-column prop="sort_order" label="排序" width="70" align="center" />
        <el-table-column label="封面" width="120">
          <template #default="{ row }">
            <img
              v-if="row.cover_url"
              :src="row.cover_url"
              class="cover-thumb"
              referrerpolicy="no-referrer"
              :alt="row.title"
            />
            <span v-else class="cover-empty">无</span>
          </template>
        </el-table-column>
        <el-table-column label="标题" min-width="260">
          <template #default="{ row }">
            <div class="title-cell">
              <span class="title-text" :title="row.title">{{ row.title }}</span>
              <span class="bvid-text">{{ row.bvid }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="110" />
        <el-table-column label="难度" width="85" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.difficulty === '入门' ? 'success' : 'warning'" effect="plain">
              {{ row.difficulty }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="up_name" label="UP 主" width="150" show-overflow-tooltip />
        <el-table-column label="时长" width="110" align="center">
          <template #default="{ row }">{{ formatDuration(row.duration) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 1 ? 'success' : 'info'">
              {{ row.status === 1 ? '已上架' : '已下架' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="toggleStatus(row)">
              {{ row.status === 1 ? '下架' : '上架' }}
            </el-button>
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && videos.length === 0" description="暂无视频，点击右上角新增" />

      <div v-if="total > filters.page_size" class="pagination-wrap">
        <el-pagination
          background
          layout="prev, pager, next"
          :current-page="filters.page"
          :page-size="filters.page_size"
          :total="total"
          @current-change="onPageChange"
        />
      </div>
    </el-card>

    <!-- 新增/编辑 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑视频' : '新增视频'"
      width="min(680px, 94vw)"
      top="6vh"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="与 B 站视频标题保持一致" maxlength="300" show-word-limit />
        </el-form-item>
        <el-form-item label="BV 号" prop="bvid">
          <el-input v-model="form.bvid" placeholder="例如 BV1EPisBWEUX" maxlength="12">
            <template #append>
              <a
                v-if="form.bvid"
                :href="`https://www.bilibili.com/video/${form.bvid}`"
                target="_blank"
                rel="noopener noreferrer"
                class="verify-link"
              >在 B 站核对</a>
              <span v-else>必填</span>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="封面地址">
          <el-input v-model="form.cover_url" placeholder="https://i0.hdslb.com/bfs/archive/xxx.jpg" />
          <img
            v-if="form.cover_url"
            :src="form.cover_url"
            class="cover-preview"
            referrerpolicy="no-referrer"
            alt="封面预览"
          />
        </el-form-item>
        <el-form-item label="UP 主">
          <el-input v-model="form.up_name" placeholder="例如 正点原子官方" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="分类" prop="category">
            <el-select v-model="form.category" filterable allow-create default-first-option class="full">
              <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
            </el-select>
          </el-form-item>
          <el-form-item label="难度">
            <el-select v-model="form.difficulty" class="full">
              <el-option label="入门" value="入门" />
              <el-option label="进阶" value="进阶" />
            </el-select>
          </el-form-item>
        </div>
        <div class="form-row">
          <el-form-item label="时长(分钟)">
            <el-input-number v-model="form.duration_min" :min="0" :max="3000" :step="1" :precision="1" class="full" />
          </el-form-item>
          <el-form-item label="排序号">
            <el-input-number v-model="form.sort_order" :min="0" :max="9999" :step="1" class="full" />
          </el-form-item>
        </div>
        <el-form-item label="播放量">
          <el-input-number v-model="form.play_count" :min="0" :max="99999999" :step="1000" class="full" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="一句话说明这套视频适合谁、能学到什么"
          />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tags_text" placeholder="多个标签用逗号分隔，例如 ESP32,入门,系统课" />
        </el-form-item>
        <el-form-item label="上架状态">
          <el-switch v-model="form.status" :active-value="1" :inactive-value="0" active-text="上架" inactive-text="下架" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { videoAdminApi, type VideoItem } from '@/api/video'

interface VideoForm {
  title: string
  bvid: string
  cover_url: string
  up_name: string
  duration_min: number
  play_count: number
  category: string
  difficulty: string
  description: string
  tags_text: string
  sort_order: number
  status: number
}

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref()
const videos = ref<VideoItem[]>([])
const total = ref(0)

const defaultCategories = ['ESP32', 'ESP-IDF', 'Arduino', 'FreeRTOS', '树莓派', '电子电路', '嵌入式开发']
const categoryOptions = computed(() => {
  const names = new Set(defaultCategories)
  videos.value.forEach(v => v.category && names.add(v.category))
  return Array.from(names)
})

const filters = reactive({
  keyword: '',
  category: '',
  status: undefined as number | undefined,
  page: 1,
  page_size: 20,
})

const emptyForm = (): VideoForm => ({
  title: '',
  bvid: '',
  cover_url: '',
  up_name: '',
  duration_min: 0,
  play_count: 0,
  category: 'ESP32',
  difficulty: '入门',
  description: '',
  tags_text: '',
  sort_order: 0,
  status: 1,
})

const form = ref<VideoForm>(emptyForm())

const rules = {
  title: [{ required: true, message: '请输入视频标题', trigger: 'blur' }],
  bvid: [
    { required: true, message: '请输入 BV 号', trigger: 'blur' },
    { pattern: /^BV[0-9A-Za-z]{10}$/, message: 'BV 号格式不正确（BV + 10 位字母数字）', trigger: 'blur' },
  ],
  category: [{ required: true, message: '请选择或填写分类', trigger: 'change' }],
}

function formatDuration(seconds: number): string {
  if (!seconds) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h} 小时 ${m} 分`
  return `${m} 分钟`
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    filters.page = 1
    loadData()
  }, 300)
}

function reload() {
  filters.page = 1
  loadData()
}

async function loadData() {
  loading.value = true
  try {
    const res = await videoAdminApi.list({
      keyword: filters.keyword || undefined,
      category: filters.category || undefined,
      status: filters.status,
      page: filters.page,
      page_size: filters.page_size,
    })
    const data = res.data.data
    videos.value = data?.items || []
    total.value = data?.total || 0
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '视频列表加载失败')
  } finally {
    loading.value = false
  }
}

function onPageChange(p: number) {
  filters.page = p
  loadData()
}

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  dialogVisible.value = true
}

function openEdit(row: VideoItem) {
  editingId.value = row.id
  form.value = {
    title: row.title,
    bvid: row.bvid,
    cover_url: row.cover_url || '',
    up_name: row.up_name || '',
    duration_min: Math.round((row.duration || 0) / 6) / 10,
    play_count: row.play_count || 0,
    category: row.category,
    difficulty: row.difficulty,
    description: row.description || '',
    tags_text: (row.tags || []).join(','),
    sort_order: row.sort_order || 0,
    status: row.status,
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  const payload = {
    title: form.value.title.trim(),
    bvid: form.value.bvid.trim(),
    cover_url: form.value.cover_url.trim(),
    up_name: form.value.up_name.trim(),
    duration: Math.round((form.value.duration_min || 0) * 60),
    play_count: form.value.play_count || 0,
    category: form.value.category,
    difficulty: form.value.difficulty,
    description: form.value.description.trim(),
    tags: form.value.tags_text.split(/[,，]/).map(t => t.trim()).filter(Boolean),
    sort_order: form.value.sort_order || 0,
    status: form.value.status,
  }

  submitting.value = true
  try {
    if (editingId.value) {
      await videoAdminApi.update(editingId.value, payload)
      ElMessage.success('视频已更新')
    } else {
      await videoAdminApi.create(payload)
      ElMessage.success('视频已添加')
    }
    dialogVisible.value = false
    loadData()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    submitting.value = false
  }
}

async function toggleStatus(row: VideoItem) {
  const next = row.status === 1 ? 0 : 1
  try {
    await videoAdminApi.setStatus(row.id, next)
    row.status = next
    ElMessage.success(next === 1 ? '已上架' : '已下架')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '操作失败')
  }
}

async function handleDelete(row: VideoItem) {
  try {
    await ElMessageBox.confirm(`确定删除视频「${row.title}」？删除后不影响 B 站原视频。`, '删除确认', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning',
    })
    await videoAdminApi.remove(row.id)
    ElMessage.success('已删除')
    loadData()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.message || '删除失败')
  }
}

onMounted(loadData)
</script>

<style scoped>
.admin-page { padding: 24px 32px; max-width: 1300px; }
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
}
.page-header h2 { font-size: 22px; font-weight: 700; color: var(--color-text-primary); margin: 0 0 6px; }
.page-sub { margin: 0; font-size: 13px; color: var(--color-text-secondary); }

.filter-row { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.filter-item { width: 160px; }
.filter-item.keyword { width: 280px; }

.cover-thumb { width: 96px; height: 60px; object-fit: cover; border-radius: 6px; display: block; }
.cover-empty { font-size: 12px; color: var(--color-text-placeholder); }
.title-cell { display: flex; flex-direction: column; gap: 2px; }
.title-text { font-size: 13px; color: var(--color-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bvid-text { font-size: 11px; color: var(--color-text-placeholder); font-family: monospace; }

.pagination-wrap { display: flex; justify-content: center; margin-top: 18px; }

.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
.full { width: 100%; }
.cover-preview { width: 160px; height: 96px; object-fit: cover; border-radius: 6px; margin-top: 8px; }
.verify-link { color: var(--color-primary); text-decoration: none; font-size: 12px; }
.verify-link:hover { text-decoration: underline; }

@media (max-width: 768px) {
  .admin-page { padding: 16px; }
  .page-header { flex-direction: column; }
  .filter-item, .filter-item.keyword { width: 100%; }
  .form-row { grid-template-columns: 1fr; }
}
</style>

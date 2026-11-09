<template>
  <div class="browse-page">
    <div class="page-header">
      <h2>知识库文档</h2>
      <div class="header-actions">
        <el-input
          v-model="keyword"
          placeholder="搜索标题、文件名或正文内容..."
          clearable
          :prefix-icon="Search"
          class="search-input"
          @input="onSearch"
        />
        <el-button
          v-if="canContribute"
          :icon="Clock"
          @click="openMyContributions"
        >我的投稿</el-button>
        <el-button
          v-if="canContribute"
          type="primary"
          :icon="Upload"
          @click="contributeVisible = true"
        >投稿资料</el-button>
      </div>
    </div>

    <!-- 知识库概览 -->
    <div class="overview-strip">
      <div class="overview-card">
        <div class="overview-icon"><el-icon :size="22"><Files /></el-icon></div>
        <div class="overview-body">
          <div class="overview-value">{{ statsLoading ? '—' : stats.total_documents }}</div>
          <div class="overview-label">文档总数</div>
        </div>
      </div>
      <div class="overview-card">
        <div class="overview-icon"><el-icon :size="22"><Tickets /></el-icon></div>
        <div class="overview-body">
          <div class="overview-value">{{ statsLoading ? '—' : stats.total_chunks }}</div>
          <div class="overview-label">知识分块</div>
        </div>
      </div>
      <div class="overview-card">
        <div class="overview-icon"><el-icon :size="22"><FolderOpened /></el-icon></div>
        <div class="overview-body">
          <div class="overview-value">{{ categories.length }}</div>
          <div class="overview-label">分类数量</div>
        </div>
      </div>
      <div class="overview-card">
        <div class="overview-icon"><el-icon :size="22"><Coin /></el-icon></div>
        <div class="overview-body">
          <div class="overview-value">{{ statsLoading ? '—' : formatFileSize(stats.total_size_bytes) }}</div>
          <div class="overview-label">知识总量</div>
        </div>
      </div>
    </div>

    <div class="browse-body">
      <!-- 分类侧边栏 -->
      <aside class="category-sidebar">
        <div class="category-title">
          <el-icon :size="16"><FolderOpened /></el-icon>
          <span>文档分类</span>
        </div>
        <div class="category-list">
          <div
            class="category-item"
            :class="{ active: !favoritesOnly && selectedCategoryId === null }"
            @click="selectAll"
          >全部文档</div>
          <div
            class="category-item"
            :class="{ active: favoritesOnly }"
            @click="selectFavorites"
          >
            <span class="category-name">
              <el-icon :size="14"><StarFilled /></el-icon>
              我的收藏
            </span>
            <el-tag size="small" effect="plain">{{ favoriteIds.length }}</el-tag>
          </div>
          <!-- 三层分类树 -->
          <el-tree
            v-if="categoryTree.length"
            :data="categoryTree"
            node-key="id"
            :props="{ label: 'name', children: 'children' }"
            :expand-on-click-node="false"
            :current-node-key="selectedCategoryId ?? undefined"
            highlight-current
            default-expand-all
            class="category-tree"
            @node-click="(node: any) => selectCategory(node.id)"
          >
            <template #default="{ data }">
              <span class="tree-node">
                <span class="tree-name">{{ data.name }}</span>
                <el-tag size="small" effect="plain">{{ data.document_count }}</el-tag>
              </span>
            </template>
          </el-tree>
        </div>

        <!-- 最近浏览 -->
        <div class="recent-block">
          <div class="recent-title">
            <el-icon :size="15"><Clock /></el-icon>
            <span>最近浏览</span>
          </div>
          <div v-if="recentDocs.length === 0" class="recent-empty">暂无浏览记录</div>
          <div
            v-for="doc in recentDocs"
            :key="doc.id"
            class="recent-item"
            :title="doc.title"
            @click="openContent(doc)"
          >
            <span class="recent-name">{{ doc.title }}</span>
          </div>
        </div>
      </aside>

      <!-- 文档列表 -->
      <div class="doc-list-area">
        <!-- 列表工具栏 -->
        <div class="list-toolbar">
          <span class="result-count">共 <b>{{ total }}</b> 篇文档</span>
          <div class="toolbar-right">
            <el-select v-model="fileType" size="small" class="toolbar-select" @change="onFilterChange">
              <el-option label="全部类型" value="" />
              <el-option label="PDF" value="pdf" />
              <el-option label="Word" value="docx" />
              <el-option label="Excel" value="xlsx" />
              <el-option label="Markdown" value="md" />
              <el-option label="纯文本" value="txt" />
            </el-select>
            <el-select v-model="sort" size="small" class="toolbar-select" @change="onSortChange">
              <el-option label="最新发布" value="latest" />
              <el-option label="最早发布" value="oldest" />
              <el-option label="标题排序" value="title" />
              <el-option label="大小降序" value="size_desc" />
              <el-option label="大小升序" value="size_asc" />
            </el-select>
            <el-select v-model="pageSize" size="small" class="toolbar-select" @change="onPageSizeChange">
              <el-option v-for="size in pageSizeOptions" :key="size" :label="size + ' 条/页'" :value="size" />
            </el-select>
          </div>
        </div>

        <el-card v-loading="loading" class="doc-card">
          <div v-if="documents.length === 0 && !loading" class="empty-state">
            <el-empty :description="emptyText" />
          </div>

          <div v-for="doc in documents" :key="doc.id" class="doc-item" @click="openContent(doc)">
            <div class="doc-icon">
              <el-icon :size="28" :color="fileIconColor(doc.file_type)">
                <component :is="fileIcon(doc.file_type)" />
              </el-icon>
            </div>
            <div class="doc-info">
              <div class="doc-title">
                <template v-for="(part, idx) in highlightParts(doc.title)" :key="idx">
                  <span v-if="part.hit" class="kw-hit">{{ part.text }}</span>
                  <span v-else>{{ part.text }}</span>
                </template>
              </div>
              <!-- 正文命中片段 -->
              <div v-if="doc.match_snippet" class="doc-snippet">
                <el-tag size="small" type="success" effect="plain">正文命中</el-tag>
                <span class="snippet-text">
                  <template v-for="(part, idx) in highlightParts(doc.match_snippet)" :key="idx">
                    <span v-if="part.hit" class="kw-hit">{{ part.text }}</span>
                    <span v-else>{{ part.text }}</span>
                  </template>
                </span>
              </div>
              <div class="doc-meta">
                <el-tag size="small" effect="plain" v-if="doc.category_name">{{ doc.category_name }}</el-tag>
                <span class="meta-item">{{ (doc.file_type || '').toUpperCase() }}</span>
                <span class="meta-item">{{ formatFileSize(doc.file_size) }}</span>
                <span class="meta-item">{{ doc.version }}</span>
                <span class="meta-item">{{ doc.publish_date || formatDate(doc.created_at) }}</span>
                <el-tag
                  v-for="tag in (doc.tags || []).slice(0, 3)"
                  :key="tag"
                  size="small"
                  type="info"
                  effect="plain"
                >{{ tag }}</el-tag>
              </div>
            </div>
            <button
              class="fav-btn"
              :class="{ active: isFavorite(doc.id) }"
              :title="isFavorite(doc.id) ? '取消收藏' : '收藏'"
              @click.stop="toggleFavorite(doc)"
            >
              <el-icon :size="16">
                <StarFilled v-if="isFavorite(doc.id)" />
                <Star v-else />
              </el-icon>
            </button>
            <div class="doc-arrow">
              <el-icon :size="16"><ArrowRight /></el-icon>
            </div>
          </div>
        </el-card>

        <!-- 分页 -->
        <div class="pagination-wrap" v-if="total > 0">
          <el-pagination
            v-model:current-page="page"
            :page-size="pageSize"
            :total="total"
            :page-sizes="pageSizeOptions"
            layout="prev, pager, next, jumper"
            @current-change="loadDocuments"
          />
        </div>
      </div>
    </div>

    <!-- 教师投稿弹窗 -->
    <el-dialog v-model="contributeVisible" title="投稿教学资料" width="560px" destroy-on-close>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="投稿将进入待审核，管理员审核通过后才会被问答检索引用"
        style="margin-bottom: 16px"
      />
      <el-form label-width="90px">
        <el-form-item label="文件" required>
          <el-upload
            :auto-upload="false"
            :limit="1"
            :on-change="handleContributeFileChange"
            :on-remove="() => (contributeFile = null)"
            accept=".pdf,.docx,.xlsx,.md,.txt"
            drag
            style="width: 100%"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽文件到此处，或 <em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">支持 PDF / DOCX / XLSX / MD / TXT</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="contributeForm.title" placeholder="默认使用文件名" />
        </el-form-item>
        <el-form-item label="所属课程">
          <el-tree-select
            v-model="contributeForm.category_id"
            :data="categoryTree"
            :props="{ label: 'name', children: 'children' }"
            node-key="id"
            value-key="id"
            clearable
            placeholder="选择课程/章节分类"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="contributeForm.tags" placeholder="多个标签用逗号分隔" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="contributeVisible = false">取消</el-button>
        <el-button type="primary" :loading="contributing" @click="submitContribute">提交审核</el-button>
      </template>
    </el-dialog>

    <!-- 我的投稿弹窗 -->
    <el-dialog v-model="myContribVisible" title="我的投稿" width="780px" destroy-on-close>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="这里可以查看审核进度与驳回意见；被驳回的文档修改后可重新提交审核"
        style="margin-bottom: 14px"
      />
      <el-table
        v-loading="myContribLoading"
        :data="myContribs"
        size="small"
        empty-text="还没有投稿记录"
        style="width: 100%"
      >
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="审核状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="reviewMeta(row.review_status).type">
              {{ reviewMeta(row.review_status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="审核意见" min-width="180">
          <template #default="{ row }">
            <span v-if="row.review_comment" class="review-comment">{{ row.review_comment }}</span>
            <span v-else class="no-action">—</span>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="120">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.review_status === 0 || row.review_status === 3"
              link
              type="primary"
              @click="resubmitDoc(row)"
            >重新提交</el-button>
            <span v-else class="no-action">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 文档内容弹窗 -->
    <el-dialog
      v-model="contentVisible"
      :title="contentDoc?.title || '文档内容'"
      width="80%"
      top="5vh"
      destroy-on-close
      class="content-dialog"
    >
      <div v-loading="contentLoading" class="content-body">
        <!-- 元数据 -->
        <div v-if="contentDoc" class="detail-meta">
          <el-tag size="small" effect="plain">{{ contentDoc.category_name || '未分类' }}</el-tag>
          <el-tag size="small" :type="levelTagType(contentDoc.security_level)" effect="plain">
            {{ levelText(contentDoc.security_level) }}
          </el-tag>
          <span class="meta-item">{{ (contentDoc.file_type || '').toUpperCase() }}</span>
          <span class="meta-item">{{ formatFileSize(contentDoc.file_size) }}</span>
          <span class="meta-item">{{ contentDoc.version }}</span>
          <span class="meta-item">{{ contentDoc.chunk_count || 0 }} 个分块</span>
          <span class="meta-item">{{ contentDoc.publish_date || formatDate(contentDoc.created_at) }}</span>
        </div>

        <div v-if="contentError" class="content-error">
          <el-result icon="error" :title="contentError">
            <template #extra>
              <el-button
                v-if="contentDoc?.source_url"
                type="primary"
                :icon="Link"
                @click="openSource"
              >查看原文</el-button>
            </template>
          </el-result>
        </div>
        <div v-else-if="contentText" class="content-text" v-html="renderedContent"></div>
        <el-empty v-else-if="!contentLoading" description="暂无内容" />
      </div>
      <template #footer>
        <el-button
          v-if="contentDoc"
          :icon="isFavorite(contentDoc.id) ? StarFilled : Star"
          @click="toggleFavorite(contentDoc)"
        >{{ isFavorite(contentDoc.id) ? '取消收藏' : '收藏' }}</el-button>
        <el-button v-if="contentDoc?.source_url" :icon="Link" @click="openSource">查看原文</el-button>
        <el-button type="primary" @click="contentVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import {
  Search, FolderOpened, ArrowRight, Document, Grid, Tickets,
    Files, Coin, Link, Star, StarFilled, Clock, Upload, UploadFilled,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import client from '@/api/client'
import { useAuthStore } from '@/store/auth'
import MarkdownIt from 'markdown-it'

// 安全：关闭 html 渲染——爬取入库的网页内容可能含原始 HTML（含脚本），
// 开启 html:true 会被直接注入执行（存储型 XSS）；原始 HTML 标签将按纯文本展示
const md = new MarkdownIt({ breaks: true })

const loading = ref(false)
const keyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const sort = ref('latest')
const fileType = ref('')
const pageSizeOptions = [10, 20, 50, 100]
const documents = ref<any[]>([])
const categories = ref<any[]>([])
const categoryTree = ref<any[]>([])
const selectedCategoryId = ref<number | null>(null)

// 收藏与最近浏览（浏览器本地存储，按用户设备保留）
const FAVORITES_KEY = 'kb_favorites'
const RECENT_KEY = 'kb_recent_docs'
const MAX_RECENT = 8
const favoritesOnly = ref(false)
const favoriteIds = ref<number[]>(loadStorage(FAVORITES_KEY, []))
const recentDocs = ref<any[]>(loadStorage(RECENT_KEY, []))

// 概览统计
const statsLoading = ref(false)
const stats = ref({
  total_documents: 0,
  total_chunks: 0,
  total_size_bytes: 0,
})

// 文档内容弹窗
const contentVisible = ref(false)
const contentLoading = ref(false)
const contentDoc = ref<any>(null)
const contentText = ref('')
const contentError = ref('')

// ==================== 教师投稿 ====================
const authStore = useAuthStore()
const canContribute = computed(() => {
  const role = authStore.user?.role_name || ''
  return ['老师', '知识库管理员', '超级管理员'].includes(role)
})

const contributeVisible = ref(false)
const contributing = ref(false)
const contributeFile = ref<File | null>(null)
const contributeForm = reactive({
  title: '',
  category_id: undefined as number | undefined,
  tags: '',
})

function handleContributeFileChange(file: any) {
  contributeFile.value = file.raw as File
}

async function submitContribute() {
  if (!contributeFile.value) {
    ElMessage.warning('请先选择要投稿的文件')
    return
  }
  const fd = new FormData()
  fd.append('file', contributeFile.value)
  if (contributeForm.title) fd.append('title', contributeForm.title)
  if (contributeForm.category_id) fd.append('category_id', String(contributeForm.category_id))
  const tagList = contributeForm.tags.split(/[,，]/).map((t) => t.trim()).filter(Boolean)
  if (tagList.length) fd.append('tags', JSON.stringify(tagList))
  fd.append('review_mode', 'pending')

  contributing.value = true
  try {
    await client.post('/documents/upload', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success('投稿成功，管理员审核通过后即可被问答引用；进度可在「我的投稿」查看')
    contributeVisible.value = false
    contributeFile.value = null
    contributeForm.title = ''
    contributeForm.category_id = undefined
    contributeForm.tags = ''
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '投稿失败')
  } finally {
    contributing.value = false
  }
}

// ==================== 我的投稿 ====================
const myContribVisible = ref(false)
const myContribLoading = ref(false)
const myContribs = ref<any[]>([])

function reviewMeta(status: number): { label: string; type: 'success' | 'info' | 'warning' | 'danger' } {
  const map: Record<number, { label: string; type: 'success' | 'info' | 'warning' | 'danger' }> = {
    0: { label: '草稿', type: 'info' },
    1: { label: '待审核', type: 'warning' },
    2: { label: '已通过', type: 'success' },
    3: { label: '已驳回', type: 'danger' },
  }
  return map[status] || { label: '未知', type: 'info' }
}

async function loadMyContributions() {
  myContribLoading.value = true
  try {
    const res = await client.get('/documents/mine', { params: { page: 1, page_size: 50 } })
    myContribs.value = res.data.data?.items || []
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '加载投稿记录失败')
  } finally {
    myContribLoading.value = false
  }
}

function openMyContributions() {
  myContribVisible.value = true
  loadMyContributions()
}

async function resubmitDoc(row: any) {
  try {
    const res = await client.post(`/documents/${row.id}/resubmit-review`)
    if (res.data.code !== 0) {
      ElMessage.warning(res.data.message || '重新提交失败')
      return
    }
    ElMessage.success('已重新提交审核')
    await loadMyContributions()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '重新提交失败')
  }
}

const emptyText = computed(() => {
  if (favoritesOnly.value) return '还没有收藏任何文档，点击文档右侧星标即可收藏'
  return keyword.value
    ? `未找到与“${keyword.value}”相关的文档`
    : '暂无文档'
})

// Markdown 渲染
const renderedContent = computed(() => {
  if (!contentText.value) return ''
  try {
    return md.render(contentText.value)
  } catch {
    return contentText.value.replace(/\n/g, '<br>')
  }
})

let searchTimer: ReturnType<typeof setTimeout> | null = null

function fileIcon(type: string) {
  return type === 'pdf' ? 'Document' : type === 'xlsx' ? 'Grid' : 'Tickets'
}

function fileIconColor(type: string) {
  return type === 'pdf' ? '#E74C3C' : type === 'xlsx' ? '#27AE60' : '#3498DB'
}

function formatFileSize(bytes: number) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatDate(value: string | undefined) {
  if (!value) return ''
  return value.slice(0, 10)
}

function levelText(level: number) {
  return { 1: '公开', 2: '内部', 3: '机密', 4: '绝密' }[level] || '内部'
}

function levelTagType(level: number): 'success' | 'info' | 'warning' | 'danger' {
  return level <= 1 ? 'success' : level === 2 ? 'info' : level === 3 ? 'warning' : 'danger'
}

/** 关键词高亮：返回分段数组，前端按段渲染，避免直接拼接 HTML */
function highlightParts(title: string) {
  const kw = keyword.value.trim()
  if (!kw) return [{ text: title, hit: false }]
  const lowerTitle = title.toLowerCase()
  const lowerKw = kw.toLowerCase()
  const idx = lowerTitle.indexOf(lowerKw)
  if (idx < 0) return [{ text: title, hit: false }]
  return [
    { text: title.slice(0, idx), hit: false },
    { text: title.slice(idx, idx + kw.length), hit: true },
    { text: title.slice(idx + kw.length), hit: false },
  ].filter((part) => part.text)
}

async function loadStats() {
  statsLoading.value = true
  try {
    const res = await client.get('/documents/stats/overview')
    const data = res.data.data || {}
    stats.value = {
      total_documents: data.total_documents || 0,
      total_chunks: data.total_chunks || 0,
      total_size_bytes: data.total_size_bytes || 0,
    }
  } catch { /* ignore */ } finally { statsLoading.value = false }
}

async function loadCategories() {
  try {
    const res = await client.get('/documents/categories/tree')
    const tree = res.data.data || []
    categoryTree.value = tree
    categories.value = flattenCategories(tree)
  } catch { /* ignore */ }
}

function flattenCategories(tree: any[], result: any[] = []): any[] {
  for (const node of tree) {
    result.push(node)
    if (node.children?.length) flattenCategories(node.children, result)
  }
  return result
}

async function loadDocuments() {
  // 收藏夹为空时无需请求，直接展示空状态
  if (favoritesOnly.value && favoriteIds.value.length === 0) {
    documents.value = []
    total.value = 0
    loading.value = false
    return
  }
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value, sort: sort.value }
    if (keyword.value) params.keyword = keyword.value
    if (selectedCategoryId.value) params.category_id = selectedCategoryId.value
    if (fileType.value) params.file_type = fileType.value
    if (favoritesOnly.value) params.ids = favoriteIds.value.join(',')
    const res = await client.get('/documents', { params })
    const data = res.data.data
    documents.value = data.items || []
    total.value = data.total || 0
  } catch { /* ignore */ } finally { loading.value = false }
}

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    loadDocuments()
  }, 300)
}

function onSortChange() {
  page.value = 1
  loadDocuments()
}

function onFilterChange() {
  page.value = 1
  loadDocuments()
}

function onPageSizeChange() {
  page.value = 1
  loadDocuments()
}

// ==================== 收藏 / 最近浏览 ====================

function loadStorage<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function saveStorage(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch { /* 存储不可用时忽略 */ }
}

function isFavorite(id: number) {
  return favoriteIds.value.includes(id)
}

function toggleFavorite(doc: any) {
  favoriteIds.value = isFavorite(doc.id)
    ? favoriteIds.value.filter((id) => id !== doc.id)
    : [doc.id, ...favoriteIds.value]
  saveStorage(FAVORITES_KEY, favoriteIds.value)
  if (favoritesOnly.value) {
    page.value = 1
    loadDocuments()
  }
}

function recordRecent(doc: any) {
  recentDocs.value = [{ ...doc }, ...recentDocs.value.filter((item) => item.id !== doc.id)]
    .slice(0, MAX_RECENT)
  saveStorage(RECENT_KEY, recentDocs.value)
}

function selectAll() {
  favoritesOnly.value = false
  selectedCategoryId.value = null
  page.value = 1
  loadDocuments()
}

function selectCategory(id: number) {
  favoritesOnly.value = false
  selectedCategoryId.value = id
  page.value = 1
  loadDocuments()
}

function selectFavorites() {
  favoritesOnly.value = true
  selectedCategoryId.value = null
  page.value = 1
  loadDocuments()
}

async function openContent(doc: any) {
  recordRecent(doc)
  contentDoc.value = doc
  contentVisible.value = true
  contentLoading.value = true
  contentText.value = ''
  contentError.value = ''
  try {
    const res = await client.get(`/documents/${doc.id}/content`)
    contentText.value = res.data.data?.content || ''
  } catch (e: any) {
    contentError.value = e.response?.data?.message || '加载失败'
  } finally {
    contentLoading.value = false
  }
}

function openSource() {
  const url = contentDoc.value?.source_url
  if (url) window.open(url, '_blank', 'noopener')
}

onMounted(() => {
  loadStats()
  loadCategories()
  loadDocuments()
})
</script>

<style scoped>
.review-comment {
  color: var(--color-danger, #b91c1c);
  line-height: 1.5;
}
.no-action {
  color: var(--color-text-secondary);
}
.browse-page { padding: 24px 32px; height: 100%; display: flex; flex-direction: column; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { font-size: 22px; font-weight: 700; color: var(--color-text-primary); margin: 0; white-space: nowrap; }
.search-input { width: 320px; }
.header-actions { display: flex; align-items: center; gap: 10px; }

/* 概览看板 */
.overview-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px; }
.overview-card {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 18px; background: var(--color-bg-card);
  border: 1px solid var(--color-border); border-radius: 10px;
}
.overview-icon {
  width: 42px; height: 42px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  background: var(--color-primary-light); color: var(--color-primary);
}
.overview-value { font-size: 22px; font-weight: 700; color: var(--color-text-primary); line-height: 1.2; }
.overview-label { font-size: 12px; color: var(--color-text-secondary); margin-top: 2px; }

.browse-body { display: flex; gap: 20px; flex: 1; min-height: 0; }

/* 分类侧边栏 */
.category-sidebar {
  width: 200px;
  flex-shrink: 0;
  background: var(--color-bg-card);
  border-radius: 8px;
  border: 1px solid var(--color-border);
  overflow-y: auto;
}
.category-title {
  display: flex; align-items: center; gap: 8px;
  padding: 14px 16px; font-weight: 600; font-size: 14px;
  color: var(--color-text-primary); border-bottom: 1px solid var(--color-border);
}
.category-list { padding: 8px; }
.category-item {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  padding: 8px 12px; border-radius: 6px; cursor: pointer;
  font-size: 13px; color: var(--color-text-secondary); transition: all 0.15s;
}
.category-item:hover { background: var(--color-primary-light); color: var(--color-primary); }
.category-item.active { background: var(--color-primary-light); color: var(--color-primary); font-weight: 600; }
.category-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 分类树 */
.category-tree { background: transparent; color: var(--color-text-secondary); }
.category-tree :deep(.el-tree-node__content) {
  height: 32px;
  border-radius: 6px;
}
.category-tree :deep(.el-tree-node__content:hover) { background: var(--color-primary-light); }
.category-tree :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: 600;
}
.tree-node { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex: 1; min-width: 0; padding-right: 6px; }
.tree-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 最近浏览 */
.recent-block { border-top: 1px solid var(--color-border); padding: 10px 8px 14px; }
.recent-title {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 12px 8px; font-size: 13px; font-weight: 600;
  color: var(--color-text-primary);
}
.recent-empty { padding: 4px 12px; font-size: 12px; color: var(--color-text-placeholder); }
.recent-item { padding: 6px 12px; border-radius: 6px; cursor: pointer; }
.recent-item:hover { background: var(--color-primary-light); }
.recent-name {
  display: block; font-size: 12px; color: var(--color-text-secondary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* 文档列表 */
.doc-list-area { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.list-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0 4px 12px;
}
.result-count { font-size: 13px; color: var(--color-text-secondary); }
.result-count b { color: var(--color-primary); font-weight: 700; }
.toolbar-right { display: flex; gap: 10px; flex-wrap: wrap; }
.toolbar-select { width: 120px; }

.doc-card { flex: 1; overflow-y: auto; }
.empty-state { padding: 40px 0; }

.doc-item {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 16px; border-bottom: 1px solid var(--color-border);
  cursor: pointer; transition: background 0.15s;
}
.doc-item:last-child { border-bottom: none; }
.doc-item:hover { background: var(--color-primary-light); }

.doc-icon { flex-shrink: 0; }
.doc-info { flex: 1; min-width: 0; }
.doc-title { font-size: 15px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 6px; }
.kw-hit { background: #FEF08A; color: #854D0E; border-radius: 3px; padding: 0 1px; }
html.dark .kw-hit { background: rgba(250, 204, 21, 0.28); color: #FDE68A; }
.doc-snippet {
  display: flex; align-items: flex-start; gap: 8px;
  margin: 6px 0 8px; padding: 6px 10px;
  background: var(--color-bg-hover); border-radius: 6px;
}
.snippet-text {
  font-size: 12px; line-height: 1.6; color: var(--color-text-secondary);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.doc-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.meta-item { font-size: 12px; color: var(--color-text-placeholder); }
.fav-btn {
  flex-shrink: 0; display: flex; align-items: center;
  border: none; background: transparent; cursor: pointer;
  padding: 6px; border-radius: 6px; color: var(--color-text-placeholder);
  transition: all 0.15s;
}
.fav-btn:hover { background: var(--color-bg-hover); color: #F59E0B; }
.fav-btn.active { color: #F59E0B; }
.doc-arrow { flex-shrink: 0; color: var(--color-text-placeholder); }

.pagination-wrap { display: flex; justify-content: center; padding: 16px 0; }

/* 内容弹窗 */
.content-body { max-height: 70vh; overflow-y: auto; }
.detail-meta {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 0 20px 12px; border-bottom: 1px solid var(--color-border);
}
.content-error { padding: 20px 0; }
.content-text {
  padding: 16px 20px; line-height: 1.8; font-size: 14px; color: var(--color-text-primary);
}
.content-text :deep(h1), .content-text :deep(h2), .content-text :deep(h3) {
  margin-top: 24px; margin-bottom: 12px; font-weight: 700;
}
.content-text :deep(p) { margin: 8px 0; }
.content-text :deep(table) { border-collapse: collapse; width: 100%; margin: 12px 0; }
.content-text :deep(th), .content-text :deep(td) { border: 1px solid var(--color-border); padding: 8px 12px; text-align: left; }
.content-text :deep(th) { background: var(--color-primary-light); font-weight: 600; }
.content-text :deep(code) {
  background: var(--color-bg-hover); color: var(--color-text-primary);
  padding: 1px 5px; border-radius: 4px; font-size: 12.5px;
  font-family: 'JetBrains Mono', Consolas, Monaco, 'Courier New', monospace;
}
.content-text :deep(pre) {
  background: #1e1e2e; color: #cdd6f4; padding: 16px; border-radius: 8px;
  overflow-x: auto; line-height: 1.65; margin: 12px 0;
}
/* 代码块内的 code 不能再用行内代码的浅色底，否则浅字压浅底，看起来只剩一条条色块 */
.content-text :deep(pre code) {
  background: transparent; color: inherit; padding: 0; border-radius: 0;
  font-family: 'JetBrains Mono', Consolas, Monaco, 'Courier New', monospace;
  font-size: 13px; white-space: pre;
}
.content-text :deep(img) { max-width: 100%; height: auto; border-radius: 6px; margin: 6px 0; }
</style>

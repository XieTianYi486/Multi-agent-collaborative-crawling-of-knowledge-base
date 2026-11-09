<template>
  <div class="admin-page">
    <div class="page-header">
      <h2>
        <el-icon :size="22" style="margin-right: 8px; vertical-align: -3px"><Refresh /></el-icon>
        补采闭环
      </h2>
      <div class="header-actions">
        <el-button @click="loadAll" :loading="loading">刷新</el-button>
      </div>
    </div>

    <!-- 未命中问题候选 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span>未命中问题候选</span>
          <span class="section-hint">
            最近 {{ days }} 天 · 拒答或点踩问题聚合 · 已入队的不再展示
          </span>
        </div>
      </template>
      <el-table :data="candidates" stripe v-loading="loading" empty-text="暂无未命中问题，知识库覆盖良好">
        <el-table-column prop="question" label="用户问题" min-width="280" show-overflow-tooltip />
        <el-table-column label="出现次数" width="100" align="center">
          <template #default="{ row }">
            <span class="count-badge">{{ row.count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="问题类型" width="160">
          <template #default="{ row }">
            <el-tag
              v-for="r in row.reasons"
              :key="r"
              :type="r === 'negative_feedback' ? 'danger' : 'warning'"
              size="small"
              effect="plain"
              style="margin-right: 4px"
            >
              {{ REASON_LABELS[r] || r }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近出现" width="170" align="center">
          <template #default="{ row }">{{ formatTime(row.last_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="openCreate(row)">转为补采</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 补采需求队列 -->
    <el-card style="margin-top: 16px">
      <template #header>
        <div class="card-header">
          <span>补采需求队列</span>
          <div class="queue-filter">
            <el-input
              v-model="keyword"
              placeholder="搜索问题"
              size="small"
              clearable
              style="width: 200px"
              @keyup.enter="loadRequests"
              @clear="loadRequests"
            />
            <el-radio-group v-model="statusFilter" size="small" @change="loadRequests">
              <el-radio-button :value="-1">全部 {{ stats.total || 0 }}</el-radio-button>
              <el-radio-button :value="0">待处理 {{ stats['0'] || 0 }}</el-radio-button>
              <el-radio-button :value="1">已触发 {{ stats['1'] || 0 }}</el-radio-button>
              <el-radio-button :value="2">已完成 {{ stats['2'] || 0 }}</el-radio-button>
              <el-radio-button :value="3">已忽略 {{ stats['3'] || 0 }}</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </template>

      <el-table :data="requests" stripe v-loading="loading" empty-text="暂无补采需求">
        <el-table-column prop="question" label="补采问题" min-width="260" show-overflow-tooltip />
        <el-table-column label="来源" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.reason === 'negative_feedback' ? 'danger' : 'warning'" size="small" effect="plain">
              {{ REASON_LABELS[row.reason] || row.reason }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" effect="plain">
              {{ row.status_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.note">{{ row.note }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="creator_name" label="提交人" width="110" />
        <el-table-column label="提交时间" width="170" align="center">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              :disabled="row.status === 2 || row.status === 3 || running"
              :loading="row.status === 1 && running"
              @click="runCrawl(row)"
            >
              触发采集
            </el-button>
            <el-button size="small" :disabled="row.status === 2" @click="markDone(row)">完成</el-button>
            <el-button size="small" type="danger" plain :disabled="row.status === 3" @click="ignore(row)">忽略</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadRequests"
          @size-change="onPageSizeChange"
        />
      </div>
    </el-card>

    <!-- 新建补采需求 -->
    <el-dialog v-model="dialogVisible" title="转为补采需求" width="560px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="问题">
          <el-input v-model="form.question" type="textarea" :rows="2" disabled />
        </el-form-item>
        <el-form-item label="来源">
          <el-tag :type="form.reason === 'negative_feedback' ? 'danger' : 'warning'" size="small" effect="plain">
            {{ REASON_LABELS[form.reason] || form.reason }}
          </el-tag>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="3" placeholder="补充线索，例如期望的来源站点、教材名称等" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">提交需求</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import {
  collectionApi,
  REASON_LABELS,
  type CollectionCandidate,
  type CollectionRequestRow,
} from '@/api/collection'

const loading = ref(false)
const submitting = ref(false)
const running = ref(false)

const days = 30
const candidates = ref<CollectionCandidate[]>([])
const requests = ref<CollectionRequestRow[]>([])
const stats = ref<Record<string, number>>({})

const statusFilter = ref(-1)
const keyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const dialogVisible = ref(false)
const form = ref({ question: '', reason: 'missed', note: '' })

function formatTime(t: string | null): string {
  if (!t) return '—'
  const d = new Date(t.endsWith('Z') || t.includes('+') ? t : t + 'Z')
  return d.toLocaleString('zh-CN', { hour12: false })
}

function statusTagType(status: number): string {
  if (status === 2) return 'success'
  if (status === 1) return 'warning'
  if (status === 3) return 'info'
  return 'primary'
}

async function loadCandidates() {
  try {
    const res = await collectionApi.candidates({ days, limit: 20 })
    candidates.value = res.data.data?.items || []
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '加载未命中问题失败')
  }
}

async function loadRequests() {
  try {
    const res = await collectionApi.listRequests({
      page: page.value,
      page_size: pageSize.value,
      status: statusFilter.value >= 0 ? statusFilter.value : undefined,
      keyword: keyword.value || undefined,
    })
    const data = res.data.data || {}
    requests.value = data.items || []
    total.value = data.total || 0
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '加载补采需求失败')
  }
}

async function loadStats() {
  try {
    const res = await collectionApi.stats()
    stats.value = res.data.data || {}
  } catch {
    stats.value = {}
  }
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadCandidates(), loadRequests(), loadStats()])
  } finally {
    loading.value = false
  }
}

function onPageSizeChange() {
  page.value = 1
  loadRequests()
}

function openCreate(row: CollectionCandidate) {
  form.value = {
    question: row.question,
    reason: row.negative_count > 0 ? 'negative_feedback' : 'missed',
    note: '',
  }
  dialogVisible.value = true
}

async function submitCreate() {
  if (!form.value.question) return
  submitting.value = true
  try {
    const res = await collectionApi.createRequest({
      question: form.value.question,
      reason: form.value.reason,
      note: form.value.note || undefined,
    })
    const data = res.data.data
    ElMessage.success(data?.duplicated ? '该问题已在补采队列中' : '补采需求已提交')
    dialogVisible.value = false
    await loadAll()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '提交补采需求失败')
  } finally {
    submitting.value = false
  }
}

async function runCrawl(row: CollectionRequestRow) {
  running.value = true
  try {
    const res = await collectionApi.runRequest(row.id)
    if (res.data.data?.started) {
      ElMessage.success('已触发采集流水线，可在数据中心查看进度')
    } else {
      ElMessage.warning(res.data.message || '流水线已在运行中，请稍后再试')
    }
    await loadAll()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '触发采集失败')
  } finally {
    running.value = false
  }
}

async function markDone(row: CollectionRequestRow) {
  try {
    await collectionApi.updateRequest(row.id, { status: 2 })
    ElMessage.success('需求已标记完成')
    await loadAll()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '更新需求失败')
  }
}

async function ignore(row: CollectionRequestRow) {
  try {
    await ElMessageBox.confirm('确认忽略该补采需求？', '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await collectionApi.updateRequest(row.id, { status: 3 })
    ElMessage.success('需求已忽略')
    await loadAll()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '更新需求失败')
  }
}

onMounted(loadAll)
</script>

<style scoped>
.admin-page { padding: 24px 32px; max-width: 1280px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
  display: flex;
  align-items: center;
}
.header-actions { display: flex; gap: 8px; }

.card-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.section-hint { font-size: 12px; color: var(--color-text-secondary); font-weight: 400; }
.queue-filter { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.count-badge {
  display: inline-block;
  min-width: 24px;
  padding: 0 8px;
  height: 22px;
  line-height: 22px;
  border-radius: 11px;
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: 600;
  font-size: 13px;
}

.text-muted { color: var(--color-text-secondary); }

.pager { display: flex; justify-content: flex-end; margin-top: 12px; }

@media (max-width: 768px) {
  .admin-page { padding: 16px; }
  .page-header { flex-direction: column; align-items: flex-start; gap: 12px; }
  .queue-filter { width: 100%; }
}
</style>

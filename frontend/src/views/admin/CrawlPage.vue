<template>
  <div class="admin-page">
    <div class="page-header">
      <h2>
        <el-icon :size="22" style="margin-right: 8px; vertical-align: -3px"><Download /></el-icon>
        数据中心
        <el-tag v-if="showCrawlStats && run.running" type="warning" size="small" effect="plain" style="margin-left: 10px">
          流水线运行中…
        </el-tag>
      </h2>
      <div class="header-actions">
        <el-button @click="loadAll" :loading="loading">刷新</el-button>
        <el-button v-if="showCrawlStats" type="primary" :disabled="run.running" :loading="starting" @click="startRun">
          <el-icon style="margin-right: 4px"><Download /></el-icon>
          {{ run.running ? '采集中…' : '立即采集' }}
        </el-button>
      </div>
    </div>

    <!-- 知识库总览（主库口径：含批量导入 / 人工上传文档） -->
    <div class="stats-section-title">
      <span>知识库总览</span>
      <span class="section-hint">知识库主库口径 · 含批量导入与人工上传文档</span>
    </div>
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon icon-indigo"><el-icon :size="22"><Files /></el-icon></div>
          <div class="stat-info">
            <div class="stat-label">知识库文档</div>
            <div class="stat-value">{{ formatNum(kb.documents) }}</div>
            <div class="stat-sub">已发布 {{ formatNum(kb.published) }} 篇 · 今日新增 {{ kb.documents_today }} 篇</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon icon-violet"><el-icon :size="22"><Grid /></el-icon></div>
          <div class="stat-info">
            <div class="stat-label">文档分块</div>
            <div class="stat-value">{{ formatNum(kb.chunks) }}</div>
            <div class="stat-sub">语义分块，已全部向量化入库</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon icon-sky"><el-icon :size="22"><Position /></el-icon></div>
          <div class="stat-info">
            <div class="stat-label">可溯源文档</div>
            <div class="stat-value">{{ formatNum(kb.with_source_url) }}</div>
            <div class="stat-sub">含原文链接，占 {{ sourceRatio }}%</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon icon-emerald"><el-icon :size="22"><Collection /></el-icon></div>
          <div class="stat-info">
            <div class="stat-label">分类节点</div>
            <div class="stat-value">{{ formatNum(kb.categories) }}</div>
            <div class="stat-sub">按教学方向三层组织</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 导入批次明细（主库口径） -->
    <el-card style="margin-top: 16px">
      <template #header>
        <div class="card-header">
          <span>导入批次明细</span>
          <span class="run-meta">按导入日期聚合 · 共 {{ formatNum(kb.documents) }} 篇</span>
        </div>
      </template>
      <el-table :data="kb.batches || []" stripe empty-text="暂无导入记录">
        <el-table-column label="导入日期" width="180">
          <template #default="{ row }">{{ row.date }}</template>
        </el-table-column>
        <el-table-column label="导入文档" width="160">
          <template #default="{ row }">
            <span style="font-weight: 600; color: var(--color-primary)">{{ formatNum(row.count) }}</span>
            <span class="text-muted" style="margin-left: 4px">篇</span>
          </template>
        </el-table-column>
        <el-table-column label="占比">
          <template #default="{ row }">{{ batchRatio(row.count) }}%</template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 爬取流水线统计（子库口径：仅本机采集子系统经手的文档） -->
    <div v-if="showCrawlStats" class="stats-section-title" style="margin-top: 20px">
      <span>爬取流水线</span>
      <span class="section-hint">采集子系统口径 · 仅统计本机流水线经手的文档</span>
    </div>
    <el-row v-if="showCrawlStats" :gutter="16" class="stats-row">
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon icon-indigo"><el-icon :size="22"><Document /></el-icon></div>
          <div class="stat-info">
            <div class="stat-label">累计采集文档</div>
            <div class="stat-value">{{ stats.documents }}</div>
            <div class="stat-sub">今日新增 {{ stats.documents_today }} 篇</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon icon-cyan"><el-icon :size="22"><CircleCheck /></el-icon></div>
          <div class="stat-info">
            <div class="stat-label">已同步知识库</div>
            <div class="stat-value">{{ stats.kb_synced }}</div>
            <div class="stat-sub">成功 {{ stats.kb_sync_ok }} · 失败 {{ stats.kb_sync_failed }}</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon icon-amber"><el-icon :size="22"><Money /></el-icon></div>
          <div class="stat-info">
            <div class="stat-label">今日 LLM 成本</div>
            <div class="stat-value">¥{{ stats.llm_cost_today?.toFixed(4) }}</div>
            <div class="stat-sub">预算 ¥{{ usage.budget_daily }} · 调用 {{ stats.llm_calls }} 次</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-icon icon-emerald"><el-icon :size="22"><Link /></el-icon></div>
          <div class="stat-info">
            <div class="stat-label">启用站点</div>
            <div class="stat-value">{{ stats.sites_enabled }}</div>
            <div class="stat-sub">共配置 {{ stats.sites }} 个站点</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 流水线运行状态 -->
    <el-card v-if="showCrawlStats" style="margin-top: 16px">
      <template #header>
        <div class="card-header">
          <span>多智能体流水线</span>
          <span v-if="run.finished_at" class="run-meta">
            {{ run.trigger === 'manual' ? '手动触发' : '定时任务' }} ·
            {{ formatTime(run.finished_at) }} 结束
          </span>
        </div>
      </template>
      <div class="pipeline-steps">
        <div v-for="stepName in CRAWL_STEP_ORDER" :key="stepName" class="pipeline-step">
          <el-tag :type="stepTagType(stepName)" size="small" effect="plain">
            {{ CRAWL_STEP_LABELS[stepName] }}
          </el-tag>
          <span class="step-status">{{ stepStatusText(stepName) }}</span>
          <span v-if="stepDuration(stepName)" class="step-duration">{{ stepDuration(stepName) }}</span>
        </div>
      </div>
      <el-alert v-if="run.error" :title="run.error" type="error" :closable="false" show-icon style="margin-top: 12px" />
    </el-card>

    <!-- 站点状态 -->
    <el-card v-if="showCrawlStats" style="margin-top: 16px">
      <template #header><span>站点采集状态</span></template>
      <el-table :data="sites" stripe v-loading="loading" empty-text="暂无站点档案">
        <el-table-column prop="code" label="站点代码" min-width="170" />
        <el-table-column prop="name" label="站点名称" min-width="170" />
        <el-table-column label="风险级" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="riskTagType(row.risk_level)" size="small" effect="plain">
              {{ riskText(row.risk_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="doc_count" label="采集文档" width="90" align="center" />
        <el-table-column label="最近采集" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="lastStatusType(row.last_status)" size="small" effect="plain">
              {{ lastStatusText(row.last_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上次时间" width="170" align="center">
          <template #default="{ row }">{{ formatTime(row.last_time) }}</template>
        </el-table-column>
        <el-table-column label="熔断至" width="170" align="center">
          <template #default="{ row }">
            <span v-if="row.breaker_until">{{ formatTime(row.breaker_until) }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-row v-if="showCrawlStats" :gutter="16" class="grid-row" style="margin-top: 16px">
      <!-- 最近入库记录 -->
      <el-col :xs="24" :md="14">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>最近入库同步</span>
              <el-radio-group v-model="syncStatus" size="small" @change="loadSyncs">
                <el-radio-button value="">全部</el-radio-button>
                <el-radio-button value="ok">成功</el-radio-button>
                <el-radio-button value="failed">失败</el-radio-button>
                <el-radio-button value="skipped">跳过</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <el-table :data="syncs" stripe v-loading="loading" empty-text="暂无同步记录" max-height="420">
            <el-table-column prop="title" label="文档标题" min-width="180" show-overflow-tooltip />
            <el-table-column label="同步状态" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="syncTagType(row.status)" size="small" effect="plain">
                  {{ syncText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="知识库状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.kb_doc" :type="row.kb_doc.status === 1 ? 'success' : 'info'" size="small" effect="plain">
                  {{ row.kb_doc.status === 1 ? '可检索' : '未发布' }}
                </el-tag>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="时间" width="160" align="center">
              <template #default="{ row }">{{ formatTime(row.synced_at) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- LLM 成本账本 -->
      <el-col :xs="24" :md="10">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>LLM 成本账本</span>
              <span class="run-meta">累计 ¥{{ usage.total_cost?.toFixed(4) }}</span>
            </div>
          </template>
          <el-table :data="usage.tasks" stripe v-loading="loading" empty-text="暂无 LLM 调用" max-height="420">
            <el-table-column label="任务" width="110">
              <template #default="{ row }">{{ taskLabel(row.task) }}</template>
            </el-table-column>
            <el-table-column prop="model" label="模型" width="110" />
            <el-table-column prop="calls" label="次数" width="60" align="center" />
            <el-table-column label="成本" align="right">
              <template #default="{ row }">¥{{ row.cost?.toFixed(5) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import client from '@/api/client'
import {
  crawlApi,
  CRAWL_STEP_LABELS,
  CRAWL_STEP_ORDER,
  type CrawlRunState,
  type CrawlSiteStatus,
  type CrawlSyncRow,
  type CrawlUsageTask,
} from '@/api/crawl'

const loading = ref(false)
const starting = ref(false)
const syncStatus = ref('')

// 爬取流水线板块开关（截图期间可临时置 false，只展示知识库导入数据）
const showCrawlStats = ref(true)

const stats = ref<any>({})
const kb = ref<any>({})
const sites = ref<CrawlSiteStatus[]>([])
const syncs = ref<CrawlSyncRow[]>([])
const usage = ref<any>({ tasks: [] as CrawlUsageTask[] })
const run = ref<CrawlRunState>({
  running: false, trigger: '', started_at: null, finished_at: null, error: '', step_results: {},
})

let pollTimer: ReturnType<typeof setInterval> | null = null

function formatTime(v: string | null): string {
  if (!v) return '—'
  return new Date(v).toLocaleString('zh-CN', { hour12: false })
}

function formatNum(v: number | undefined): string {
  return (v ?? 0).toLocaleString('zh-CN')
}

const sourceRatio = computed(() => {
  const total = kb.value.documents || 0
  if (!total) return '0.0'
  return (((kb.value.with_source_url || 0) / total) * 100).toFixed(1)
})

function batchRatio(count: number): string {
  const total = kb.value.documents || 0
  if (!total) return '0.0'
  return ((count / total) * 100).toFixed(1)
}

async function loadAll() {
  loading.value = true
  try {
    const [overviewRes, sitesRes, syncsRes, usageRes] = await Promise.all([
      crawlApi.overview(),
      crawlApi.sites(),
      crawlApi.syncs({ limit: 20, status: syncStatus.value }),
      crawlApi.usage(),
    ])
    stats.value = overviewRes.data.data?.stats || {}
    kb.value = overviewRes.data.data?.kb || {}
    run.value = overviewRes.data.data?.run || run.value
    sites.value = sitesRes.data.data || []
    syncs.value = syncsRes.data.data || []
    usage.value = usageRes.data.data || { tasks: [] }
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '加载数据中心数据失败')
  } finally {
    loading.value = false
  }
}

async function loadSyncs() {
  try {
    const res = await crawlApi.syncs({ limit: 20, status: syncStatus.value })
    syncs.value = res.data.data || []
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '加载同步记录失败')
  }
}

async function startRun() {
  starting.value = true
  try {
    const res = await crawlApi.run()
    if (res.data.data?.started) {
      ElMessage.success('流水线已启动：采集 → 打标 → 审核 → 摘要 → 入库')
      startPolling()
      await loadAll()
    } else {
      ElMessage.warning('流水线已在运行中，请稍后再试')
    }
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '启动流水线失败')
  } finally {
    starting.value = false
  }
}

async function pollRunStatus() {
  try {
    const res = await crawlApi.runStatus()
    const prevRunning = run.value.running
    run.value = res.data.data || run.value
    if (prevRunning && !run.value.running) {
      ElMessage.success('流水线执行完成')
      stopPolling()
      await loadAll()
    }
  } catch {
    // 轮询失败静默，下轮重试
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(pollRunStatus, 5000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// ---- 展示辅助 ----

function stepTagType(stepName: string): string {
  const r = run.value.step_results?.[stepName]
  if (!r) return run.value.running ? 'warning' : 'info'
  if (r.ok) return 'success'
  if (r.skipped) return 'info'
  return 'danger'
}

function stepStatusText(stepName: string): string {
  const r = run.value.step_results?.[stepName]
  if (!r) return run.value.running ? '等待/运行中' : '未开始'
  if (r.ok) return '完成'
  if (r.skipped) return '跳过（预算/LLM 不可用）'
  return '失败'
}

function stepDuration(stepName: string): string {
  const r = run.value.step_results?.[stepName]
  if (!r || !r.duration_ms) return ''
  const s = (r.duration_ms / 1000).toFixed(1)
  return `${s}s`
}

function riskTagType(level: string): string {
  if (level === 'low') return 'success'
  if (level === 'medium') return 'warning'
  return 'danger'
}

function riskText(level: string): string {
  if (level === 'low') return '低'
  if (level === 'medium') return '中'
  return '高'
}

function lastStatusType(status: string): string {
  if (status === 'ok') return 'success'
  if (status === 'breaker') return 'danger'
  if (status === 'no_adapter' || status === 'high_risk_skipped') return 'info'
  if (status === '未采集') return 'info'
  return 'danger'
}

function lastStatusText(status: string): string {
  const map: Record<string, string> = {
    ok: '成功', failed: '失败', breaker: '熔断中',
    no_adapter: '无适配器', high_risk_skipped: '高风险跳过', '未采集': '未采集',
  }
  return map[status] || status
}

function syncTagType(status: string): string {
  if (status === 'ok') return 'success'
  if (status === 'skipped') return 'info'
  return 'danger'
}

function syncText(status: string): string {
  if (status === 'ok') return '成功'
  if (status === 'skipped') return '跳过'
  return '失败'
}

function taskLabel(task: string): string {
  const map: Record<string, string> = {
    tagger: '打标', reviewer: '审核', summarizer: '摘要',
  }
  return map[task] || task
}

onMounted(async () => {
  await loadAll()
  if (run.value.running) startPolling()
})

onUnmounted(stopPolling)
</script>

<style scoped>
.admin-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  display: flex;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.stats-section-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.stats-section-title::before {
  content: '';
  align-self: center;
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: var(--color-primary);
}

.section-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--color-text-secondary);
}

.stats-row {
  margin-bottom: 0;
  row-gap: 16px;
}

.grid-row {
  row-gap: 16px;
}

.stat-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 18px 16px;
  display: flex;
  align-items: center;
  gap: 14px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: transform .2s, box-shadow .2s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
}

.stat-icon {
  width: 46px;
  height: 46px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

.icon-indigo { background: linear-gradient(135deg, #4F46E5, #818CF8); }
.icon-cyan { background: linear-gradient(135deg, #0891B2, #22D3EE); }
.icon-amber { background: linear-gradient(135deg, #D97706, #FBBF24); }
.icon-emerald { background: linear-gradient(135deg, #059669, #34D399); }
.icon-violet { background: linear-gradient(135deg, #7C3AED, #A78BFA); }
.icon-sky { background: linear-gradient(135deg, #0284C7, #38BDF8); }

.stat-info { min-width: 0; }

.stat-label {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  margin: 4px 0;
  color: var(--color-text-primary);
  line-height: 1.2;
}

.stat-sub {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.run-meta {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.pipeline-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
}

.pipeline-step {
  display: flex;
  align-items: center;
  gap: 8px;
}

.step-status {
  font-size: 13px;
  color: var(--color-text-body);
}

.step-duration {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.text-muted {
  color: var(--color-text-secondary);
  font-size: 12px;
}
</style>

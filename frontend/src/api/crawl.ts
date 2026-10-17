// ============================================================
// 爬取中心 API 封装
// 多智能体爬取流水线：站点状态 / 总览 / 入库同步记录 / LLM 成本 / 手动触发
// ============================================================

import client from './client'

export interface CrawlStepResult {
  ok: boolean
  skipped: boolean
  error: string
  duration_ms: number
}

export interface CrawlRunState {
  running: boolean
  trigger: string
  started_at: string | null
  finished_at: string | null
  error: string
  step_results: Record<string, CrawlStepResult>
}

export interface CrawlStats {
  sites: number
  sites_enabled: number
  documents: number
  documents_today: number
  kb_synced: number
  kb_sync_ok: number
  kb_sync_failed: number
  llm_cost_today: number
  llm_calls: number
}

export interface CrawlSiteStatus {
  code: string
  name: string
  enabled: boolean
  risk_level: string
  doc_count: number
  last_status: string
  last_time: string | null
  breaker_until: string | null
}

export interface CrawlSyncRow {
  doc_id: number
  kb_doc_id: number | null
  title: string
  status: string
  error: string
  synced_at: string | null
  kb_doc: { title: string; status: number; review_status: number } | null
}

export interface CrawlUsageTask {
  task: string
  model: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost: number
}

export const CRAWL_STEP_LABELS: Record<string, string> = {
  crawl: '采集',
  tagger: '打标（分类）',
  review: '审核',
  summarize: '摘要',
  kb_sync: '入库知识库',
}

export const CRAWL_STEP_ORDER = ['crawl', 'tagger', 'review', 'summarize', 'kb_sync']

export const crawlApi = {
  overview: () => client.get('/crawler/overview'),
  sites: () => client.get('/crawler/sites'),
  syncs: (params: { limit?: number; status?: string }) =>
    client.get('/crawler/syncs', { params }),
  usage: () => client.get('/crawler/usage'),
  run: () => client.post('/crawler/run'),
  runStatus: () => client.get('/crawler/run'),
}

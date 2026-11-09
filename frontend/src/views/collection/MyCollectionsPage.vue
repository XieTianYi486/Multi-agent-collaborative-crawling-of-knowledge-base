<template>
  <div class="collection-page">
    <div class="page-header">
      <div class="header-left">
        <el-icon class="header-icon" :size="22"><Refresh /></el-icon>
        <h2>我的补采</h2>
        <el-tag v-if="total" effect="plain">{{ total }} 条</el-tag>
      </div>
      <el-button type="primary" :icon="ChatDotRound" @click="goChat">去提问</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="补采需求由管理员统一处理，处理进度与结果会实时显示在这里"
      class="hint"
    />

    <el-tabs v-model="activeStatus" @tab-change="loadRequests">
      <el-tab-pane label="全部" name="" />
      <el-tab-pane label="待处理" name="0" />
      <el-tab-pane label="已触发采集" name="1" />
      <el-tab-pane label="已完成" name="2" />
      <el-tab-pane label="已忽略" name="3" />
    </el-tabs>

    <el-empty v-if="!loading && requests.length === 0" description="还没有提交过补采需求，问答中没有找到答案时可以点击“提交补采”" />

    <div v-else v-loading="loading" class="request-list">
      <el-card v-for="r in requests" :key="r.id" class="request-item" shadow="never">
        <div class="request-main">
          <div class="request-title-row">
            <span class="request-no">#{{ r.id }}</span>
            <span class="request-question">{{ r.question }}</span>
          </div>
          <div class="request-note" v-if="r.note">{{ r.note }}</div>
          <div class="request-footer">
            <el-tag size="small" :type="statusMeta(r.status).type">{{ statusMeta(r.status).label }}</el-tag>
            <el-tag size="small" type="info" effect="plain">{{ reasonLabel(r.reason) }}</el-tag>
            <span class="request-time">{{ formatTime(r.created_at) }} 提交</span>
            <span v-if="r.updated_at && r.updated_at !== r.created_at" class="request-time">
              最近更新 {{ formatTime(r.updated_at) }}
            </span>
          </div>
        </div>
      </el-card>
    </div>

    <div v-if="total > pageSize" class="pagination">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadRequests"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, ChatDotRound } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { collectionApi, COLLECTION_STATUS, REASON_LABELS } from '@/api/collection'
import type { CollectionRequestRow } from '@/api/collection'

const router = useRouter()
const loading = ref(false)
const requests = ref<CollectionRequestRow[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const activeStatus = ref('')

function statusMeta(status: number): { label: string; type: 'success' | 'warning' | 'info' | 'primary' } {
  const label = COLLECTION_STATUS[status] || '未知'
  const type = status === 2 ? 'success' : status === 1 ? 'primary' : status === 0 ? 'warning' : 'info'
  return { label, type }
}

function reasonLabel(reason: string) {
  return REASON_LABELS[reason] || reason
}

function formatTime(value: string | null) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

async function loadRequests() {
  loading.value = true
  try {
    const res = await collectionApi.myRequests({
      page: page.value,
      page_size: pageSize.value,
      status: activeStatus.value === '' ? undefined : Number(activeStatus.value),
    })
    const data = res.data.data
    requests.value = data.items || []
    total.value = data.total || 0
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '加载补采记录失败')
  } finally {
    loading.value = false
  }
}

function goChat() {
  router.push('/chat')
}

onMounted(loadRequests)
</script>

<style scoped>
.collection-page {
  padding: 24px;
  min-height: 100%;
  background: var(--color-bg-page);
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.header-left h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.header-icon {
  color: var(--color-primary);
}
.hint {
  margin-bottom: 12px;
}
.request-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.request-item {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card, 12px);
  background: var(--color-bg-card);
}
.request-title-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.request-no {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.request-question {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.5;
  word-break: break-word;
}
.request-note {
  margin-top: 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
  background: var(--color-bg-page);
  border-radius: 8px;
  padding: 8px 10px;
}
.request-footer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
}
.request-time {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>

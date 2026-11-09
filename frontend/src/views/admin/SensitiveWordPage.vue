<template>
  <div class="page">
    <div class="page-header">
      <div class="header-left">
        <el-icon class="header-icon" :size="22"><Lock /></el-icon>
        <h2>敏感词管理</h2>
        <el-tag effect="plain">{{ total }} 条</el-tag>
      </div>
      <div class="header-right">
        <el-select v-model="enabledFilter" placeholder="启用状态" clearable style="width: 130px" @change="() => { page = 1; load() }">
          <el-option label="启用" :value="1" />
          <el-option label="停用" :value="0" />
        </el-select>
        <el-input v-model="keyword" placeholder="搜索敏感词" clearable style="width: 200px" :prefix-icon="Search" @change="() => { page = 1; load() }" />
        <el-button type="primary" :icon="Plus" @click="openCreate">新增敏感词</el-button>
      </div>
    </div>

    <!-- 命中说明 -->
    <el-alert
      class="tip-alert"
      type="info"
      :closable="false"
      show-icon
      title="脱敏规则：登录问答时，AI 回答中命中敏感词将被自动替换，并写入审计日志。级别 3（高危）命中将记录为拦截。"
    />

    <!-- 敏感词命中测试 -->
    <el-card class="tester-card" shadow="never">
      <div class="tester-title">
        <el-icon :size="16"><Search /></el-icon>
        <span>敏感词命中测试</span>
        <el-tag size="small" type="info" effect="plain">{{ enabledWords.length }} 个启用词</el-tag>
      </div>
      <el-input
        v-model="testText"
        type="textarea"
        :rows="4"
        maxlength="500"
        show-word-limit
        placeholder="输入一段文本，实时检测命中的敏感词并高亮显示..."
      />
      <div class="tester-result">
        <template v-if="testText">
          <div class="tester-legend">
            <span>命中 <b>{{ testHits.length }}</b> 处</span>
            <el-tag
              v-for="(h, i) in uniqueHits"
              :key="i"
              size="small"
              :type="levelType(h.level)"
              effect="plain"
            >{{ h.word }} · {{ levelText(h.level) }}</el-tag>
            <span v-if="testHits.length === 0" class="tester-safe">未命中任何敏感词</span>
          </div>
          <div class="tester-preview">
            <template v-for="(seg, idx) in testSegments" :key="idx">
              <span v-if="seg.hit" class="hit-token" :class="'hit-level-' + seg.level">{{ seg.text }}</span>
              <span v-else>{{ seg.text }}</span>
            </template>
          </div>
        </template>
        <div v-else class="tester-placeholder">输入文本后，命中的敏感词将在此高亮显示</div>
      </div>
    </el-card>

    <el-card class="table-card" shadow="never">
      <el-table v-loading="loading" :data="list" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="word" label="敏感词" min-width="150">
          <template #default="{ row }">
            <span class="word-text">{{ row.word }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="110">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="level" label="级别" width="110">
          <template #default="{ row }">
            <el-tag :type="levelType(row.level)" size="small">{{ levelText(row.level) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="action" label="动作" width="100">
          <template #default="{ row }">
            {{ actionText(row.action) }}
          </template>
        </el-table-column>
        <el-table-column prop="replacement" label="替换串" width="90">
          <template #default="{ row }">
            <code>{{ row.replacement }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="状态" width="90">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled === 1" @change="(v: boolean) => toggle(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="load"
        />
      </div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑敏感词' : '新增敏感词'" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="敏感词" prop="word">
          <el-input v-model="form.word" placeholder="请输入敏感词" />
        </el-form-item>
        <el-form-item label="级别" prop="level">
          <el-select v-model="form.level" style="width: 100%">
            <el-option label="1 - 提示级（仅记录）" :value="1" />
            <el-option label="2 - 拦截级（脱敏替换）" :value="2" />
            <el-option label="3 - 高危级（记录拦截）" :value="3" />
          </el-select>
        </el-form-item>
        <el-form-item label="动作" prop="action">
          <el-select v-model="form.action" style="width: 100%">
            <el-option label="替换（mask）" value="mask" />
            <el-option label="拦截（block）" value="block" />
          </el-select>
        </el-form-item>
        <el-form-item label="替换串" prop="replacement">
          <el-input v-model="form.replacement" placeholder="默认 ***" />
        </el-form-item>
        <el-form-item label="分类" prop="category">
          <el-select v-model="form.category" style="width: 100%">
            <el-option label="通用 general" value="general" />
            <el-option label="安全 security" value="security" />
            <el-option label="个人隐私 pii" value="pii" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Lock } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { sensitiveApi } from '@/api/security'

const loading = ref(false)
const list = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const keyword = ref('')
const enabledFilter = ref<number | undefined>(undefined)

// ---- 敏感词命中测试 ----
const testText = ref('')
const allWords = ref<any[]>([])
const enabledWords = computed(() => allWords.value.filter((w) => w.enabled === 1 && w.word))

function escapeRegExp(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

const testSegments = computed(() => {
  const text = testText.value
  if (!text) return [] as Array<{ text: string; hit: boolean; level?: number; word?: string }>
  const words = enabledWords.value
  if (!words.length) return [{ text, hit: false }]
  const sorted = [...words].sort((a, b) => b.word.length - a.word.length)
  const re = new RegExp(sorted.map((w) => escapeRegExp(w.word)).join('|'), 'gi')
  const segs: Array<{ text: string; hit: boolean; level?: number; word?: string }> = []
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) segs.push({ text: text.slice(last, m.index), hit: false })
    const hitWord = sorted.find((w) => w.word.toLowerCase() === m![0].toLowerCase())
    segs.push({ text: m[0], hit: true, level: hitWord?.level, word: hitWord?.word || m[0] })
    last = m.index + m[0].length
    if (m[0].length === 0) re.lastIndex++
  }
  if (last < text.length) segs.push({ text: text.slice(last), hit: false })
  return segs
})

const testHits = computed(() => testSegments.value.filter((s) => s.hit))

const uniqueHits = computed(() => {
  const seen = new Set<string>()
  const out: Array<{ word: string; level: number }> = []
  for (const h of testHits.value) {
    const key = (h.word || '').toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push({ word: h.word || '', level: h.level ?? 1 })
  }
  return out
})

const dialogVisible = ref(false)
const editing = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({
  id: 0, word: '', level: 2, action: 'mask', replacement: '***', category: 'general',
})
const rules: FormRules = {
  word: [{ required: true, message: '请输入敏感词', trigger: 'blur' }],
}

function levelText(l: number) {
  return { 1: '提示', 2: '拦截', 3: '高危' }[l] || '拦截'
}
function levelType(l: number) {
  return { 1: 'info', 2: 'warning', 3: 'danger' }[l] as any
}
function actionText(a: string) {
  return a === 'block' ? '拦截' : '替换'
}

async function loadAllWords() {
  // 接口单页上限 100，分页拉全量用于命中测试
  try {
    const words: any[] = []
    let p = 1
    for (;;) {
      const res = await sensitiveApi.list({ page: p, page_size: 100 })
      const data = res.data.data
      const items = data?.items || []
      words.push(...items)
      if (items.length === 0 || words.length >= (data?.total || 0)) break
      p++
    }
    allWords.value = words
  } catch { /* ignore */ }
}

async function load() {
  loading.value = true
  try {
    const res = await sensitiveApi.list({
      page: page.value, page_size: pageSize,
      keyword: keyword.value || undefined,
      enabled: enabledFilter.value,
    })
    const data = res.data.data
    list.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = false
  Object.assign(form, { id: 0, word: '', level: 2, action: 'mask', replacement: '***', category: 'general' })
  dialogVisible.value = true
}
function openEdit(row: any) {
  editing.value = true
  Object.assign(form, {
    id: row.id, word: row.word, level: row.level,
    action: row.action, replacement: row.replacement, category: row.category,
  })
  dialogVisible.value = true
}

async function toggle(row: any, v: boolean) {
  try {
    await sensitiveApi.update(row.id, { enabled: v ? 1 : 0 })
    row.enabled = v ? 1 : 0
    loadAllWords()
    ElMessage.success('已更新')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '操作失败')
  }
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (editing.value) {
      await sensitiveApi.update(form.id, {
        word: form.word, level: form.level, action: form.action,
        replacement: form.replacement, category: form.category,
      })
    } else {
      await sensitiveApi.create({
        word: form.word, level: form.level, action: form.action,
        replacement: form.replacement, category: form.category,
      })
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    load()
    loadAllWords()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '保存失败')
  } finally {
    submitting.value = false
  }
}

async function onDelete(row: any) {
  await ElMessageBox.confirm(`确认删除敏感词「${row.word}」？`, '提示', { type: 'warning' })
  try {
    await sensitiveApi.remove(row.id)
    ElMessage.success('已删除')
    load()
    loadAllWords()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || '删除失败')
  }
}

onMounted(() => {
  load()
  loadAllWords()
})
</script>

<style scoped>
.page {
  padding: 20px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
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
}
.header-icon {
  color: var(--el-color-primary);
}
.header-right {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.tip-alert {
  margin-bottom: 14px;
  border-radius: 8px;
}

/* 命中测试 */
.tester-card {
  border-radius: 10px;
  margin-bottom: 14px;
}
.tester-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 12px;
}
.tester-title .el-icon { color: var(--el-color-primary); }
.tester-result {
  margin-top: 12px;
  border: 1px dashed var(--color-border);
  border-radius: 8px;
  padding: 12px 14px;
  min-height: 64px;
  background: var(--color-bg-page);
}
.tester-legend {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 10px;
}
.tester-legend b { color: var(--el-color-danger); }
.tester-safe { color: var(--el-color-success); }
.tester-preview {
  font-size: 14px;
  line-height: 1.8;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.hit-token {
  padding: 1px 4px;
  border-radius: 4px;
  font-weight: 600;
}
.hit-level-1 { background: rgba(144, 147, 153, .18); color: #909399; }
.hit-level-2 { background: rgba(230, 162, 60, .18); color: #b88230; }
.hit-level-3 { background: rgba(245, 108, 108, .18); color: #c45656; }
html.dark .hit-level-1 { background: rgba(144, 147, 153, .28); color: #C8CBD0; }
html.dark .hit-level-2 { color: #E6A23C; }
html.dark .hit-level-3 { color: #F56C6C; }
.tester-placeholder {
  font-size: 13px;
  color: var(--color-text-placeholder);
}
.table-card {
  border-radius: 10px;
}
.word-text {
  font-weight: 500;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
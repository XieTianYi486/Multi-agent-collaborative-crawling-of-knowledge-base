<template>
  <div class="video-page">
    <div class="page-header">
      <div class="header-text">
        <h2>视频专区</h2>
        <p>精选 B 站入门经典，先看视频建立直觉，再到知识库查细节</p>
      </div>
      <el-input
        v-model="keyword"
        placeholder="搜索视频、UP 主或关键词..."
        clearable
        :prefix-icon="Search"
        class="search-input"
        @input="onSearch"
      />
    </div>

    <!-- 学习路径提示 -->
    <div class="study-path">
      <div class="path-item">
        <span class="path-index">1</span>
        <span class="path-text">选方向</span>
      </div>
      <span class="path-arrow">→</span>
      <div class="path-item">
        <span class="path-index">2</span>
        <span class="path-text">看视频上手</span>
      </div>
      <span class="path-arrow">→</span>
      <div class="path-item">
        <span class="path-index">3</span>
        <span class="path-text">查文档 / 问 AI 助手</span>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="category-pills">
        <button
          type="button"
          class="pill"
          :class="{ active: category === '' }"
          @click="selectCategory('')"
        >全部</button>
        <button
          v-for="item in categories"
          :key="item.name"
          type="button"
          class="pill"
          :class="{ active: category === item.name }"
          @click="selectCategory(item.name)"
        >
          {{ item.name }}
          <span class="pill-count">{{ item.count }}</span>
        </button>
      </div>
      <el-select v-model="difficulty" class="difficulty-select" @change="selectDifficulty">
        <el-option label="全部难度" value="" />
        <el-option label="入门" value="入门" />
        <el-option label="进阶" value="进阶" />
      </el-select>
    </div>

    <!-- 视频卡片 -->
    <div v-loading="loading" class="video-grid-wrap">
      <div v-if="videos.length" class="video-grid">
        <div
          v-for="video in videos"
          :key="video.id"
          class="video-card"
          @click="openPlayer(video)"
        >
          <div class="cover-wrap">
            <img
              :src="video.cover_url"
              :alt="video.title"
              loading="lazy"
              referrerpolicy="no-referrer"
              class="cover"
            />
            <span class="play-mask">
              <el-icon :size="38"><VideoPlay /></el-icon>
            </span>
            <span class="duration-badge">{{ formatDuration(video.duration) }}</span>
            <span class="category-badge">{{ video.category }}</span>
          </div>
          <div class="card-body">
            <h3 class="video-title" :title="video.title">{{ video.title }}</h3>
            <div class="card-meta">
              <span class="up-name">
                <el-icon :size="14"><User /></el-icon>
                {{ video.up_name || 'B 站 UP 主' }}
              </span>
              <span v-if="video.play_count" class="play-count">
                <el-icon :size="14"><View /></el-icon>
                {{ formatPlayCount(video.play_count) }}
              </span>
            </div>
            <div class="card-tags">
              <el-tag size="small" :type="video.difficulty === '入门' ? 'success' : 'warning'" effect="plain">
                {{ video.difficulty }}
              </el-tag>
              <el-tag
                v-for="tag in video.tags.slice(0, 2)"
                :key="tag"
                size="small"
                effect="plain"
              >{{ tag }}</el-tag>
            </div>
          </div>
        </div>
      </div>

      <el-empty
        v-else-if="!loading"
        description="没有找到匹配的视频，换个关键词或分类试试"
      />
    </div>

    <div v-if="total > pageSize" class="pagination-wrap">
      <el-pagination
        background
        layout="prev, pager, next"
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        @current-change="onPageChange"
      />
    </div>

    <p class="copyright-note">
      视频版权归 B 站原作者所有，本站仅做教学索引，点击卡片可在站内播放，也可前往 B 站观看原视频。
    </p>

    <!-- 播放弹层 -->
    <el-dialog
      v-model="playerVisible"
      :title="activeVideo?.title || '视频播放'"
      width="min(920px, 94vw)"
      top="5vh"
      destroy-on-close
      class="video-player-dialog"
    >
      <div v-if="activeVideo" class="player-body">
        <div class="player-frame">
          <iframe
            :src="playerUrl(activeVideo.bvid)"
            scrolling="no"
            frameborder="0"
            allowfullscreen="true"
            referrerpolicy="no-referrer"
          ></iframe>
        </div>
        <div class="player-info">
          <div class="player-meta">
            <el-tag size="small" type="primary" effect="plain">{{ activeVideo.category }}</el-tag>
            <el-tag size="small" :type="activeVideo.difficulty === '入门' ? 'success' : 'warning'" effect="plain">
              {{ activeVideo.difficulty }}
            </el-tag>
            <span class="meta-item">
              <el-icon :size="14"><User /></el-icon>
              {{ activeVideo.up_name }}
            </span>
            <span class="meta-item">
              <el-icon :size="14"><Clock /></el-icon>
              {{ formatDuration(activeVideo.duration) }}
            </span>
          </div>
          <p class="player-desc">{{ activeVideo.description }}</p>
          <div class="player-tags">
            <el-tag v-for="tag in activeVideo.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag>
          </div>
        </div>
      </div>
      <template #footer>
        <a
          v-if="activeVideo"
          :href="activeVideo.url"
          target="_blank"
          rel="noopener noreferrer"
          class="bilibili-link"
        >
          <el-icon :size="16"><Link /></el-icon>
          在 B 站打开原视频
        </a>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { Search, VideoPlay, User, View, Clock, Link } from '@element-plus/icons-vue'
import { videoApi, type VideoItem } from '@/api/video'

const loading = ref(false)
const route = useRoute()
const keyword = ref('')
const category = ref('')
const difficulty = ref('')
const page = ref(1)
const pageSize = 12
const total = ref(0)
const videos = ref<VideoItem[]>([])
const categories = ref<{ name: string; count: number }[]>([])

const playerVisible = ref(false)
const activeVideo = ref<VideoItem | null>(null)

let searchTimer: ReturnType<typeof setTimeout> | null = null

function formatDuration(seconds: number): string {
  if (!seconds) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h} 小时 ${m} 分`
  if (m > 0) return `${m} 分 ${s} 秒`
  return `${s} 秒`
}

function formatPlayCount(n: number): string {
  if (!n) return ''
  if (n >= 10000) return `${(n / 10000).toFixed(1)} 万播放`
  return `${n} 播放`
}

function playerUrl(bvid: string): string {
  return `https://player.bilibili.com/player.html?bvid=${bvid}&page=1&high_quality=1&danmaku=0&autoplay=0`
}

async function loadCategories() {
  try {
    const res = await videoApi.categories()
    categories.value = res.data.data || []
  } catch {
    categories.value = []
  }
}

async function loadVideos() {
  loading.value = true
  try {
    const res = await videoApi.list({
      keyword: keyword.value || undefined,
      category: category.value || undefined,
      difficulty: difficulty.value || undefined,
      page: page.value,
      page_size: pageSize,
    })
    const data = res.data.data
    videos.value = data?.items || []
    total.value = data?.total || 0
  } catch {
    videos.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    loadVideos()
  }, 300)
}

function selectCategory(name: string) {
  category.value = name
  page.value = 1
  loadVideos()
}

function selectDifficulty() {
  page.value = 1
  loadVideos()
}

function onPageChange(p: number) {
  page.value = p
  loadVideos()
}

function openPlayer(video: VideoItem) {
  activeVideo.value = video
  playerVisible.value = true
}

onMounted(() => {
  // 支持从 AI 助手资料卡片跳转过来，带上 keyword 直接检索
  const queryKeyword = route.query.keyword
  if (typeof queryKeyword === 'string' && queryKeyword.trim()) {
    keyword.value = queryKeyword.trim()
  }
  loadCategories()
  loadVideos()
})

onUnmounted(() => {
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<style scoped>
.video-page {
  padding: 24px 32px 40px;
  max-width: 1240px;
}

/* 头部 */
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
}
.header-text h2 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary);
}
.header-text p {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}
.search-input { width: 300px; flex-shrink: 0; }

/* 学习路径 */
.study-path {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px 18px;
  margin-bottom: 18px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-bg-card);
}
.path-item { display: flex; align-items: center; gap: 8px; }
.path-index {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 700;
}
.path-text { font-size: 13px; color: var(--color-text-body); }
.path-arrow { color: var(--color-text-placeholder); font-size: 13px; }

/* 筛选 */
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.category-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}
.pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-bg-card);
  color: var(--color-text-secondary);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s;
}
.pill:hover { border-color: var(--color-primary); color: var(--color-primary); }
.pill.active {
  background: var(--color-primary-light);
  border-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: 600;
}
.pill-count { font-size: 11px; opacity: 0.75; }
.difficulty-select { width: 130px; flex-shrink: 0; }

/* 卡片网格 */
.video-grid-wrap { min-height: 180px; }
.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 18px;
}
.video-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-bg-card);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}
.video-card:hover {
  transform: translateY(-3px);
  border-color: var(--color-primary);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.12);
}
.cover-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 10;
  background: var(--color-bg-hover);
  overflow: hidden;
}
.cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.play-mask {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.32);
  color: #fff;
  opacity: 0;
  transition: opacity 0.18s ease;
}
.video-card:hover .play-mask { opacity: 1; }
.duration-badge {
  position: absolute;
  right: 8px;
  bottom: 8px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.75);
  color: #fff;
  font-size: 11px;
  line-height: 18px;
}
.category-badge {
  position: absolute;
  left: 8px;
  top: 8px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(79, 70, 229, 0.9);
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  font-weight: 600;
}
.card-body { padding: 12px 14px 14px; }
.video-title {
  margin: 0 0 8px;
  font-size: 14px;
  line-height: 1.45;
  font-weight: 600;
  color: var(--color-text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 40px;
}
.card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}
.up-name, .play-count {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-tags { display: flex; flex-wrap: wrap; gap: 6px; }

/* 分页 */
.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}
.copyright-note {
  margin: 24px 0 0;
  text-align: center;
  font-size: 12px;
  color: var(--color-text-placeholder);
  line-height: 1.6;
}

/* 播放弹层 */
.player-frame {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}
.player-frame iframe {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
}
.player-info { margin-top: 14px; }
.player-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}
.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.player-desc {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text-body);
}
.player-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.bilibili-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--color-primary);
  text-decoration: none;
}
.bilibili-link:hover { text-decoration: underline; }

/* 移动端 */
@media (max-width: 768px) {
  .video-page { padding: 16px 16px 32px; }
  .page-header { flex-direction: column; align-items: flex-start; gap: 12px; }
  .search-input { width: 100%; }
  .filter-bar { flex-direction: column; align-items: stretch; }
  .difficulty-select { width: 100%; }
  .video-grid { grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
  .video-title { font-size: 13px; min-height: 38px; }
  .card-tags { display: none; }
}
</style>

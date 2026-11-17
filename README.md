# 人工智能学院教学知识库

> AI Academy Teaching Knowledge Base

多智能体协作爬取的专业知识库 + 向量检索问答（垂直 RAG）。面向 **ESP32 / 树莓派 / 嵌入式开发** 等硬件技术，以及 **大模型应用 / AI Agent / 软件工程** 等方向的校内教学资料：由多智能体流水线自动爬取、打标、审核、摘要并入库，师生用自然语言提问即可获得**带来源引用的可溯源解答**——只做事实资料检索，不做大模型微调，杜绝 AI 幻觉。

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178c6.svg)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ 核心特性

### 🕷️ 多智能体协作爬取（爬取中心）
- **9 个数据源配置驱动**：乐鑫官方文档/官网、ESP32 论坛、ESP-IDF GitHub、电子发烧友、树莓派博客等，新增站点零代码（YAML 一条配置）
- **流水线 DAG**：采集 → 补采侦察/定向抓取 → 打标（LLM 分类映射分类树）→ 审核（LLM 拦截广告/垃圾/版权高风险）→ 摘要（LLM）→ 入库（待管理员审核）→ 补采需求自动闭环
- **三层去重**（URL / 内容哈希 / SimHash）+ 站点限速熔断，重复运行零副作用
- **每日 LLM 预算闸门**（默认 ¥2.0）+ 成本账本；LLM 不可用时规则管线照常运行
- **版权分级留痕**：全文 / 节选500字+原文链接 / 不入库 三级 + robots.txt 合规检查，仅校内教学使用
- Windows 任务计划每日定时 + 管理后台页面手动触发、流水线 8 步实时状态

### 📄 文档管理
- 多格式上传：PDF、Word、Excel、Markdown、纯文本，自动解析、分块、向量化、分类打标、版本管理
- **OCR（RapidOCR）**：扫描件 PDF 自动识别（逐页混合策略——有文本层走原路径，扫描页渲染成图识别）
- 文档密级与用户角色匹配的权限过滤

### 💬 智能问答（垂直 RAG）
- **混合检索**：向量检索 + BM25 关键词检索双路召回 + 归一化加权融合 + LLM 重排序
- **查询改写**：口语 → 技术术语（"板子点不亮" → "ESP32 启动失败 调试"）+ 多轮对话上下文理解
- **来源溯源**：答案引用 `[来源N]`，展示文档名称、章节、页码、**原文链接**
- **幻觉抑制与拒答**：严格基于入库资料回答，不用自身通用知识；无相关资料时主动拒答
- **流式输出**（SSE）

### 🎬 视频专区（B 站精选）
- 独立视频专区页面：按 ESP32 / ESP-IDF / Arduino / FreeRTOS / 树莓派 / 电子电路等嵌入式方向，以及大模型部署 / AI 应用开发 / AI Agent 等软件工程方向精选课程
- 预置 24 个已校验的 B 站视频，支持关键词搜索、分类与难度筛选
- 配套学习资料已入库知识库（`backend/uploads/materials_20261109/`），可在知识库检索、被 AI 问答引用
- **只存元数据**（BV 号 / 标题 / 封面 / UP 主 / 时长 / 播放量快照），播放通过 B 站官方 iframe，不转存视频文件
- 管理端支持新增、编辑、排序、上下架与删除；播放量与封面为手动维护快照，不会自动刷新

### 🔐 权限管控
- RBAC 角色（学生 / 老师 / 院系管理员 / 知识库管理员 / 超级管理员）
- JWT Token 认证 + bcrypt 密码哈希 + 算式验证码 + 连续失败锁定（5 次锁 15 分钟）
- 文档密级与用户角色自动匹配的检索过滤
- **生产安全自检**：弱密钥/弱口令/关验证码一律拒绝启动（`SKIP_SAFETY_CHECK` 仅限本地调试）

### 🤖 AI 助手（悬浮式智能助手）
- **任务型 Agent**：任务/个人数据/找资料类问题走工具链路（补采、工单、通知、班级学情、运营统计等 20+ 工具），普通概念问答自动走主 RAG
- **写操作两阶段确认**：模型只能"提议"，用户点确认卡后才执行（令牌数据库持久化、5 分钟过期、一次性消费、防重放）
- 多轮会话、历史记录、引用来源展开与跳转、Edge TTS 语音播报（分段合成，免费）
- 由 `COUNSELOR_ENABLED` 控制启用

### 📊 系统管理
- 问答日志审计（问题、答案、来源、耗时、用户反馈）
- 统计分析（问答量趋势、高频问题、未命中问题、满意度）
- 爬取中心（站点状态、流水线监控、LLM 成本、入库同步记录）
- 系统配置热更新

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     展示层 (Presentation)                │
│  Vue 3 前端（管理后台 + 对话界面）                        │
├─────────────────────────────────────────────────────────┤
│                     应用层 (Application)                 │
│  FastAPI 后端 ─ 用户认证 │ 文档管理 │ 问答服务 │ 日志审计 │
├─────────────────────────────────────────────────────────┤
│                     检索层 (Retrieval)                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐          │
│  │ 向量检索  │  │ BM25检索 │  │ 混合检索+融合 │          │
│  └──────────┘  └──────────┘  └──────────────┘          │
├─────────────────────────────────────────────────────────┤
│                     数据层 (Data)                        │
│  ChromaDB/FAISS │ SQLite/MySQL │ BM25 索引 │ 文件存储  │
└─────────────────────────────────────────────────────────┘
        ▲ 多智能体爬取子系统（独立批处理包，与主应用解耦）
        │ 采集 → 补采侦察/定向抓取 → 打标 → 审核 → 摘要 → 入库（待审核）
```

### 技术栈

**后端（backend/）**

| 类别 | 技术 | 说明 |
|------|------|------|
| 语言 | Python 3.9+ | 开发机实测 3.9.1 |
| Web 框架 | FastAPI | 高性能异步，自动生成 API 文档 |
| ORM | SQLAlchemy 2.0 | 同步模式，支持 SQLite / MySQL |
| 向量数据库 | ChromaDB（+FAISS 降级） | 本机 sqlite3 < 3.35 时自动走 FAISS 后端 |
| 关键词检索 | rank-bm25 + jieba | 轻量 BM25 中文全文检索 |
| LLM 接入 | 阿里云百炼 DashScope | 通义千问系列（OpenAI 兼容端点） |
| 嵌入模型 | text-embedding-v2 | 1536 维文本向量 |
| 文档解析 | PyMuPDF / python-docx / openpyxl | 多格式文档解析 |
| OCR | RapidOCR（onnxruntime） | 扫描件 PDF 逐页混合识别 |
| 爬虫采集 | httpx / feedparser / trafilatura / lxml | RSS / 列表 / Sitemap / GitHub / SPA 探活 |
| 认证 | JWT + Passlib + bcrypt | Token 认证与密码哈希 |
| 缓存 | cachetools + diskcache | 内存 + 磁盘双层缓存 |
| 日志 | Loguru | 结构化日志 |
| 测试 | PyTest + pytest-asyncio | 153 用例 |

**前端（frontend/）**

| 类别 | 技术 | 说明 |
|------|------|------|
| 框架 | Vue 3 + TypeScript | Composition API + `<script setup>` |
| UI 组件库 | Element Plus | 企业级 UI，含深色模式 |
| 状态管理 | Pinia | Vue 官方推荐 |
| 路由 | Vue Router 4 | 含权限守卫 |
| HTTP | Axios | 拦截器 + Token 管理 |
| Markdown | markdown-it + highlight.js | 答案渲染与代码高亮 |
| 构建 | Vite | 快速构建 |

---

## 📂 项目结构

```
├── backend/
│   ├── app/                      # FastAPI 主应用
│   │   ├── api/v1/               # auth / chat / documents / admin / crawler / videos / counselor / teaching 路由
│   │   ├── agent/                # 🤖 AI 助手任务型 Agent（registry 工具注册表 / tools 工具实现 / actions 写操作确认令牌）
│   │   ├── core/                 # 配置（Pydantic Settings）/ JWT / 异常
│   │   ├── models/               # SQLAlchemy 模型（用户/文档/分类/分块/会话/视频/agent_action 等）
│   │   ├── schemas/              # Pydantic 请求/响应模型
│   │   ├── services/             # 业务层（认证/问答/文档/视频种子/补采闭环）
│   │   ├── db/                   # SQLAlchemy 引擎 / 向量库客户端（ChromaDB+FAISS）/ 缓存
│   │   ├── rag/                  # 🔥 RAG 引擎
│   │   │   ├── chunker/          # 语义分块
│   │   │   ├── embeddings/       # DashScope 向量嵌入
│   │   │   ├── retrievers/       # 向量 / BM25 / 混合检索
│   │   │   ├── query_processor/  # 查询改写 / 意图识别
│   │   │   ├── llm/              # LLM 调用封装（超时保护）
│   │   │   ├── prompts/          # Prompt 模板（技术资料域防幻觉）
│   │   │   ├── reranker/         # LLM 重排序
│   │   │   ├── ocr.py            # RapidOCR 扫描件识别
│   │   │   └── ingestion.py      # 文档入库流水线
│   │   ├── tasks/                # 后台线程（文档处理）
│   │   └── main.py               # 应用入口（生产安全自检）
│   ├── crawler/                  # 🕷️ 多智能体爬取子系统（独立批处理包）
│   │   ├── config/               # sites.yaml 站点档案 + models.yaml 模型档位 + seeds.yaml 补采种子 + prompts/
│   │   ├── crawl/                # 采集层（adapters/ 适配器 + dedup 三层去重 + politeness 限速熔断 + robots.txt 合规 + targeted 定向抓取）
│   │   ├── process/              # HTML→Markdown / 归一化 / 元数据
│   │   ├── store/                # 爬虫侧独立 SQLite（分库）
│   │   ├── llm/                  # Provider + 成本账本 + 预算闸门
│   │   ├── agents/               # DAG 编排器 + tagger/reviewer/summarizer/scout 智能体
│   │   ├── sync/                 # 入库同步器 + 补采需求自动闭环（resolve）
│   │   ├── lock.py               # 跨进程流水线互斥锁
│   │   ├── pipeline.py           # 每日流水线 DAG（8 步）
│   │   └── data/                 # crawler.db + md/ raw/ 落盘文件
│   ├── data/                     # KB 主库 SQLite
│   ├── uploads/                  # 上传/采集文档文件
│   ├── eval/                     # 评测集与实验脚本（论文第 6 章，103 题：93 检索 + 10 拒答）
│   ├── tests/                    # 单元测试（153 用例，自动隔离测试库）
│   ├── requirements.txt
│   ├── run_crawl_daily.py        # 每日爬取流水线入口（Windows 任务计划调用）
│   ├── register_crawl_task.bat   # 注册每日爬取任务计划（每日 08:30）
│   ├── rebuild_indexes.py        # FAISS+BM25 索引全量重建
│   └── fix_vector_index.py       # 向量索引一致性修复（零批量成本，删幽灵/补缺失）
├── frontend/
│   └── src/
│       ├── api/                  # Axios 封装（含 SSE 流式）
│       ├── views/
│       │   ├── auth/             # 登录 / 注册 / 个人中心
│       │   ├── chat/             # 对话问答界面
│       │   ├── videos/           # 🎬 视频专区（B 站精选，iframe 播放）
│       │   ├── help/             # 📖 使用帮助页（公开，按角色说明功能入口）
│       │   └── admin/            # 管理后台 14 页（文档/审核/用户/统计/日志/爬取中心/视频管理等）
│       ├── components/           # 公共组件（含 counselor 悬浮 AI 助手 / AssistantMascot 形象）
│       ├── store/                # Pinia（auth / chat / theme）
│       └── router/               # 路由与权限守卫
├── deploy/                       # 🚀 部署脚本（deploy.sh 首装 / update.ps1+update.sh 增量更新 / 内容与学生同步）
├── .claude/                      # Claude Code 配置（agents / commands / settings）
├── start_all.bat                 # 一键启动前后端
├── start_backend.bat
├── start_frontend.bat
├── CLAUDE.md                     # AI 助手指南（产品文档）
└── README.md
```

> 

---

## 🚀 快速开始

### 环境要求

- **Python** 3.9+（开发机实测 3.9.1）
- **Node.js** 20.19+（Vite 8 要求；22.12+ 亦可）
- **阿里云百炼 API Key**（[免费申请](https://bailian.console.aliyun.com/)）

### 1. 克隆项目

```bash
git clone https://github.com/XieTianYi486/Multi-agent-collaborative-crawling-of-knowledge-base.git
cd Multi-agent-collaborative-crawling-of-knowledge-base
```

### 2. 后端启动

```bash
cd backend
pip install -r requirements.txt

# 配置环境变量（Windows 用 copy 命令）
cp .env.example .env
# 编辑 .env：填入 DASHSCOPE_API_KEY，并修改 ADMIN_PASSWORD / JWT_SECRET_KEY

# 启动后端服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

> ⚠️ **生产安全自检**：启动时会校验 JWT 密钥、管理员密码与验证码开关——命中弱口令/占位密钥/关闭验证码将**拒绝启动**。仅本地调试可设 `SKIP_SAFETY_CHECK=true` 豁免。

启动后访问：
- 📖 Swagger API 文档：http://localhost:8001/docs
- 💚 健康检查：http://localhost:8001/api/health

### 3. 前端启动

```bash
cd frontend
npm install
npm run dev          # 访问 http://localhost:5173
```

### 4. 一键启动（Windows）

```bash
start_all.bat
```

### 5. 运行爬取流水线（可选，手动/定时）

```bash
cd backend
python run_crawl_daily.py                    # 手动全量（采集→打标→审核→摘要→入库）
python run_crawl_daily.py --site esp32_forum_idf   # 只采指定站点（调试）
register_crawl_task.bat                      # 注册 Windows 任务计划（每日 08:30）
```

也可以在管理后台「爬取中心」页面一键触发并查看实时进度。

### 管理员账号

管理员账号由 `.env` 的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 决定（首次启动自动创建；库内已存在弱口令管理员时，部署脚本会自动轮换为新密码）。登录需完成算式验证码（`CAPTCHA_ENABLED=true`）。

---

## 📦 知识库数据获取（clone 后必读）

⚠️ **KB 主库与向量索引均不随仓库分发**（均为运行期二进制，出于体积与密钥安全考虑不入库）。clone 后需向项目管理员索取，否则问答检索无结果。

| 数据 | 位置 | 获取方式 |
|------|------|----------|
| KB 主库 | `backend/data/enterprise_rag.db` | 向项目管理员索取该文件，放入 `backend/data/` 目录 |
| 向量索引 | `backend/chroma_data/faiss_index/`（约 500MB） | 向管理员索取 FAISS 索引包，解压覆盖 `backend/chroma_data/` |
| BM25 索引 | `backend/bm25_index.pkl`（约 52MB） | 同上（缺它则关键词路召回为空，仅剩向量路） |
| 爬虫库 | `backend/crawler/data/db/crawler.db` | 随仓库分发，clone 即可用 |

**索引修复与重建工具**：

```bash
cd backend
python fix_vector_index.py   # 一致性修复：删除幽灵向量、补齐缺失分块（几乎零 API 成本，自动备份）
python rebuild_indexes.py    # 全量重建（重新嵌入全部分块，约 ¥5+ 与十几分钟，需 API Key）
# 完成后重启后端服务
```

**其他说明**：
- `backend/uploads/` 原文件未随仓库分发——个别本地上传文档的"原文下载"功能不可用，**不影响问答检索**（爬虫文档均自带原文链接）
- `.env`（API Key）属机密不随仓库分发，请自行配置或向管理员索取
- （历史遗留说明）旧版项目若沿用 ChromaDB 集合 `labor_law_docs`：执行 `python scripts/migrate_collection_name.py` 复制向量到 `teaching_kb_docs`；当前交付版本统一使用 FAISS（`VECTOR_BACKEND=faiss`），无需处理
- 问答、AI 助手、TTS 的限流为**进程内令牌桶**，多进程/多实例部署时需替换为 Redis 等共享存储才能全局生效

---

## 🚢 生产部署（Ubuntu 22.04 + Nginx + systemd）

首次部署：把发布包（含后端代码、前端 dist、数据文件）上传到服务器 `/tmp`，执行：

```bash
sudo bash deploy/deploy.sh /tmp/kb_deploy.tar.gz
```

脚本会自动完成：系统依赖（含 OCR/FAISS 运行库）→ 解压 → 创建 `kb` 运行用户 → **生成随机管理员密码并强制开启验证码**（同时轮换库内弱口令管理员）→ 固定 `VECTOR_BACKEND=faiss`（避免 Ubuntu 的 SQLite 版本自动改选 ChromaDB 导致检索为空）→ venv 装依赖 → systemd 服务 → Nginx 反代 → 启动并做 15 次健康检查（失败即报错退出）。管理员初始密码在部署日志末尾打印，请登录后立即修改。

增量更新（本地构建前端 → 打包 → 上传 → 服务端解压重启，带发布标记校验）：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\update.ps1     # 需先配置免密 SSH
powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -SkipBuild   # 仅后端改动时复用现有 dist
```

说明：
- 部署包**不含** `.env` / 数据库 / 学生名单——API Key 等机密在服务器上单独配置；
- 前端由 Nginx 直接托管 `frontend/dist`，`/api/` 与 `/static/` 反代到后端 8001；
- 后端固定单 worker（`--workers 1`），进程内限流在单实例下全局生效；多实例需替换为 Redis 等共享存储；
- 学生账号导入：`KB_APP_DIR=/opt/kb /opt/kb/backend/.venv/bin/python /opt/kb/deploy/sync_students.py`（读取 `deploy/students.json`，幂等）。

---

## 🕷️ 多智能体爬取子系统（backend/crawler/）

面向 ESP32/树莓派/嵌入式开发教学资料的自动采集入库（**仅校内教学使用**），与 FastAPI 主应用完全解耦的独立批处理包。

### 流水线拓扑

```
crawl（必需：遍历站点→适配器→三层去重→落盘）
  → discover（补采侦察，可选）→ targeted（定向抓取补采候选，可选）
  → tagger（LLM 可选：分类打标，映射 KB 分类树）
  → review（LLM 可选：拦截广告/垃圾/版权高风险）
  → summarize（LLM 可选：一句话摘要，仅存爬虫库）
  → kb_sync（必需：入库 KB 主库 → 置待审核）
  → resolve（补采需求自动闭环，可选）
```

- **智能体协作**：轻量 DAG 编排器，deps/指数退避重试/optional；LLM 步骤超每日预算（默认 ¥2.0，实测全量一轮仅 ¥0.067）或 API 不可用时自动跳过，规则管线照常运行
- **幂等**：URL 哈希 → 内容哈希 → SimHash 三层去重 + KB 侧 `source_hash` 闸门 + `kb_syncs` 唯一索引，重复运行零副作用
- **版权合规**：risk_level 分级（low 全文 / medium 节选500字+原文链接 / high 不入库），`source_authorizations` 留痕；论坛内容只存节选
- **入库**：爬取文档入库后置为待审核（`review_status=1`，`security_level=1`），由管理员在「知识审核」页人工确认后发布；写入 `source_url/source_hash` 溯源字段，回答中展示原文链接
- **新增站点零代码**：`crawler/config/sites.yaml` 加一条配置即可。已有适配器：`rss_feed` / `html_list`（list+tree）/ `sitemap` / `github`（search+repo）/ `espressif_docs`（SPA 探活）；探活失败/无权限的站点自动跳过（"爬不了就不爬"）

> 注意：爬虫进程与 uvicorn 共用向量库，建议低峰调度；首轮大批量回填建议临时停服。

---

## 📡 API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/login` | 用户登录（算式验证码） |
| POST | `/api/v1/auth/register` | 用户注册（学生/老师） |
| GET | `/api/v1/auth/captcha` | 获取算式验证码 |
| GET | `/api/v1/auth/me` | 当前用户信息 |
| POST | `/api/v1/chat/ask` | 问答（同步） |
| POST | `/api/v1/chat/stream` | 问答（SSE 流式） |
| GET | `/api/v1/chat/sessions` | 会话列表 |
| POST | `/api/v1/documents/upload` | 上传文档 |
| GET | `/api/v1/documents` | 文档列表 |
| GET | `/api/v1/documents/categories/tree` | 文档分类树 |
| POST | `/api/v1/admin/documents/{id}/review` | 文档审核（通过/驳回/提交/撤回） |
| GET | `/api/v1/videos` | 视频列表（已上架，支持关键词/分类/难度） |
| GET | `/api/v1/videos/categories` | 视频分类及数量 |
| GET | `/api/v1/admin/videos` | 视频管理列表（管理员） |
| POST/PUT/DELETE | `/api/v1/admin/videos[/{id}]` | 视频增改删/上下架（管理员） |
| POST | `/api/v1/counselor/stream` | AI 助手问答（SSE：token/tool_call/tool_result/confirmation_required/done） |
| POST | `/api/v1/counselor/actions/confirm` | **确认执行助手提议的写操作**（一次性令牌） |
| GET | `/api/v1/counselor/sessions` | AI 助手会话列表 |
| GET | `/api/v1/counselor/tts` | Edge TTS 语音合成（免费，限流） |
| GET | `/api/v1/teaching/my-classes` | 教师：我的班级 |
| GET | `/api/v1/teaching/my-classes/{id}/students` | 教师：班级学生学情（仅任教班级） |
| GET/POST | `/api/v1/tickets` | 我的工单 / 提交工单 |
| GET/POST | `/api/v1/collection/requests` | 补采需求查询 / 提交 |
| POST | `/api/v1/collection/requests/{id}/run` | 触发定向补采（管理员） |
| GET | `/api/v1/notifications` | 站内通知 |
| GET | `/api/v1/admin/stats/overview` | 统计概览（管理员） |
| GET | `/api/v1/admin/logs` | 问答日志审计（管理员） |
| GET | `/api/v1/admin/announcements/active` | 生效公告 |
| GET/POST | `/api/v1/admin/sensitive-words` | 敏感词管理（超级管理员） |
| GET/POST | `/api/v1/api-clients` | 开放 API 调用方管理（超级管理员，明文 Key 仅返回一次） |
| GET | `/api/v1/crawler/overview` | 爬取中心总览（管理员） |
| GET | `/api/v1/crawler/sites` | 站点采集状态 |
| GET | `/api/v1/crawler/syncs` | 入库同步记录 |
| GET | `/api/v1/crawler/usage` | LLM 成本账本 |
| POST | `/api/v1/crawler/run` | 手动触发爬取流水线（后台线程） |
| GET | `/api/v1/crawler/run` | 流水线运行状态 |
| POST | `/openapi/v1/search` | 开放 API 知识片段检索（API Key Bearer 鉴权） |
| POST | `/openapi/v1/ask` | 开放 API 知识库问答（完整 RAG） |
| GET | `/api/health` | 健康检查 |

> 完整 API 文档见 http://localhost:8001/docs
>
> 视频专区只保存 B 站元数据，播放走官方 iframe；播放量与封面是手动维护的快照，不会自动刷新。

---

## ⚙️ 关键配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 后端端口 | 8001 | FastAPI 服务端口 |
| 前端端口 | 5173 | Vite 开发服务器 |
| `VECTOR_BACKEND` | auto（**部署固定 faiss**） | 交付索引为 FAISS 格式；Linux 上 auto 会改选 ChromaDB 导致检索为空 |
| 向量维度 | 1536 | DashScope text-embedding-v2 |
| 分块大小 | 512 token | 语义分块 |
| 召回 Top-K | 20 → 50 → 5 | 向量/BM25 各召回 20，融合 50，重排后保留 5 |
| JWT 过期 | 24h | Token 有效期 |
| `SKIP_SAFETY_CHECK` | false | 生产安全自检豁免开关，**仅限本地调试**（弱密钥/弱口令/关验证码拒绝启动） |
| LLM 超时 | 读 120s / 连 10s | 防止挂起的 LLM 调用占死同步线程池 |
| 爬取预算闸门 | ¥2.0/日 | LLM 步骤超预算自动降级规则管线 |
| 定时爬取 | 每日 08:30 | Windows 任务计划 |
| 流水线互斥锁 | `crawler/data/run.lock` | 定时任务与手动触发跨进程互斥，3 小时过期自愈 |

---

## 🧪 评测与实验

毕业设计论文第 6 章实验数据由 `backend/eval/` 产出（103 道评测题：93 道检索题 + 10 道应拒答题，含检索指标 Recall/MRR/nDCG 与端到端 LLM judge），详见 [backend/eval/README.md](backend/eval/README.md)。

```bash
cd backend
python eval/run_eval.py --retrievers bm25    # L1 纯 BM25（零 API 调用，可离线）
python eval/run_eval.py --retrievers all     # L2 五配置对比（需 DASHSCOPE_API_KEY）
python eval/run_eval.py --mode e2e --sample-size 40   # L3 端到端（建议抽样控制配额）
```

---

## 🛠️ 开发指南

### 运行测试

```bash
cd backend
python -m pytest -v        # 153 用例全绿；测试自动隔离到 tests/.tmp_test/test.db
```

### Claude Code 命令

| 命令 | 说明 |
|------|------|
| `/run-app` | 启动前后端服务 |
| `/rebuild-app` | 重新构建前端 |
| `/unit-test` | 创建并执行单元测试 |
| `/comments-check` | 检查代码注释质量 |
| `/security-audit` | 安全审计 |
| `/git-save` | 提交代码（自动运行测试+质量检查） |

### 代码规范

- **Python**：type hints + docstring + Pydantic 数据校验
- **Vue**：`<script setup lang="ts">` + Composition API + Pinia
- **API**：统一响应格式 `{code, message, data}`；错误码 1xxx 参数 / 2xxx 认证 / 3xxx 业务 / 4xxx 系统
- **安全**：JWT 认证、密码 bcrypt 哈希、文档密级过滤、`.env` 不入库

---

## 📚 数据来源与版权声明

- 知识库资料全部来自爬虫子系统采集的公开技术站点（乐鑫官方文档/官网、ESP32 论坛、ESP-IDF GitHub、电子发烧友、树莓派博客等），入库时按版权分级处理并写入来源授权留痕（`source_authorizations` 表）
- 论坛等用户生成内容仅存节选并附原文链接；爬取行为遵循各站点限速策略与 robots 规范（robots.txt 5xx/网络异常时按拒绝处理，不绕过许可检查）
- 本系统**仅限校内教学使用**，不做任何商业分发；回答严格基于入库资料，末尾固定"以上内容基于知识库收录资料整理，仅供教学参考"声明
- 若版权方要求移除内容，可在管理后台删除对应文档（数据库与向量索引同步清理）

---

## License

MIT © 2026

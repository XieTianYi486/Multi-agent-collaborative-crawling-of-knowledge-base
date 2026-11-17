# 人工智能学院教学知识库 — 产品文档

## 项目基本信息

- **项目名称**：人工智能学院教学知识库
- **项目类型**：多智能体协作爬取的专业知识库 + 向量检索问答（垂直 RAG）
- **目标用户**：院校师生、知识库管理员、超级管理员
- **部署方式**：私有化部署，支持完全内网运行
- **数据存储**：SQLite 为主（MySQL 预留适配）+ 向量库 FAISS 后端（`VECTOR_BACKEND=faiss`，交付索引为 FAISS 格式；ChromaDB 为可选后端）+ 爬虫侧独立 SQLite
- **知识域**：ESP32、树莓派、嵌入式开发等技术资料 + 大模型应用/AI Agent/软件工程方向（多智能体流水线自动爬取入库，仅校内教学使用）
- **核心原则**：只做事实资料检索，不做大模型微调训练；LLM 仅用于资料处理（打标/审核/摘要），问答严格基于入库资料，杜绝 AI 幻觉

---

## 产品功能需求

### 1. 多智能体协作爬取（爬取中心）
- 9 个数据源配置驱动（乐鑫官方文档/官网、ESP32 论坛、GitHub、电子发烧友、树莓派博客等），新增站点零代码
- 流水线 DAG：采集 → 打标（LLM 分类）→ 审核（LLM 拦截广告垃圾）→ 摘要（LLM）→ 自动入库知识库
- 三层去重（URL/内容哈希/SimHash）+ 站点限速熔断 + 版权分级留痕（仅校内教学使用）
- 每日 LLM 预算闸门（默认 ¥2.0）+ 成本账本；LLM 不可用时规则管线照常
- Windows 任务计划每日定时 + 管理后台页面手动触发、实时步骤状态

### 2. 文档管理
- 多格式文档上传（PDF、Word、Excel、Markdown、纯文本）
- 自动解析、分块、向量化、分类标签、版本管理
- OCR（RapidOCR）：扫描件 PDF 自动识别（逐页混合策略）
- 支持文档密级与权限过滤

### 3. 智能问答
- 基于 RAG 的多路召回（向量检索 + BM25 关键词检索）+ 重排序
- 多轮对话上下文理解、查询改写（口语 → 技术术语）
- 来源溯源（答案引用 [来源N]，来源展示文档名称、章节、页码、原文链接）
- 幻觉抑制与拒答机制（回答末尾固定资料参考声明）
- 流式输出（SSE）

### 4. 用户权限
- RBAC 权限模型（学生、老师、院系管理员、知识库管理员、超级管理员）
- JWT Token 认证
- 文档密级与用户角色匹配的检索过滤

### 5. 系统管理
- 问答日志审计（记录每次问答的耗时、来源、反馈）
- 统计分析（问答量趋势、高频问题、未命中问题、用户满意度）
- 爬取中心（站点状态、流水线监控、LLM 成本、入库同步记录）
- 系统配置热更新

### 6. 扩展功能
- **AI 助手**：悬浮式智能助手（任务型 Agent + 主 RAG 双链路）：任务/个人数据/找资料类问题走工具链路（`app/agent/` 注册表 + 20+ 工具），普通概念问答复用主教学知识库 RAG（与 /chat 同一检索链路）；**写操作两阶段确认**（模型提议 → 用户确认卡 → 一次性令牌执行，令牌 DB 持久化防重放）；支持多轮会话、历史记录、引用来源展开与跳转、Edge TTS 语音播报；由 `COUNSELOR_ENABLED` 控制启用
- **视频专区**：独立页面展示 B 站精选课程（ESP32 / ESP-IDF / Arduino / FreeRTOS / 树莓派 / 电子电路，以及软件工程方向的大模型部署 / AI 应用开发 / AI Agent），预置 24 个已校验视频；只存 BV 号等元数据，播放走 B 站官方 iframe，不转存视频；管理端支持增删改查、排序与上下架（播放量/封面为手动维护快照）
- **开放 API**：`/openapi/v1` 命名空间，API Key（SHA-256 哈希存储）鉴权 + 调用方密级上限，供第三方系统对接检索/问答
- **工单系统**：师生提交问题工单，管理员处理流转
- **敏感词管理**：提问侧高危词拦截（审计留痕）+ 回答侧脱敏
- **公告管理**：系统公告发布展示
- **登录安全**：图形/算式验证码、连续失败锁定（5 次锁 15 分钟）、SSO 预留（企业微信/钉钉/飞书/Keycloak）

---

## 技术架构

### 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                     展示层 (Presentation)                │
│  Vue 3 前端 (管理后台 + 对话界面)                         │
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
│  ChromaDB 向量库 │ SQLite/MySQL │ BM25 索引 │ 文件存储  │
└─────────────────────────────────────────────────────────┘
```

### 技术栈

#### 后端 (backend/)
| 类别 | 技术 | 说明 |
|------|------|------|
| 语言 | Python 3.9+ | 开发环境实测 3.9.1，代码兼容 3.9 语法 |
| Web 框架 | FastAPI | 高性能异步，自动生成 API 文档 |
| 数据库 ORM | SQLAlchemy 2.0 | 同步模式，支持 SQLite / MySQL |
| 向量数据库 | ChromaDB / FAISS | ChromaDB 为主；SQLite < 3.35 时自动降级 FAISS（两后端分数语义统一） |
| 关键词检索 | rank-bm25 | 轻量 BM25 算法实现 |
| LLM 接入 | 阿里云百炼 DashScope | 通义千问系列模型 |
| 文档解析 | PyMuPDF / python-docx / openpyxl | 多格式文档解析 |
| 认证 | JWT + Passlib + bcrypt | Token 认证与密码加密 |
| 缓存 | cachetools + diskcache | 问答缓存与会话缓存 |
| 日志 | Loguru | 结构化日志 |
| 测试 | PyTest + pytest-asyncio | 后端测试框架 |

#### 前端 (frontend/)
| 类别 | 技术 | 说明 |
|------|------|------|
| 框架 | Vue 3 + TypeScript | 渐进式框架 |
| UI 组件库 | Element Plus | 企业级 UI 组件库 |
| 状态管理 | Pinia | Vue 官方推荐 |
| 路由 | Vue Router 4 | 官方路由 |
| HTTP 客户端 | Axios | 请求拦截与 Token 管理 |
| Markdown 渲染 | markdown-it | 渲染 LLM 返回的 Markdown |
| 代码高亮 | highlight.js | 代码块语法高亮 |
| 构建工具 | Vite | 快速构建 |

---

## 项目目录结构

```
Multi-agent collaborative crawling of knowledge base/
├── backend/
│   ├── app/
│   │   ├── api/              # API 路由层
│   │   │   ├── v1/           # v1 版本接口（auth/chat/documents/videos/counselor/teaching/collection/tickets/crawler/admin）
│   │   │   ├── open_api/     # 开放 API（API Key 鉴权）
│   │   │   └── deps.py          # 依赖注入（获取当前用户/角色/API 调用方）
│   │   ├── agent/            # AI 助手任务型 Agent
│   │   │   ├── registry.py      # 工具注册表（角色过滤 + 参数校验 + 审计）
│   │   │   ├── tools.py         # 20+ 工具实现（检索/补采/工单/通知/学情/运营）
│   │   │   ├── actions.py       # 写操作确认令牌（DB 持久化、一次性消费、防重放）
│   │   │   ├── agent.py         # 工具调用循环（写操作转确认卡）
│   │   │   └── routing.py       # 意图门控（任务类问题才进工具链路）
│   │   ├── core/             # 核心模块
│   │   │   ├── config.py        # 配置管理（Pydantic Settings）
│   │   │   ├── security.py      # JWT + 密码哈希
│   │   │   └── exceptions.py    # 自定义异常
│   │   ├── models/           # SQLAlchemy 数据模型
│   │   │   ├── user.py
│   │   │   ├── document.py
│   │   │   ├── video.py
│   │   │   ├── chat.py
│   │   │   └── agent_action.py  # 助手写操作确认令牌表
│   │   ├── schemas/          # Pydantic 请求/响应模型
│   │   ├── db/               # 数据库连接
│   │   │   ├── sqlite.py        # SQLAlchemy 引擎 + Session（池化 + WAL + 索引）
│   │   │   ├── chroma_client.py # 向量库客户端（ChromaDB / FAISS 双后端）
│   │   │   └── cache.py         # 缓存管理
│   │   ├── rag/              # RAG 核心引擎
│   │   │   ├── chunker/         # 文档分块
│   │   │   ├── embeddings/      # 向量嵌入（DashScope）
│   │   │   ├── retrievers/      # 检索引擎（向量/BM25/混合）
│   │   │   ├── query_processor/ # 查询预处理（改写/意图识别）
│   │   │   ├── llm/             # LLM 调用封装（超时保护）
│   │   │   ├── prompts/         # Prompt 模板
│   │   │   ├── reranker/        # 重排序
│   │   │   └── ingestion.py     # 文档入库流程
│   │   └── main.py           # 应用入口（生产安全自检：弱密钥/弱口令/关验证码拒绝启动）
│   ├── crawler/              # 多智能体爬取子系统（独立批处理包，与 app/ 解耦）
│   │   ├── config/              # sites.yaml 站点档案 + models.yaml 模型档位 + seeds.yaml 补采种子 + prompts/
│   │   ├── crawl/               # 采集层（adapters/ 适配器 + dedup 三层去重 + politeness 限速熔断 + robots.txt 合规 + targeted 定向抓取）
│   │   ├── process/             # HTML→Markdown / 归一化 / 元数据
│   │   ├── store/               # 爬虫侧独立 SQLite（crawler/data/crawler.db，分库）
│   │   ├── llm/                 # LLM Provider + 批量接口 + 成本账本 + 预算闸门
│   │   ├── agents/              # DAG 编排器 + tagger/reviewer/summarizer/scout 智能体
│   │   ├── sync/                # ingest.py 入库同步器 + resolve.py 补采需求自动闭环
│   │   ├── lock.py              # 跨进程流水线互斥锁（3 小时过期自愈）
│   │   ├── pipeline.py          # 每日流水线 DAG：crawl→discover→targeted→tagger→review→summarize→kb_sync→resolve
│   │   └── data/                # crawler.db + md/ raw/ 落盘文件
│   ├── data/                 # SQLite 数据文件
│   ├── cache/                # 磁盘缓存
│   ├── uploads/              # 上传的文档文件
│   ├── eval/                 # 评测集与实验（103 道 QA + run_eval.py，论文第 6 章）
│   ├── tests/                # 单元测试（153 用例：爬虫/Agent/令牌/robots/敏感词/OCR/拒答一致性/评测集校验）
│   ├── requirements.txt
│   ├── run_crawl_daily.py    # 每日爬取流水线入口（Windows 任务计划调用）
│   ├── register_crawl_task.bat # 注册每日爬取任务计划
│   ├── rebuild_indexes.py    # FAISS+BM25 索引全量重建
│   └── fix_vector_index.py   # 向量索引一致性修复（零批量成本：删幽灵/补缺失/恢复 source_url）
├── frontend/
│   ├── src/
│   │   ├── api/              # API 调用封装
│   │   │   ├── client.ts        # Axios 实例与拦截器
│   │   │   ├── auth.ts
│   │   │   ├── chat.ts
│   │   │   ├── video.ts
│   │   │   ├── counselor.ts     # AI 助手 SSE 流式（含工具事件/确认卡）
│   │   │   └── session.ts
│   │   ├── views/            # 页面组件
│   │   │   ├── auth/            # 登录/注册/个人中心
│   │   │   ├── chat/            # 对话问答界面
│   │   │   ├── videos/          # 视频专区（B 站精选）
│   │   │   ├── help/            # 使用帮助页（公开，按角色说明功能入口）
│   │   │   └── admin/           # 管理后台页面（含视频管理/知识审核/补采闭环）
│   │   ├── components/       # 公共组件（counselor/ 悬浮 AI 助手 + AssistantMascot 形象）
│   │   ├── store/            # Pinia 状态管理
│   │   ├── router/           # Vue Router 路由配置
│   │   ├── styles/           # 全局样式
│   │   ├── App.vue
│   │   └── main.ts
│   ├── package.json
│   └── vite.config.ts
├── deploy/                   # 部署脚本（deploy.sh 首装 / update.ps1+update.sh 增量更新 / sync_content+sync_students 数据同步 / materials 配套资料）
├── .claude/                  # Claude Code 配置
│   ├── agents/               # 子代理定义
│   ├── commands/             # 自定义斜杠命令
│   ├── check-results/        # 质量检查结果
│   └── settings.json         # 权限配置
├── start_all.bat             # 一键启动前后端
├── start_backend.bat
└── start_frontend.bat
```

---

## 🚀 如何运行

### 环境准备
- Python 3.9+（开发环境实测 3.9.1）
- Node.js 20.19+（Vite 8 要求；22.12+ 亦可）
- 阿里云百炼 API Key（DashScope）

### 后端
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env    # 编辑 .env 填入 API Key，并修改 ADMIN_PASSWORD / JWT_SECRET_KEY
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001    # 本机勿用 --reload（Windows 下残留孤儿 worker 占端口）
```

> 生产安全自检：弱 JWT 密钥/弱管理员口令/关闭验证码会拒绝启动；仅本地调试可设 `SKIP_SAFETY_CHECK=true`（部署脚本会强制写回 false）。

### 前端
```bash
cd frontend
npm install
npm run dev             # 访问 http://localhost:5173
```

### 一键启动
```bash
start_all.bat
```

### 运行测试
```bash
cd backend
python -m pytest -v
```

---

## 🚀 生产部署（deploy/）

| 脚本 | 用途 |
|------|------|
| `deploy/deploy.sh` | Ubuntu 22.04 首装：依赖/解压/kb 用户/随机管理员密码+强制验证码+`VECTOR_BACKEND=faiss`/venv/systemd/Nginx/健康检查 |
| `deploy/update.ps1` + `deploy/update.sh` | 增量更新：本地构建 dist → 打包上传 → 服务端整体替换前端资源 + 重启（发布标记校验） |
| `deploy/sync_content.py` | 幂等补录视频与配套资料（`deploy/materials/`） |
| `deploy/sync_students.py` | 学生名单导入（按角色 code 解析，幂等；读取 `deploy/students.json`） |

要点：
- 部署包不含 `.env`/数据库/学生名单；API Key 在服务器单独配置
- `deploy.sh` 会轮换库内弱口令管理员并把新密码打印在日志末尾
- 前端由 Nginx 托管 `frontend/dist`，`/api/` 与 `/static/` 反代到 8001
- 后端单 worker；进程内限流单实例全局生效，多实例需换共享存储

---

## 🕷️ 多智能体爬取子系统（backend/crawler/）

面向 ESP32/树莓派/嵌入式开发教学资料的自动采集入库（仅校内教学使用）。参照 E:\Crawler（crawler-kb）设计，与 FastAPI 应用完全解耦的独立批处理包。

### 流水线拓扑
```
crawl（必需：遍历站点→适配器→三层去重→落盘）
  → discover（补采侦察，可选）→ targeted（定向抓取补采候选，可选）
  → tagger（LLM 可选：分类打标，映射 KB 分类树）
  → review（LLM 可选：拦截广告/垃圾/版权高风险）
  → summarize（LLM 可选：一句话摘要，仅存爬虫库）
  → kb_sync（必需：复用 seed 范式入库 KB 主库 → 置待审核）
  → resolve（补采需求自动闭环，可选）
```

- **智能体协作**：轻量 DAG 编排器（`crawler/agents/orchestrator.py`），deps/指数退避重试/optional；LLM 步骤超每日预算（默认 ¥2.0）或 API 不可用时自动 skipped，规则管线照常运行
- **幂等**：URL 哈希 → 内容哈希 → SimHash 三层去重 + KB 侧 `source_hash` 闸门 + `kb_syncs` 唯一索引，重复运行零副作用
- **版权合规**：risk_level 分级（low 全文 / medium 节选500字+原文链接 / high 不入库），`source_authorizations` 留痕；论坛内容只存节选
- **入库**：`crawler/sync/ingest.py` 采用已验证的入库范式（建 Document 行 → `_process_document_task` → `review_status=1 + status=1` 待管理员审核）；管理员在「知识审核」页人工确认后发布。爬取文档全部 `security_level=1`，并写入 `source_url/source_hash` 溯源字段（回答中展示原文链接）
- **OCR**：`app/rag/ocr.py`（RapidOCR）在 `parse_pdf` 中对无文本层页面自动识别（逐页混合策略，`OCR_ENABLED/OCR_MAX_PAGES` 配置控制）

### 站点配置（crawler/config/sites.yaml）
新增站点零代码：加一条 YAML（code/adapter/risk_level/rate_limit/config），`repo.sync_sites` 自动同步进爬虫库。已有适配器：`rss_feed` / `html_list`（list+tree）/ `sitemap` / `github`（search+repo）/ `espressif_docs`（SPA 探活）。探活失败/无权限的站点自动跳过（"爬不了就不爬"）。

### 运行与调度
```bash
cd backend
python run_crawl_daily.py                # 手动全量
python run_crawl_daily.py --site esp32_forum_idf   # 只采指定站点（调试）
register_crawl_task.bat                  # 注册 Windows 任务计划（每日 08:30）
```
注意：爬虫进程与 uvicorn 共用 ChromaDB，建议低峰调度；首轮大批量回填建议临时停服。

---

## 开发协作规则

1. **代码质量**：提交前确保通过测试和质量检查（使用 `/git-save` 或让 gitcommit-agent 处理）
2. **API 规范**：统一响应格式 `{code, message, data}`；错误码 1xxx 参数错误、2xxx 认证错误、3xxx 业务错误、4xxx 系统错误
3. **Python 规范**：使用 type hints、docstring 注释、Pydantic 做数据校验
4. **Vue 规范**：使用 `<script setup lang="ts">` 语法、Pinia store 管理状态
5. **安全原则**：JWT 认证、密码 bcrypt 哈希、文档密级过滤、API 参数校验

---

## 关键配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 后端端口 | 8001 | FastAPI 服务端口 |
| 前端端口 | 5173 | Vite 开发服务器 |
| VECTOR_BACKEND | auto（部署固定 faiss） | 交付索引为 FAISS 格式；Linux 上 auto 会改选 ChromaDB 导致检索为空 |
| 向量维度 | 1536 | DashScope text-embedding-v2 |
| 分块大小 | 512 token | 语义分块 |
| 召回 Top-K | 向量/BM25 各 20 → 融合 50 → 重排 5 | 混合检索三级漏斗 |
| JWT 过期 | 24h | Token 有效期 |
| SKIP_SAFETY_CHECK | false | 生产安全自检豁免开关，仅限本地调试 |
| LLM 超时 | 读 120s / 连 10s / 重试 1 次 | 防止挂起调用占死同步线程池 |

---

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/auth/login | 用户登录 |
| POST | /api/v1/auth/register | 用户注册 |
| GET | /api/v1/auth/me | 当前用户信息 |
| POST | /api/v1/chat/ask | 问答（同步） |
| POST | /api/v1/chat/stream | 问答（SSE 流式） |
| GET | /api/v1/chat/sessions | 会话列表 |
| POST | /api/v1/documents/upload | 上传文档 |
| GET | /api/v1/documents | 文档列表 |
| GET | /api/v1/videos | 视频列表（已上架，支持关键词/分类/难度） |
| GET | /api/v1/videos/categories | 视频分类及数量 |
| GET | /api/v1/videos/{id} | 视频详情 |
| GET | /api/v1/admin/videos | 视频管理列表（管理员） |
| POST | /api/v1/admin/videos | 新增视频（管理员） |
| PUT | /api/v1/admin/videos/{id} | 编辑视频（管理员） |
| PUT | /api/v1/admin/videos/{id}/status | 上架/下架（管理员） |
| DELETE | /api/v1/admin/videos/{id} | 删除视频（管理员） |
| GET | /api/v1/admin/stats/overview | 统计概览 |
| GET | /api/v1/crawler/overview | 爬取中心总览（管理员） |
| GET | /api/v1/crawler/sites | 站点采集状态 |
| GET | /api/v1/crawler/syncs | 入库同步记录 |
| GET | /api/v1/crawler/usage | LLM 成本账本 |
| POST | /api/v1/crawler/run | 手动触发爬取流水线（后台线程） |
| GET | /api/v1/crawler/run | 流水线运行状态 |
| POST | /api/v1/counselor/ask | AI 助手问答（同步） |
| POST | /api/v1/counselor/stream | AI 助手问答（SSE：token/tool_call/tool_result/confirmation_required/done） |
| POST | /api/v1/counselor/actions/confirm | 确认执行助手提议的写操作（一次性令牌，DB 持久化防重放） |
| GET | /api/v1/counselor/sessions | AI 助手会话列表 |
| GET | /api/v1/counselor/tts | Edge TTS 语音合成（免费，限流） |
| GET | /api/v1/teaching/my-classes | 教师：我的班级 |
| GET | /api/v1/teaching/my-classes/{id}/students | 教师：班级学生学情（仅任教班级） |
| GET/POST | /api/v1/collection/requests | 补采需求查询/提交 |
| POST | /api/v1/collection/requests/{id}/run | 触发定向补采流水线（管理员） |
| GET/POST | /api/v1/tickets | 工单查询/提交 |
| GET | /api/v1/notifications | 站内通知 |
| GET/POST | /api/v1/admin/sensitive-words | 敏感词管理（超级管理员） |
| GET/POST | /api/v1/api-clients | 开放 API 调用方管理（超级管理员） |
| POST | /openapi/v1/search | 开放 API 知识片段检索（API Key Bearer 鉴权） |
| POST | /openapi/v1/ask | 开放 API 知识库问答（API Key Bearer 鉴权） |
| GET | /api/health | 健康检查 |

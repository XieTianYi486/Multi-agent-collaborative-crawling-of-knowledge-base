# 人工智能学院教学知识库 — 产品文档

## 项目基本信息

- **项目名称**：人工智能学院教学知识库
- **项目类型**：多智能体协作爬取的专业知识库 + 向量检索问答（垂直 RAG）
- **目标用户**：院校师生、知识库管理员、超级管理员
- **部署方式**：私有化部署，支持完全内网运行
- **数据存储**：SQLite（开发）/ MySQL（生产）+ ChromaDB 向量库 + 爬虫侧独立 SQLite
- **知识域**：ESP32、树莓派、嵌入式开发、智能玩具等技术资料（多智能体流水线自动爬取入库，仅校内教学使用）
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
- RBAC 权限模型（普通员工、部门管理员、知识库管理员、超级管理员）
- JWT Token 认证
- 文档密级与用户角色匹配的检索过滤

### 5. 系统管理
- 问答日志审计（记录每次问答的耗时、来源、反馈）
- 统计分析（问答量趋势、高频问题、未命中问题、用户满意度）
- 爬取中心（站点状态、流水线监控、LLM 成本、入库同步记录）
- 系统配置热更新

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
| 语言 | Python 3.10+ | AI/ML 生态最完善 |
| Web 框架 | FastAPI | 高性能异步，自动生成 API 文档 |
| 数据库 ORM | SQLAlchemy 2.0 | 同步模式，支持 SQLite / MySQL |
| 向量数据库 | ChromaDB | 嵌入式向量存储，自带持久化 |
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
Enterprise Employee Self-Service Intelligent Knowledge Base/
├── backend/
│   ├── app/
│   │   ├── api/              # API 路由层
│   │   │   ├── v1/           # v1 版本接口
│   │   │   │   ├── auth.py       # 认证接口
│   │   │   │   ├── chat.py       # 问答接口
│   │   │   │   ├── documents.py  # 文档管理接口
│   │   │   │   └── admin.py      # 管理接口
│   │   │   └── deps.py          # 依赖注入（获取当前用户等）
│   │   ├── core/             # 核心模块
│   │   │   ├── config.py        # 配置管理（Pydantic Settings）
│   │   │   ├── security.py      # JWT + 密码哈希
│   │   │   └── exceptions.py    # 自定义异常
│   │   ├── models/           # SQLAlchemy 数据模型
│   │   │   ├── user.py
│   │   │   ├── document.py
│   │   │   └── chat.py
│   │   ├── schemas/          # Pydantic 请求/响应模型
│   │   ├── db/               # 数据库连接
│   │   │   ├── sqlite.py        # SQLAlchemy 引擎 + Session
│   │   │   ├── chroma_client.py # ChromaDB 客户端
│   │   │   └── cache.py         # 缓存管理
│   │   ├── rag/              # RAG 核心引擎
│   │   │   ├── chunker/         # 文档分块
│   │   │   ├── embeddings/      # 向量嵌入（DashScope）
│   │   │   ├── retrievers/      # 检索引擎（向量/BM25/混合）
│   │   │   ├── query_processor/ # 查询预处理（改写/意图识别）
│   │   │   ├── llm/             # LLM 调用封装
│   │   │   ├── prompts/         # Prompt 模板
│   │   │   ├── reranker/        # 重排序
│   │   │   └── ingestion.py     # 文档入库流程
│   │   ├── eval/             # 评测集与实验（74 道 QA + run_eval.py，论文第 6 章）
│   │   ├── tests/            # 单元测试
│   │   └── main.py           # 应用入口
│   ├── crawler/              # 多智能体爬取子系统（独立批处理包，与 app/ 解耦）
│   │   ├── config/              # sites.yaml 站点档案 + models.yaml 模型档位 + prompts/
│   │   ├── crawl/               # 采集层（adapters/ 适配器 + dedup 三层去重 + politeness 限速熔断）
│   │   ├── process/             # HTML→Markdown / 归一化 / 元数据
│   │   ├── store/               # 爬虫侧独立 SQLite（crawler/data/crawler.db，分库）
│   │   ├── llm/                 # LLM Provider + 批量接口 + 成本账本 + 预算闸门
│   │   ├── agents/              # DAG 编排器 + tagger/reviewer/summarizer 智能体
│   │   ├── sync/ingest.py       # 入库同步器（爬虫文档 → KB 主库，复用 seed 范式）
│   │   ├── pipeline.py          # 每日流水线 DAG：crawl→tagger→review→summarize→kb_sync
│   │   └── data/                # crawler.db + md/ raw/ 落盘文件
│   ├── data/                 # SQLite 数据文件
│   ├── cache/                # 磁盘缓存
│   ├── uploads/              # 上传的文档文件
│   ├── requirements.txt
│   ├── run_crawl_daily.py    # 每日爬取流水线入口（Windows 任务计划调用）
│   ├── register_crawl_task.bat # 注册每日爬取任务计划
│   └── rebuild_indexes.py    # FAISS+BM25 索引重建（修复用）
├── frontend/
│   ├── src/
│   │   ├── api/              # API 调用封装
│   │   │   ├── client.ts        # Axios 实例与拦截器
│   │   │   ├── auth.ts
│   │   │   ├── chat.ts
│   │   │   └── session.ts
│   │   ├── views/            # 页面组件
│   │   │   ├── auth/            # 登录/注册/个人中心
│   │   │   ├── chat/            # 对话问答界面
│   │   │   └── admin/           # 管理后台页面
│   │   ├── components/       # 公共组件
│   │   ├── store/            # Pinia 状态管理
│   │   ├── router/           # Vue Router 路由配置
│   │   ├── styles/           # 全局样式
│   │   ├── App.vue
│   │   └── main.ts
│   ├── package.json
│   └── vite.config.ts
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
- Python 3.10+
- Node.js 18+
- 阿里云百炼 API Key（DashScope）

### 后端
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env    # 编辑 .env 填入 API Key
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

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

## 🕷️ 多智能体爬取子系统（backend/crawler/）

面向 ESP32/树莓派/嵌入式开发教学资料的自动采集入库（仅校内教学使用）。参照 E:\Crawler（crawler-kb）设计，与 FastAPI 应用完全解耦的独立批处理包。

### 流水线拓扑
```
crawl（必需：遍历站点→适配器→三层去重→落盘）
  → tagger（LLM 可选：分类打标，映射 KB 分类树）
  → review（LLM 可选：拦截广告/垃圾/版权高风险）
  → summarize（LLM 可选：一句话摘要，仅存爬虫库）
  → kb_sync（必需：复用 seed 范式入库 KB 主库 → 自动过审发布）
```

- **智能体协作**：轻量 DAG 编排器（`crawler/agents/orchestrator.py`），deps/指数退避重试/optional；LLM 步骤超每日预算（默认 ¥2.0）或 API 不可用时自动 skipped，规则管线照常运行
- **幂等**：URL 哈希 → 内容哈希 → SimHash 三层去重 + KB 侧 `source_hash` 闸门 + `kb_syncs` 唯一索引，重复运行零副作用
- **版权合规**：risk_level 分级（low 全文 / medium 节选500字+原文链接 / high 不入库），`source_authorizations` 留痕；论坛内容只存节选
- **入库**：`crawler/sync/ingest.py` 采用已验证的入库范式（建 Document 行 → `_process_document_task` → `review_status=2 + status=1` 自动过审）；爬取文档全部 `security_level=1`，并写入 `source_url/source_hash` 溯源字段（回答中展示原文链接）
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
| 向量维度 | 1536 | DashScope text-embedding-v2 |
| 分块大小 | 512 token | 语义分块 |
| 召回 Top-K | 10 | 混合检索召回数量 |
| JWT 过期 | 24h | Token 有效期 |

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
| GET | /api/v1/admin/stats/overview | 统计概览 |
| GET | /api/v1/crawler/overview | 爬取中心总览（管理员） |
| GET | /api/v1/crawler/sites | 站点采集状态 |
| GET | /api/v1/crawler/syncs | 入库同步记录 |
| GET | /api/v1/crawler/usage | LLM 成本账本 |
| POST | /api/v1/crawler/run | 手动触发爬取流水线（后台线程） |
| GET | /api/v1/crawler/run | 流水线运行状态 |
| GET | /api/health | 健康检查 |

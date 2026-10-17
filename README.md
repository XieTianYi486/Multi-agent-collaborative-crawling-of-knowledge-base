# 人工智能学院教学知识库

> AI Academy Teaching Knowledge Base

多智能体协作爬取的专业知识库 + 向量检索问答（垂直 RAG）。面向 **ESP32 / 树莓派 / 嵌入式开发 / 智能玩具** 等技术教学资料：由多智能体流水线自动爬取、打标、审核、摘要并入库，师生用自然语言提问即可获得**带来源引用的可溯源解答**——只做事实资料检索，不做大模型微调，杜绝 AI 幻觉。

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883.svg)](https://vuejs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178c6.svg)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ 核心特性

### 🕷️ 多智能体协作爬取（爬取中心）
- **9 个数据源配置驱动**：乐鑫官方文档/官网、ESP32 论坛、ESP-IDF GitHub、电子发烧友、树莓派博客等，新增站点零代码（YAML 一条配置）
- **流水线 DAG**：采集 → 打标（LLM 分类映射分类树）→ 审核（LLM 拦截广告/垃圾/版权高风险）→ 摘要（LLM）→ 自动入库
- **三层去重**（URL / 内容哈希 / SimHash）+ 站点限速熔断，重复运行零副作用
- **每日 LLM 预算闸门**（默认 ¥2.0）+ 成本账本；LLM 不可用时规则管线照常运行
- **版权分级留痕**：全文 / 节选500字+原文链接 / 不入库 三级，仅校内教学使用
- Windows 任务计划每日定时 + 管理后台页面手动触发、流水线 5 步实时状态

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

### 🔐 权限管控
- RBAC 四级角色（普通员工 / 部门管理员 / 知识库管理员 / 超级管理员）
- JWT Token 认证 + bcrypt 密码哈希
- 文档密级与用户角色自动匹配的检索过滤

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
        │ 采集 → 打标 → 审核 → 摘要 → 自动入库
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
| 测试 | PyTest + pytest-asyncio | 108 用例 |

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
│   │   ├── api/v1/               # auth / chat / documents / admin / crawler 路由
│   │   ├── core/                 # 配置（Pydantic Settings）/ JWT / 异常
│   │   ├── models/               # SQLAlchemy 模型（用户/文档/分类/分块/会话）
│   │   ├── schemas/              # Pydantic 请求/响应模型
│   │   ├── services/             # 业务层（认证/问答/文档）
│   │   ├── db/                   # SQLAlchemy 引擎 / 向量库客户端 / 缓存
│   │   ├── rag/                  # 🔥 RAG 引擎
│   │   │   ├── chunker/          # 语义分块
│   │   │   ├── embeddings/       # DashScope 向量嵌入
│   │   │   ├── retrievers/       # 向量 / BM25 / 混合检索
│   │   │   ├── query_processor/  # 查询改写 / 意图识别
│   │   │   ├── llm/              # LLM 调用封装
│   │   │   ├── prompts/          # Prompt 模板（技术资料域防幻觉）
│   │   │   ├── reranker/         # LLM 重排序
│   │   │   ├── ocr.py            # RapidOCR 扫描件识别
│   │   │   └── ingestion.py      # 文档入库流水线
│   │   ├── tasks/                # 后台线程（文档处理）
│   │   ├── eval/                 # 评测集与实验脚本（论文第 6 章，74 题）
│   │   ├── tests/                # 单元测试（108 用例）
│   │   └── main.py               # 应用入口
│   ├── crawler/                  # 🕷️ 多智能体爬取子系统（独立批处理包）
│   │   ├── config/               # sites.yaml 站点档案 + models.yaml 模型档位 + prompts/
│   │   ├── crawl/                # 采集层（adapters/ 适配器 + dedup 三层去重 + politeness 限速熔断）
│   │   ├── process/              # HTML→Markdown / 归一化 / 元数据
│   │   ├── store/                # 爬虫侧独立 SQLite（分库）
│   │   ├── llm/                  # Provider + 成本账本 + 预算闸门
│   │   ├── agents/               # DAG 编排器 + tagger/reviewer/summarizer 智能体
│   │   ├── sync/                 # 入库同步器（爬虫文档 → KB 主库）
│   │   ├── pipeline.py           # 每日流水线 DAG
│   │   └── data/                 # crawler.db + md/ raw/ 落盘文件
│   ├── data/                     # KB 主库 SQLite
│   ├── uploads/                  # 上传/采集文档文件
│   ├── requirements.txt
│   ├── run_crawl_daily.py        # 每日爬取流水线入口（Windows 任务计划调用）
│   ├── register_crawl_task.bat   # 注册每日爬取任务计划（每日 08:30）
│   └── rebuild_indexes.py        # FAISS+BM25 索引重建（修复用）
├── frontend/
│   └── src/
│       ├── api/                  # Axios 封装（含 SSE 流式）
│       ├── views/
│       │   ├── auth/             # 登录 / 注册 / 个人中心
│       │   ├── chat/             # 对话问答界面
│       │   └── admin/            # 管理后台 13 页（文档/审核/用户/统计/日志/**爬取中心**等）
│       ├── components/           # 公共组件
│       ├── store/                # Pinia（auth / chat / theme）
│       └── router/               # 路由与权限守卫
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
- **Node.js** 18+
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

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY

# 启动后端服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

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

### 演示账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | 超级管理员 |

> ⚠️ 生产环境请务必修改默认密码和 JWT Secret

---

## 🕷️ 多智能体爬取子系统（backend/crawler/）

面向 ESP32/树莓派/嵌入式开发教学资料的自动采集入库（**仅校内教学使用**），与 FastAPI 主应用完全解耦的独立批处理包。

### 流水线拓扑

```
crawl（必需：遍历站点→适配器→三层去重→落盘）
  → tagger（LLM 可选：分类打标，映射 KB 分类树）
  → review（LLM 可选：拦截广告/垃圾/版权高风险）
  → summarize（LLM 可选：一句话摘要，仅存爬虫库）
  → kb_sync（必需：入库 KB 主库 → 自动过审发布）
```

- **智能体协作**：轻量 DAG 编排器，deps/指数退避重试/optional；LLM 步骤超每日预算（默认 ¥2.0，实测全量一轮仅 ¥0.067）或 API 不可用时自动跳过，规则管线照常运行
- **幂等**：URL 哈希 → 内容哈希 → SimHash 三层去重 + KB 侧 `source_hash` 闸门 + `kb_syncs` 唯一索引，重复运行零副作用
- **版权合规**：risk_level 分级（low 全文 / medium 节选500字+原文链接 / high 不入库），`source_authorizations` 留痕；论坛内容只存节选
- **入库**：爬取文档自动过审发布（`security_level=1`），写入 `source_url/source_hash` 溯源字段，回答中展示原文链接
- **新增站点零代码**：`crawler/config/sites.yaml` 加一条配置即可。已有适配器：`rss_feed` / `html_list`（list+tree）/ `sitemap` / `github`（search+repo）/ `espressif_docs`（SPA 探活）；探活失败/无权限的站点自动跳过（"爬不了就不爬"）

> 注意：爬虫进程与 uvicorn 共用向量库，建议低峰调度；首轮大批量回填建议临时停服。

---

## 📡 API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/login` | 用户登录 |
| POST | `/api/v1/auth/register` | 用户注册 |
| GET | `/api/v1/auth/me` | 当前用户信息 |
| POST | `/api/v1/chat/ask` | 问答（同步） |
| POST | `/api/v1/chat/stream` | 问答（SSE 流式） |
| GET | `/api/v1/chat/sessions` | 会话列表 |
| POST | `/api/v1/documents/upload` | 上传文档 |
| GET | `/api/v1/documents` | 文档列表 |
| GET | `/api/v1/admin/stats/overview` | 统计概览 |
| GET | `/api/v1/crawler/overview` | 爬取中心总览（管理员） |
| GET | `/api/v1/crawler/sites` | 站点采集状态 |
| GET | `/api/v1/crawler/syncs` | 入库同步记录 |
| GET | `/api/v1/crawler/usage` | LLM 成本账本 |
| POST | `/api/v1/crawler/run` | 手动触发爬取流水线（后台线程） |
| GET | `/api/v1/crawler/run` | 流水线运行状态 |
| GET | `/api/health` | 健康检查 |

> 完整 API 文档见 http://localhost:8001/docs

---

## ⚙️ 关键配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 后端端口 | 8001 | FastAPI 服务端口 |
| 前端端口 | 5173 | Vite 开发服务器 |
| 向量维度 | 1536 | DashScope text-embedding-v2 |
| 分块大小 | 512 token | 语义分块 |
| 召回 Top-K | 10 | 混合检索召回数量 |
| JWT 过期 | 24h | Token 有效期 |
| 爬取预算闸门 | ¥2.0/日 | LLM 步骤超预算自动降级规则管线 |
| 定时爬取 | 每日 08:30 | Windows 任务计划 |

---

## 🧪 评测与实验

毕业设计论文第 6 章实验数据由 `backend/eval/` 产出（74 道评测题 + 检索指标 Recall/MRR/nDCG + 端到端 LLM judge），详见 [backend/eval/README.md](backend/eval/README.md)。

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
python -m pytest -v        # 108 用例全绿；测试自动隔离到 tests/.tmp_test/test.db
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
- 论坛等用户生成内容仅存节选并附原文链接；爬取行为遵循各站点限速策略与 robots 规范
- 本系统**仅限校内教学使用**，不做任何商业分发；回答严格基于入库资料，末尾固定"以上内容基于知识库收录资料整理，仅供教学参考"声明
- 若版权方要求移除内容，可在管理后台删除对应文档（数据库与向量索引同步清理）

---

## License

MIT © 2026

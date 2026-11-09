# ============================================================
# 应用核心配置
# 使用 pydantic-settings 从 .env 文件和环境变量加载配置
# ============================================================

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


# 项目根目录（backend/）
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """应用配置类，所有配置项从 .env 文件读取"""

    # ==================== 应用基础配置 ====================
    APP_NAME: str = "人工智能学院教学知识库"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "多智能体协作爬取的嵌入式开发教学知识库（ESP32 / ESP-IDF / 树莓派 / 电子电路 / 物联网教学资料检索）"
    DEBUG: bool = True
    SECRET_KEY: str = "change-this-to-a-random-secret-key-in-production"

    # ==================== 服务端口 ====================
    HOST: str = "0.0.0.0"
    PORT: int = 8001

    # ==================== 数据库配置 ====================
    # SQLite 为主（零配置），后续可切换到 MySQL
    # 使用绝对路径避免工作目录问题
    _data_dir: str = str(BASE_DIR / "data")
    DATABASE_URL: str = f"sqlite:///{_data_dir}/enterprise_rag.db"

    # ==================== LLM 对话配置 ====================
    # provider: dashscope=阿里云百炼 qwen-plus, deepseek=DeepSeek deepseek-chat
    LLM_PROVIDER: str = "dashscope"
    LLM_MODEL: str = "qwen-plus"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""  # 默认按 provider 自动填充
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2048
    # qwen3 系模型是否启用思考模式；关闭可显著降低首字延迟（仅对 dashscope 的 qwen3 模型生效）
    LLM_ENABLE_THINKING: bool = True

    # ==================== 向量嵌入（支持 DashScope / DeepSeek 远程 + ONNX 本地）====================
    # provider: dashscope=阿里云百炼 text-embedding-v2, deepseek=DeepSeek API (不公开)
    #           onnx_bge=本地 BGE-small-zh-v1.5 ONNX (512维, 零成本零依赖)
    EMBEDDING_PROVIDER: str = "dashscope"
    EMBEDDING_API_KEY: str = ""   # 远程 API 用；优先，否则回退 DASHSCOPE_API_KEY
    EMBEDDING_BASE_URL: str = ""  # 留空则按 provider 自动填
    EMBEDDING_LOCAL_MODEL: str = ""  # 本地 ONNX 模型目录（onnx_bge 用）
    EMBEDDING_MODEL: str = "text-embedding-v2"
    EMBEDDING_DIMENSION: int = 1536

    # 向后兼容：阿里云百炼旧配置项
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = ""
    DASHSCOPE_OPENAI_BASE_URL: str = ""

    # ==================== 检索配置 ====================
    VECTOR_TOP_K: int = 20        # 向量检索召回数量
    BM25_TOP_K: int = 20          # BM25 检索召回数量
    FUSION_TOP_K: int = 50        # 融合后候选集大小
    RERANK_CANDIDATES: int = 20   # 送入重排序器的候选数量
    RERANK_TOP_N: int = 5         # 重排序后最终保留数量
    # 查询改写的最长等待时间（毫秒）：超时直接用原问题检索，保证首字延迟有上限
    QUERY_REWRITE_TIMEOUT_MS: int = 1200
    # 改写策略：conditional=仅短问句/指代问句/带历史时改写（省时省钱），always=全量，off=关闭
    QUERY_REWRITE_MODE: str = "conditional"
    QUERY_REWRITE_MIN_CHARS: int = 16  # 条件改写：问题长度小于该值时触发
    SIMILARITY_THRESHOLD: float = 0.5  # 相似度阈值（低于此值拒答）
    # 融合策略：weighted=最大值归一化加权；rrf=倒数排名融合（对分数尺度更稳健）
    FUSION_STRATEGY: str = "weighted"
    RRF_K: int = 60               # RRF 平滑常数
    VECTOR_WEIGHT: float = 0.5    # 向量检索融合权重（weighted 策略生效）
    BM25_WEIGHT: float = 0.5      # BM25 检索融合权重（weighted 策略生效）

    # ==================== 文档分块配置 ====================
    CHUNK_SIZE: int = 512         # 分块大小（token 估算）
    CHUNK_OVERLAP: int = 50       # 分块重叠（token 估算）

    # ==================== OCR 配置（扫描件 PDF 识别）====================
    OCR_ENABLED: bool = True      # 是否启用 RapidOCR 识别扫描页/图片页
    OCR_MAX_PAGES: int = 0        # 单文档 OCR 页数上限（0=不限）

    # ==================== JWT 认证配置 ====================
    JWT_SECRET_KEY: str = "jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # Token 有效期 24 小时

    # ==================== 缓存配置 ====================
    CACHE_TTL_ANSWER: int = 86400    # 问答结果缓存 TTL（秒），默认 24h
    CACHE_TTL_SESSION: int = 3600    # 会话缓存 TTL（秒），默认 1h
    CACHE_DIR: str = str(BASE_DIR / "cache")

    # ==================== 文件上传配置 ====================
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    MAX_UPLOAD_SIZE_MB: int = 50      # 单文件最大上传大小
    ALLOWED_EXTENSIONS: list = ["pdf", "docx", "xlsx", "md", "txt"]

    # ==================== 默认管理员账号 ====================
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    ADMIN_EMAIL: str = "admin@company.com"

    # ==================== 登录安全 ====================
    LOGIN_MAX_FAILURES: int = 5           # 连续失败次数达到阈值即锁定
    LOGIN_LOCK_MINUTES: int = 15          # 锁定时长（分钟）
    CAPTCHA_ENABLED: bool = True          # 登录是否需要图形/算式验证码
    CAPTCHA_TTL_SECONDS: int = 120        # 验证码有效期（秒）

    # ==================== SSO 单点登录（预留） ====================
    # 用于对接企业微信/钉钉/飞书/统一身份认证(如 Keycloak)等企业 SSO
    SSO_ENABLED: bool = False             # 是否启用 SSO 登录
    SSO_PROVIDER: str = "none"            # none | wecom | dingtalk | feishu | saml | oauth2
    SSO_SERVER_URL: str = ""              # 认证服务器地址
    SSO_APP_ID: str = ""                  # 应用 Client ID
    SSO_APP_SECRET: str = ""              # 应用 Client Secret
    SSO_CALLBACK_URL: str = ""            # 回调地址（默认为 /api/v1/auth/sso/callback）

    # ==================== 敏感词 / 合规 ====================
    SENSITIVE_WORD_ENABLED: bool = True   # 是否启用敏感词过滤与脱敏

    # ==================== 知识审核发布 ====================
    DOCUMENT_REVIEW_ENABLED: bool = True  # 是否启用"草稿->待审核->已发布"审核发布流

    # ==================== AI 助手 ====================
    COUNSELOR_ENABLED: bool = True        # 是否启用悬浮 AI 助手入口（沿用 counselor 模块名）

    # ==================== 接口限流 ====================
    RATE_LIMIT_ENABLED: bool = True   # 是否启用进程内令牌桶限流
    RATE_LIMIT_PER_MINUTE: int = 30   # 每个用户/凭证每分钟允许的请求数
    RATE_LIMIT_BURST: int = 10        # 令牌桶容量（允许的瞬时突发请求数）

    # ==================== 日志配置 ====================
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = str(BASE_DIR / "logs")

    # ==================== 向量后端配置 ====================
    # auto: 优先 ChromaDB，sqlite3<3.35 时降级 FAISS
    # chroma: 强制 ChromaDB；faiss: 强制 FAISS
    VECTOR_BACKEND: str = "auto"
    CHROMA_PERSIST_DIR: str = str(BASE_DIR / "chroma_data")
    CHROMA_COLLECTION_NAME: str = "teaching_kb_docs"

    # ==================== 初始化目录 ====================
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 确保必要的目录存在
        for dir_path in [self.UPLOAD_DIR, self.CHROMA_PERSIST_DIR,
                         self.CACHE_DIR, self.LOG_DIR,
                         str(BASE_DIR / "data")]:
            os.makedirs(dir_path, exist_ok=True)

    model_config = dict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # 忽略未知的环境变量
    )


# 全局单例配置对象
settings = Settings()

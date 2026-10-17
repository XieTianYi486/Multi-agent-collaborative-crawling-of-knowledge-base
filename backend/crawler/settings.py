"""爬虫侧全局配置。

与知识库主应用（app/core/config.py）共享同一份 backend/.env：
- DASHSCOPE_API_KEY         —— LLM 打标/审核/摘要共用同一个 Key
- DASHSCOPE_OPENAI_BASE_URL —— 自定义 OpenAI 兼容端点（可选）

非敏感参数全部用代码默认值；站点档案在 config/sites.yaml、
模型档位在 config/models.yaml（数据驱动，新增站点零代码）。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录（.env 所在位置）
BACKEND_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = Path(__file__).resolve().parent / "config"
# 爬虫侧数据目录：SQLite + 落盘文件（与知识库主数据隔离，可整体删除重建）
# 测试可设置 KB_DATA_DIR 指向临时目录
DATA_DIR = Path(os.environ.get("KB_DATA_DIR") or (Path(__file__).resolve().parent / "data"))


class Settings(BaseSettings):
    """爬虫侧全局设置（.env / 环境变量 / 代码默认值）。"""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM（与知识库共享 .env 的 DASHSCOPE_API_KEY）---
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_openai_base_url: str = ""  # .env 自定义 OpenAI 兼容端点（优先）
    github_token: str = ""

    # --- 预算与成本 ---
    daily_budget_cny: float = 2.0  # 每日 LLM 预算（元），超限 LLM 步骤自动跳过

    # --- 去重 ---
    simhash_hamming_threshold: int = 3
    simhash_near_window_days: int = 3

    # --- 采集 ---
    # 注意：HTTP 头必须纯 ASCII，说明文字用英文
    crawl_user_agent: str = "CampusKB/0.1 (campus teaching use; contact: kb-admin@campus.edu.cn)"
    crawl_timeout_seconds: int = 30

    # --- 批量接口（半价，失败自动回退顺序调用）---
    # 实测本账号批量任务排队不完成，每步白等 15 分钟才回退；
    # 每日 <100 篇的小批量场景顺序调用成本可忽略（12 篇约 ¥0.0025），
    # 默认关闭；大批量回填时可临时置 true 省钱
    llm_batch_enabled: bool = False
    llm_batch_poll_timeout_seconds: int = 3600  # 批量任务最长等待
    llm_batch_early_fallback_seconds: int = 900  # 排队超时且 0 完成 → 取消回退

    # --- 知识库入库同步 ---
    kb_sync_limit: int = 100  # 单次流水线最多同步几篇到知识库

    @property
    def llm_base_url(self) -> str:
        """LLM OpenAI 兼容端点（自定义端点优先）。"""
        return self.dashscope_openai_base_url or self.dashscope_base_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


class SiteConfig(BaseModel):
    """站点档案条目（config/sites.yaml）。"""

    code: str
    name: str
    source_type: str = "rss"  # rss / api / html
    adapter: str = ""
    base_url: str = ""
    risk_level: str = "low"  # low=全文入库 / medium=仅节选+链接 / high=不入库仅留痕
    authority_weight: float = 1.0
    enabled: bool = True
    rate_limit: float = 5.0  # 同一站点两次请求最小间隔（秒）
    license_note: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class ModelSpec(BaseModel):
    """LLM 任务档位（config/models.yaml）。"""

    provider: str = "dashscope"
    model: str = ""
    batch: bool = False
    price_in: float = 0.0  # 元/百万输入 token（仅估算）
    price_out: float = 0.0  # 元/百万输出 token（仅估算）
    disable_thinking: bool = True


@lru_cache
def load_sites() -> list[SiteConfig]:
    sites_file = CONFIG_DIR / "sites.yaml"
    raw = yaml.safe_load(sites_file.read_text(encoding="utf-8")) or {}
    return [SiteConfig(**s) for s in raw.get("sites", [])]


@lru_cache
def load_models() -> dict[str, ModelSpec]:
    models_file = CONFIG_DIR / "models.yaml"
    raw = yaml.safe_load(models_file.read_text(encoding="utf-8")) or {}
    return {task: ModelSpec(**spec) for task, spec in raw.get("tasks", {}).items()}

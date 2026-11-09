# ============================================================
# 来源权威度：把爬虫站点档案的 authority_weight 映射到知识库文档来源
#
# 知识库文档只保留 source_url，不含爬虫侧 site_id，因此按域名匹配：
# 站点档案中的 base_url 与 config 内所有 URL 字段都作为该站点的可识别域名，
# 支持子域名归并（docs.espressif.com → espressif.com，
# www.espressif.com.cn → espressif.com.cn）。
# 检索融合时按权威度加权，官方文档优先于论坛转载。
#
# 站点档案优先读 config/sites.yaml；PyYAML 缺失时回退读爬虫库 sites 表。
# ============================================================

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.core.config import BASE_DIR

logger = logging.getLogger(__name__)

_SITES_FILE = Path(BASE_DIR) / "crawler" / "config" / "sites.yaml"
_CRAWLER_DB = Path(os.environ.get("KB_DATA_DIR") or (Path(BASE_DIR) / "crawler" / "data")) / "db" / "crawler.db"

# 两级公共后缀（避免把 espressif.com.cn 误归并为 com.cn）
_CCTLD_2 = {
    "com.cn", "net.cn", "org.cn", "edu.cn", "gov.cn",
    "com.hk", "com.tw", "co.uk", "org.uk", "co.jp", "com.au",
}

# (数据源签名, 域名 → (权威度, 站点名))
_cache: Optional[Tuple[Tuple, Dict[str, Tuple[float, str]]]] = None


def _strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def _parent_domain(host: str) -> Optional[str]:
    """取可注册域名（两级后缀时取三级），用于子域名归并"""
    labels = host.split(".")
    if len(labels) < 2:
        return None
    tail2 = ".".join(labels[-2:])
    if tail2 in _CCTLD_2 and len(labels) >= 3:
        return ".".join(labels[-3:])
    return tail2


def _collect_hosts(value, hosts: set) -> None:
    """递归收集配置中的 URL 域名"""
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            host = (urlparse(value).hostname or "").lower()
            if host:
                hosts.add(host)
                hosts.add(_strip_www(host))
    elif isinstance(value, dict):
        for v in value.values():
            _collect_hosts(v, hosts)
    elif isinstance(value, list):
        for v in value:
            _collect_hosts(v, hosts)


def _build_mapping(sites: List[dict]) -> Dict[str, Tuple[float, str]]:
    """把站点档案列表转换为 域名 → (authority_weight, 站点名) 映射"""
    mapping: Dict[str, Tuple[float, str]] = {}
    for site in sites:
        if not site.get("enabled", True):
            continue
        try:
            weight = float(site.get("authority_weight") or 1.0)
        except (TypeError, ValueError):
            weight = 1.0
        site_name = site.get("name") or site.get("code") or ""

        hosts: set = set()
        _collect_hosts(site.get("base_url") or "", hosts)
        config = site.get("config") or site.get("config_json") or {}
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except ValueError:
                config = {}
        _collect_hosts(config, hosts)

        for host in hosts:
            # 同一域名多个站点时取权威度更高的站点
            if host not in mapping or weight > mapping[host][0]:
                mapping[host] = (weight, site_name)
    return mapping


def _load_from_yaml() -> Optional[Dict[str, Tuple[float, str]]]:
    """从 config/sites.yaml 读取（PyYAML 缺失/解析失败返回 None）"""
    try:
        import yaml

        raw = yaml.safe_load(_SITES_FILE.read_text(encoding="utf-8")) or {}
        return _build_mapping(raw.get("sites", []))
    except Exception as e:
        logger.warning(f"读取 sites.yaml 失败，尝试回退爬虫库: {e}")
        return None


def _load_from_crawler_db() -> Optional[Dict[str, Tuple[float, str]]]:
    """回退方案：读爬虫库 sites 表（不依赖 PyYAML）"""
    if not _CRAWLER_DB.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{_CRAWLER_DB}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT name, base_url, authority_weight, config_json, enabled FROM sites"
            ).fetchall()
        finally:
            conn.close()
        sites = [
            {
                "name": name,
                "base_url": base_url or "",
                "authority_weight": weight,
                "config_json": config_json or "{}",
                "enabled": bool(enabled),
            }
            for name, base_url, weight, config_json, enabled in rows
        ]
        return _build_mapping(sites)
    except Exception as e:
        logger.warning(f"读取爬虫库站点档案失败: {e}")
        return None


def _load_authority_map() -> Dict[str, Tuple[float, str]]:
    """读取站点档案并缓存；站点档案/爬虫库任一变化后自动重建"""
    global _cache

    signature = []
    for path in (_SITES_FILE, _CRAWLER_DB):
        try:
            signature.append(path.stat().st_mtime)
        except OSError:
            signature.append(0)

    sig = tuple(signature)
    if _cache is not None and _cache[0] == sig:
        return _cache[1]

    mapping = _load_from_yaml()
    if mapping is None:
        mapping = _load_from_crawler_db() or {}

    _cache = (sig, mapping)
    return mapping


def get_source_authority(source_url: str) -> Tuple[float, str]:
    """
    解析来源地址对应的权威度。

    返回: (authority_weight, 站点名)；未匹配站点档案时返回 (1.0, "")
    """
    if not source_url:
        return (1.0, "")

    host = (urlparse(source_url).hostname or "").lower()
    if not host:
        return (1.0, "")

    mapping = _load_authority_map()
    for candidate in (host, _strip_www(host), _parent_domain(host)):
        if candidate and candidate in mapping:
            return mapping[candidate]
    return (1.0, "")


def authority_label(weight: float) -> str:
    """把权威度数值转成给用户/重排器看的标签"""
    if weight >= 1.3:
        return "官方文档"
    if weight >= 1.0:
        return "社区资料"
    return "转载内容"

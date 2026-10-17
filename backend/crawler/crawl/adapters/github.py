"""GitHub 适配器：两种模式。

- search 模式（默认）：官方 Search API 拉取近 N 天新建的高星仓库；
  限流：匿名 10 次/小时；配 GITHUB_TOKEN 后 5000 次/小时。
- repo 模式：指定仓库（如 espressif/esp-idf），采集仓库元数据 +
  最新 N 条 release notes + README（高质量技术事实来源）。
"""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timedelta

import httpx

from ...settings import get_settings
from ...timeutil import utcnow
from ..politeness import wait_before_request
from .base import RawItem

log = logging.getLogger(__name__)


def fetch(site, http: httpx.Client) -> list[RawItem]:
    cfg = getattr(site, "config_json", None) or getattr(site, "config", None) or {}
    if cfg.get("mode") == "repo":
        return _fetch_repo(site, http, cfg)
    return _fetch_search(site, http, cfg)


def _headers(settings) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    token = settings.github_token or os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_search(site, http: httpx.Client, cfg: dict) -> list[RawItem]:
    settings = get_settings()
    since_days = int(cfg.get("since_days", 2))
    min_stars = int(cfg.get("min_stars", 80))
    per_page = int(cfg.get("per_page", 30))
    since = (utcnow() - timedelta(days=since_days)).strftime("%Y-%m-%d")

    base = site.base_url or "https://api.github.com/search/repositories"
    params = {
        "q": f"created:>={since} stars:>{min_stars}",
        "sort": "stars",
        "order": "desc",
        "per_page": per_page,
    }
    resp = http.get(base, params=params, headers=_headers(settings),
                    timeout=settings.crawl_timeout_seconds)
    if resp.status_code == 403:
        log.warning("GitHub API 限流（403），本次跳过")
        return []
    resp.raise_for_status()
    data = resp.json()

    items: list[RawItem] = []
    for repo in data.get("items", []):
        description = (repo.get("description") or "").strip()
        text_parts = [description, f"语言: {repo.get('language') or 'N/A'}",
                      f"主题: {' '.join(repo.get('topics') or [])}"]
        created = repo.get("created_at")
        published = None
        if created:
            published = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
        items.append(RawItem(
            url=repo.get("html_url", ""),
            title=f"{repo.get('full_name', '')}：{description}"[:500],
            content_text="\n".join(text_parts),
            published_at=published,
            author=(repo.get("owner") or {}).get("login", ""),
            meta={
                "stars": int(repo.get("stargazers_count") or 0),
                "forks": int(repo.get("forks_count") or 0),
                "language": repo.get("language") or "",
                "topics": repo.get("topics") or [],
            },
        ))
    return items


def _fetch_repo(site, http: httpx.Client, cfg: dict) -> list[RawItem]:
    """repo 模式：仓库元数据 + 最新 releases + README。"""
    settings = get_settings()
    owner = (cfg.get("owner") or "").strip()
    repo = (cfg.get("repo") or "").strip()
    if not owner or not repo:
        log.warning("站点 %s repo 模式缺 owner/repo 配置，跳过", site.code)
        return []
    headers = _headers(settings)
    api = "https://api.github.com"
    items: list[RawItem] = []

    def get(path: str, **kwargs) -> httpx.Response:
        wait_before_request(site.code, site.rate_limit)
        return http.get(f"{api}{path}", headers=headers,
                        timeout=settings.crawl_timeout_seconds, **kwargs)

    # 1. 仓库元数据
    resp = get(f"/repos/{owner}/{repo}")
    if resp.status_code == 404:
        log.warning("GitHub 仓库 %s/%s 不存在或无权访问，跳过", owner, repo)
        return []
    if resp.status_code == 403:
        log.warning("GitHub API 限流（403），跳过站点 %s", site.code)
        return []
    resp.raise_for_status()
    meta = resp.json()
    parts = [
        meta.get("description") or "",
        f"主页: {meta.get('homepage') or '无'}",
        f"语言: {meta.get('language') or 'N/A'}",
        f"主题: {' '.join(meta.get('topics') or [])}",
        f"Star: {meta.get('stargazers_count') or 0}  Fork: {meta.get('forks_count') or 0}",
        f"许可证: {(meta.get('license') or {}).get('spdx_id') or 'N/A'}",
    ]
    items.append(RawItem(
        url=meta.get("html_url", f"https://github.com/{owner}/{repo}"),
        title=f"{owner}/{repo}：{meta.get('description') or '仓库元数据'}"[:500],
        content_text="\n".join(parts),
        published_at=_parse_iso(meta.get("created_at")),
        author=owner,
        meta={"stars": int(meta.get("stargazers_count") or 0),
              "language": meta.get("language") or "",
              "topics": meta.get("topics") or []},
    ))

    # 2. 最新 N 条 release notes（高质量技术事实：芯片支持/API 变更）
    releases = int(cfg.get("releases", 5))
    resp = get(f"/repos/{owner}/{repo}/releases", params={"per_page": releases})
    if resp.status_code == 200:
        for rel in resp.json():
            body = (rel.get("body") or "").strip()
            if not body:
                continue
            items.append(RawItem(
                url=rel.get("html_url", ""),
                title=f"Release {rel.get('tag_name', '')}：{rel.get('name', '')}"[:500],
                content_text=body[:5000],
                published_at=_parse_iso(rel.get("published_at") or rel.get("created_at")),
                author=owner,
                meta={"type": "release", "tag": rel.get("tag_name", "")},
            ))
    else:
        log.warning("GitHub releases 拉取失败（%d），继续 README", resp.status_code)

    # 3. README（仓库说明，官方内容）
    resp = get(f"/repos/{owner}/{repo}/readme")
    if resp.status_code == 200:
        readme = resp.json()
        try:
            content = base64.b64decode(readme.get("content") or "").decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            content = ""
        if content:
            items.append(RawItem(
                url=f"https://github.com/{owner}/{repo}#readme",
                title=f"{owner}/{repo} README"[:500],
                content_text=content[:20000],
                author=owner,
                meta={"type": "readme"},
            ))
    return items


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None

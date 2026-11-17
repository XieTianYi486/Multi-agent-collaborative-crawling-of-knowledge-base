"""补采侦察 Agent（Scout）：把「知识库答不上来的问题」变成可抓取的候选 URL。

职责边界：只做检索与排序，不判断内容质量（内容判断交给后续审核 Agent）。

检索通道全部为站点内检索，无需额外搜索服务密钥：
- github_repo   GitHub 仓库搜索 API（按 star 排序，教程/知识体系类问题更对口）
- github        GitHub Issues 搜索 API（配置 GITHUB_TOKEN 可提高限额）
- stackoverflow StackExchange API（Stack Overflow）
- electronics  StackExchange API（Electronics，硬件电路问题更对口）

esp32.com 论坛有 JS 机器人挑战，无法直接抓取搜索结果，因此不作为检索通道。

LLM 只用于生成检索式；不可用/超预算时退化为规则检索式，流水线照常运行。
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass

import httpx
import yaml

from ..llm import registry, usage
from ..llm.base import parse_json_response
from ..settings import CONFIG_DIR, get_settings
from ..store.models import DiscoveryQueue

log = logging.getLogger(__name__)

CHANNELS = ("github_repo", "github", "stackoverflow", "electronics")
_PROMPT_FILE = CONFIG_DIR / "prompts" / "scout.md"
_SEEDS_FILE = CONFIG_DIR / "seeds.yaml"

_ASCII_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-_.+]{1,}")
_CN_RE = re.compile(r"[\u4e00-\u9fff]+")
_CN_STOP = {"如何", "怎么", "怎样", "什么", "为什", "是否", "可以", "能否", "请问", "一下"}

# 通道权威度：问答社区的二手经验略降权
_CHANNEL_WEIGHT = {"github_repo": 1.0, "github": 1.0, "stackoverflow": 1.0, "electronics": 0.95}

# 不适合课堂教学的候选特征（面试题库、资源清单、招聘），命中后降权
_NEGATIVE_RE = re.compile(r"面试|面经|interview|awesome|简历|招聘|求职", re.I)

# 入门/教程类特征，命中后加权
_TEACHING_RE = re.compile(r"入门|教程|教学|学习|tutorial|course|learn|basics|getting started", re.I)


def _term_re(term: str) -> re.Pattern[str]:
    """英文术语词边界匹配；允许术语后接数字（java 可命中 java8），避免命中 javascript。"""
    return re.compile(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z_])", re.I)


@dataclass
class Candidate:
    channel: str
    url: str
    title: str
    snippet: str = ""
    score: float = 0.0


def _seed_candidates(question: str) -> list[Candidate]:
    """命中种子关键词时，返回官方/权威教程 URL（高优先，先于检索结果入队）。"""
    if not _SEEDS_FILE.exists():
        return []
    try:
        raw = yaml.safe_load(_SEEDS_FILE.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        log.warning("seeds.yaml 解析失败，跳过种子源: %s", exc)
        return []

    ql = question.lower()
    out: list[Candidate] = []
    for item in raw.get("seeds") or []:
        keywords = [str(k).lower() for k in item.get("keywords") or []]
        if not keywords or not any(k in ql for k in keywords):
            continue
        for url in item.get("urls") or []:
            out.append(Candidate(
                channel="official",
                url=str(url),
                title=str(item.get("title") or url),
                snippet="官方入门教程",
            ))
    return out


def discover(session, request_id: int, question: str, limit: int = 8) -> int:
    """检索候选 URL 并写入 discovery_queue，返回新入队数量。"""
    question = (question or "").strip()
    if not question:
        return 0

    queries = _plan_queries(session, question)
    settings = get_settings()
    candidates: list[Candidate] = _seed_candidates(question)
    with httpx.Client(
        headers={"User-Agent": settings.crawl_user_agent},
        timeout=settings.crawl_timeout_seconds,
        follow_redirects=True,
    ) as http:
        for channel, query in queries:
            try:
                candidates.extend(_search(http, channel, query, limit))
            except Exception as exc:  # noqa: BLE001 - 单通道失败不影响其他通道
                log.warning("检索通道 %s 失败（%s）: %s", channel, query, exc)

    # URL 去重 → 相关度打分 → 取前 N
    seen: set[str] = set()
    unique: list[Candidate] = []
    for c in candidates:
        if not c.url or c.url in seen:
            continue
        seen.add(c.url)
        c.score = _score(question, c)
        unique.append(c)
    unique.sort(key=lambda c: c.score, reverse=True)

    queued = 0
    for c in unique:
        if queued >= limit:
            break
        if c.score <= 0:  # 与本问题无关的误命中不入队
            continue
        existing = (
            session.query(DiscoveryQueue)
            .filter(DiscoveryQueue.url == c.url[:1024])
            .first()
        )
        if existing is not None:
            # URL 全局唯一：历史上失败的候选允许"重挂"到新需求上重试，
            # 否则 transient 故障（GitHub 429 / 熔断）会让该 URL 永远死路
            if existing.status in ("failed", "skipped"):
                existing.request_id = request_id
                existing.status = "queued"
                existing.error = None
                existing.fetched_at = None
                queued += 1
            continue
        session.add(DiscoveryQueue(
            request_id=request_id,
            channel=c.channel,
            url=c.url[:1024],
            title=c.title[:512],
            snippet=c.snippet[:1000],
            score=c.score,
        ))
        queued += 1

    if queued == 0:
        # 哨兵行：本轮确实侦察过该需求但没有可入队的候选。
        # 没有它的话，resolve 无法区分"候选全被去重（应留到下一轮）"和
        # "确实没搜到（应标记未匹配）"——区分不出来就只能永久空转或永久误杀。
        sentinel_url = f"none://{request_id}"
        sentinel = (
            session.query(DiscoveryQueue)
            .filter(DiscoveryQueue.url == sentinel_url)
            .first()
        )
        if sentinel is None:
            session.add(DiscoveryQueue(
                request_id=request_id,
                channel="scout",
                url=sentinel_url,
                title="本轮未检索到可用候选",
                snippet="",
                score=0,
                status="skipped",
            ))
        else:
            # 需求重试多轮仍未出结果：复用哨兵行（url 唯一约束）
            sentinel.status = "skipped"
            sentinel.title = "本轮未检索到可用候选"
    session.flush()
    log.info("补采需求 #%d 侦察完成：检索 %d 条，入队 %d 条", request_id, len(unique), queued)
    return queued


# ---------------------------------------------------------------- 检索式


def _plan_queries(session, question: str) -> list[tuple[str, str]]:
    spec = registry.get_spec("scout")
    provider = registry.get_chat_provider()
    if spec is not None and provider is not None:
        try:
            usage.ensure_budget(session, "scout")
            system = _PROMPT_FILE.read_text(encoding="utf-8")
            resp = provider.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"用户问题：{question[:500]}"},
                ],
                spec.model,
                json_mode=True,
                disable_thinking=spec.disable_thinking,
                max_tokens=500,
                temperature=0.2,
            )
            usage.record_call(
                session, task="scout", spec=spec, batch=False,
                tokens_in=max(resp.tokens_in, 1), tokens_out=max(resp.tokens_out, 1),
                latency_ms=resp.latency_ms,
            )
            data = parse_json_response(resp.content) or {}
            planned: list[tuple[str, str]] = []
            for item in data.get("queries", []):
                channel = str(item.get("channel", "")).strip()
                query = str(item.get("query", "")).strip()
                if channel in CHANNELS and query:
                    planned.append((channel, query[:120]))
            if planned:
                return planned[:4]
        except Exception as exc:  # noqa: BLE001 - LLM 不可用则退化
            log.warning("侦察 Agent 生成检索式失败，回退规则检索式: %s", exc)

    return _fallback_queries(question)


def _fallback_queries(question: str) -> list[tuple[str, str]]:
    """规则检索式：优先用问题里的英文/数字术语，没有则取问题前 60 字。

    教程/知识体系类问题（Java、Python 等）优先走仓库检索，仓库主页的 README
    通常就是成体系的入门材料，比 issue 讨论更接近“教学资料”。
    """
    terms = _ASCII_RE.findall(question)
    key = " ".join(dict.fromkeys(terms))[:80] or question[:60]
    # 找教学资料/入门学习类诉求：只写语言名会命中面试题库与 awesome 清单，
    # 补上教程类限定词，命中成体系的入门教程与官方文档
    if any(w in question for w in ("教学", "入门", "新手", "学习", "教程", "资料", "课程")):
        key = f"{key} tutorial 入门"
    return [("github_repo", key), ("stackoverflow", key), ("github", key)]


# ---------------------------------------------------------------- 各通道检索


def _channel_query(channel: str, query: str) -> str:
    """按通道适配检索式。

    GitHub 的仓库/issue 搜索对中文分词支持很差，"Java 教程 入门 基础语法"
    这种长中文检索式几乎命中不到东西，因此只保留英文/数字术语；
    仓库通道再补 tutorial 限定词，避免只命中面试题库与资源清单。
    """
    if channel not in ("github_repo", "github") or query.isascii():
        return query
    ascii_part = " ".join(dict.fromkeys(_ASCII_RE.findall(query)))
    if not ascii_part:
        return query
    # 词太多会让 GitHub 全词匹配过严，只保留前 4 个术语
    ascii_part = " ".join(ascii_part.split()[:4])
    if channel == "github_repo" and "tutorial" not in ascii_part.lower():
        ascii_part = f"{ascii_part} tutorial"
    return ascii_part


def _search(http: httpx.Client, channel: str, query: str, limit: int) -> list[Candidate]:
    query = _channel_query(channel, query)
    if channel == "github_repo":
        return _search_github_repos(http, query, limit)
    if channel == "github":
        return _search_github(http, query, limit)
    if channel == "stackoverflow":
        return _search_stackexchange(http, query, "stackoverflow", channel, limit)
    if channel == "electronics":
        return _search_stackexchange(http, query, "electronics", channel, limit)
    return []


def _search_github_repos(http: httpx.Client, query: str, limit: int) -> list[Candidate]:
    """GitHub 仓库检索（按 star 降序）：教程/awesome 清单/官方示例的命中率更高。"""
    settings = get_settings()
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    resp = http.get(
        "https://api.github.com/search/repositories",
        params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
        headers=headers,
    )
    resp.raise_for_status()
    result: list[Candidate] = []
    for item in resp.json().get("items", []):
        result.append(Candidate(
            channel="github_repo",
            url=str(item.get("html_url", "")),
            title=str(item.get("full_name", "")),
            snippet=str(item.get("description") or "")[:300],
        ))
    return result


def _search_github(http: httpx.Client, query: str, limit: int) -> list[Candidate]:
    settings = get_settings()
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    resp = http.get(
        "https://api.github.com/search/issues",
        params={"q": f"{query} in:title,body", "per_page": limit},
        headers=headers,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    result: list[Candidate] = []
    for item in items:
        if "pull_request" in item:  # 只保留 issue / discussion
            continue
        result.append(Candidate(
            channel="github",
            url=str(item.get("html_url", "")),
            title=str(item.get("title", "")),
            snippet=str(item.get("body") or "")[:300],
        ))
    return result


def _search_stackexchange(
    http: httpx.Client, query: str, site: str, channel: str, limit: int,
) -> list[Candidate]:
    resp = http.get(
        "https://api.stackexchange.com/2.3/search/advanced",
        params={
            "order": "desc",
            "sort": "relevance",
            "q": query,
            "site": site,
            "pagesize": limit,
        },
    )
    resp.raise_for_status()
    result: list[Candidate] = []
    for item in resp.json().get("items", []):
        result.append(Candidate(
            channel=channel,
            url=str(item.get("link", "")),
            title=html.unescape(str(item.get("title", ""))),
            snippet="",
        ))
    return result


# ---------------------------------------------------------------- 相关度


def _terms(text: str) -> set[str]:
    """英文术语 + 中文二元组（去疑问词），用于相关度粗排。"""
    out = {t.lower() for t in _ASCII_RE.findall(text or "") if len(t) >= 2}
    for seg in _CN_RE.findall(text or ""):
        for i in range(len(seg) - 1):
            gram = seg[i:i + 2]
            if gram not in _CN_STOP:
                out.add(gram)
    return out


def _score(question: str, c: Candidate) -> float:
    # 种子源是官方/权威教程，关键词已命中，固定最高优先级
    if c.channel == "official":
        return 200.0
    qt = _terms(question)
    if not qt:
        return 0.0
    haystack = f"{c.title} {c.snippet}".lower()
    hits = 0
    for t in qt:
        if t.isascii():
            # 英文术语按词边界匹配，避免 java 命中 javascript、c 命中 css
            if _term_re(t).search(haystack):
                hits += 1
        elif t in haystack:
            hits += 1
    score = hits / len(qt) * 100 * _CHANNEL_WEIGHT.get(c.channel, 0.8)
    # 仓库通道：标题/简介里没有任何问题相关的英文技术词，说明是误命中，直接丢弃
    ascii_terms = [t for t in _ASCII_RE.findall(question) if len(t) > 1]
    if c.channel == "github_repo" and ascii_terms:
        if not any(_term_re(t).search(haystack) for t in ascii_terms):
            return 0.0
    # 入门教程类材料加权：新手教学资料优先于速查/源码仓库
    if _TEACHING_RE.search(haystack):
        score += 15
    # 面试题库、资源清单类仓库不适合课堂教学，降权
    if _NEGATIVE_RE.search(haystack):
        score *= 0.4
    return round(score, 2)

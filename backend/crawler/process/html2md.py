"""HTML → Markdown：trafilatura 主选，readability + markdownify 回退。

统一格式目标：所有文档最终为「Markdown + 元数据」，便于教学资料复用。
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def html_to_markdown(html: str, url: str = "") -> tuple[str, str]:
    """返回 (markdown, 纯文本)；失败返回 ("", "")。"""
    if not html or not html.strip():
        return "", ""
    try:
        import trafilatura

        md = trafilatura.extract(
            html,
            url=url or None,
            output_format="markdown",
            include_images=True,
            include_links=True,
        )
        if md:
            text = trafilatura.extract(html, url=url or None, output_format="text") or ""
            return md.strip(), text.strip()
    except Exception as exc:  # noqa: BLE001
        log.debug("trafilatura 解析失败，尝试回退: %s", exc)

    # 回退：readability 提取正文 → markdownify 转 Markdown
    try:
        from markdownify import markdownify
        from readability import Document

        article = Document(html).summary()
        md = markdownify(article, heading_style="ATX").strip()
        if md:
            text = markdownify(article, heading_style="ATX", strip=["a", "img"]).strip()
            # markdownify 的 strip 输出仍可能带 markdown 符号，简单清理
            import re

            text = re.sub(r"[#*`>\[\]()!-]", " ", text)
            return md, re.sub(r"\s+", " ", text).strip()
    except Exception as exc:  # noqa: BLE001
        log.debug("readability 回退也失败: %s", exc)

    return "", ""

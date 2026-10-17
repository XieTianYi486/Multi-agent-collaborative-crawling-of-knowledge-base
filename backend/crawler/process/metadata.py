"""元数据构建：来源、授权信息随文档入库（版权合规要求）。"""
from __future__ import annotations

from ..timeutil import utcnow


def build_meta(site, item) -> dict:
    """组装文档元数据（含授权等级与依据，检索/报告必须展示）。"""
    return {
        "source_url": item.url,
        "site_code": site.code,
        "site_name": site.name,
        "risk_level": site.risk_level,
        "license_note": site.license_note,
        "author": item.author,
        "tags": item.meta.get("tags", []),
        "fetched_at": utcnow().isoformat(),
        "usage_scope": "校内教学，不对外分发",
    }

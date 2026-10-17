"""DashScope 批量接口封装（实时价 5 折，用于每日打标/摘要等大批量任务）。

流程：组装 JSONL → 上传 files → 创建 batch → 轮询 → 下载结果解析。
任何环节失败返回 None，由调用方自动回退为顺序调用，保证流水线可用性。
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from openai import OpenAI

from ..settings import DATA_DIR, get_settings

log = logging.getLogger(__name__)

BATCH_ENDPOINT = "/v1/chat/completions"


class BatchClient:
    """批量对话客户端。submit() 成功返回 {custom_id: (content, tokens_in, tokens_out)}。"""

    def __init__(self, client: OpenAI):
        self._client = client
        self._settings = get_settings()

    def submit(
        self,
        requests: list[dict],
        model: str,
        *,
        json_mode: bool = True,
        disable_thinking: bool = True,
        max_tokens: int = 2000,
    ) -> dict[str, tuple[str, int, int]] | None:
        """requests: [{"custom_id": str, "messages": [...]}]。

        返回 {custom_id: (content, tokens_in, tokens_out)}；任何环节失败返回 None。
        """
        if not requests:
            return {}
        try:
            return self._submit(requests, model, json_mode, disable_thinking, max_tokens)
        except Exception as exc:  # noqa: BLE001 - 批量接口失败必须兜底
            log.warning("批量接口调用失败，将回退顺序调用: %s", exc)
            return None

    def _submit(
        self,
        requests: list[dict],
        model: str,
        json_mode: bool,
        disable_thinking: bool,
        max_tokens: int,
    ) -> dict[str, tuple[str, int, int]]:
        lines = []
        for r in requests:
            body: dict = {
                "model": model,
                "messages": r["messages"],
                "max_tokens": max_tokens,
                "temperature": 0.2,
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            if disable_thinking:
                body["enable_thinking"] = False
            lines.append({
                "custom_id": r["custom_id"],
                "method": "POST",
                "url": BATCH_ENDPOINT,
                "body": body,
            })
        tmp_dir = DATA_DIR / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = tmp_dir / f"batch_{uuid.uuid4().hex[:12]}.jsonl"
        jsonl_path.write_text(
            "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n",
            encoding="utf-8",
        )

        with open(jsonl_path, "rb") as f:
            file_obj = self._client.files.create(file=f, purpose="batch")
        batch = self._client.batches.create(
            input_file_id=file_obj.id,
            endpoint=BATCH_ENDPOINT,
            completion_window="24h",
        )
        log.info("批量任务已创建：%s（%d 条请求），等待完成…", batch.id, len(requests))

        poll_interval = 30.0
        deadline = time.monotonic() + self._settings.llm_batch_poll_timeout_seconds
        # 提前回退：排队超过 N 秒且一条都没完成 → 取消并回退顺序调用（只检查一次）
        early_deadline = time.monotonic() + self._settings.llm_batch_early_fallback_seconds
        early_checked = False
        status = batch.status
        while status not in ("completed", "failed", "expired", "cancelled"):
            if time.monotonic() > deadline:
                log.warning("批量任务 %s 超时未完成，放弃等待", batch.id)
                return None
            if not early_checked and time.monotonic() > early_deadline:
                early_checked = True
                try:
                    info = self._client.batches.retrieve(batch.id)
                    counts = info.request_counts
                    if info.status == "in_progress" and counts and counts.completed == 0:
                        log.warning(
                            "批量任务 %s 排队超过 %d 秒且 0 完成，取消并回退顺序调用",
                            batch.id, self._settings.llm_batch_early_fallback_seconds,
                        )
                        self._client.batches.cancel(batch.id)
                        return None
                except Exception as exc:  # noqa: BLE001 - 检查失败不影响主轮询
                    log.debug("批量任务提前回退检查失败: %s", exc)
            time.sleep(poll_interval)
            status = self._client.batches.retrieve(batch.id).status
            log.info("批量任务 %s 状态：%s", batch.id, status)
        if status != "completed" or not batch.output_file_id:
            log.warning("批量任务 %s 状态为 %s", batch.id, status)
            return None

        content = self._client.files.content(batch.output_file_id).text
        results: dict[str, tuple[str, int, int]] = {}
        for line in content.splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            body = record.get("response", {}).get("body", {})
            choices = body.get("choices") or []
            if not choices:
                continue
            usage = body.get("usage") or {}
            text = (choices[0].get("message", {}).get("content") or "").strip()
            results[str(record.get("custom_id"))] = (
                text,
                int(usage.get("prompt_tokens") or 0),
                int(usage.get("completion_tokens") or 0),
            )
        return results

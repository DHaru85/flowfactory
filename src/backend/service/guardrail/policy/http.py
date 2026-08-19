"""HTTP 策略服务适配。缺 URL 不发网。"""

from __future__ import annotations

from loguru import logger

from service.guardrail.schemas import GuardrailHit, GuardrailStage, ViolationAction
from settings.config import get_settings


class HttpPolicyDetector:
    def __init__(self, *, url: str | None = None, timeout_seconds: float | None = None) -> None:
        cfg = get_settings()
        self._url = (url if url is not None else cfg.guardrail_policy_url).strip()
        self._timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else cfg.guardrail_policy_timeout_seconds
        )

    async def detect(self, text: str, stage: GuardrailStage) -> list[GuardrailHit]:
        if not self._url:
            return []
        try:
            import httpx
        except ImportError:
            logger.error("未安装 httpx，跳过远程护栏")
            return []
        payload = {"text": text, "stage": stage}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._url, json=payload)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.exception("远程护栏检测失败 url={}", self._url)
            return []
        return _parse_hits(body, stage)


def _parse_hits(body: object, stage: GuardrailStage) -> list[GuardrailHit]:
    if not isinstance(body, dict):
        return []
    raw = body.get("hits")
    if not isinstance(raw, list):
        return []
    hits: list[GuardrailHit] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("rule_code") or "remote")
        action_raw = str(item.get("action") or "log").lower()
        action: ViolationAction = "log"
        if action_raw in {"block", "mask", "log"}:
            action = action_raw  # type: ignore[assignment]
        hits.append(
            GuardrailHit(
                rule_code=code,
                action=action,
                excerpt=str(item.get("excerpt") or "")[:200],
                rule_type=str(item.get("rule_type") or "remote"),
                stage=stage,
            )
        )
    return hits

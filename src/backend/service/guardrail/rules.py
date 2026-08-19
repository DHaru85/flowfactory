"""规则规格与本地匹配。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from loguru import logger

from service.guardrail.schemas import GuardrailHit, ViolationAction
from service.observability.redact import redact_text

_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_CN_MOBILE = re.compile(r"1[3-9]\d{9}")
_CN_ID = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_BANK_CARD = re.compile(r"(?<!\d)\d{16,19}(?!\d)")

_ACTION_RANK = {"block": 3, "mask": 2, "log": 1}

KNOWN_RULE_TYPES = frozenset({"jailbreak", "pii", "keyword"})


@dataclass
class RuleSpec:
    code: str
    name: str
    stage: str
    rule_type: str
    config: dict[str, object]
    rule_id: UUID | None = None


def _as_action(raw: object, default: ViolationAction) -> ViolationAction:
    text = str(raw or default).lower()
    if text in {"block", "mask", "log"}:
        return text  # type: ignore[return-value]
    return default


def _clip_excerpt(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def merge_action(hits: list[GuardrailHit]) -> ViolationAction | None:
    if not hits:
        return None
    best = hits[0]
    best_rank = _ACTION_RANK.get(best.action, 0)
    for hit in hits[1:]:
        rank = _ACTION_RANK.get(hit.action, 0)
        if rank > best_rank:
            best = hit
            best_rank = rank
    return best.action


def apply_masks(text: str, hits: list[GuardrailHit]) -> str:
    result = text
    for hit in hits:
        if hit.action != "mask":
            continue
        if hit.rule_type == "pii":
            result = redact_text(result)
            continue
        if hit.excerpt and hit.excerpt in result:
            result = result.replace(hit.excerpt, "***")
    return result


def match_rule(spec: RuleSpec, text: str, *, excerpt_limit: int) -> list[GuardrailHit]:
    if spec.rule_type not in KNOWN_RULE_TYPES:
        logger.warning("未知护栏 rule_type={} code={}", spec.rule_type, spec.code)
        return []
    if spec.rule_type == "jailbreak":
        return _match_patterns(spec, text, default_action="block", excerpt_limit=excerpt_limit)
    if spec.rule_type == "keyword":
        return _match_keywords(spec, text, excerpt_limit=excerpt_limit)
    return _match_pii(spec, text, excerpt_limit=excerpt_limit)


def _match_patterns(
    spec: RuleSpec,
    text: str,
    *,
    default_action: ViolationAction,
    excerpt_limit: int,
) -> list[GuardrailHit]:
    raw_patterns = spec.config.get("patterns")
    if not isinstance(raw_patterns, list):
        return []
    action = _as_action(spec.config.get("action"), default_action)
    hits: list[GuardrailHit] = []
    for item in raw_patterns:
        expr = str(item)
        try:
            matched = re.search(expr, text, flags=re.IGNORECASE)
        except re.error:
            logger.warning("护栏正则无效 code={} pattern={}", spec.code, expr)
            continue
        if matched is None:
            continue
        excerpt = _clip_excerpt(matched.group(0), excerpt_limit)
        hits.append(
            GuardrailHit(
                rule_code=spec.code,
                rule_id=spec.rule_id,
                action=action,
                excerpt=excerpt,
                rule_type=spec.rule_type,
                stage=spec.stage,  # type: ignore[arg-type]
            )
        )
        break
    return hits


def _match_keywords(spec: RuleSpec, text: str, *, excerpt_limit: int) -> list[GuardrailHit]:
    raw_words = spec.config.get("words")
    if not isinstance(raw_words, list) or not raw_words:
        return []
    action = _as_action(spec.config.get("action"), "mask")
    replacement = str(spec.config.get("replacement") or "***")
    lowered = text.lower()
    hits: list[GuardrailHit] = []
    for item in raw_words:
        word = str(item).strip()
        if not word:
            continue
        idx = lowered.find(word.lower())
        if idx < 0:
            continue
        original = text[idx : idx + len(word)]
        excerpt = _clip_excerpt(original, excerpt_limit)
        hits.append(
            GuardrailHit(
                rule_code=spec.code,
                rule_id=spec.rule_id,
                action=action,
                excerpt=excerpt,
                rule_type="keyword",
                stage=spec.stage,  # type: ignore[arg-type]
            )
        )
        if action == "mask":
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            text = pattern.sub(replacement, text)
            lowered = text.lower()
    return hits


def _match_pii(spec: RuleSpec, text: str, *, excerpt_limit: int) -> list[GuardrailHit]:
    action = _as_action(spec.config.get("action"), "mask")
    found: list[str] = []
    for pattern in (_EMAIL, _CN_ID, _CN_MOBILE, _BANK_CARD):
        found.extend(pattern.findall(text))
    extra = spec.config.get("extra_patterns")
    if isinstance(extra, list):
        for item in extra:
            try:
                found.extend(re.findall(str(item), text))
            except re.error:
                logger.warning("PII extra 正则无效 code={}", spec.code)
    if not found:
        return []
    excerpt = _clip_excerpt(" ".join(str(part) for part in found[:3]), excerpt_limit)
    return [
        GuardrailHit(
            rule_code=spec.code,
            rule_id=spec.rule_id,
            action=action,
            excerpt=excerpt,
            rule_type="pii",
            stage=spec.stage,  # type: ignore[arg-type]
        )
    ]

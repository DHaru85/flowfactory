"""空库时的内置最小规则集。"""

from __future__ import annotations

from service.guardrail.rules import RuleSpec

BUILTIN_JAILBREAK_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"you are now (DAN|unrestricted)",
    r"developer\s+mode",
    r"越狱",
    r"忽略(以上|之前的)(所有)?(指令|规则|提示)",
    r"无视(以上|之前的)规则",
]


def builtin_specs() -> list[RuleSpec]:
    return [
        RuleSpec(
            code="builtin.jailbreak",
            name="内置越狱启发式",
            stage="input",
            rule_type="jailbreak",
            config={"patterns": BUILTIN_JAILBREAK_PATTERNS, "action": "block"},
        ),
        RuleSpec(
            code="builtin.pii",
            name="内置 PII 遮蔽",
            stage="output",
            rule_type="pii",
            config={"action": "mask"},
        ),
        RuleSpec(
            code="builtin.keyword",
            name="内置敏感词",
            stage="output",
            rule_type="keyword",
            config={"words": [], "action": "mask", "replacement": "***"},
        ),
    ]

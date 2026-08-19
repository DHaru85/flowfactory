"""从库表与内置规则加载规格。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.security.models import GuardrailRule
from service.guardrail.builtin import builtin_specs
from service.guardrail.rules import RuleSpec
from service.persistence.factory import get_repositories
from settings.config import get_settings


def _from_row(row: GuardrailRule) -> RuleSpec:
    config = dict(row.config) if isinstance(row.config, dict) else {}
    return RuleSpec(
        code=row.code,
        name=row.name,
        stage=row.stage,
        rule_type=row.rule_type,
        config=config,
        rule_id=row.id,
    )


async def load_rule_specs(session: AsyncSession) -> list[RuleSpec]:
    repos = get_repositories(session)
    rows = await repos.security.list_enabled_rules()
    by_code = {row.code: _from_row(row) for row in rows}
    cfg = get_settings()
    if not cfg.guardrail_builtin_rules:
        return list(by_code.values())
    for spec in builtin_specs():
        if spec.code in by_code:
            continue
        row = GuardrailRule(
            code=spec.code,
            name=spec.name,
            stage=spec.stage,
            rule_type=spec.rule_type,
            config=spec.config,
            is_enabled=True,
        )
        await repos.security.rule.add(row)
        spec.rule_id = row.id
        by_code[spec.code] = spec
    return list(by_code.values())

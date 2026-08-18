"""Security 域仓储。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.security.models import GuardrailRule, PolicyViolation
from service.persistence.base import Repository


class SecurityRepository:
    """安全护栏聚合仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.rule = Repository(session, GuardrailRule)
        self.violation = Repository(session, PolicyViolation)

    async def list_enabled_rules(self, stage: str | None = None) -> list[GuardrailRule]:
        stmt = select(GuardrailRule).where(GuardrailRule.is_enabled.is_(True))
        if stage is not None:
            stmt = stmt.where(GuardrailRule.stage == stage)
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_rule_by_code(self, code: str) -> GuardrailRule | None:
        stmt = select(GuardrailRule).where(GuardrailRule.code == code)
        return await self._session.scalar(stmt)

    async def record_violation(self, violation: PolicyViolation) -> PolicyViolation:
        self._session.add(violation)
        await self._session.flush()
        return violation

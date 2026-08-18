"""Security 域仓储。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_schema.security.models import GuardrailRule, PolicyViolation
from service.persistence.base import Repository


class SecurityRepository:
    """安全护栏聚合仓储。"""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.rule = Repository(session, GuardrailRule)
        self.violation = Repository(session, PolicyViolation)

    def list_enabled_rules(self, stage: str | None = None) -> list[GuardrailRule]:
        stmt = select(GuardrailRule).where(GuardrailRule.is_enabled.is_(True))
        if stage is not None:
            stmt = stmt.where(GuardrailRule.stage == stage)
        return list(self._session.scalars(stmt).all())

    def get_rule_by_code(self, code: str) -> GuardrailRule | None:
        stmt = select(GuardrailRule).where(GuardrailRule.code == code)
        return self._session.scalar(stmt)

    def record_violation(self, violation: PolicyViolation) -> PolicyViolation:
        self._session.add(violation)
        self._session.flush()
        return violation

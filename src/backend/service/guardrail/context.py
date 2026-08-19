"""当前 Run 的护栏 Evaluator ContextVar。"""

from __future__ import annotations

from contextvars import ContextVar, Token

from service.guardrail.evaluator import GuardrailEvaluator

_current_evaluator: ContextVar[GuardrailEvaluator | None] = ContextVar(
    "flowfactory_guardrail_evaluator",
    default=None,
)


def get_current_evaluator() -> GuardrailEvaluator | None:
    return _current_evaluator.get()


def attach_evaluator(evaluator: GuardrailEvaluator) -> Token[GuardrailEvaluator | None]:
    return _current_evaluator.set(evaluator)


def reset_evaluator(token: Token[GuardrailEvaluator | None]) -> None:
    _current_evaluator.reset(token)


def reset_guardrail_context() -> None:
    _current_evaluator.set(None)

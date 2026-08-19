"""受限表达式求值。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.runtime.expr import ExprError, eval_expr, router_key  # noqa: E402


def test_path_compare_and_bool() -> None:
    state: dict[str, object] = {
        "messages": [],
        "variables": {"x": 1, "flag": True, "name": "ok"},
        "metadata": {},
    }
    assert eval_expr("variables.x == 1", state) is True
    assert eval_expr("variables.name != \"no\"", state) is True
    assert eval_expr("not variables.flag", state) is False
    assert eval_expr("(variables.x == 1) and (variables.flag == true)", state) is True
    assert router_key(eval_expr("variables.x == 2", state)) == "false"


def test_rejects_eval() -> None:
    with pytest.raises((ExprError, ValueError)):
        eval_expr("__import__('os')", {"messages": [], "variables": {}, "metadata": {}})

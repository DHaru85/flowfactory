"""Agent 内部 code 生成。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.agent_code import generate_agent_code  # noqa: E402


def test_generate_agent_code_prefix_and_length() -> None:
    code = generate_agent_code("profile")
    assert code.startswith("profile-")
    suffix = code.removeprefix("profile-")
    assert len(suffix) == 8
    assert suffix.isalnum()

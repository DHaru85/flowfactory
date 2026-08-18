"""运行时 Schema 冒烟。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.runtime.schemas import CeleryTaskEnvelope, RunStatePayload  # noqa: E402


def test_run_state_roundtrip() -> None:
    payload = RunStatePayload(messages=[{"role": "user", "content": "hi"}], variables={"k": 1})
    state = payload.to_graph_state()
    restored = RunStatePayload.from_graph_state(state)
    assert restored.variables["k"] == 1
    assert restored.messages[0]["content"] == "hi"


def test_celery_envelope_json() -> None:
    env = CeleryTaskEnvelope(
        task_name="run",
        run_id=uuid4(),
        flow_id=uuid4(),
        thread_id=uuid4(),
        langgraph_thread_id="t",
        input_payload=RunStatePayload(),
    )
    dumped = env.model_dump(mode="json")
    parsed = CeleryTaskEnvelope.model_validate(dumped)
    assert parsed.langgraph_thread_id == "t"

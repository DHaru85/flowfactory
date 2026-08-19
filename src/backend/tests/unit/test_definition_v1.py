"""FlowDefinitionV1 配置态校验（不依赖 compile）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.runtime.definition_v1 import (  # noqa: E402
    empty_flow_definition,
    parse_flow_definition,
    subgraph_flow_codes,
)


def test_empty_graph_is_valid() -> None:
    doc = empty_flow_definition()
    assert doc.schema_version == 1
    names = {ch.name for ch in doc.state.channels}
    assert names == {"messages", "variables", "metadata"}
    dumped = doc.model_dump(mode="json")
    again = parse_flow_definition(dumped)
    assert again.nodes[0].type == "start"


def test_two_starts_rejected() -> None:
    raw = empty_flow_definition().model_dump(mode="json")
    raw["nodes"].append(
        {"id": "start2", "type": "start", "title": None, "data": {"inject": []}}
    )
    with pytest.raises(ValidationError):
        parse_flow_definition(raw)


def test_unknown_edge_target_rejected() -> None:
    raw = empty_flow_definition().model_dump(mode="json")
    raw["edges"].append(
        {"id": "bad", "source": "start", "target": "missing", "label": None}
    )
    with pytest.raises(ValidationError):
        parse_flow_definition(raw)


def test_tool_output_must_be_variables() -> None:
    raw = empty_flow_definition().model_dump(mode="json")
    raw["nodes"].append(
        {
            "id": "t1",
            "type": "tool",
            "title": None,
            "data": {
                "tool_code": "kb_retrieve",
                "arguments_from": {},
                "output_to": "messages",
            },
        }
    )
    with pytest.raises(ValidationError):
        parse_flow_definition(raw)


def test_subgraph_codes() -> None:
    raw = empty_flow_definition().model_dump(mode="json")
    raw["nodes"].append(
        {
            "id": "sub",
            "type": "subgraph",
            "title": None,
            "data": {
                "flow_code": "child_flow",
                "version": None,
                "input_map": [],
                "output_map": [],
                "timeout_seconds": 30,
            },
        }
    )
    raw["edges"].append({"id": "e2", "source": "start", "target": "sub", "label": None})
    raw["edges"].append({"id": "e3", "source": "sub", "target": "end", "label": None})
    doc = parse_flow_definition(raw)
    assert subgraph_flow_codes(doc) == ["child_flow"]

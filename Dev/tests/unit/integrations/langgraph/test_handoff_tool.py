# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ``precept.integrations.langgraph.handoff_tool`` (PRC-014).

The LangGraph / langchain-core surface is faked in ``sys.modules`` before
import (AC: "mock the LangGraph pieces"), so these run without
``langgraph`` installed and are insulated from its API churn
(DEPENDENCIES.md section 4.1). The integration suite exercises the real
library.

LangGraph API surface depended on (documented so drift is detectable,
per DEPENDENCIES.md section 4.1 mitigation 4):

* ``langchain_core.tools.tool`` decorator + ``InjectedToolCallId``
* ``langchain_core.messages.ToolMessage``
* ``langgraph.prebuilt.InjectedState``
* ``langgraph.types.Command`` (with ``Command.PARENT``)
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from types import ModuleType
from typing import Any, ClassVar

import pytest

from precept.contract.registry import ContractRegistry
from precept.contract.schema import ContractFields, HandoffContract
from precept.errors import HandoffBlockedError
from precept.evaluator.engine import Evaluator
from precept.scoring.base import FieldScore, HandoffPayload, Scorer, ScoreResult


class _StubScorer(Scorer):
    name: ClassVar[str] = "stub"
    version: ClassVar[str] = "0.0.1"

    def __init__(self, *, score: float = 1.0) -> None:
        self._score = score

    def score(
        self, source: HandoffPayload, target: HandoffPayload, contract: HandoffContract
    ) -> ScoreResult:
        threshold = (
            contract.fields.min_fidelity if contract.fields.min_fidelity is not None else 0.5
        )
        field_scores = [
            FieldScore(
                field_name=n, score=self._score, method="stub", passed=self._score >= threshold
            )
            for n in contract.fields.required_fields
        ]
        return ScoreResult(
            overall_score=self._score,
            field_scores=field_scores,
            scorer_name=self.name,
            scorer_version=self.version,
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
        )


class _FakeToolMessage:
    def __init__(self, *, content: str, name: str, tool_call_id: str) -> None:
        self.content = content
        self.name = name
        self.tool_call_id = tool_call_id


class _FakeCommand:
    PARENT = "__parent__"

    def __init__(self, *, goto: str, update: dict[str, Any], graph: str) -> None:
        self.goto = goto
        self.update = update
        self.graph = graph


class _FakeTool:
    """Stand-in for a langchain ``StructuredTool``: keeps the wrapped
    function callable so the test can invoke the handoff directly."""

    def __init__(self, name: str, description: str, func: Any) -> None:
        self.name = name
        self.description = description
        self.func = func


def _fake_tool_decorator(name: str, *, description: str | None = None) -> Any:
    def _wrap(func: Any) -> _FakeTool:
        return _FakeTool(name, description or "", func)

    return _wrap


@pytest.fixture
def handoff_tool_mod() -> Any:
    """Import ``handoff_tool`` against faked langgraph/langchain modules,
    then remove it so real-library environments re-import cleanly."""
    fakes: dict[str, ModuleType] = {}

    lc_tools = ModuleType("langchain_core.tools")
    lc_tools.tool = _fake_tool_decorator  # type: ignore[attr-defined]
    lc_tools.InjectedToolCallId = type("InjectedToolCallId", (), {})  # type: ignore[attr-defined]
    lc_tools.BaseTool = _FakeTool  # type: ignore[attr-defined]

    lc_messages = ModuleType("langchain_core.messages")
    lc_messages.ToolMessage = _FakeToolMessage  # type: ignore[attr-defined]

    lc = ModuleType("langchain_core")

    lg_prebuilt = ModuleType("langgraph.prebuilt")
    lg_prebuilt.InjectedState = type("InjectedState", (), {})  # type: ignore[attr-defined]

    lg_types = ModuleType("langgraph.types")
    lg_types.Command = _FakeCommand  # type: ignore[attr-defined]

    lg = ModuleType("langgraph")

    fakes = {
        "langchain_core": lc,
        "langchain_core.tools": lc_tools,
        "langchain_core.messages": lc_messages,
        "langgraph": lg,
        "langgraph.prebuilt": lg_prebuilt,
        "langgraph.types": lg_types,
    }
    saved = {name: sys.modules.get(name) for name in fakes}
    sys.modules.update(fakes)
    sys.modules.pop("precept.integrations.langgraph.handoff_tool", None)
    try:
        yield importlib.import_module("precept.integrations.langgraph.handoff_tool")
    finally:
        sys.modules.pop("precept.integrations.langgraph.handoff_tool", None)
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _registry(*, mode: str) -> ContractRegistry:
    reg = ContractRegistry()
    reg.register(
        HandoffContract(name="r_to_s", mode=mode, fields=ContractFields(required_fields=["body"]))
    )
    return reg


def test_tool_created_with_valid_contract_evaluates_on_invocation(handoff_tool_mod: Any) -> None:
    rec_scores: list[float] = []

    class _Probe(_StubScorer):
        def score(
            self, source: HandoffPayload, target: HandoffPayload, contract: HandoffContract
        ) -> ScoreResult:
            rec_scores.append(1.0)
            return super().score(source, target, contract)

    tool = handoff_tool_mod.create_precept_handoff_tool(
        "summariser",
        "r_to_s",
        registry=_registry(mode="warn"),
        evaluator=Evaluator(_Probe()),
    )

    tool.func(state={"body": "hello"}, tool_call_id="call-1")

    assert rec_scores == [1.0]  # the contract was evaluated during invocation
    assert tool.name == "transfer_to_summariser"


def test_underlying_handoff_preserved_when_contract_passes(handoff_tool_mod: Any) -> None:
    tool = handoff_tool_mod.create_precept_handoff_tool(
        "summariser",
        "r_to_s",
        registry=_registry(mode="block"),
        evaluator=Evaluator(_StubScorer(score=1.0)),
    )

    command = tool.func(state={"body": "hello"}, tool_call_id="call-1")

    assert command.goto == "summariser"
    assert command.graph == "__parent__"
    messages = command.update["messages"]
    assert len(messages) == 1
    assert messages[0].tool_call_id == "call-1"
    assert messages[0].name == "transfer_to_summariser"


def test_block_mode_contract_failure_surfaces_as_raise(handoff_tool_mod: Any) -> None:
    tool = handoff_tool_mod.create_precept_handoff_tool(
        "summariser",
        "r_to_s",
        registry=_registry(mode="block"),
        evaluator=Evaluator(_StubScorer(score=0.1)),
    )

    # ToolNode converts a raised exception into an error ToolMessage to
    # the supervisor LLM (AC); at unit level we assert the raise.
    with pytest.raises(HandoffBlockedError):
        tool.func(state={"body": "hello"}, tool_call_id="call-1")


def test_custom_name_and_description_are_used(handoff_tool_mod: Any) -> None:
    tool = handoff_tool_mod.create_precept_handoff_tool(
        "writer",
        "r_to_s",
        registry=_registry(mode="warn"),
        evaluator=Evaluator(_StubScorer()),
        name="go_to_writer",
        description="Custom routing.",
    )

    assert tool.name == "go_to_writer"
    assert tool.description == "Custom routing."

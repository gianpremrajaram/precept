# SPDX-License-Identifier: MIT
"""Integration tests for the PRC-014 LangGraph paths.

Exercises both surfaces against the *real* pinned ``langgraph`` (and
``langgraph_supervisor`` for the supervisor case). This file is the
CI-gated drift detector called for in DEPENDENCIES.md section 4.1
(mitigations 3 and 5): it runs on every PR against ``langgraph>=0.5,<0.7``
and a pinned ``langgraph-supervisor``; an upstream API change surfaces
here. ``importorskip`` keeps it collectable (skipped, not errored) in
environments without the libraries -- e.g. the maintainer's local
interpreter outside the 3.10-3.12 matrix.

No real LLM is used: the supervisor path drives a scripted
``GenericFakeChatModel`` so the tier stays offline and CI-safe (real-LLM
runs are the manual e2e tier per DEPENDENCIES.md section 7).

LangGraph API surface exercised (documented so drift is attributable):
``langgraph.graph.StateGraph`` / ``START`` / ``END``,
``langgraph.types.Command``, ``langgraph.prebuilt.create_react_agent``,
``langgraph_supervisor.create_supervisor``.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from typing import Annotated, Any, ClassVar, TypedDict

import pytest

pytest.importorskip("langgraph")

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command

from precept.contract.registry import ContractRegistry
from precept.contract.schema import ContractFields, HandoffContract
from precept.errors import HandoffBlockedError
from precept.evaluator.engine import Evaluator
from precept.exporters.base import Exporter
from precept.integrations.langgraph import evaluate_handoff
from precept.scoring.base import FieldScore, HandoffPayload, Scorer, ScoreResult
from precept.types import ViolationEvent


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
        fs = [
            FieldScore(
                field_name=n, score=self._score, method="stub", passed=self._score >= threshold
            )
            for n in contract.fields.required_fields
        ]
        return ScoreResult(
            overall_score=self._score,
            field_scores=fs,
            scorer_name=self.name,
            scorer_version=self.version,
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
        )


class _Recording(Exporter):
    name: ClassVar[str] = "recording"

    def __init__(self) -> None:
        self.received: list[ViolationEvent] = []

    def export(self, event: ViolationEvent) -> None:
        self.received.append(event)


def _registry(*, mode: str) -> ContractRegistry:
    reg = ContractRegistry()
    reg.register(
        HandoffContract(
            name="researcher_to_summariser",
            mode=mode,
            fields=ContractFields(required_fields=["body"]),
        )
    )
    return reg


class _State(TypedDict):
    body: str
    messages: Annotated[list[Any], add_messages]


# --- AC: Command(goto=...) pattern + evaluate_handoff(), end to end --------


def test_command_pattern_passing_emits_event_via_exporter() -> None:
    rec = _Recording()
    ev = Evaluator(_StubScorer(score=1.0), rec)
    reg = _registry(mode="block")

    def supervisor(state: _State) -> Command:
        evaluate_handoff(state, state, "researcher_to_summariser", registry=reg, evaluator=ev)
        return Command(goto="worker")

    def worker(state: _State) -> dict[str, Any]:
        return {"body": state["body"]}

    g: StateGraph = StateGraph(_State)
    g.add_node("supervisor", supervisor)
    g.add_node("worker", worker)
    g.add_edge(START, "supervisor")
    g.add_edge("worker", END)
    app = g.compile()

    result = app.invoke({"body": "hello", "messages": []})

    assert result["body"] == "hello"
    assert len(rec.received) == 1
    assert rec.received[0].passed is True
    assert rec.received[0].contract_name == "researcher_to_summariser"


def test_command_pattern_degraded_handoff_blocks() -> None:
    rec = _Recording()
    ev = Evaluator(_StubScorer(score=0.1), rec)  # below threshold -> fails
    reg = _registry(mode="block")

    def supervisor(state: _State) -> Command:
        evaluate_handoff(state, state, "researcher_to_summariser", registry=reg, evaluator=ev)
        return Command(goto="worker")

    g: StateGraph = StateGraph(_State)
    g.add_node("supervisor", supervisor)
    g.add_node("worker", lambda s: {"body": s["body"]})
    g.add_edge(START, "supervisor")
    g.add_edge("worker", END)
    app = g.compile()

    with pytest.raises(HandoffBlockedError):
        app.invoke({"body": "hello", "messages": []})
    # Event was still exported before the block propagated.
    assert len(rec.received) == 1
    assert rec.received[0].passed is False


# --- AC: async LangGraph node calling evaluate_handoff stays loop-clean ----


def test_async_node_evaluate_handoff_no_loop_warnings() -> None:
    import asyncio

    rec = _Recording()
    ev = Evaluator(_StubScorer(score=1.0), rec)
    reg = _registry(mode="warn")

    async def supervisor(state: _State) -> Command:
        # Bare sync call from an async node: the hook detects the running
        # loop and offloads evaluate() to a worker thread.
        evaluate_handoff(state, state, "researcher_to_summariser", registry=reg, evaluator=ev)
        return Command(goto="worker")

    g: StateGraph = StateGraph(_State)
    g.add_node("supervisor", supervisor)
    g.add_node("worker", lambda s: {"body": s["body"]})
    g.add_edge(START, "supervisor")
    g.add_edge("worker", END)
    app = g.compile()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        asyncio.run(app.ainvoke({"body": "hello", "messages": []}))

    assert len(rec.received) == 1
    assert not [w for w in caught if issubclass(w.category, RuntimeWarning)]


# --- AC: real langgraph_supervisor + create_precept_handoff_tool -----------


def test_supervisor_path_evaluates_and_emits_event() -> None:
    """Real ``langgraph_supervisor`` driving the contract-checking handoff
    tool via a scripted fake model. CI-gated drift detector for the
    partially-deprecated supervisor helper (DEPENDENCIES.md 4.1)."""
    pytest.importorskip("langgraph_supervisor")
    from langchain_core.language_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage
    from langgraph.prebuilt import create_react_agent
    from langgraph_supervisor import create_supervisor

    from precept.integrations.langgraph import create_precept_handoff_tool

    rec = _Recording()
    ev = Evaluator(_StubScorer(score=1.0), rec)
    reg = _registry(mode="warn")

    worker_model = GenericFakeChatModel(messages=iter([AIMessage(content="done")]))
    worker = create_react_agent(worker_model, tools=[], name="summariser")

    handoff = create_precept_handoff_tool(
        "summariser", "researcher_to_summariser", registry=reg, evaluator=ev
    )
    supervisor_model = GenericFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "transfer_to_summariser",
                            "args": {},
                            "id": "call-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="finished"),
            ]
        )
    )
    app = create_supervisor([worker], model=supervisor_model, tools=[handoff]).compile()

    app.invoke({"messages": [("user", "summarise this")]})

    assert len(rec.received) >= 1
    assert rec.received[0].contract_name == "researcher_to_summariser"

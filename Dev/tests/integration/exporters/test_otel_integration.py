# SPDX-License-Identifier: Apache-2.0
"""Integration test: ``OTelExporter`` wired into a real ``Evaluator``
with an ``InMemorySpanExporter`` collector.

Skipped (not errored) when ``opentelemetry.sdk`` is absent, matching
the PRC-014 LangGraph integration-test convention -- this test does
not gate CI on the optional extra being installed.
"""

from __future__ import annotations

import pytest

# Skip the entire module if [otel] is not installed. The base-install
# behaviour (stub raises ImportError) is unit-tested via subprocess.
pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from precept.contract.schema import ContractFields, HandoffContract
from precept.evaluator.engine import Evaluator
from precept.exporters.otel import OTelExporter
from precept.scoring.base import HandoffPayload
from precept.scoring.embedding_proxy import EmbeddingProxy


@pytest.fixture(scope="module")
def proxy() -> EmbeddingProxy:
    return EmbeddingProxy()


@pytest.fixture(scope="module")
def contract() -> HandoffContract:
    return HandoffContract(
        name="researcher_to_summariser",
        mode="block",
        fields=ContractFields(
            required_fields=["hypothesis", "citations"],
            preserved_entities=[],
            forbidden_drops=[],
            min_fidelity=0.75,
        ),
    )


@pytest.fixture
def in_memory_provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    provider = TracerProvider()
    memory = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    return provider, memory


def test_otel_exporter_end_to_end_clean_handoff(
    proxy: EmbeddingProxy,
    contract: HandoffContract,
    in_memory_provider: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, memory = in_memory_provider
    tracer = provider.get_tracer("precept-integration")
    exporter = OTelExporter(tracer=tracer)
    evaluator = Evaluator(proxy, exporter)

    source = HandoffPayload(
        fields={
            "hypothesis": "Heat-pump adoption correlates with MCS scheme uptake.",
            "citations": [
                "MCS Quarterly Statistics 2025",
                "Boiler Upgrade Scheme 2024 evaluation",
            ],
        }
    )
    target = HandoffPayload(fields=dict(source.fields))

    event = evaluator.evaluate(source, target, contract)
    assert event.passed is True

    finished = memory.get_finished_spans()
    # No active span on entry → synthetic ``invoke_agent`` span opens.
    assert len(finished) == 1
    span = finished[0]
    assert span.name == "invoke_agent"

    events = list(span.events)
    names = [e.name for e in events]
    assert "gen_ai.evaluation.result" in names
    captured = next(e for e in events if e.name == "gen_ai.evaluation.result")
    attrs = captured.attributes
    assert attrs is not None
    assert attrs["gen_ai.evaluation.name"] == "researcher_to_summariser"
    assert attrs["gen_ai.evaluation.score.label"] == "passed"
    # Content capture defaults off; no source/target keys leak.
    for k in attrs:
        assert not str(k).startswith("precept.source.")
        assert not str(k).startswith("precept.target.")


def test_otel_exporter_end_to_end_degraded_handoff(
    proxy: EmbeddingProxy,
    contract: HandoffContract,
    in_memory_provider: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, memory = in_memory_provider
    tracer = provider.get_tracer("precept-integration")
    exporter = OTelExporter(tracer=tracer)
    evaluator = Evaluator(proxy, exporter)

    source = HandoffPayload(
        fields={
            "hypothesis": "Heat-pump adoption correlates with MCS scheme uptake.",
            "citations": [
                "MCS Quarterly Statistics 2025",
                "Boiler Upgrade Scheme 2024 evaluation",
            ],
        }
    )
    # Degraded: drop the citations entirely so the required-fields
    # rule + the per-field score both fire failures.
    target = HandoffPayload(
        fields={"hypothesis": source.fields["hypothesis"]},
    )

    event = evaluator.evaluate(source, target, contract)
    assert event.passed is False

    finished = memory.get_finished_spans()
    assert len(finished) == 1
    span = finished[0]
    events = list(span.events)
    captured = next(e for e in events if e.name == "gen_ai.evaluation.result")
    attrs = captured.attributes
    assert attrs is not None
    assert attrs["gen_ai.evaluation.score.label"] == "failed"
    assert "missing" in str(attrs["gen_ai.evaluation.explanation"]).lower()

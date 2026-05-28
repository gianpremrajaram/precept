# SPDX-License-Identifier: Apache-2.0
"""Integration test: ``Evaluator`` end-to-end with the real
``EmbeddingProxy``.

Loads the sentence-transformer model once per module, wires it into an
:class:`Evaluator`, and runs a clean and a degraded handoff against a
realistic ``min_fidelity=0.75`` contract. Inline payloads (no PRC-018
fixtures) match the existing PRC-011 integration-test convention.
"""

from __future__ import annotations

import json

import pytest

from precept.contract.schema import ContractFields, HandoffContract
from precept.evaluator.engine import Evaluator
from precept.exporters.base import NoOpExporter
from precept.scoring.base import HandoffPayload
from precept.scoring.embedding_proxy import EmbeddingProxy


@pytest.fixture(scope="module")
def proxy() -> EmbeddingProxy:
    return EmbeddingProxy()


@pytest.fixture(scope="module")
def evaluator(proxy: EmbeddingProxy) -> Evaluator:
    return Evaluator(proxy, NoOpExporter())


@pytest.fixture(scope="module")
def contract() -> HandoffContract:
    return HandoffContract(
        name="researcher_to_summariser",
        mode="block",
        fields=ContractFields(
            required_fields=["hypothesis", "citations"],
            min_fidelity=0.75,
        ),
    )


def test_clean_handoff_event_passes(
    evaluator: Evaluator,
    contract: HandoffContract,
) -> None:
    source = HandoffPayload(
        fields={
            "hypothesis": (
                "Prolonged exposure to fluorinated surfactants in groundwater "
                "correlates with elevated PFOA serum concentrations."
            ),
            "citations": "Smith et al. 2024; Wang & Chen 2023",
        }
    )
    # Same content -> embedding cosine ~1.0 on both fields.
    event = evaluator.evaluate(source, source, contract)
    assert event.passed is True
    assert all(fs.passed for fs in event.score_result.field_scores)


def test_degraded_handoff_event_fails_on_citations(
    evaluator: Evaluator,
    contract: HandoffContract,
) -> None:
    source = HandoffPayload(
        fields={
            "hypothesis": (
                "Prolonged exposure to fluorinated surfactants in groundwater "
                "correlates with elevated PFOA serum concentrations in adults "
                "living within 5 km of source facilities."
            ),
            "citations": "Smith et al. 2024; Wang & Chen 2023; EPA TR-2024-117",
        }
    )
    # Hypothesis paraphrased faithfully; citations gutted to a generic.
    target = HandoffPayload(
        fields={
            "hypothesis": (
                "Sustained exposure to fluorinated surfactants in groundwater "
                "is associated with raised PFOA blood levels in adults living "
                "near source facilities."
            ),
            "citations": "various sources",
        }
    )
    event = evaluator.evaluate(source, target, contract)
    assert event.passed is False
    by_field = {fs.field_name: fs for fs in event.score_result.field_scores}
    assert by_field["hypothesis"].passed is True
    assert by_field["citations"].passed is False


def test_compact_dict_under_4kib_for_real_event(
    evaluator: Evaluator,
    contract: HandoffContract,
) -> None:
    source = HandoffPayload(
        fields={
            "hypothesis": "Short hypothesis.",
            "citations": "Short citations.",
        }
    )
    event = evaluator.evaluate(source, source, contract)
    payload = json.dumps(
        event.to_compact_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert len(payload) <= 4096

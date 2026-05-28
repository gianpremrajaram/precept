# SPDX-License-Identifier: Apache-2.0
"""Integration test for ``EmbeddingProxy`` end-to-end on a degraded handoff.

Loads the real sentence-transformer model and scores a hand-built
source/target pair against a ``HandoffContract`` whose ``min_fidelity``
threshold is realistic for production use (``0.75``). Asserts that a
strongly-degraded field is flagged as failing while a faithful field
passes.

This test does NOT depend on PRC-018 fixtures (which don't exist yet);
the payloads are inlined here. PRC-018 will land its own
fixture-driven integration tests later.
"""

from __future__ import annotations

import pytest

from precept.contract.schema import ContractFields, HandoffContract
from precept.scoring.base import HandoffPayload
from precept.scoring.embedding_proxy import EmbeddingProxy


@pytest.fixture(scope="module")
def proxy() -> EmbeddingProxy:
    return EmbeddingProxy()


def test_degraded_handoff_flags_low_fidelity_field(proxy: EmbeddingProxy) -> None:
    """Faithful field passes the 0.75 threshold; degraded field fails it."""
    contract = HandoffContract(
        name="researcher_to_summariser",
        mode="block",
        fields=ContractFields(
            required_fields=["hypothesis", "citations"],
            min_fidelity=0.75,
        ),
    )

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

    # Target: hypothesis is paraphrased faithfully; citations are gutted.
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

    result = proxy.score(source, target, contract)

    by_name = {fs.field_name: fs for fs in result.field_scores}
    assert by_name["hypothesis"].passed is True, (
        f"faithful paraphrase should clear 0.75; got {by_name['hypothesis'].score}"
    )
    assert by_name["citations"].passed is False, (
        f"gutted citation list should fail 0.75; got {by_name['citations'].score}"
    )
    assert result.scorer_name == "embedding_proxy"

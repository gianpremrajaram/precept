# SPDX-License-Identifier: MIT
"""Integration test: both example YAML contracts load as distinct valid IRs.

Matches PRC-007 Acceptance Criteria requirement: "loading both example
files produces two distinct valid contracts".
"""

from __future__ import annotations

from pathlib import Path

from precept.contract.yaml_loader import load_contract

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXAMPLES = _REPO_ROOT / "examples" / "contracts"


def test_both_example_contracts_load_and_are_distinct() -> None:
    c1 = load_contract(_EXAMPLES / "researcher_to_summariser.yaml")
    c2 = load_contract(_EXAMPLES / "summariser_to_writer.yaml")

    assert c1.name != c2.name
    assert c1.fields.required_fields != c2.fields.required_fields
    assert c1.fields.min_fidelity != c2.fields.min_fidelity

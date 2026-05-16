# SPDX-License-Identifier: MIT
"""Integration test: decorator and YAML frontends produce an identical IR.

PRC-008 Acceptance Criteria: "YAML-loaded contract and decorator-declared
contract with equivalent inputs produce equal ``HandoffContract``
instances (IR equivalence)". Both frontends feed the same
``HandoffContract`` per ADR 0001; the evaluator must not be able to tell
them apart.

Pydantic structural ``==`` already compares every field (including
``metadata``), so a divergence would fail the equality assertion rather
than pass silently. The explicit per-field asserts exist only to make
*which* field diverged obvious when the equality assertion fails.
"""

from __future__ import annotations

from precept.contract.decorator import handoff_contract
from precept.contract.schema import HandoffContract
from precept.contract.yaml_loader import load_contract_from_string

_FULL_YAML = """
name: researcher_to_summariser
version: "1.0"
mode: block
description: "research to summariser"
fields:
  required_fields:
    - hypothesis
    - citations
  preserved_entities:
    - primary_source
  min_fidelity: 0.75
  forbidden_drops:
    - uncertainty_bounds
"""


def test_decorator_matches_yaml_for_fully_specified_contract() -> None:
    @handoff_contract(
        name="researcher_to_summariser",
        version="1.0",
        mode="block",
        description="research to summariser",
        required=["hypothesis", "citations"],
        preserved_entities=["primary_source"],
        min_fidelity=0.75,
        forbidden_drops=["uncertainty_bounds"],
    )
    def handoff(state: dict[str, object]) -> dict[str, object]:
        return state

    from_decorator: HandoffContract = handoff.__precept_contract__
    from_yaml = load_contract_from_string(_FULL_YAML)

    # Explicit field-level asserts first (diagnostic clarity on failure).
    assert from_decorator.name == from_yaml.name
    assert from_decorator.version == from_yaml.version
    assert from_decorator.mode == from_yaml.mode
    assert from_decorator.description == from_yaml.description
    assert from_decorator.fields == from_yaml.fields
    assert from_decorator.metadata == {} == from_yaml.metadata
    # Full structural equivalence.
    assert from_decorator == from_yaml


def test_decorator_matches_yaml_for_default_only_contract() -> None:
    @handoff_contract(name="minimal")
    def handoff(state: dict[str, object]) -> dict[str, object]:
        return state

    from_decorator: HandoffContract = handoff.__precept_contract__
    from_yaml = load_contract_from_string("name: minimal\nfields: {}\n")

    # Defaults must resolve identically across frontends.
    assert from_decorator.version == from_yaml.version == "0.1"
    assert from_decorator.mode == from_yaml.mode == "warn"
    assert from_decorator.metadata == {} == from_yaml.metadata
    assert from_decorator == from_yaml

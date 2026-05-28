# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ``precept.contract.yaml_loader``."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from precept.contract.schema import HandoffContract
from precept.contract.yaml_loader import load_contract, load_contract_from_string
from precept.errors import ContractValidationError

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXAMPLES = _REPO_ROOT / "examples" / "contracts"


# --- Example-file loading -------------------------------------------------


def test_researcher_to_summariser_loads_with_expected_fields() -> None:
    c = load_contract(_EXAMPLES / "researcher_to_summariser.yaml")
    assert c.name == "researcher_to_summariser"
    assert c.version == "0.1"
    assert c.mode == "block"
    assert c.description == "Contract for research agent handing off to summariser"
    assert c.fields.required_fields == ["hypothesis", "citations"]
    assert c.fields.preserved_entities == ["MCS Quarterly Statistics", "Boiler Upgrade Scheme"]
    assert c.fields.min_fidelity == 0.75
    assert c.fields.forbidden_drops == ["uncertainty_bounds"]


def test_summariser_to_writer_loads_with_block_mode_and_forbidden_drops() -> None:
    c = load_contract(_EXAMPLES / "summariser_to_writer.yaml")
    assert c.name == "summariser_to_writer"
    assert c.mode == "block"
    assert c.fields.required_fields == ["summary", "key_entities"]
    assert c.fields.preserved_entities == ["MCS Quarterly Statistics"]
    assert c.fields.min_fidelity == 0.70
    assert c.fields.forbidden_drops == ["uncertainty_bounds"]


# --- From-string loading --------------------------------------------------


def test_load_contract_from_string_returns_handoff_contract() -> None:
    text = """
name: example
version: "0.1"
mode: warn
fields:
  required_fields: [a, b]
"""
    c = load_contract_from_string(text)
    assert isinstance(c, HandoffContract)
    assert c.name == "example"
    assert c.fields.required_fields == ["a", "b"]


# --- Round-trip (semantic, post-defaults) --------------------------------


def test_semantic_round_trip_preserves_model_dump() -> None:
    """IR round-trip is semantic: load -> dump via ``model_dump`` -> reload.

    Defaults are applied on the first load; the re-dumped YAML contains
    the defaults explicitly. The two IR instances must be equal by
    ``model_dump`` (source-faithful round-trip is not a goal; see
    clarifying-question 14 decision in the PR).
    """
    text = """
name: round_trip
fields:
  required_fields: [a]
"""
    c1 = load_contract_from_string(text)
    redumped = yaml.safe_dump(c1.model_dump())
    c2 = load_contract_from_string(redumped)
    assert c1.model_dump() == c2.model_dump()


# --- Error paths ----------------------------------------------------------


def test_malformed_yaml_raises_with_line_column_info() -> None:
    bad = """
name: example
fields:
  required_fields: [unclosed
"""
    with pytest.raises(ContractValidationError) as exc_info:
        load_contract_from_string(bad)
    err = exc_info.value
    assert err.details, "should carry at least one structured issue"
    issue = err.details[0]
    assert issue.field_path == "<yaml>"
    assert issue.yaml_mark is not None
    line, column = issue.yaml_mark
    assert line >= 1
    assert column >= 1
    assert f"line {line}" in str(err)
    assert f"column {column}" in str(err)


def test_unknown_top_level_field_rejected() -> None:
    text = """
name: example
bogus: true
fields:
  required_fields: [a]
"""
    with pytest.raises(ContractValidationError):
        load_contract_from_string(text)


def test_empty_file_rejected() -> None:
    with pytest.raises(ContractValidationError) as exc_info:
        load_contract_from_string("")
    assert "empty" in str(exc_info.value).lower()


def test_whitespace_only_file_rejected() -> None:
    with pytest.raises(ContractValidationError) as exc_info:
        load_contract_from_string("   \n\n   \n")
    assert "empty" in str(exc_info.value).lower()


def test_top_level_non_mapping_rejected() -> None:
    with pytest.raises(ContractValidationError) as exc_info:
        load_contract_from_string("- just\n- a\n- list\n")
    assert "mapping" in str(exc_info.value)


def test_missing_file_raises_contract_validation_error() -> None:
    with pytest.raises(ContractValidationError):
        load_contract("/nonexistent/path/does_not_exist.yaml")


def test_load_contract_accepts_path_and_string() -> None:
    # Path object
    c1 = load_contract(_EXAMPLES / "researcher_to_summariser.yaml")
    # string path
    c2 = load_contract(str(_EXAMPLES / "researcher_to_summariser.yaml"))
    assert c1.model_dump() == c2.model_dump()


# --- Anchors and aliases --------------------------------------------------


def test_yaml_anchor_alias_resolves() -> None:
    text = """
name: anchor_demo
fields:
  required_fields: &shared [alpha, beta]
  preserved_entities: *shared
  min_fidelity: 0.5
"""
    c = load_contract_from_string(text)
    assert c.fields.required_fields == ["alpha", "beta"]
    assert c.fields.preserved_entities == ["alpha", "beta"]


# --- tmp_path round-trip --------------------------------------------------


def test_load_contract_from_tmp_path(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text(
        "name: tmp_contract\nfields:\n  required_fields: [a]\n",
        encoding="utf-8",
    )
    c = load_contract(p)
    assert c.name == "tmp_contract"

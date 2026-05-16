# SPDX-License-Identifier: MIT
"""Unit tests for ``precept.contract.registry`` (PRC-009).

Covers register/get/list semantics, duplicate and missing-name error
behaviour, and ``load_directory`` (count, non-YAML and malformed-file
skipping with a logged warning rather than a raise, recursion, and
idempotent re-load).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from precept.contract.registry import ContractRegistry, default_registry
from precept.contract.schema import HandoffContract

_REGISTRY_LOGGER = "precept.contract.registry"


def _contract(name: str) -> HandoffContract:
    return HandoffContract(name=name, fields={"required_fields": ["hypothesis"]})


# --- register / get / list ------------------------------------------------


def test_register_and_retrieve() -> None:
    registry = ContractRegistry()
    contract = _contract("researcher_to_summariser")

    registry.register(contract)

    assert registry.get("researcher_to_summariser") is contract
    assert registry.list_contracts() == ["researcher_to_summariser"]


def test_list_contracts_is_sorted() -> None:
    registry = ContractRegistry()
    registry.register(_contract("charlie"))
    registry.register(_contract("alpha"))
    registry.register(_contract("bravo"))

    assert registry.list_contracts() == ["alpha", "bravo", "charlie"]


def test_duplicate_name_raises_unless_overwrite() -> None:
    registry = ContractRegistry()
    registry.register(_contract("researcher_to_summariser"))

    with pytest.raises(KeyError):
        registry.register(_contract("researcher_to_summariser"))

    replacement = HandoffContract(
        name="researcher_to_summariser",
        fields={"required_fields": ["summary"]},
    )
    registry.register(replacement, overwrite=True)
    assert registry.get("researcher_to_summariser") is replacement


def test_missing_name_raises_with_available_listed() -> None:
    registry = ContractRegistry()
    registry.register(_contract("bar"))
    registry.register(_contract("baz"))

    with pytest.raises(KeyError) as exc_info:
        registry.get("foo")

    message = exc_info.value.args[0]
    assert "foo" in message
    assert "Available: bar, baz" in message


def test_missing_name_on_empty_registry_reports_none() -> None:
    registry = ContractRegistry()

    with pytest.raises(KeyError) as exc_info:
        registry.get("foo")

    assert "Available: (none)" in exc_info.value.args[0]


def test_default_registry_is_a_registry_instance() -> None:
    assert isinstance(default_registry, ContractRegistry)


# --- load_directory -------------------------------------------------------

_VALID_A = """
name: researcher_to_summariser
mode: block
fields:
  required_fields: [hypothesis, citations]
"""

_VALID_B = """
name: summariser_to_writer
fields:
  required_fields: [summary]
"""


def test_load_directory_loads_multiple_and_returns_count(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(_VALID_A, encoding="utf-8")
    (tmp_path / "b.yaml").write_text(_VALID_B, encoding="utf-8")

    registry = ContractRegistry()
    count = registry.load_directory(tmp_path)

    assert count == 2
    assert registry.list_contracts() == [
        "researcher_to_summariser",
        "summariser_to_writer",
    ]


def test_load_directory_skips_non_yaml_and_malformed_with_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (tmp_path / "good.yaml").write_text(_VALID_A, encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a contract", encoding="utf-8")
    (tmp_path / "broken_syntax.yaml").write_text("name: [unclosed", encoding="utf-8")
    (tmp_path / "no_name.yaml").write_text("fields: {}\n", encoding="utf-8")

    registry = ContractRegistry()
    with caplog.at_level(logging.WARNING, logger=_REGISTRY_LOGGER):
        count = registry.load_directory(tmp_path)

    assert count == 1
    assert registry.list_contracts() == ["researcher_to_summariser"]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2  # broken_syntax.yaml + no_name.yaml
    assert all("Skipping contract file" in r.getMessage() for r in warnings)


def test_load_directory_recursive(tmp_path: Path) -> None:
    nested = tmp_path / "team"
    nested.mkdir()
    (tmp_path / "a.yaml").write_text(_VALID_A, encoding="utf-8")
    (nested / "b.yaml").write_text(_VALID_B, encoding="utf-8")

    # Fresh registry per assertion: each count reflects traversal scope
    # alone, not re-registration. Idempotency is covered separately by
    # test_load_directory_reload_is_idempotent.
    assert ContractRegistry().load_directory(tmp_path) == 1  # top level only
    assert ContractRegistry().load_directory(tmp_path, recursive=True) == 2  # descends


def test_load_directory_reload_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(_VALID_A, encoding="utf-8")
    registry = ContractRegistry()

    assert registry.load_directory(tmp_path) == 1
    # Re-loading an already-loaded directory must not raise on the
    # already-registered name.
    assert registry.load_directory(tmp_path) == 1
    assert registry.list_contracts() == ["researcher_to_summariser"]

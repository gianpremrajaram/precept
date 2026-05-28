# SPDX-License-Identifier: Apache-2.0
"""Schema-shape unit tests for the demo trace fixtures (PRC-017).

The fixtures under ``examples/fixtures/`` are the input to PRC-019's demo
runner and PRC-022's observatory; any drift in their JSON shape breaks
both downstream consumers silently. This module defines an inline
``TraceFixture`` Pydantic model and asserts each committed fixture
parses against it.

The fixtures themselves are loaded by ``Dev/tests/conftest.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CONTRACTS_DIR = _REPO_ROOT / "examples" / "contracts"


class HandoffMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_agent: str
    target_agent: str
    contract_name: str
    timestamp_iso: str


class Hop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handoff_metadata: HandoffMetadata
    source_payload: dict[str, Any]
    target_payload: dict[str, Any]


class TraceFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_name: Literal["clean", "degraded"]
    schema_version: str
    hops: list[Hop]


@pytest.mark.parametrize("fixture_name", ["clean_trace", "degraded_trace"])
def test_fixture_parses_as_trace_fixture(
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    raw: dict[str, Any] = request.getfixturevalue(fixture_name)
    parsed = TraceFixture.model_validate(raw)
    assert parsed.hops, "fixture must declare at least one hop"


def test_clean_trace_has_expected_pipeline_shape(clean_trace: dict[str, Any]) -> None:
    parsed = TraceFixture.model_validate(clean_trace)
    assert parsed.trace_name == "clean"
    assert [h.handoff_metadata.source_agent for h in parsed.hops] == [
        "researcher",
        "summariser",
    ]
    assert [h.handoff_metadata.target_agent for h in parsed.hops] == [
        "summariser",
        "writer",
    ]


def test_degraded_trace_has_expected_pipeline_shape(degraded_trace: dict[str, Any]) -> None:
    parsed = TraceFixture.model_validate(degraded_trace)
    assert parsed.trace_name == "degraded"
    assert [h.handoff_metadata.source_agent for h in parsed.hops] == [
        "researcher",
        "summariser",
    ]


@pytest.mark.parametrize("fixture_name", ["clean_trace", "degraded_trace"])
def test_fixture_contract_names_resolve_to_files(
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    parsed = TraceFixture.model_validate(request.getfixturevalue(fixture_name))
    for hop in parsed.hops:
        contract_yaml = _CONTRACTS_DIR / f"{hop.handoff_metadata.contract_name}.yaml"
        assert contract_yaml.is_file(), (
            f"fixture references contract {hop.handoff_metadata.contract_name!r} "
            f"but {contract_yaml} does not exist"
        )

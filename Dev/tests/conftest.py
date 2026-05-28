# SPDX-License-Identifier: Apache-2.0
"""Shared pytest fixtures for the Precept test suite.

Lives at the ``tests/`` root (not ``tests/fixtures/``) so the trace fixtures
defined here reach both ``tests/unit/`` and ``tests/integration/`` consumers
- a conftest is only visible to descendants of its directory, and PRC-017's
integration test ``test_fixtures.py`` is a sibling of any hypothetical
``tests/fixtures/`` directory rather than a child.

The two trace fixtures load JSON files committed under
``examples/fixtures/`` at the repo root. They are co-designed with the
contract YAMLs under ``examples/contracts/``: editing one without the other
will silently break the rule firing the evaluator expects (see the
``preserved_entities`` substring coupling documented in
``tests/integration/test_fixtures.py``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES_DIR = _REPO_ROOT / "examples" / "fixtures"


def _load_trace(name: str) -> dict[str, Any]:
    path = _FIXTURES_DIR / name
    with path.open(encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


@pytest.fixture
def clean_trace() -> dict[str, Any]:
    """Two-hop demo trace where every contract passes."""
    return _load_trace("clean_trace.json")


@pytest.fixture
def degraded_trace() -> dict[str, Any]:
    """Two-hop demo trace where the summariser->writer hop violates
    ``preserved_entities`` (drops ``primary_source``) and
    ``forbidden_drops`` (drops the ``uncertainty_bounds`` field)."""
    return _load_trace("degraded_trace.json")

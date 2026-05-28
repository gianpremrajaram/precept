# SPDX-License-Identifier: Apache-2.0
"""Shared Hypothesis strategies for contract-schema tests.

These live next to the contract unit tests because pytest's default
``prepend`` import mode places this directory on ``sys.path`` when
collecting tests here. Future tickets that need the same generators
(PRC-008 decorator frontend, PRC-012 rule evaluators) can import
directly from this module.

Kept deliberately small; extended as new validators land.
"""

from __future__ import annotations

from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

__all__ = [
    "valid_contract_names",
    "valid_field_names",
    "valid_min_fidelity",
]

valid_contract_names: SearchStrategy[str] = st.from_regex(
    r"^[a-z][a-z0-9_-]{0,32}$",
    fullmatch=True,
)
"""Strings matching ``NAME_PATTERN``; length-bounded for Hypothesis efficiency."""

valid_min_fidelity: SearchStrategy[float] = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)
"""Floats in ``[0.0, 1.0]``; excludes NaN / infinity to match Pydantic's coercion rules."""

valid_field_names: SearchStrategy[str] = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd"),
        whitelist_characters="_-.",
    ),
    min_size=1,
    max_size=32,
)
"""Field-name-like strings for the three contract list fields."""

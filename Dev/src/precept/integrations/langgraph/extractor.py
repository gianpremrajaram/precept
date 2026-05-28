# SPDX-License-Identifier: Apache-2.0
"""Contracted-field extractor: LangGraph state -> ``HandoffPayload`` (PRC-016).

Precept evaluates handoffs against contracts, and a contract names
*exactly* which fields matter (``required_fields`` and
``preserved_entities``). This module reads only those fields from an
arbitrary upstream state object and ignores everything else.

Security rationale (see ``CLAUDE.md`` -> "Contracted-fields-only
extraction"): by never reading uncontracted state, Precept cannot leak
secrets that an application happens to keep in the same state object.
There is no recursive descent and no PII-redaction heuristic - the
contract is the allow-list, and the allow-list is enforced by the simple
fact that we only ever iterate the contracted field names. Note this is
*not* enforced by ``HandoffPayload``'s ``extra="forbid"``: that config
governs unknown *model attributes*, not keys inside the ``fields`` dict.
The single guarantee is the iterate-only-contracted-fields loop below; a
regression test gates it.

State-shape handling is two well-defined branches, not the literal
three-step fallback the PRC-016 acceptance criteria sketch: a bare
``state[field]`` raises ``KeyError`` on a missing key, which would
collide with the "missing fields are recorded as literal ``None``"
requirement. So mapping-shaped state goes through ``Mapping.get`` and
object-shaped state through ``getattr``; both use a private sentinel so
a field that is genuinely absent is distinguished from one that is
present with a ``None`` value (the former increments
``missing_field_count``; the latter does not).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Literal

from precept.contract.schema import HandoffContract
from precept.scoring.base import HandoffPayload

__all__ = ["extract_payload"]

ExtractionMethod = Literal["mapping", "attribute"]
"""How a payload's values were read. One value per payload, decided by
the shape of ``state`` (``Mapping`` -> ``"mapping"``, otherwise
``"attribute"``). Stored as a plain ``str`` in
``HandoffPayload.metadata`` (which is ``dict[str, str]``); typed here so
downstream consumers (PRC-014, PRC-026) have a stable contract."""

_MISSING: Final = object()
"""Sentinel for "field not present in state". Distinct from a field that
is present with the value ``None`` - the distinction is what keeps
``missing_field_count`` correct."""

_TRUNC_SUFFIX = "... [truncated {n} chars]"
"""Appended to over-long string values. ``n`` is the number of
characters removed (``len(value) - max_field_chars``). The structured
truncation signal for machine consumers is
``metadata["truncated_field_count"]``; this human-readable suffix is not
meant to be parsed."""


def _truncate(value: Any, max_field_chars: int) -> tuple[Any, bool]:
    """Return ``(value, truncated)``.

    Only ``str`` values longer than ``max_field_chars`` are truncated;
    every other value (including non-strings) passes through unchanged -
    the scorer and rules stringify at use site, so we do not coerce here.
    """
    if isinstance(value, str) and len(value) > max_field_chars:
        removed = len(value) - max_field_chars
        return value[:max_field_chars] + _TRUNC_SUFFIX.format(n=removed), True
    return value, False


def extract_payload(
    state: Any,
    contract: HandoffContract,
    *,
    max_field_chars: int = 2000,
) -> HandoffPayload:
    """Extract the contracted fields of ``state`` into a ``HandoffPayload``.

    Reads only ``contract.fields.required_fields`` and
    ``contract.fields.preserved_entities`` (de-duplicated, first-seen
    order preserved). No other part of ``state`` is touched, and no
    recursion is attempted into nested values - a field whose value is a
    Pydantic model, a list of messages, or any other object is captured
    as-is and left for the scorer/rules to stringify.

    Missing fields are recorded as the literal ``None`` in
    ``HandoffPayload.fields`` (not omitted) so downstream rule evaluators
    can mark the field missing rather than mis-attribute its absence.
    A field that is *present* with the value ``None`` is recorded as
    ``None`` too, but is counted as extracted, not missing.

    String values longer than ``max_field_chars`` are truncated with a
    ``"... [truncated N chars]"`` suffix; non-string values are never
    truncated or coerced.

    The returned ``metadata`` carries four string entries:
    ``extraction_method`` (``"mapping"`` or ``"attribute"``),
    ``extracted_field_count``, ``missing_field_count``, and
    ``truncated_field_count``. Counts are stringified because
    ``HandoffPayload.metadata`` is ``dict[str, str]``.
    """
    field_names = list(
        dict.fromkeys([*contract.fields.required_fields, *contract.fields.preserved_entities])
    )

    is_mapping = isinstance(state, Mapping)
    method: ExtractionMethod = "mapping" if is_mapping else "attribute"

    fields: dict[str, Any] = {}
    missing_count = 0
    truncated_count = 0

    for name in field_names:
        raw = state.get(name, _MISSING) if is_mapping else getattr(state, name, _MISSING)

        if raw is _MISSING:
            fields[name] = None
            missing_count += 1
            continue

        value, was_truncated = _truncate(raw, max_field_chars)
        fields[name] = value
        if was_truncated:
            truncated_count += 1

    metadata: dict[str, str] = {
        "extraction_method": method,
        "extracted_field_count": str(len(field_names) - missing_count),
        "missing_field_count": str(missing_count),
        "truncated_field_count": str(truncated_count),
    }

    return HandoffPayload(fields=fields, metadata=metadata)

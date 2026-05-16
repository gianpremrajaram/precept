# SPDX-License-Identifier: MIT
"""LangGraph integration package.

PRC-016 lands ``extractor.extract_payload`` (LangGraph state ->
``HandoffPayload``, contracted fields only). PRC-014 will add the pure
``evaluate_handoff`` hook and the ``create_precept_handoff_tool`` wrapper
in sibling modules without touching the extractor.

``__all__`` is intentionally empty at this stage. The public surface is
defined by PRC-026; until then, callers import concrete names directly
from the relevant submodule, mirroring the ``precept.evaluator`` and
``precept.exporters`` scaffold convention.
"""

from __future__ import annotations

__all__: list[str] = []

# SPDX-License-Identifier: Apache-2.0
"""Framework integration package.

Houses the adapters that connect Precept's framework-agnostic core
(contract IR, scorer, evaluator) to specific agent frameworks. LangGraph
is the v0 target (``precept.integrations.langgraph``): PRC-016 lands the
contracted-field extractor here; PRC-014 adds the evaluation hook and
tool wrapper alongside it.

``__all__`` is intentionally empty at this stage. The public surface is
defined by PRC-026; until then, callers import concrete names directly
from the relevant submodule (e.g.
``from precept.integrations.langgraph.extractor import extract_payload``).
"""

from __future__ import annotations

__all__: list[str] = []

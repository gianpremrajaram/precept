# SPDX-License-Identifier: Apache-2.0
"""LangGraph integration package.

Public names (PRC-014 AC explicitly requires both to be importable from
this package -- this supersedes the earlier "intentionally empty
``__all__``" scaffold note for *these two names only*; PRC-026 still owns
the top-level ``precept`` namespace):

* ``evaluate_handoff`` -- the pure, framework-API-independent hook
  (:mod:`precept.integrations.langgraph.eval_hook`). Imports no
  ``langgraph`` symbol.
* ``create_precept_handoff_tool`` -- the LangGraph tool wrapper
  (:mod:`precept.integrations.langgraph.handoff_tool`). Importing it
  pulls in ``langgraph`` / ``langchain-core`` (hard runtime deps).

Both are resolved lazily via :pep:`562` ``__getattr__`` so that
``from precept.integrations.langgraph import evaluate_handoff`` never
imports ``langgraph`` -- the pure hook stays usable as the
framework-independent fallback (CLAUDE.md -> "Two integration paths for
LangGraph") even in an environment where the tool API is unavailable or
broken. ``extract_payload`` (PRC-016) remains submodule-only by the
PRC-026 surface convention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["create_precept_handoff_tool", "evaluate_handoff"]

if TYPE_CHECKING:
    from precept.integrations.langgraph.eval_hook import evaluate_handoff
    from precept.integrations.langgraph.handoff_tool import create_precept_handoff_tool


def __getattr__(name: str) -> Any:
    if name == "evaluate_handoff":
        from precept.integrations.langgraph.eval_hook import evaluate_handoff

        return evaluate_handoff
    if name == "create_precept_handoff_tool":
        from precept.integrations.langgraph.handoff_tool import create_precept_handoff_tool

        return create_precept_handoff_tool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

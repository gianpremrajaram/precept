# SPDX-License-Identifier: Apache-2.0
"""Evaluation engine package.

Houses the per-field rule evaluators (PRC-012) and, in PRC-013, the
``Evaluator`` class that composes them with a ``Scorer`` to produce
``ViolationEvent`` instances.

``__all__`` is intentionally empty at this stage. The public surface
of the evaluator subsystem is defined by PRC-026; until then, callers
import concrete names directly from the relevant submodule (e.g.
``from precept.evaluator.rules import RuleResult``).
"""

from __future__ import annotations

__all__: list[str] = []

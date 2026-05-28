# SPDX-License-Identifier: Apache-2.0
"""Evaluation engine -- composes rules + scorer + exporter.

The :class:`Evaluator` is the single entry point an integration layer
(PRC-014's tool wrapper or pure ``evaluate_handoff`` hook) calls per
handoff. It runs the three v0 rule evaluators (PRC-012), invokes the
injected :class:`Scorer` (PRC-010), aggregates the result into a
:class:`ViolationEvent` (PRC-013), and dispatches to the injected
:class:`Exporter` (PRC-013) with per-call failure isolation.

The evaluator itself **never raises on a contract violation**. The
returned :class:`ViolationEvent` carries ``passed`` and ``mode`` so the
integration layer (PRC-014) can decide whether to raise
:class:`precept.errors.HandoffBlockedError`. This split keeps the
evaluator usable from non-LangGraph code paths and from observability
tools that only want to record events.

Thread-safety contract:

The :class:`Evaluator` holds its injected ``scorer`` and ``exporter``
immutably after construction. :meth:`Evaluator.evaluate` reads but does
not mutate ``self``; it produces a fresh :class:`ViolationEvent` per
call. Both injected components are required by their own docstrings to
be thread-safe (see :class:`Scorer` and :class:`Exporter`). One
:class:`Evaluator` instance is therefore safe to call from multiple
threads. Any future change that introduces caching or per-call
mutation on ``self`` MUST update this contract loudly -- downstream
integration code (PRC-014/PRC-015) will assume the present guarantee.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from precept.evaluator.rules import (
    forbidden_drops_rule,
    preserved_entities_rule,
    required_fields_rule,
)
from precept.exporters.base import Exporter, NoOpExporter
from precept.types import ViolationEvent

if TYPE_CHECKING:
    from precept.contract.schema import HandoffContract
    from precept.scoring.base import HandoffPayload, Scorer

__all__ = [
    "Evaluator",
]


logger = logging.getLogger(__name__)


class Evaluator:
    """Compose rules, scoring, and export into a single handoff evaluation.

    Construct with an injected :class:`Scorer` and (optionally) an
    :class:`Exporter`. When no exporter is supplied, a
    :class:`NoOpExporter` is installed so :meth:`evaluate` still has a
    valid sink for tests and unconfigured environments.

    See module docstring for the full thread-safety contract.
    """

    def __init__(
        self,
        scorer: Scorer,
        exporter: Exporter | None = None,
    ) -> None:
        self._scorer: Scorer = scorer
        self._exporter: Exporter = exporter if exporter is not None else NoOpExporter()

    @property
    def exporter(self) -> Exporter:
        """The exporter used by :meth:`evaluate` (read-only accessor)."""
        return self._exporter

    @property
    def scorer(self) -> Scorer:
        """The scorer used by :meth:`evaluate` (read-only accessor)."""
        return self._scorer

    def evaluate(
        self,
        source: HandoffPayload,
        target: HandoffPayload,
        contract: HandoffContract,
    ) -> ViolationEvent:
        """Evaluate ``target`` given ``source`` under ``contract``.

        Runs the three rule evaluators, invokes the scorer, builds a
        :class:`ViolationEvent` carrying both, and dispatches it to the
        injected exporter. Exporter failures are logged and swallowed
        so the evaluator always returns a valid event. The decision to
        raise :class:`HandoffBlockedError` is the caller's (PRC-014).
        """
        rule_results = [
            required_fields_rule(source, target, contract.fields.required_fields),
            preserved_entities_rule(source, target, contract.fields.preserved_entities),
            forbidden_drops_rule(source, target, contract.fields.forbidden_drops),
        ]
        score_result = self._scorer.score(source, target, contract)
        rules_pass = all(r.passed for r in rule_results)
        scores_pass = all(fs.passed for fs in score_result.field_scores)
        passed = rules_pass and scores_pass

        event = ViolationEvent(
            contract_name=contract.name,
            contract_version=contract.version,
            mode=contract.mode,
            passed=passed,
            score_result=score_result,
            rule_results=rule_results,
            triggered_at_iso=datetime.now(timezone.utc).isoformat(),
            source_summary=_summarise(source),
            target_summary=_summarise(target),
        )

        try:
            self._exporter.export(event)
        # Defensive boundary: the Exporter contract requires
        # implementations not to raise on transport failure, but we
        # cannot trust third-party concretes. Swallow here so a
        # misconfigured exporter never starves callers of their
        # ViolationEvent. Documented intent of the AC.
        except Exception as exc:
            logger.warning(
                "exporter %r raised during export: %s; evaluation result preserved",
                self._exporter.name,
                exc,
            )

        return event


def _summarise(payload: HandoffPayload) -> dict[str, str]:
    """Build a compact ``{field_name: stringified_value[:100]}`` summary.

    Truncating to 100 chars per value bounds the per-field contribution
    to the :meth:`ViolationEvent.to_compact_dict` budget, ahead of the
    secondary 4 KiB-of-JSON ceiling that runs at compact-dict time.
    """
    return {name: str(value)[:100] for name, value in payload.fields.items()}

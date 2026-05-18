# SPDX-License-Identifier: MIT
"""Pure handoff-evaluation hook (PRC-014).

``evaluate_handoff`` is the durable, framework-API-independent surface of
the LangGraph integration. It deliberately imports **no** ``langgraph``
symbol so that a LangGraph tool-API change can only break
``handoff_tool`` (the convenience wrapper built on top of this), never
this function. Users on the ``Command(goto=...)`` pattern call it
directly inside a node before returning the command.

Fail-open on missing contract (loud, deliberate -- see CLAUDE.md ->
"Fail-open on missing contract" and DEPENDENCIES.md section 9):
if ``contract_name`` is not in the registry, this logs a ``WARNING`` and
returns a synthetic *pass* :class:`ViolationEvent`. It does **not**
raise and does **not** push the synthetic event through any exporter.
Observability tooling that crashes the pipeline is worse than
observability that silently misses a check.

Default evaluator (lazy, not import-time): when no ``evaluator`` is
supplied, a module-cached ``Evaluator(EmbeddingProxy())`` is built on the
*first* call -- never at import. This is consistent with CLAUDE.md ->
"Constructor-time model load": that rule governs *where* an
``EmbeddingProxy`` loads its weights (in its own ``__init__``, not in
``score()``), and is preserved. What is deferred here is only *when the
default proxy instance is constructed* -- on first use rather than at
``import precept...``, so importing this module never triggers the
~80 MB / ~5 s model download. The first ``evaluate_handoff()`` call that
relies on the default pays that one-time cost; pass an explicit
``evaluator`` to control when it happens. Mirrors the ``default_registry``
convenience precedent in :mod:`precept.contract.registry`.

Async safety (see CLAUDE.md -> "Async safety"): LangGraph nodes may be
sync or async. ``evaluate_handoff`` is synchronous. When it detects a
running event loop (it is being called from inside an async node), it
runs the CPU-bound ``Evaluator.evaluate`` on a worker thread so the
GIL-releasing model inference does not monopolise the loop thread. A
bare synchronous call cannot itself yield to the loop, so the fully
non-blocking idiom from an async node remains
``await asyncio.to_thread(evaluate_handoff, ...)``; the auto-dispatch
here keeps the naive call from being pathologically loop-hostile.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from precept.contract.registry import default_registry
from precept.errors import HandoffBlockedError
from precept.evaluator.engine import Evaluator
from precept.integrations.langgraph.extractor import extract_payload
from precept.integrations.langgraph.impact import populate_impact_summary
from precept.scoring.base import ScoreResult
from precept.types import ViolationEvent

if TYPE_CHECKING:
    from precept.contract.registry import ContractRegistry
    from precept.contract.schema import HandoffContract
    from precept.scoring.base import HandoffPayload

__all__ = ["evaluate_handoff"]

logger = logging.getLogger(__name__)


_DEFAULT_EVALUATOR: Evaluator | None = None
_DEFAULT_EVALUATOR_LOCK = threading.Lock()


def _default_evaluator() -> Evaluator:
    """Return the lazily-built, module-cached default evaluator.

    Built on first call (never at import), guarded by a lock with a
    double-check so concurrent first calls construct the model exactly
    once. See module docstring for why this does not contradict the
    constructor-time-load discipline.
    """

    global _DEFAULT_EVALUATOR

    ev = _DEFAULT_EVALUATOR
    if ev is not None:
        return ev
    with _DEFAULT_EVALUATOR_LOCK:
        ev = _DEFAULT_EVALUATOR
        if ev is None:
            # Deferred import: keep sentence-transformers off this
            # module's import path so importing the pure hook is cheap.
            from precept.scoring.embedding_proxy import EmbeddingProxy

            logger.info(
                "constructing default Evaluator(EmbeddingProxy()) on first "
                "evaluate_handoff() call; this triggers a one-time model load"
            )
            ev = Evaluator(EmbeddingProxy())
            _DEFAULT_EVALUATOR = ev
        return ev


def _synthetic_pass_event(contract_name: str) -> ViolationEvent:
    """Build the fail-open synthetic *pass* event for a missing contract.

    Sentinel values are deliberate and documented: ``contract_version``
    is ``"unknown"`` (the real version is unknowable -- the contract was
    not found), ``mode`` is ``"warn"`` (fail-open never blocks),
    ``passed`` is ``True``, rule/field results are empty, and the score
    is a vacuous ``1.0`` from a ``"synthetic"`` scorer. This event is
    returned to the caller but is **never** exported.
    """

    now = datetime.now(timezone.utc).isoformat()
    return ViolationEvent(
        contract_name=contract_name,
        contract_version="unknown",
        mode="warn",
        passed=True,
        score_result=ScoreResult(
            overall_score=1.0,
            field_scores=[],
            scorer_name="synthetic",
            scorer_version="0",
            timestamp_iso=now,
        ),
        rule_results=[],
        triggered_at_iso=now,
        source_summary={},
        target_summary={},
    )


def _evaluate(
    evaluator: Evaluator,
    source: HandoffPayload,
    target: HandoffPayload,
    contract: HandoffContract,
) -> ViolationEvent:
    """Run ``evaluator.evaluate``, off-loading it when inside a loop.

    See module docstring -> "Async safety". The per-call single-worker
    pool is intentional: the dominant cost is the ~500 ms inference, not
    the microsecond pool setup; the ``with`` block joins the worker
    deterministically (no leaked thread, no ``atexit`` reliance); and a
    per-call pool avoids the process-wide global -- with its own
    ``max_workers`` tuning and shutdown lifecycle -- that PRC-014's scope
    does not call for. The v0 limitation under burst-concurrent handoffs
    is tracked in DEPENDENCIES.md section 10 (Technical Debt Ledger).
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop: a plain sync call path. Run inline.
        return evaluator.evaluate(source, target, contract)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(evaluator.evaluate, source, target, contract).result()


def evaluate_handoff(
    source: Any,
    target: Any,
    contract_name: str,
    *,
    registry: ContractRegistry | None = None,
    evaluator: Evaluator | None = None,
    raise_on_block: bool = True,
) -> ViolationEvent:
    """Evaluate a single agent-to-agent handoff against a named contract.

    ``source`` and ``target`` are arbitrary upstream state -- a LangGraph
    state ``dict``, a Pydantic ``BaseModel``, or any object. Only the
    fields named by the contract are read (see
    :func:`precept.integrations.langgraph.extractor.extract_payload`); the
    parameters are typed ``Any`` because the boundary state is genuinely
    polymorphic, the one case CLAUDE.md permits.

    Resolution order: ``registry`` defaults to
    :data:`precept.contract.registry.default_registry`; ``evaluator``
    defaults to the lazily-built module default (see module docstring).

    Behaviour:

    * **Missing contract** -> log ``WARNING``, return a synthetic *pass*
      event, do not raise, do not export (fail-open).
    * Construct source/target :class:`HandoffPayload` via the contracted-
      field extractor, call ``evaluator.evaluate`` (which also dispatches
      to the configured exporter), and obtain the
      :class:`ViolationEvent`.
    * If ``raise_on_block`` (default ``True``) **and**
      ``contract.mode == "block"`` **and** ``not event.passed``: build a
      :class:`precept.errors.HandoffBlockedError`, populate its impact
      summary (PRC-015) immediately before raising, and raise it.
    * Otherwise (warn mode, passing, or ``raise_on_block=False``) return
      the event; the caller decides what to do.

    The synchronous ``evaluator.evaluate`` is auto-dispatched to a worker
    thread when a running event loop is detected; see module docstring ->
    "Async safety".
    """

    active_registry = registry if registry is not None else default_registry

    try:
        contract = active_registry.get(contract_name)
    except KeyError:
        logger.warning(
            "contract %r not found in registry (available: %s); "
            "failing open -- returning synthetic pass event, no block, no export",
            contract_name,
            ", ".join(active_registry.list_contracts()) or "(none)",
        )
        return _synthetic_pass_event(contract_name)

    active_evaluator = evaluator if evaluator is not None else _default_evaluator()

    source_payload = extract_payload(source, contract)
    target_payload = extract_payload(target, contract)

    event = _evaluate(active_evaluator, source_payload, target_payload, contract)

    if raise_on_block and contract.mode == "block" and not event.passed:
        error = HandoffBlockedError(event)
        # PRC-015 wiring: the single bounded post-construction write,
        # performed immediately before re-raise (see HandoffBlockedError
        # docstring and ISSUES.md PRC-015 AC).
        populate_impact_summary(error)
        raise error

    return event

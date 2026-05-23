# SPDX-License-Identifier: MIT
"""Precept demo runner -- single-shot contract-engine demonstration (PRC-019).

Reads the committed fixture traces under ``examples/fixtures/``, evaluates
each hop against the contract named in the fixture's
``handoff_metadata.contract_name`` (loaded from ``examples/contracts/``),
prints a human-readable summary to stdout, and writes a deterministic
JSON trace file the PRC-022 observatory renders.

This is the *contract engine* demo, not the LangGraph runtime demo: it
calls :class:`precept.evaluator.engine.Evaluator` directly with
:class:`precept.scoring.base.HandoffPayload` instances built straight
from the fixture JSON. LangGraph end-to-end coverage lives in
``Dev/tests/integration/integrations/langgraph/`` (PRC-014). Per the
PRC-019 acceptance criteria the demo deliberately does NOT wire into a
real LangGraph pipeline.

Exit code convention (PRC-019 AC, Unix convention):

* ``0`` -- the demo ran end-to-end. Violations detected in a degraded
  trace are a *successful* demo run; the violation count is surfaced via
  stdout and the output JSON, never via the exit code. A reviewer typing
  ``python examples/demo.py`` and seeing exit code ``1`` would assume
  the script crashed -- so violations never produce that.
* ``2`` -- a runtime error prevented the demo from completing (fixture
  missing, contract unreadable, output path unwritable, unexpected
  exception). The error message is printed to stderr prefixed
  ``DEMO FAILED:``.

Determinism (PRC-019 AC: "running the same trace twice produces
byte-identical output JSON"). Three fields in
:class:`precept.types.ViolationEvent` are set from
``datetime.now(timezone.utc)`` or ``uuid.uuid4()`` at evaluation time
and so vary run to run: ``event_id``, ``triggered_at_iso``, and the
nested ``score_result.timestamp_iso``. The runner overwrites these in
the *serialised* dict (the live :class:`ViolationEvent` is left
untouched) with stable values derived from the hop's fixture timestamp
and a SHA-256 of the (trace_name, hop_index, contract_name) tuple.
``generated_at_iso`` at the top of the output is the last hop's fixture
timestamp for the same reason. Embedding-cosine scores are themselves
deterministic on a single machine (``EmbeddingProxy`` runs
``sentence-transformers`` with grad disabled and frozen weights), so
they need no special handling.

Impact-summary baking (PRC-022 coordination, see ISSUES.md PRC-022 ->
"Impact copy provenance"). The static observatory loads this JSON
client-side and runs no Python; the runner therefore calls
``render_impact_text`` directly for each failed hop and writes the
rendered string into the per-hop ``impact_summary`` key. Source and
target agent names come from the fixture's ``handoff_metadata``
(authoritative) rather than the contract-name-parsing heuristic in
``impact._agents_from_contract_name`` (which has a documented v0
weakness for source names embedding ``_to_``; see DEPENDENCIES.md
section 10).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from precept import __version__ as _PRECEPT_VERSION
from precept.contract.schema import HandoffContract
from precept.contract.yaml_loader import load_contract
from precept.evaluator.engine import Evaluator
from precept.exporters.base import NoOpExporter
from precept.integrations.langgraph.impact import render_impact_text
from precept.scoring.base import HandoffPayload
from precept.scoring.embedding_proxy import EmbeddingProxy
from precept.types import ViolationEvent

_HERE = Path(__file__).resolve().parent
_DEFAULT_CONTRACTS_DIR = _HERE / "contracts"
_DEFAULT_FIXTURES_DIR = _HERE / "fixtures"
_DEFAULT_OUTPUT_PATH = _HERE / "output" / "demo_trace.json"

_OUTPUT_SCHEMA_VERSION = "0.1"
_OBSERVATORY_HINT = "Open docs/index.html and drop examples/output/demo_trace.json to view details"
_SCORE_GATE_LABEL = "minimum_fidelity"

_RULE_HEAVY = "=" * 62
_RULE_LIGHT = "-" * 62
_CHECK = "✓"
_CROSS = "✗"

_ANSI_RESET = "\033[0m"
_ANSI_GREEN = "\033[32m"
_ANSI_RED = "\033[31m"
_ANSI_BOLD = "\033[1m"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="demo.py",
        description="Run the Precept handoff-integrity demo against a committed fixture trace.",
    )
    parser.add_argument(
        "--trace",
        choices=("clean", "degraded"),
        default="degraded",
        help="Which fixture trace to evaluate (default: degraded).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT_PATH,
        help=f"Path to write the demo trace JSON (default: {_DEFAULT_OUTPUT_PATH}).",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=_DEFAULT_FIXTURES_DIR,
        help=f"Directory containing <trace>_trace.json files (default: {_DEFAULT_FIXTURES_DIR}).",
    )
    parser.add_argument(
        "--contracts-dir",
        type=Path,
        default=_DEFAULT_CONTRACTS_DIR,
        help=f"Directory containing *.yaml contracts (default: {_DEFAULT_CONTRACTS_DIR}).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colour output even on a TTY.",
    )
    return parser.parse_args(argv)


def _color(text: str, code: str, *, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{code}{text}{_ANSI_RESET}"


def _load_contracts(contracts_dir: Path) -> dict[str, HandoffContract]:
    """Load every ``*.yaml`` in ``contracts_dir``, keyed by contract name.

    Raises ``FileNotFoundError`` if ``contracts_dir`` does not exist or
    holds no contracts -- the demo cannot proceed without contracts and
    the failure should be loud, not silent. Individual contract files
    surface their own ``ContractValidationError`` via ``load_contract``.
    """
    if not contracts_dir.is_dir():
        raise FileNotFoundError(f"contracts directory not found: {contracts_dir}")
    contracts: dict[str, HandoffContract] = {}
    for path in sorted(contracts_dir.glob("*.yaml")):
        contract = load_contract(path)
        contracts[contract.name] = contract
    if not contracts:
        raise FileNotFoundError(f"no *.yaml contracts found in {contracts_dir}")
    return contracts


def _load_trace(fixtures_dir: Path, trace_name: str) -> dict[str, Any]:
    """Load and JSON-parse ``<fixtures_dir>/<trace_name>_trace.json``."""
    path = fixtures_dir / f"{trace_name}_trace.json"
    with path.open(encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def _failing_rule_name(event: ViolationEvent) -> str:
    """First ``passed is False`` rule, or the score-gate sentinel.

    Mirrors :func:`precept.integrations.langgraph.impact._failing_rule_name`
    so the rule label this runner feeds into ``render_impact_text`` is
    the same label the production impact populator would have selected.
    The sentinel is intentionally absent from ``IMPACT_TEMPLATES`` so it
    renders the documented fallback string.
    """
    for r in event.rule_results:
        if not r.passed:
            return r.rule_name
    return _SCORE_GATE_LABEL


def _violation_reason(event: ViolationEvent) -> str | None:
    """Human-readable one-liner explaining the failure, or ``None`` on a pass.

    Prefers the first failing rule's ``violation_message`` (always
    populated when ``passed is False``). Falls back to a synthesised
    score-gate message when every rule passed but per-field scores
    dragged the event under threshold.
    """
    if event.passed:
        return None
    for r in event.rule_results:
        if not r.passed and r.violation_message:
            return r.violation_message
    failing_fields = [fs.field_name for fs in event.score_result.field_scores if not fs.passed]
    if failing_fields:
        return f"field score below threshold for: {', '.join(failing_fields)}"
    return None


def _render_impact(event: ViolationEvent, source_agent: str, target_agent: str) -> str | None:
    """Bake the observatory's impact line for a failed hop, else ``None``.

    Uses agent names from ``handoff_metadata`` rather than the
    contract-name-parsing heuristic; see module docstring.
    """
    if event.passed:
        return None
    return render_impact_text(
        event.contract_name,
        _failing_rule_name(event),
        source_agent,
        target_agent,
    )


def _stable_event_id(trace_name: str, hop_index: int, contract_name: str) -> str:
    """SHA-256-derived event id, prefixed so it cannot be confused with a UUID4."""
    digest = hashlib.sha256(f"{trace_name}:{hop_index}:{contract_name}".encode()).hexdigest()
    return f"demo-{digest[:24]}"


def _stabilise_event_dict(
    event: ViolationEvent,
    *,
    hop_index: int,
    trace_name: str,
    fixture_timestamp_iso: str,
) -> dict[str, Any]:
    """Return ``event.model_dump(mode='json')`` with non-deterministic fields fixed.

    Overwrites ``event_id``, ``triggered_at_iso``, and the nested
    ``score_result.timestamp_iso``. The live :class:`ViolationEvent` is
    not modified -- this is a pure projection.
    """
    d: dict[str, Any] = event.model_dump(mode="json")
    d["event_id"] = _stable_event_id(trace_name, hop_index, event.contract_name)
    d["triggered_at_iso"] = fixture_timestamp_iso
    d["score_result"]["timestamp_iso"] = fixture_timestamp_iso
    return d


def _build_trace_output(
    trace_name: str,
    hops_in: list[dict[str, Any]],
    events: list[ViolationEvent],
    impacts: list[str | None],
) -> dict[str, Any]:
    """Assemble the output JSON for the observatory.

    Echoes the fixture's ``source_payload`` / ``target_payload`` so the
    observatory can render per-field comparisons without re-fetching
    fixtures, attaches the deterministic per-hop ``violation_event``,
    and writes the baked ``impact_summary`` (``None`` on a passing hop
    so the observatory can render an "all clear" badge consistently).
    ``generated_at_iso`` is the last hop's fixture timestamp for
    determinism (see module docstring).
    """
    out_hops: list[dict[str, Any]] = []
    for i, (hop, event, impact) in enumerate(zip(hops_in, events, impacts, strict=True)):
        meta: dict[str, str] = hop["handoff_metadata"]
        out_hops.append(
            {
                "handoff_metadata": meta,
                "source_payload": hop["source_payload"],
                "target_payload": hop["target_payload"],
                "violation_event": _stabilise_event_dict(
                    event,
                    hop_index=i,
                    trace_name=trace_name,
                    fixture_timestamp_iso=meta["timestamp_iso"],
                ),
                "impact_summary": impact,
            }
        )
    generated_at = hops_in[-1]["handoff_metadata"]["timestamp_iso"] if hops_in else ""
    return {
        "schema_version": _OUTPUT_SCHEMA_VERSION,
        "precept_version": _PRECEPT_VERSION,
        "trace_name": trace_name,
        "generated_at_iso": generated_at,
        "hops": out_hops,
    }


def _print_banner(trace_name: str, fixture_path: Path, *, color: bool) -> None:
    print(_RULE_HEAVY)
    title = f"  Precept v{_PRECEPT_VERSION} -- Handoff Integrity Demo"
    print(_color(title, _ANSI_BOLD, enabled=color))
    print(_RULE_HEAVY)
    print()
    print(f"Trace: {trace_name}   ({fixture_path})")


def _print_rule_row(event: ViolationEvent, *, color: bool) -> None:
    parts: list[str] = []
    for r in event.rule_results:
        mark = (
            _color(_CHECK, _ANSI_GREEN, enabled=color)
            if r.passed
            else _color(_CROSS, _ANSI_RED, enabled=color)
        )
        parts.append(f"{r.rule_name} {mark}")
    print(f"        rules: {'  '.join(parts)}")


def _print_hop(
    *,
    index: int,
    total: int,
    hop: dict[str, Any],
    event: ViolationEvent,
    impact: str | None,
    color: bool,
) -> None:
    meta: dict[str, str] = hop["handoff_metadata"]
    source = meta["source_agent"]
    target = meta["target_agent"]
    contract = meta["contract_name"]
    status = (
        _color("PASS", _ANSI_GREEN, enabled=color)
        if event.passed
        else _color("FAIL", _ANSI_RED, enabled=color)
    )
    print()
    print(f"  [{index}/{total}] {source} -> {target}   contract: {contract}")
    print(f"        score {event.score_result.overall_score:.3f}   {status}")
    _print_rule_row(event, color=color)
    reason = _violation_reason(event)
    if reason is not None:
        print(f"        reason: {reason}")
    if impact is not None:
        print(f"        impact: {impact}")


def _summary_violation_phrase(n: int) -> str:
    if n == 0:
        return "no violations"
    if n == 1:
        return "1 violation detected"
    return f"{n} violations detected"


def _print_summary(
    *,
    total: int,
    failed: int,
    elapsed_secs: float,
    output_path: Path,
) -> None:
    passed = total - failed
    print()
    print(_RULE_LIGHT)
    print(f"  {total} handoffs   {passed} passed   {failed} failed   elapsed {elapsed_secs:.1f}s")
    print(f"  Trace written to {output_path}")
    print(f"  {_OBSERVATORY_HINT}")
    print(_RULE_LIGHT)
    print(f"DEMO COMPLETED ({_summary_violation_phrase(failed)})")


def _run(args: argparse.Namespace, *, color: bool) -> None:
    """Single end-to-end pass; raises on any failure so ``main`` returns 2."""
    fixture_path = args.fixtures_dir / f"{args.trace}_trace.json"

    overall_start = time.perf_counter()

    _print_banner(args.trace, fixture_path, color=color)

    # Construct the scorer early so the model-load latency is visible
    # *before* the per-hop section starts; otherwise a ~3-10s pause would
    # appear inside the [1/N] block and look like a single very slow hop.
    print()
    print("Loading embedding model (~80 MB; first run downloads, then cached)...", flush=True)
    load_start = time.perf_counter()
    scorer = EmbeddingProxy()
    print(f"  ... done ({time.perf_counter() - load_start:.1f}s)")

    print(f"Loading contracts from {args.contracts_dir}/")
    contracts = _load_contracts(args.contracts_dir)
    print(f"  ... {len(contracts)} loaded")

    trace = _load_trace(args.fixtures_dir, args.trace)
    hops: list[dict[str, Any]] = trace["hops"]

    evaluator = Evaluator(scorer, NoOpExporter())

    events: list[ViolationEvent] = []
    impacts: list[str | None] = []
    for i, hop in enumerate(hops, start=1):
        meta = hop["handoff_metadata"]
        contract_name = meta["contract_name"]
        if contract_name not in contracts:
            raise KeyError(
                f"hop {i} references contract {contract_name!r} but no such "
                f"contract was loaded from {args.contracts_dir}"
            )
        source = HandoffPayload(fields=hop["source_payload"])
        target = HandoffPayload(fields=hop["target_payload"])
        event = evaluator.evaluate(source, target, contracts[contract_name])
        impact = _render_impact(event, meta["source_agent"], meta["target_agent"])
        _print_hop(
            index=i,
            total=len(hops),
            hop=hop,
            event=event,
            impact=impact,
            color=color,
        )
        events.append(event)
        impacts.append(impact)

    output = _build_trace_output(args.trace, hops, events, impacts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, sort_keys=True)
        f.write("\n")

    failed = sum(1 for e in events if not e.passed)
    _print_summary(
        total=len(events),
        failed=failed,
        elapsed_secs=time.perf_counter() - overall_start,
        output_path=args.output,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    color_enabled = sys.stdout.isatty() and not args.no_color
    try:
        _run(args, color=color_enabled)
    # Boundary-only broad catch: any uncaught exception is a "runtime
    # error" per the PRC-019 AC and must translate to exit 2 with a
    # human-legible "DEMO FAILED" line, not a Python traceback dump.
    except Exception as exc:
        print(f"DEMO FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

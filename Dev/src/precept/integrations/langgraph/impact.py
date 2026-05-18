# SPDX-License-Identifier: MIT
"""Violation impact summaries -- the populator (PRC-015).

When a ``mode="block"`` contract fails, the supervisor (or any layer
catching :class:`precept.errors.HandoffBlockedError`) needs a
human-legible description of *what breaks downstream* -- not just which
rule tripped. This module is the **populator**: it fills the
default-empty ``HandoffBlockedError.impact_summary`` with concrete,
domain-specific copy drawn from a curated lookup table.

Why a Python dict and not YAML (per ISSUES.md PRC-015): a contract
rename in a YAML table would silently fall through to the generic
fallback for every violation. A Python dict surfaces a missing key at
test time (``assert (contract, rule) in IMPACT_TEMPLATES``) and is
IDE-refactorable. YAML-based runtime override is deferred to Phase 2.

**Agent identity.** Neither :class:`precept.types.ViolationEvent` nor
:class:`precept.contract.schema.HandoffContract` carries source/target
agent names, and ``populate_impact_summary``'s signature (fixed by the
ticket) receives only the error. Agent names are therefore derived from
the contract name, which follows the ``<source>_to_<target>``
convention used by the demo contracts (e.g. ``researcher_to_summariser``
-> ``researcher`` / ``summariser``). A contract name without the
``_to_`` infix falls back to the generic ``upstream`` / ``downstream``.

**Failing rule.** The first :class:`~precept.evaluator.rules.RuleResult`
with ``passed is False`` (evaluator order: required_fields,
preserved_entities, forbidden_drops) is the one the operator most needs
explained. A block produced purely by a sub-threshold field score --
every rule passes but :attr:`ViolationEvent.passed` is ``False`` -- has
no failing rule; it is labelled :data:`_SCORE_GATE_LABEL` which, not
being a template key, renders the default fallback impact text.

This is a deliberate v0 placeholder (per ISSUES.md Q8): impact text is
hand-written, not computed. Learned impact prediction is Phase 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from precept.errors import HandoffBlockedError

__all__ = [
    "DEFAULT_IMPACT_FALLBACK",
    "IMPACT_TEMPLATES",
    "populate_impact_summary",
    "render_impact_text",
]


DEFAULT_IMPACT_FALLBACK = (
    "Downstream agents may receive incomplete or misleading context for this decision."
)
"""Rendered impact text when no ``(contract_name, rule_name)`` entry
matches. Named (not inlined) so tests can assert the fallthrough path
explicitly."""


IMPACT_TEMPLATES: dict[tuple[str, str], str] = {
    ("researcher_to_summariser", "required_fields"): (
        "Writer agent will compose output without hypothesis grounding; "
        "conclusions may be unsupported"
    ),
    ("researcher_to_summariser", "preserved_entities"): (
        "Source attribution is dropped before summarisation; final output "
        "cannot trace claims to citations"
    ),
    ("summariser_to_writer", "preserved_entities"): (
        "Primary sources may be dropped from final output, breaking citation integrity"
    ),
    ("summariser_to_writer", "forbidden_drops"): (
        "Uncertainty bounds removed; downstream output will overstate confidence"
    ),
}
"""Curated ``(contract_name, failing_rule_name) -> impact_text`` table.
Extend with one entry per demo contract+rule combination as PRC-018
contracts land; the regression test in ``test_impact.py`` asserts no
demo combination is omitted."""


_SCORE_GATE_LABEL = "minimum_fidelity"
"""Rule-slot label used when a block is caused solely by a sub-threshold
field score (no rule failed). Intentionally absent from
:data:`IMPACT_TEMPLATES` so it renders :data:`DEFAULT_IMPACT_FALLBACK`."""

_AGENT_INFIX = "_to_"
_FALLBACK_SOURCE_AGENT = "upstream"
_FALLBACK_TARGET_AGENT = "downstream"


def _agents_from_contract_name(contract_name: str) -> tuple[str, str]:
    """Derive ``(source_agent, target_agent)`` from a contract name.

    Demo contracts use ``<source>_to_<target>`` with single-token agent
    names (``researcher_to_summariser`` -> ``researcher`` /
    ``summariser``). Partition on the *first* ``_to_``, so a target that
    itself contains the infix is preserved on the target side
    (``a_to_b_to_c`` -> ``a`` / ``b_to_c``). The corollary v0 limitation:
    a *source* agent name that embeds ``_to_`` mis-attributes the split
    (``data_to_json_to_writer`` -> ``data`` / ``json_to_writer``). The
    demo agents are single-token so this does not arise; the convention
    and its failure mode are tracked in DEPENDENCIES.md section 10.
    Names without the infix -- or with an empty side -- yield the
    generic ``upstream`` / ``downstream`` pair.
    """

    source, infix, target = contract_name.partition(_AGENT_INFIX)
    if not infix or not source or not target:
        return _FALLBACK_SOURCE_AGENT, _FALLBACK_TARGET_AGENT
    return source, target


def render_impact_text(
    contract_name: str,
    rule_name: str,
    source_agent: str,
    target_agent: str,
) -> str:
    """Render the one-line impact narrative for a blocked handoff.

    Pure and side-effect-free so the observatory (PRC-022) can render
    impact copy without constructing a :class:`HandoffBlockedError`.
    Looks up ``(contract_name, rule_name)`` in :data:`IMPACT_TEMPLATES`,
    falling back to :data:`DEFAULT_IMPACT_FALLBACK` on a miss.
    """

    impact_text = IMPACT_TEMPLATES.get((contract_name, rule_name), DEFAULT_IMPACT_FALLBACK)
    return (
        f"Handoff from {source_agent} to {target_agent} blocked: "
        f"{rule_name} failed on contract '{contract_name}'. "
        f"Downstream impact: {impact_text}."
    )


def _failing_rule_name(error: HandoffBlockedError) -> str:
    """Return the first failed rule's name, or the score-gate label.

    Evaluator order is required_fields -> preserved_entities ->
    forbidden_drops; the first ``passed is False`` entry is selected. A
    block with every rule passing is a pure field-score (fidelity-floor)
    failure and is labelled :data:`_SCORE_GATE_LABEL`. The same branch
    covers a hand-constructed error with an empty ``rule_results``.
    """

    for result in error.violation_event.rule_results:
        if not result.passed:
            return result.rule_name
    return _SCORE_GATE_LABEL


def populate_impact_summary(error: HandoffBlockedError) -> None:
    """Set ``error.impact_summary`` in place from the attached event.

    This is the single, bounded post-construction write described in
    :class:`precept.errors.HandoffBlockedError`'s contract; PRC-014's
    integration layer calls it immediately before re-raising. Reads only
    ``error.violation_event`` and never mutates it -- the attached event
    is left byte-for-byte identical so exporters see the unmodified
    record.
    """

    event = error.violation_event
    source_agent, target_agent = _agents_from_contract_name(event.contract_name)
    error.impact_summary = render_impact_text(
        event.contract_name,
        _failing_rule_name(error),
        source_agent,
        target_agent,
    )

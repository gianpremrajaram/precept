# SPDX-License-Identifier: MIT
"""OpenTelemetry GenAI exporter (PRC-020).

Emits one ``gen_ai.evaluation.result`` event per :class:`ViolationEvent`
following the OTel GenAI semantic conventions (status: Development /
experimental as of April 2026). The emission target is whatever the
host application has configured -- Datadog, Grafana, Honeycomb,
OpenObserve all consume the standard shape without custom integration.

**Optional dependency.** This module imports
``opentelemetry.api`` and ``opentelemetry.sdk``; both ship in the
``[otel]`` extra (``pip install precept[otel]``). When neither is
installed, the module still imports cleanly; the
:class:`OTelExporter` class becomes a stub whose constructor raises
:class:`ImportError` with the install hint. This is the
documented base-install behaviour (DEPENDENCIES.md §3.2, §4.5).

**Stable vs experimental emission paths.** The primary path is
``span.add_event`` -- a stable OTel API surface. The
:class:`opentelemetry._events.EventLogger` API is still experimental;
when a user passes an ``event_logger`` to the constructor we prefer
it (the user has opted in), otherwise the stable span-event path is
used. This matches PRC-020 AC: the constructor signature exposes both
hooks; the runtime decision is driven by what the user supplied.

**OTEL_SEMCONV_STABILITY_OPT_IN.** Read at every :meth:`export` and
logged at DEBUG. v0 emits only the experimental GenAI schema (the
only one in scope), so the env var has no behavioural branch yet --
it is wired in as a forward-compat hook so future contributors find
the integration point already in place when OTel renames an attribute
(DEPENDENCIES.md §4.3 lays out the emit-then-migrate plan).

**Content capture gate.** By default, ``precept.source.*`` and
``precept.target.*`` attributes are stripped before emission so
payload values do not leak to telemetry backends. Setting
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=True`` (the OTel
GenAI canonical env var) opts in to including them.

**Per-attribute size check.** :meth:`ViolationEvent.to_compact_dict`
already enforces a 4 KiB total ceiling; this exporter additionally
checks each individual string attribute and truncates any one
exceeding 4 KiB with a ``...[truncated]`` suffix. This is the second
defence per DEPENDENCIES.md §4.4.

**Failure isolation.** Per the :class:`Exporter` contract, transport
or SDK failures NEVER raise out of :meth:`export`. SDK not configured
(global no-op provider, no real span available) is logged at DEBUG;
unexpected OTel exceptions are also logged at DEBUG and swallowed.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, ClassVar

from precept.exporters.base import Exporter
from precept.types import ViolationEvent

# Per-attribute size budget (UTF-8 bytes). Same constant as
# ``precept.types._COMPACT_LIMIT_BYTES`` (the event-level ceiling) --
# any single string attribute that somehow exceeds 4 KiB on its own
# (rare; the event-level ceiling normally bites first) is truncated by
# this exporter as a backstop.
_PER_ATTRIBUTE_LIMIT_BYTES = 4096
_TRUNCATION_SUFFIX = "...[truncated]"


# Runtime import guard. Both opentelemetry-api and -sdk ship in the
# ``[otel]`` extra (DEPENDENCIES.md §3.2). Module import must succeed
# on base installs (DEPENDENCIES.md §4.5); instantiation surfaces the
# install hint instead.
try:
    from opentelemetry import trace as _trace_api

    _OTEL_AVAILABLE = True
except ImportError:
    _trace_api = None  # type: ignore[assignment, unused-ignore]
    _OTEL_AVAILABLE = False


if TYPE_CHECKING:
    # Type-only imports. ``from __future__ import annotations`` keeps
    # these out of runtime resolution, and ``[[tool.mypy.overrides]]
    # opentelemetry.*`` keeps mypy green on base installs where these
    # are not importable.
    from opentelemetry._events import EventLogger
    from opentelemetry.trace import Span, Tracer

__all__ = ["OTelExporter"]


logger = logging.getLogger(__name__)


_INSTALL_HINT = "OTelExporter requires the 'otel' extra. Install via: pip install precept[otel]"


if _OTEL_AVAILABLE:

    class OTelExporter(Exporter):
        """Emit ``gen_ai.evaluation.result`` events to OpenTelemetry.

        Constructor parameters:

        ``tracer``: optional :class:`opentelemetry.trace.Tracer`. When
        omitted, falls back to ``trace.get_tracer(__name__)``, which
        the host application's globally configured ``TracerProvider``
        resolves.

        ``event_logger``: optional
        :class:`opentelemetry._events.EventLogger`. When supplied, the
        exporter prefers the experimental events API for emission.
        Otherwise the stable ``span.add_event`` path is used.

        See module docstring for the content-capture env-var gate, the
        semantic-conventions opt-in hook, and the per-attribute 4 KiB
        truncation backstop.
        """

        name: ClassVar[str] = "otel"

        def __init__(
            self,
            tracer: Tracer | None = None,
            event_logger: EventLogger | None = None,
        ) -> None:
            assert _trace_api is not None  # narrowed by _OTEL_AVAILABLE
            self._tracer: Tracer = tracer if tracer is not None else _trace_api.get_tracer(__name__)
            self._event_logger: EventLogger | None = event_logger

        def export(self, event: ViolationEvent) -> None:
            attrs = _build_attributes(event)
            try:
                self._emit(event, attrs)
            # Per Exporter contract: never raise out of export() on
            # transport failure. Catch broadly here because OTel SDK
            # errors are wide-ranging (network, serialisation, exporter
            # pipe) and we cannot enumerate them; CLAUDE.md tolerates a
            # broad except at this kind of integration boundary so
            # long as the failure is logged. We log at DEBUG so a
            # misconfigured OTel does not flood WARNING.
            except Exception as exc:
                logger.debug("OTelExporter: export failed: %s", exc)

        def _emit(
            self,
            event: ViolationEvent,
            attrs: dict[str, Any],
        ) -> None:
            assert _trace_api is not None

            # Forward-compat hook: read OTEL_SEMCONV_STABILITY_OPT_IN
            # so a future contributor finds the integration point
            # already wired. v0 only emits the experimental GenAI
            # schema (the only one in scope), so the value has no
            # behavioural branch yet -- see module docstring + AC.
            stability_opt_in = os.environ.get("OTEL_SEMCONV_STABILITY_OPT_IN")
            if stability_opt_in:
                logger.debug(
                    "OTelExporter: OTEL_SEMCONV_STABILITY_OPT_IN=%r "
                    "(v0 emits experimental GenAI schema only)",
                    stability_opt_in,
                )

            event_name = "gen_ai.evaluation.result"

            # Experimental EventLogger path: opted into by the user
            # supplying an event_logger to the constructor.
            if self._event_logger is not None:
                from opentelemetry._events import Event as _OTelEvent

                self._event_logger.emit(_OTelEvent(name=event_name, attributes=attrs))
                return

            # Stable path: attach to current recording span if one
            # exists; otherwise open a synthetic ``invoke_agent`` span
            # (per PRC-020 AC).
            current_span: Span = _trace_api.get_current_span()
            if current_span.is_recording():
                current_span.add_event(event_name, attributes=attrs)
                return

            with self._tracer.start_as_current_span("invoke_agent") as synth:
                synth.add_event(event_name, attributes=attrs)
                if not synth.is_recording():
                    # No SDK configured (global no-op TracerProvider)
                    # — the event has been written to a no-op span and
                    # is effectively dropped. Log at DEBUG so the
                    # operator can detect the misconfiguration without
                    # being paged.
                    logger.debug(
                        "OTelExporter: no OTel SDK configured; "
                        "gen_ai.evaluation.result event dropped"
                    )

else:

    class OTelExporter(Exporter):  # type: ignore[no-redef]
        """Stub for environments without the ``[otel]`` extra installed.

        Construction raises :class:`ImportError` with the install hint
        (PRC-020 AC). :meth:`export` also raises the same
        :class:`ImportError` as a defensive backstop for any code path
        that holds a class reference and bypasses ``__init__`` (e.g.
        subclassing).
        """

        name: ClassVar[str] = "otel"

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(_INSTALL_HINT)

        def export(self, event: ViolationEvent) -> None:
            raise ImportError(_INSTALL_HINT)


def _build_attributes(event: ViolationEvent) -> dict[str, Any]:
    """Build the OTel attribute dict for ``event``.

    Combines :meth:`ViolationEvent.to_compact_dict` output (Precept
    namespace, already 4 KiB-capped) with the GenAI canonical
    attribute set, then applies the content-capture gate and the
    per-attribute size backstop. Returned dict is the ready-to-emit
    attribute set.
    """
    attrs: dict[str, Any] = dict(event.to_compact_dict())

    # GenAI canonical attributes (PRC-020 AC). These names mirror the
    # OTel GenAI semantic conventions, so any backend tracking the
    # spec (Datadog, Grafana, Honeycomb) can consume the score without
    # parsing precept.* keys.
    attrs["gen_ai.evaluation.name"] = event.contract_name
    attrs["gen_ai.evaluation.score.value"] = event.score_result.overall_score
    attrs["gen_ai.evaluation.score.label"] = "passed" if event.passed else "failed"
    attrs["gen_ai.evaluation.explanation"] = _explanation_text(event)

    # Content-capture gate. The OTel GenAI canonical env var name is
    # OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT; "True" is
    # the documented opt-in value (case-insensitive accepted).
    capture = (
        os.environ.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "").strip().lower()
        == "true"
    )
    if not capture:
        attrs = {
            k: v
            for k, v in attrs.items()
            if not (k.startswith("precept.source.") or k.startswith("precept.target."))
        }

    # Per-attribute size backstop. Only string-valued attributes are
    # truncatable; numeric and bool attrs fit comfortably under any
    # backend limit.
    for k, v in list(attrs.items()):
        if isinstance(v, str) and len(v.encode("utf-8")) > _PER_ATTRIBUTE_LIMIT_BYTES:
            attrs[k] = _truncate_utf8(v, _PER_ATTRIBUTE_LIMIT_BYTES)

    return attrs


def _explanation_text(event: ViolationEvent) -> str:
    """Human-readable explanation for the canonical event payload.

    On pass: empty string (the AC requires the key to be present, not
    to carry content). On fail: ``;``-joined non-None
    ``violation_message`` strings, or a generic fallback when the
    failure was a pure score-gate (no rule produced a message).
    """
    if event.passed:
        return ""
    messages = [r.violation_message for r in event.rule_results if r.violation_message]
    if messages:
        return "; ".join(messages)
    return "evaluation failed: see precept.score.* attributes for per-field detail"


def _truncate_utf8(value: str, limit_bytes: int) -> str:
    """Truncate ``value`` so its UTF-8 byte length plus the truncation
    suffix fits within ``limit_bytes``.

    Bytes are sliced (not characters) so a multi-byte glyph straddling
    the boundary is handled cleanly via ``errors="ignore"`` on decode.
    """
    suffix_len = len(_TRUNCATION_SUFFIX.encode("utf-8"))
    head_budget = max(limit_bytes - suffix_len, 0)
    head = value.encode("utf-8")[:head_budget].decode("utf-8", errors="ignore")
    return head + _TRUNCATION_SUFFIX

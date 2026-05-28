# SPDX-License-Identifier: Apache-2.0
"""Exporter ABC plus the two built-in concrete sinks.

The :class:`Exporter` ABC is the integration surface between the
evaluator (PRC-013) and any telemetry transport (OTel in PRC-020, JSON
file in PRC-021, plus user-supplied exporters). Defining the ABC here
keeps the evaluator transport-agnostic.

Implementation contract (rendered in :class:`Exporter`'s docstring):

* ``export()`` MUST NOT raise on transport failure. Failed exports are
  logged and swallowed; an evaluator call never fails because telemetry
  is misconfigured (see ``CLAUDE.md`` -> "Error handling").
* ``export()`` MUST NOT mutate ``event`` -- the same instance may be
  passed to multiple exporters via :class:`MultiExporter`.
* ``export()`` MUST be safe to call from multiple threads on a single
  instance. Concrete exporters that hold transport handles must
  protect them with the appropriate primitive.
* ``export()`` SHOULD be idempotent on repeated calls with the same
  ``event.event_id`` -- best-effort dedup is the exporter's
  responsibility, not the evaluator's.

The two concretes here are :class:`NoOpExporter` (default safe sink for
tests and unconfigured environments) and :class:`MultiExporter` (fans
out to multiple child exporters with per-exporter failure isolation).
"""

from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from precept.types import ViolationEvent

__all__ = [
    "Exporter",
    "MultiExporter",
    "NoOpExporter",
]


logger = logging.getLogger(__name__)


class Exporter(ABC):
    """Abstract base class for handoff-violation event exporters.

    Concrete subclasses ship a single :meth:`export` method that
    delivers a :class:`ViolationEvent` to a transport (OTel collector,
    JSON file, HTTP webhook). The evaluator (PRC-013) holds exactly one
    :class:`Exporter`; deployments needing more than one (typical:
    OTel + local JSON audit log) wrap them in :class:`MultiExporter`.

    Subclasses must declare a class-level ``name: str`` attribute --
    a stable identifier surfaced in logs and dedup state. The
    requirement is enforced via :meth:`__init_subclass__` at class
    definition time; intermediate abstract subclasses (still carrying
    unimplemented abstract methods) are exempt via
    :func:`inspect.isabstract`, mirroring the
    :class:`precept.scoring.base.Scorer` pattern.

    See module docstring for the full implementation contract
    (no-raise on transport failure, no event mutation, thread-safety,
    best-effort idempotency on ``event_id``).
    """

    name: ClassVar[str]
    """Stable identifier for this exporter (e.g. ``"noop"``, ``"otel"``)."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return
        value = getattr(cls, "name", None)
        if not isinstance(value, str) or not value:
            raise TypeError(
                f"Exporter subclass {cls.__name__!r} must define a "
                f"non-empty class-level 'name' attribute (str); "
                f"got {value!r}"
            )

    @abstractmethod
    def export(self, event: ViolationEvent) -> None:
        """Deliver ``event`` to the underlying transport.

        Per the class contract: this method must not raise on transport
        failure (log and continue), must not mutate ``event``, must be
        safe to call from multiple threads, and should be idempotent
        on repeated ``event.event_id``.
        """
        ...


class NoOpExporter(Exporter):
    """Discard-everything exporter.

    Default safe sink for the evaluator when no exporter is configured,
    and for unit tests that need a real :class:`Exporter` instance
    without any side effects. ``export()`` is a no-op.
    """

    name: ClassVar[str] = "noop"

    def export(self, event: ViolationEvent) -> None:
        return None


class MultiExporter(Exporter):
    """Fan-out exporter with per-exporter failure isolation.

    Holds an ordered list of child :class:`Exporter` instances and
    forwards each :meth:`export` call to all of them. A failure in one
    child is logged and swallowed; subsequent children still receive
    the event. An empty child list is allowed (silent success) so
    deployments can compose conditionally without special-casing.
    """

    name: ClassVar[str] = "multi"

    def __init__(self, exporters: list[Exporter]) -> None:
        # Defensive copy so the caller can mutate their own list later
        # without affecting our iteration. ``self._exporters`` is set
        # exactly here and never mutated, which is why ``export`` can
        # iterate it lock-free under the class-level thread-safety
        # contract. Any future ``add_exporter`` / ``remove_exporter``
        # API on this class would need to revisit that guarantee.
        self._exporters: list[Exporter] = list(exporters)

    def export(self, event: ViolationEvent) -> None:
        for exporter in self._exporters:
            try:
                exporter.export(event)
            # Defensive boundary: the Exporter contract requires
            # implementations not to raise, but MultiExporter is the
            # last line before the evaluator catches its own exporter
            # failures. Catching Exception here means a misbehaving
            # third-party exporter never starves its siblings of the
            # event. Documented intent of the AC.
            except Exception as exc:
                logger.warning(
                    "exporter %r raised during export: %s; continuing",
                    exporter.name,
                    exc,
                )

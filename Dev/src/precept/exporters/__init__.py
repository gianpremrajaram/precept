# SPDX-License-Identifier: MIT
"""Exporter abstractions and built-in concrete sinks.

Houses the :class:`Exporter` ABC plus the two ship-with-PRC-013
concretes :class:`NoOpExporter` and :class:`MultiExporter`. The OTel
(PRC-020) and JSON-file (PRC-021) exporters land as separate concrete
modules later.

``__all__`` is intentionally empty at this stage. The public surface of
the exporters subsystem is defined by PRC-026; until then, callers
import concrete names directly from
``precept.exporters.base`` (and, in due course, from the per-transport
modules ``precept.exporters.otel`` and ``precept.exporters.jsonfile``).
"""

from __future__ import annotations

__all__: list[str] = []

# SPDX-License-Identifier: Apache-2.0
"""Exporter abstractions and built-in concrete sinks.

Houses the :class:`Exporter` ABC plus the four ship-with-MVP
concretes:

* :class:`precept.exporters.base.NoOpExporter` and
  :class:`precept.exporters.base.MultiExporter` (PRC-013)
* :class:`precept.exporters.json_exporter.JSONFileExporter` and
  :class:`precept.exporters.json_exporter.JSONStreamExporter` (PRC-021)
* :class:`precept.exporters.otel.OTelExporter` (PRC-020, opt-in via
  the ``[otel]`` extra)

``__all__`` is intentionally empty at this stage. The public surface of
the exporters subsystem is defined by PRC-026; until then, callers
import concrete names directly from the per-transport modules. This
package's ``__init__`` deliberately does NOT re-export from ``.otel``
so that ``from precept.exporters import *`` (or any wildcard pattern
reaching this module) on a base install without the ``[otel]`` extra
does not need to touch the OTel surface (DEPENDENCIES.md §4.5).
"""

from __future__ import annotations

__all__: list[str] = []

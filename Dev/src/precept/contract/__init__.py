# SPDX-License-Identifier: Apache-2.0
"""Contract declaration surface.

This package hosts the canonical IR (``schema``) and the parser modules
that produce IR instances (``yaml_loader``, ``decorator`` in PRC-008).
The top-level ``precept`` public API (PRC-026) re-exports the pieces
users should import directly; this package is not a public namespace.
"""

from __future__ import annotations

__all__: list[str] = []

# SPDX-License-Identifier: Apache-2.0
"""Scoring engine surface.

This package hosts the abstract ``Scorer`` interface and its result types
(PRC-010), plus the v0 concrete ``EmbeddingProxy`` (PRC-011). The top-
level ``precept`` public API (PRC-026) re-exports the pieces users should
import directly; this package is not a public namespace.
"""

from __future__ import annotations

__all__: list[str] = []

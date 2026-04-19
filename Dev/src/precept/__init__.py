# SPDX-License-Identifier: MIT
"""Precept: handoff integrity contracts for multi-agent pipelines."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("precept")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

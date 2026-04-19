# SPDX-License-Identifier: MIT
"""Smoke test: the `precept` package imports and exposes `__version__`."""

from __future__ import annotations

import precept


def test_version_is_non_empty_string() -> None:
    assert isinstance(precept.__version__, str)
    assert precept.__version__

# SPDX-License-Identifier: MIT
"""YAML frontend: parses a YAML source into a ``HandoffContract`` IR.

One of two v0 frontends declared in ADR 0001. The other is the decorator
frontend (PRC-008). Both produce the same ``HandoffContract`` type and
surface errors through ``precept.errors.ContractValidationError``.

YAML is loaded via ``yaml.safe_load`` exclusively; ``yaml.load`` is a
remote-code-execution surface and is never used anywhere in the codebase
(CLAUDE.md -> "Things to never do").

Error enrichment at v0: syntax errors carry ``(line, column)`` via
``yaml_mark``; schema errors carry Pydantic field paths but no YAML
position. Propagating YAML positions to Pydantic errors requires a
position-tracking loader and is deferred to PRC-007a.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from precept.contract.schema import HandoffContract
from precept.errors import ContractValidationError, ContractValidationIssue

__all__ = ["load_contract", "load_contract_from_string"]


def load_contract(path: str | Path) -> HandoffContract:
    """Load a ``HandoffContract`` from a YAML file.

    Raises ``ContractValidationError`` if the file cannot be read, the
    YAML is malformed, the top-level structure is not a mapping, the
    file is empty, or the resulting data does not satisfy the
    ``HandoffContract`` schema.
    """

    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractValidationError(
            f"unable to read contract file {p}: {exc}",
        ) from exc
    return _parse(text, source=str(p))


def load_contract_from_string(yaml_str: str) -> HandoffContract:
    """Parse a ``HandoffContract`` from a YAML string."""

    return _parse(yaml_str, source=None)


def _parse(text: str, *, source: str | None) -> HandoffContract:
    src_suffix = f" ({source})" if source else ""

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = ""
        yaml_mark: tuple[int, int] | None = None
        if mark is not None:
            line = mark.line + 1
            column = mark.column + 1
            location = f" (line {line}, column {column})"
            yaml_mark = (line, column)
        raise ContractValidationError(
            f"malformed YAML{src_suffix}{location}: {exc}",
            details=[
                ContractValidationIssue(
                    field_path="<yaml>",
                    message=str(exc),
                    yaml_mark=yaml_mark,
                )
            ],
        ) from exc

    if data is None:
        raise ContractValidationError(f"contract file is empty{src_suffix}")

    if not isinstance(data, dict):
        raise ContractValidationError(
            f"top-level YAML structure must be a mapping{src_suffix}, got {type(data).__name__}"
        )

    return HandoffContract(**data)

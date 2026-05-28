# SPDX-License-Identifier: Apache-2.0
"""In-process contract registry and lookup (PRC-009).

Intended usage pattern: load contracts once at application startup
(``register`` per contract, or ``load_directory`` for a folder of YAML
files), then reference them by name at handoff-evaluation time. This keeps
contract objects off the call path - the LangGraph integration (PRC-014)
looks a contract up by name rather than threading it through every node.

A module-level ``default_registry`` instance is provided for the simple
single-registry case. It is a plain module attribute, **not** a Singleton:
tests (and embedders that want isolation) construct their own
``ContractRegistry()`` and pass it explicitly. Singletons are hostile to
unit testing; a replaceable default is not.

Thread-safety: ``register`` (and the registration ``load_directory``
performs) is guarded by a ``threading.Lock``. This is deliberately
cheap insurance for the realistic case of a Gunicorn/Uvicorn worker pool
registering contracts at request-handling time rather than at startup. It
is documented but not stress-tested at v0; concurrency stress tests are a
Phase 2 item if a real-world report surfaces (DEPENDENCIES.md
technical-debt ledger).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from precept.contract.schema import HandoffContract
from precept.contract.yaml_loader import load_contract
from precept.errors import ContractValidationError

__all__ = ["ContractRegistry", "default_registry"]

logger = logging.getLogger(__name__)


class ContractRegistry:
    """A name-keyed collection of ``HandoffContract`` instances."""

    def __init__(self) -> None:
        self._contracts: dict[str, HandoffContract] = {}
        self._lock: threading.Lock = threading.Lock()

    def register(self, contract: HandoffContract, *, overwrite: bool = False) -> None:
        """Register ``contract`` under ``contract.name``.

        Raises ``KeyError`` if a contract with the same name is already
        registered and ``overwrite`` is ``False``.
        """

        with self._lock:
            if contract.name in self._contracts and not overwrite:
                raise KeyError(
                    f"Contract {contract.name!r} already registered; "
                    f"pass overwrite=True to replace it"
                )
            self._contracts[contract.name] = contract

    def get(self, name: str) -> HandoffContract:
        """Return the contract registered under ``name``.

        Raises ``KeyError`` with the list of available contract names if
        ``name`` is not registered.
        """

        try:
            return self._contracts[name]
        except KeyError:
            available = ", ".join(sorted(self._contracts)) or "(none)"
            raise KeyError(f"Contract {name!r} not found. Available: {available}") from None

    def list_contracts(self) -> list[str]:
        """Return the registered contract names, sorted."""

        return sorted(self._contracts)

    def load_directory(self, path: str | Path, *, recursive: bool = False) -> int:
        """Load every ``*.yaml`` file in ``path`` and register the contracts.

        Returns the number of contracts successfully registered. Files that
        fail to load or validate are skipped with a ``WARNING`` log entry,
        not raised - a single malformed file must not abort a startup-time
        directory load. Non-``.yaml`` files are not matched and so are
        ignored. ``recursive=True`` descends into subdirectories.

        A directory load is treated as a declarative set: contracts are
        registered with ``overwrite=True``, so re-loading the same (or an
        overlapping) directory is idempotent rather than raising on names
        already present. Use the explicit ``register`` for duplicate-name
        protection on the deliberate single-contract path.
        """

        directory = Path(path)
        matches = directory.rglob("*.yaml") if recursive else directory.glob("*.yaml")

        count = 0
        for yaml_path in sorted(matches):
            try:
                contract = load_contract(yaml_path)
            except ContractValidationError as exc:
                logger.warning("Skipping contract file %s: %s", yaml_path, exc)
                continue
            self.register(contract, overwrite=True)
            count += 1
        return count


default_registry = ContractRegistry()
"""Module-level convenience registry for the simple single-registry case.

Replaceable per the module docstring; not a Singleton.
"""

# SPDX-License-Identifier: MIT
"""Scoring abstractions: scorer interface and result types.

This module defines the four types that anchor the scoring layer:
``HandoffPayload`` (the boundary type a ``Scorer`` reads), ``FieldScore``
(per-field result), ``ScoreResult`` (aggregate scorer output), and
``Scorer`` (abstract base class). The v0 concrete is
``precept.scoring.embedding_proxy.EmbeddingProxy`` (PRC-011); a
research-validated ``CalibratedScorer`` lands as the post-dissertation
Phase 2 deliverable (PRC-035).

The ``Scorer`` interface is deliberately method-agnostic: it does not
commit to mutual-information terminology. MI is one possible internal
method among several (KSG, Gaussian closed-form, InfoNCE, MINE) the
dissertation will evaluate. Keeping the interface generic ensures the
Phase 2 concrete drops in cleanly without an interface break.

Per ``CLAUDE.md`` -> "Scorer stays generic" and "Constructor-time model
load": concrete implementations holding model state must load that state
in ``__init__``, not lazily on first ``score()`` call.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from precept.contract.schema import HandoffContract

__all__ = [
    "FieldScore",
    "HandoffPayload",
    "ScoreResult",
    "Scorer",
]


class HandoffPayload(BaseModel):
    """Structured boundary payload a ``Scorer`` reads.

    Instances are produced by the contracted-field extractor (PRC-016)
    from arbitrary upstream state (a LangGraph dict, a ``BaseModel``
    instance, an arbitrary object). The extractor reads ONLY contracted
    fields; this type intentionally has no recursive raw-state surface,
    so secrets in uncontracted state cannot reach exporters or violation
    events.

    See ``CLAUDE.md`` -> "Contracted-fields-only extraction" for the
    secret-leakage rationale.
    """

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, Any]
    """Contracted field values, keyed by field name. Values are ``Any``
    because contract-declared fields may be strings, numbers, lists, or
    nested structures; the scorer converts these to its own internal
    representation (e.g. ``str()`` for embedding-based scorers, see
    ``EmbeddingProxy`` in PRC-011)."""

    raw: str | None = None
    """Optional pre-stringified concatenation for embedding-style scorers
    that prefer working on a single textual surface. Calibrated scorers
    (Phase 2) typically ignore this and operate on ``fields`` directly."""

    metadata: dict[str, str] = Field(default_factory=dict)
    """Free-form string-keyed annotations (agent name, trace id, etc.).
    Strict ``str``/``str`` typing matches OTel attribute conventions."""


class FieldScore(BaseModel):
    """Per-field scoring result, embedded inside a ``ScoreResult``."""

    model_config = ConfigDict(extra="forbid")

    field_name: str
    """Name of the contracted field this score corresponds to."""

    score: float = Field(ge=0.0, le=1.0)
    """Field-level fidelity in ``[0.0, 1.0]``. Interpretation depends on
    ``method``: an embedding scorer reports cosine similarity, a
    calibrated scorer reports a calibrated probability."""

    method: str
    """Identifier for the scoring method used (e.g.
    ``"embedding_cosine"``, ``"calibrated_proxy_v1"``). Surfaces in
    ``ViolationEvent`` for post-hoc analysis."""

    passed: bool
    """Whether this field cleared the contract's threshold. Scorers set
    this in alignment with their own threshold logic; the ``Evaluator``
    (PRC-013) does not re-derive it."""


class ScoreResult(BaseModel):
    """Aggregate output of ``Scorer.score()`` for one source/target pair."""

    model_config = ConfigDict(extra="forbid")

    overall_score: float = Field(ge=0.0, le=1.0)
    """Aggregate fidelity in ``[0.0, 1.0]``. Aggregation method is a
    scorer-implementation detail (unweighted mean for ``EmbeddingProxy``;
    documented per concrete class)."""

    field_scores: list[FieldScore] = Field(default_factory=list)
    """One entry per contracted field. Empty list is valid for empty
    contracts (ADR 0001 scaffold mode)."""

    scorer_name: str
    """Class-level ``Scorer.name`` of the producing scorer."""

    scorer_version: str
    """Class-level ``Scorer.version`` of the producing scorer."""

    timestamp_iso: str
    """ISO 8601 UTC timestamp when ``score()`` produced this result.
    Producers should use ``datetime.now(timezone.utc).isoformat()``.
    Must encode a UTC offset; naive datetimes and non-UTC offsets are
    rejected by ``_validate_timestamp_iso_utc``."""

    @field_validator("timestamp_iso")
    @classmethod
    def _validate_timestamp_iso_utc(cls, v: str) -> str:
        # Normalise "Z" -> "+00:00" for Python 3.10 fromisoformat compat (3.11+ accepts Z).
        err = (
            "timestamp_iso must be a UTC-offset ISO 8601 string "
            "(e.g. 2026-05-02T21:00:00+00:00); naive datetimes and "
            "non-UTC offsets are not accepted"
        )
        candidate = v[:-1] + "+00:00" if v.endswith("Z") else v
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError(err) from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ValueError(err)
        return v


class Scorer(ABC):
    """Abstract base class for handoff-fidelity scorers.

    Implementations are configuration-swappable by design: a future
    ``CalibratedScorer`` (Phase 2, PRC-035) implements the same interface
    as the v0 ``EmbeddingProxy`` (PRC-011), so users upgrade by changing
    their evaluator wiring, not their integration code.

    Implementation contract for ``score()``:

    * **Deterministic.** Same ``(source, target, contract)`` input must
      produce the same ``ScoreResult`` across runs. Implementations using
      stochastic models must seed all RNGs at construction time.
    * **Non-mutating.** ``score()`` must not modify ``source``,
      ``target``, or ``contract``; treat them as immutable.
    * **Tolerant of missing optional fields.** A field listed in
      ``contract.fields.required_fields`` that is absent from
      ``target.fields`` should produce a ``FieldScore`` with
      ``score=0.0`` and ``passed=False``, not raise.
    * **Thread-safe.** ``score()`` is callable from multiple threads on
      a single instance. Heavy resources (model weights, tokenisers)
      must be loaded at construction time, not inside ``score()`` (see
      ``CLAUDE.md`` -> "Constructor-time model load").

    Subclasses must declare two class-level attributes:

    * ``name: str`` - stable identifier (e.g. ``"embedding_proxy"``);
      surfaces in ``ScoreResult.scorer_name`` and ``ViolationEvent``.
    * ``version: str`` - implementation version (e.g. ``"0.1.0"``);
      surfaces in ``ScoreResult.scorer_version`` and ``ViolationEvent``.

    Both are enforced via ``__init_subclass__``: a concrete subclass
    that omits either attribute fails at class-definition time.
    Intermediate abstract subclasses (those still carrying unimplemented
    abstract methods) skip the check, so layered hierarchies remain
    possible if needed.
    """

    name: ClassVar[str]
    """Stable identifier for the scoring strategy."""

    version: ClassVar[str]
    """Version string for this scorer implementation."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return
        for attr in ("name", "version"):
            value = getattr(cls, attr, None)
            if not isinstance(value, str) or not value:
                raise TypeError(
                    f"Scorer subclass {cls.__name__!r} must define a "
                    f"non-empty class-level {attr!r} attribute (str); "
                    f"got {value!r}"
                )

    @abstractmethod
    def score(
        self,
        source: HandoffPayload,
        target: HandoffPayload,
        contract: HandoffContract,
    ) -> ScoreResult:
        """Score the fidelity of ``target`` given ``source`` under ``contract``.

        See class docstring for the full implementation contract
        (determinism, non-mutation, missing-field tolerance,
        thread-safety, no-lazy-load discipline).
        """
        ...

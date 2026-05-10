# SPDX-License-Identifier: MIT
"""Embedding-based proxy scorer (PRC-011).

``EmbeddingProxy`` is the v0 concrete ``Scorer``: a sentence-transformers
cosine-similarity proxy. It is deliberately a proxy. Cosine in embedding
space correlates with but does not equal mutual information; a research-
validated calibrated scorer is the post-dissertation Phase 2 deliverable
(``CalibratedScorer``, PRC-035).

Per ``CLAUDE.md`` -> "Constructor-time model load": the sentence-
transformer is loaded in ``__init__``, not lazily on first ``score()``
call. This moves the multi-second first-run cost to application startup
and prevents a hidden event-loop block on the first handoff.

Per ``CLAUDE.md`` -> "Scorer stays generic": this module owns its own
calibration constants. When a contract has ``required_fields`` set but
``min_fidelity`` is ``None``, ``EmbeddingProxy`` applies a scorer-level
fallback of ``0.5`` cosine similarity and logs a ``WARNING``. The IR
keeps ``min_fidelity`` as ``Optional[float]`` so future scorers (PRC-035
calibrated MI scorer) can pick their own thresholds without inheriting a
number that only makes sense in cosine space.

Empty contracts (``required_fields == []``) return
``overall_score=1.0``, ``field_scores=[]``. This aligns with ADR 0001's
scaffold/observe-only contract semantics: a contract with no required
fields cannot fail field-presence checks.

Memory footprint (informational; users provisioning many parallel
processes need to plan accordingly):

* ``all-MiniLM-L6-v2``: ~80 MB on disk, ~150-200 MB resident.
* ``paraphrase-MiniLM-L3-v2``: ~60 MB on disk, ~120 MB resident.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from precept.scoring.base import (
    FieldScore,
    HandoffPayload,
    Scorer,
    ScoreResult,
)

if TYPE_CHECKING:
    from precept.contract.schema import HandoffContract

__all__ = ["EmbeddingProxy"]

logger = logging.getLogger(__name__)

_DEFAULT_MIN_FIDELITY = 0.5
"""Cosine-similarity threshold applied when ``contract.fields.min_fidelity`` is ``None``.

This default lives at the scorer level, not in the IR. A future
``CalibratedScorer`` (PRC-035) will choose its own threshold from a
calibrated probability distribution; baking ``0.5`` into ``ContractFields``
would couple the IR to embedding-cosine semantics that don't generalise.
See module docstring for the full rationale.
"""

_KNOWN_MODEL_FOOTPRINT: dict[str, str] = {
    "all-MiniLM-L6-v2": "~80MB on disk, ~150-200MB resident",
    "paraphrase-MiniLM-L3-v2": "~60MB on disk, ~120MB resident",
}


class EmbeddingProxy(Scorer):
    """Embedding-based cosine-similarity proxy scorer (v0).

    Loads a sentence-transformer model at construction time and computes
    per-field cosine similarity between ``source`` and ``target`` field
    values. Per-field scores are aggregated as an unweighted mean.

    This is a PROXY, not a mutual-information measurement. Cosine in
    embedding space correlates with but does not equal MI. A research-
    validated calibrated scorer is the post-dissertation Phase 2
    deliverable (``CalibratedScorer``, PRC-035).

    ``score()`` is synchronous and CPU-bound (~100-500 ms per call on a
    typical laptop). When called from inside an asyncio coroutine, wrap
    with ``asyncio.to_thread(scorer.score, ...)`` to avoid blocking the
    event loop. The PRC-014 LangGraph integration handles this
    automatically when an async context is detected.

    Threshold semantics: ``FieldScore.passed = (score >= threshold)``,
    where ``threshold`` is ``contract.fields.min_fidelity`` if set,
    otherwise ``_DEFAULT_MIN_FIDELITY`` (``0.5``) with a single
    ``WARNING`` logged per ``score()`` call.

    Empty contracts (``required_fields == []``) return
    ``overall_score=1.0`` with an empty ``field_scores`` list, per
    ADR 0001's scaffold semantics.

    :param model_name: sentence-transformers model identifier.
    :param _skip_model_load: TEST-ONLY escape hatch. When ``True``, the
        model is not loaded; subsequent ``score()`` calls raise
        ``RuntimeError``. Used by unit tests that exercise scorer
        wiring without paying the model-load cost. Not part of public
        API; the leading underscore is the only marker.
    """

    name: ClassVar[str] = "embedding_proxy"
    version: ClassVar[str] = "0.1.0"

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        *,
        _skip_model_load: bool = False,
    ) -> None:
        self._model_name = model_name
        self._model: SentenceTransformer | None = None

        if _skip_model_load:
            logger.debug("EmbeddingProxy: _skip_model_load=True; model not loaded (test-only path)")
            return

        torch.set_grad_enabled(False)
        self._model = SentenceTransformer(model_name)
        footprint = _KNOWN_MODEL_FOOTPRINT.get(
            model_name, f"resident memory size unknown for model={model_name!r}"
        )
        logger.info(
            "EmbeddingProxy initialised: model=%s, %s",
            model_name,
            footprint,
        )

    def score(
        self,
        source: HandoffPayload,
        target: HandoffPayload,
        contract: HandoffContract,
    ) -> ScoreResult:
        if self._model is None:
            raise RuntimeError(
                "EmbeddingProxy was constructed with _skip_model_load=True; "
                "score() requires a loaded model. Construct without "
                "_skip_model_load to use scoring."
            )

        threshold = self._resolve_threshold(contract)

        field_scores: list[FieldScore] = []
        for field_name in contract.fields.required_fields:
            field_scores.append(self._score_field(field_name, source, target, threshold))

        overall = sum(fs.score for fs in field_scores) / len(field_scores) if field_scores else 1.0

        return ScoreResult(
            overall_score=overall,
            field_scores=field_scores,
            scorer_name=self.name,
            scorer_version=self.version,
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
        )

    def _resolve_threshold(self, contract: HandoffContract) -> float:
        threshold = contract.fields.min_fidelity
        if threshold is None and contract.fields.required_fields:
            logger.warning(
                "contract %r has required_fields but min_fidelity is None; "
                "EmbeddingProxy defaulting to %.2f cosine threshold "
                "(scorer-level fallback; see embedding_proxy module docstring)",
                contract.name,
                _DEFAULT_MIN_FIDELITY,
            )
            return _DEFAULT_MIN_FIDELITY
        # Either an explicit threshold is set, or required_fields is empty
        # (in which case the threshold is unused and the actual value
        # doesn't matter; pick the default for type-narrowing).
        return _DEFAULT_MIN_FIDELITY if threshold is None else threshold

    def _score_field(
        self,
        field_name: str,
        source: HandoffPayload,
        target: HandoffPayload,
        threshold: float,
    ) -> FieldScore:
        target_value = target.fields.get(field_name)
        if target_value is None:
            return FieldScore(
                field_name=field_name,
                score=0.0,
                method="embedding_cosine",
                passed=False,
            )

        source_value = source.fields.get(field_name)
        # str(None) -> "None"; use empty string for genuinely-absent source
        # so cosine reflects "target text vs nothing" rather than "target
        # text vs the literal string 'None'".
        source_str = "" if source_value is None else str(source_value)
        target_str = str(target_value)

        cosine = self._cosine(source_str, target_str)
        return FieldScore(
            field_name=field_name,
            score=cosine,
            method="embedding_cosine",
            passed=cosine >= threshold,
        )

    def _cosine(self, a: str, b: str) -> float:
        assert self._model is not None  # guarded in score()
        embeddings: np.ndarray = self._model.encode(
            [a, b],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        # Normalised vectors -> dot product is cosine similarity.
        cos = float(np.dot(embeddings[0], embeddings[1]))
        # Clamp to FieldScore's [0,1] domain. Sentence-transformer cosines
        # can drift slightly negative on adversarial pairs and slightly
        # above 1.0 on identical inputs due to floating-point error.
        return max(0.0, min(1.0, cos))

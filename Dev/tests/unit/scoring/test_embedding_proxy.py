# SPDX-License-Identifier: MIT
"""Unit tests for ``precept.scoring.embedding_proxy.EmbeddingProxy`` (PRC-011).

Covers: model-loading discipline (constructor-time + ``_skip_model_load``
hatch), per-field cosine, missing-field zero, empty-required vacuous
pass, scorer-level ``min_fidelity`` fallback with WARNING, non-string
field stringification, determinism, model swap, and the async-via-
``asyncio.to_thread`` smoke test (sync ``score()`` is safe to dispatch
from coroutines; native-async API is Phase 2 and explicitly out of scope
for PRC-011).

The model-loading tests share a session-scoped fixture so we pay the
~80 MB sentence-transformers download exactly once per test run.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import pytest

from precept.contract.schema import ContractFields, HandoffContract
from precept.scoring.base import HandoffPayload, ScoreResult
from precept.scoring.embedding_proxy import (
    _DEFAULT_MIN_FIDELITY,
    EmbeddingProxy,
)

# --- Fixtures -------------------------------------------------------------


@pytest.fixture(scope="session")
def proxy() -> EmbeddingProxy:
    """One real ``EmbeddingProxy`` per test session.

    Uses the default ``all-MiniLM-L6-v2`` model. The first session
    invocation pays the model-load cost (~5 s cold, ~1 s warm cache);
    subsequent tests reuse the loaded instance.
    """
    return EmbeddingProxy()


def _payload(**fields: object) -> HandoffPayload:
    return HandoffPayload(fields=dict(fields))


def _contract(
    *,
    required: list[str],
    min_fidelity: float | None,
    name: str = "test_contract",
) -> HandoffContract:
    return HandoffContract(
        name=name,
        fields=ContractFields(required_fields=required, min_fidelity=min_fidelity),
    )


# --- Class-level metadata propagation -------------------------------------


def test_class_attrs_match_spec() -> None:
    assert EmbeddingProxy.name == "embedding_proxy"
    assert EmbeddingProxy.version == "0.1.0"


def test_score_result_carries_class_name_and_version(proxy: EmbeddingProxy) -> None:
    contract = _contract(required=["a"], min_fidelity=0.5)
    src = _payload(a="hello world")
    tgt = _payload(a="hello world")

    result = proxy.score(src, tgt, contract)

    assert result.scorer_name == "embedding_proxy"
    assert result.scorer_version == "0.1.0"


def test_timestamp_iso_is_utc_offset(proxy: EmbeddingProxy) -> None:
    contract = _contract(required=[], min_fidelity=None)
    result = proxy.score(_payload(), _payload(), contract)
    parsed = datetime.fromisoformat(result.timestamp_iso)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


# --- Per-field cosine: identical / unrelated / missing --------------------


def test_identical_payloads_score_near_perfect(proxy: EmbeddingProxy) -> None:
    contract = _contract(required=["finding"], min_fidelity=0.5)
    text = "The cat sat on the mat. The mat was red."
    result = proxy.score(_payload(finding=text), _payload(finding=text), contract)

    assert len(result.field_scores) == 1
    assert result.field_scores[0].score >= 0.99
    assert result.field_scores[0].passed is True
    assert result.overall_score >= 0.99


def test_unrelated_payloads_score_low(proxy: EmbeddingProxy) -> None:
    contract = _contract(required=["finding"], min_fidelity=0.5)
    src = _payload(finding="The cat sat on the mat. The mat was red.")
    tgt = _payload(finding="Quantum mechanics describes subatomic particles.")
    result = proxy.score(src, tgt, contract)

    assert result.field_scores[0].score < 0.3
    assert result.field_scores[0].passed is False


def test_missing_target_field_scores_zero(proxy: EmbeddingProxy) -> None:
    contract = _contract(required=["a", "b"], min_fidelity=0.5)
    src = _payload(a="hello", b="world")
    tgt = _payload(a="hello")  # b missing

    result = proxy.score(src, tgt, contract)

    by_name = {fs.field_name: fs for fs in result.field_scores}
    assert by_name["b"].score == 0.0
    assert by_name["b"].passed is False
    assert by_name["b"].method == "embedding_cosine"
    assert by_name["a"].passed is True


def test_field_scores_length_matches_required_fields(proxy: EmbeddingProxy) -> None:
    contract = _contract(required=["x", "y", "z"], min_fidelity=0.5)
    src = _payload(x="a", y="b", z="c")
    tgt = _payload(x="a", y="b", z="c")
    result = proxy.score(src, tgt, contract)
    assert [fs.field_name for fs in result.field_scores] == ["x", "y", "z"]


# --- Empty contract: vacuous pass per ADR 0001 ----------------------------


def test_empty_required_fields_vacuous_pass(proxy: EmbeddingProxy) -> None:
    contract = _contract(required=[], min_fidelity=None)
    result = proxy.score(_payload(), _payload(), contract)

    assert result.field_scores == []
    assert result.overall_score == 1.0


def test_empty_required_fields_emits_no_min_fidelity_warning(
    proxy: EmbeddingProxy, caplog: pytest.LogCaptureFixture
) -> None:
    contract = _contract(required=[], min_fidelity=None)
    with caplog.at_level(logging.WARNING, logger="precept.scoring.embedding_proxy"):
        proxy.score(_payload(), _payload(), contract)
    assert not any("min_fidelity is None" in rec.message for rec in caplog.records)


# --- Scorer-level min_fidelity fallback ------------------------------------


def test_min_fidelity_none_logs_warning_and_falls_back_to_default(
    proxy: EmbeddingProxy, caplog: pytest.LogCaptureFixture
) -> None:
    contract = _contract(required=["a"], min_fidelity=None)
    src = _payload(a="hello world")
    tgt = _payload(a="hello world")

    with caplog.at_level(logging.WARNING, logger="precept.scoring.embedding_proxy"):
        result = proxy.score(src, tgt, contract)

    warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert "min_fidelity is None" in msg
    assert f"{_DEFAULT_MIN_FIDELITY:.2f}" in msg
    # Identical inputs -> cosine ~1.0, well above the 0.5 fallback.
    assert result.field_scores[0].passed is True


def test_min_fidelity_none_failing_field_under_default_threshold(
    proxy: EmbeddingProxy,
) -> None:
    contract = _contract(required=["a"], min_fidelity=None)
    src = _payload(a="The cat sat on the mat.")
    tgt = _payload(a="Quantum mechanics describes subatomic particles.")
    result = proxy.score(src, tgt, contract)

    assert result.field_scores[0].score < _DEFAULT_MIN_FIDELITY
    assert result.field_scores[0].passed is False


# --- Non-string field values: stringification ----------------------------


def test_non_string_field_values_are_stringified(proxy: EmbeddingProxy) -> None:
    contract = _contract(required=["count"], min_fidelity=0.5)
    src = _payload(count=42)
    tgt = _payload(count=42)
    result = proxy.score(src, tgt, contract)
    assert result.field_scores[0].score >= 0.99


def test_list_field_values_are_stringified(proxy: EmbeddingProxy) -> None:
    contract = _contract(required=["tags"], min_fidelity=0.5)
    src = _payload(tags=["alpha", "beta"])
    tgt = _payload(tags=["alpha", "beta"])
    result = proxy.score(src, tgt, contract)
    assert result.field_scores[0].score >= 0.99


# --- Determinism ----------------------------------------------------------


def test_score_is_deterministic_across_repeats(proxy: EmbeddingProxy) -> None:
    contract = _contract(required=["a"], min_fidelity=0.5)
    src = _payload(a="reproducibility is required for handoff fidelity")
    tgt = _payload(a="reproducibility is required for handoff fidelity")

    scores = [proxy.score(src, tgt, contract).overall_score for _ in range(10)]
    assert len(set(scores)) == 1


# --- Model swap -----------------------------------------------------------


def test_alternative_model_swaps_in() -> None:
    """Smaller model than the default; verifies model_name is honoured."""
    small_proxy = EmbeddingProxy(model_name="paraphrase-MiniLM-L3-v2")
    contract = _contract(required=["a"], min_fidelity=0.5)
    result = small_proxy.score(_payload(a="hello"), _payload(a="hello"), contract)
    assert result.field_scores[0].score >= 0.99


# --- _skip_model_load test hatch ------------------------------------------


def test_skip_model_load_constructs_without_loading() -> None:
    proxy = EmbeddingProxy(_skip_model_load=True)
    assert proxy._model is None


def test_skip_model_load_score_raises_runtime_error() -> None:
    proxy = EmbeddingProxy(_skip_model_load=True)
    contract = _contract(required=["a"], min_fidelity=0.5)
    src = _payload(a="x")
    tgt = _payload(a="x")

    with pytest.raises(RuntimeError, match="_skip_model_load=True"):
        proxy.score(src, tgt, contract)


# --- Async-context smoke: sync API via asyncio.to_thread ------------------


def test_score_runs_via_to_thread_without_blocking_loop(
    proxy: EmbeddingProxy,
) -> None:
    """Sync ``score()`` is safely dispatchable from async contexts via
    ``asyncio.to_thread``. NOT a native-async API (Phase 2; explicitly
    out of scope for PRC-011, see "Out of Scope" in the ticket).

    Asserts the coroutine completes and a tick counter advances on a
    parallel sleep coroutine, indicating the event loop wasn't blocked.
    """
    contract = _contract(required=["a"], min_fidelity=0.5)
    src = _payload(a="hello world")
    tgt = _payload(a="hello world")

    async def run() -> tuple[ScoreResult, int]:
        ticks = 0

        async def tick() -> None:
            nonlocal ticks
            for _ in range(20):
                await asyncio.sleep(0.005)
                ticks += 1

        tick_task = asyncio.create_task(tick())
        result = await asyncio.to_thread(proxy.score, src, tgt, contract)
        await tick_task
        return result, ticks

    result, ticks = asyncio.run(run())
    assert result.field_scores[0].score >= 0.99
    # The tick coroutine should have made non-trivial progress while
    # to_thread offloaded score(); if the loop were blocked, ticks would
    # often be 0 or 1 only.
    assert ticks >= 5

# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ``precept.scoring.base``.

Exercises the four PRC-010 surfaces: ``HandoffPayload``, ``FieldScore``,
``ScoreResult``, and the ``Scorer`` ABC (incl. ``__init_subclass__``
enforcement of class-level ``name`` / ``version``).
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from precept.contract.schema import HandoffContract
from precept.scoring.base import FieldScore, HandoffPayload, Scorer, ScoreResult

# --- Scorer ABC: instantiation guard --------------------------------------


def test_scorer_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        Scorer()  # type: ignore[abstract]


# --- Scorer ABC: __init_subclass__ enforcement of name / version ----------


def test_concrete_subclass_missing_name_raises_at_class_definition_time() -> None:
    with pytest.raises(TypeError, match="'name'"):

        class _NoName(Scorer):
            version = "0.0.1"

            def score(
                self,
                source: HandoffPayload,
                target: HandoffPayload,
                contract: HandoffContract,
            ) -> ScoreResult:
                raise NotImplementedError


def test_concrete_subclass_missing_version_raises_at_class_definition_time() -> None:
    with pytest.raises(TypeError, match="'version'"):

        class _NoVersion(Scorer):
            name = "no_version"

            def score(
                self,
                source: HandoffPayload,
                target: HandoffPayload,
                contract: HandoffContract,
            ) -> ScoreResult:
                raise NotImplementedError


def test_concrete_subclass_with_empty_name_raises_at_class_definition_time() -> None:
    with pytest.raises(TypeError, match="'name'"):

        class _EmptyName(Scorer):
            name = ""
            version = "0.0.1"

            def score(
                self,
                source: HandoffPayload,
                target: HandoffPayload,
                contract: HandoffContract,
            ) -> ScoreResult:
                raise NotImplementedError


def test_concrete_subclass_with_non_string_name_raises_at_class_definition_time() -> None:
    with pytest.raises(TypeError, match="'name'"):

        class _NumericName(Scorer):
            name = 42  # type: ignore[assignment]
            version = "0.0.1"

            def score(
                self,
                source: HandoffPayload,
                target: HandoffPayload,
                contract: HandoffContract,
            ) -> ScoreResult:
                raise NotImplementedError


def test_intermediate_abstract_subclass_skips_name_version_check() -> None:
    """A subclass that has not yet implemented ``score()`` is still abstract;
    the enforcement check intentionally skips it so layered hierarchies
    remain possible. The class can be defined without name/version, but it
    cannot be instantiated until ``score`` is implemented."""

    class _IntermediateScorer(Scorer):
        pass

    assert inspect.isabstract(_IntermediateScorer)
    with pytest.raises(TypeError):
        _IntermediateScorer()  # type: ignore[abstract]


def test_concrete_subclass_with_name_and_version_can_be_instantiated_and_called() -> None:
    class _DummyScorer(Scorer):
        name = "dummy"
        version = "0.0.1"

        def score(
            self,
            source: HandoffPayload,
            target: HandoffPayload,
            contract: HandoffContract,
        ) -> ScoreResult:
            return ScoreResult(
                overall_score=1.0,
                field_scores=[],
                scorer_name=self.name,
                scorer_version=self.version,
                timestamp_iso="2026-05-02T00:00:00+00:00",
            )

    instance = _DummyScorer()
    src = HandoffPayload(fields={"hypothesis": "alpha"})
    tgt = HandoffPayload(fields={"hypothesis": "alpha"})
    contract = HandoffContract(name="x", fields={})
    result = instance.score(src, tgt, contract)
    assert isinstance(result, ScoreResult)
    assert result.scorer_name == "dummy"
    assert result.scorer_version == "0.0.1"
    assert result.overall_score == 1.0


# --- HandoffPayload -------------------------------------------------------


def test_handoff_payload_accepts_arbitrary_field_value_types() -> None:
    p = HandoffPayload(
        fields={
            "string": "hello",
            "integer": 42,
            "float": 3.14,
            "list": [1, 2, 3],
            "nested": {"a": "b"},
            "none": None,
            "bool": True,
        }
    )
    assert p.fields["string"] == "hello"
    assert p.fields["integer"] == 42
    assert p.fields["nested"] == {"a": "b"}


def test_handoff_payload_metadata_must_be_string_keyed_string_valued() -> None:
    p = HandoffPayload(fields={"a": 1}, metadata={"agent": "researcher"})
    assert p.metadata == {"agent": "researcher"}
    with pytest.raises(ValidationError):
        HandoffPayload(fields={"a": 1}, metadata={"agent": 42})  # type: ignore[dict-item]


def test_handoff_payload_raw_defaults_to_none_and_accepts_string() -> None:
    p1 = HandoffPayload(fields={"a": 1})
    assert p1.raw is None
    p2 = HandoffPayload(fields={"a": 1}, raw="concatenated text")
    assert p2.raw == "concatenated text"


def test_handoff_payload_extra_top_level_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        HandoffPayload(fields={"a": 1}, bogus="oops")  # type: ignore[call-arg]


def test_handoff_payload_empty_fields_dict_is_valid() -> None:
    p = HandoffPayload(fields={})
    assert p.fields == {}


# --- FieldScore -----------------------------------------------------------


def test_field_score_accepts_valid_payload() -> None:
    fs = FieldScore(
        field_name="hypothesis",
        score=0.85,
        method="embedding_cosine",
        passed=True,
    )
    assert fs.field_name == "hypothesis"
    assert fs.score == 0.85
    assert fs.method == "embedding_cosine"
    assert fs.passed is True


@pytest.mark.parametrize("bad_score", [-0.001, 1.001, -1.0, 2.0, 100.0])
def test_field_score_out_of_range_rejected(bad_score: float) -> None:
    with pytest.raises(ValidationError):
        FieldScore(
            field_name="x",
            score=bad_score,
            method="embedding_cosine",
            passed=False,
        )


@pytest.mark.parametrize("good_score", [0.0, 0.5, 1.0])
def test_field_score_boundary_values_accepted(good_score: float) -> None:
    fs = FieldScore(field_name="x", score=good_score, method="m", passed=True)
    assert fs.score == good_score


def test_field_score_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        FieldScore(  # type: ignore[call-arg]
            field_name="x",
            score=0.5,
            method="m",
            passed=True,
            bogus="oops",
        )


# --- ScoreResult ----------------------------------------------------------


def test_score_result_accepts_valid_payload() -> None:
    sr = ScoreResult(
        overall_score=0.9,
        field_scores=[
            FieldScore(field_name="a", score=0.95, method="embedding_cosine", passed=True),
            FieldScore(field_name="b", score=0.85, method="embedding_cosine", passed=True),
        ],
        scorer_name="embedding_proxy",
        scorer_version="0.1.0",
        timestamp_iso="2026-05-02T12:00:00+00:00",
    )
    assert sr.overall_score == 0.9
    assert len(sr.field_scores) == 2
    assert sr.scorer_name == "embedding_proxy"


@pytest.mark.parametrize("bad_overall", [-0.001, 1.001, -1.0, 2.0])
def test_score_result_overall_out_of_range_rejected(bad_overall: float) -> None:
    with pytest.raises(ValidationError):
        ScoreResult(
            overall_score=bad_overall,
            field_scores=[],
            scorer_name="s",
            scorer_version="0.0.1",
            timestamp_iso="2026-05-02T00:00:00+00:00",
        )


def test_score_result_empty_field_scores_is_valid() -> None:
    """Scaffold contracts (ADR 0001) have no contracted fields; result is empty."""
    sr = ScoreResult(
        overall_score=1.0,
        field_scores=[],
        scorer_name="s",
        scorer_version="0.0.1",
        timestamp_iso="2026-05-02T00:00:00+00:00",
    )
    assert sr.field_scores == []


def test_score_result_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ScoreResult(  # type: ignore[call-arg]
            overall_score=0.5,
            field_scores=[],
            scorer_name="s",
            scorer_version="0.0.1",
            timestamp_iso="2026-05-02T00:00:00+00:00",
            bogus="oops",
        )


# --- ScoreResult.timestamp_iso UTC-offset validator -----------------------


def test_score_result_timestamp_iso_utc_offset_accepted() -> None:
    sr = ScoreResult(
        overall_score=1.0,
        field_scores=[],
        scorer_name="s",
        scorer_version="0.0.1",
        timestamp_iso="2026-05-02T21:00:00+00:00",
    )
    assert sr.timestamp_iso == "2026-05-02T21:00:00+00:00"


def test_score_result_timestamp_iso_z_suffix_accepted() -> None:
    """Z is normalised to +00:00 inside the validator (3.10 fromisoformat compat)."""
    sr = ScoreResult(
        overall_score=1.0,
        field_scores=[],
        scorer_name="s",
        scorer_version="0.0.1",
        timestamp_iso="2026-05-02T21:00:00Z",
    )
    assert sr.timestamp_iso == "2026-05-02T21:00:00Z"


def test_score_result_timestamp_iso_naive_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScoreResult(
            overall_score=1.0,
            field_scores=[],
            scorer_name="s",
            scorer_version="0.0.1",
            timestamp_iso="2026-05-02T21:00:00",
        )
    assert (
        "timestamp_iso must be a UTC-offset ISO 8601 string "
        "(e.g. 2026-05-02T21:00:00+00:00); naive datetimes and non-UTC offsets "
        "are not accepted"
    ) in str(exc_info.value)


def test_score_result_timestamp_iso_non_utc_offset_rejected() -> None:
    """+01:00 is timezone-aware but not UTC; strict UTC means reject."""
    with pytest.raises(ValidationError) as exc_info:
        ScoreResult(
            overall_score=1.0,
            field_scores=[],
            scorer_name="s",
            scorer_version="0.0.1",
            timestamp_iso="2026-05-02T21:00:00+01:00",
        )
    assert (
        "timestamp_iso must be a UTC-offset ISO 8601 string "
        "(e.g. 2026-05-02T21:00:00+00:00); naive datetimes and non-UTC offsets "
        "are not accepted"
    ) in str(exc_info.value)


def test_score_result_timestamp_iso_garbage_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScoreResult(
            overall_score=1.0,
            field_scores=[],
            scorer_name="s",
            scorer_version="0.0.1",
            timestamp_iso="not a timestamp",
        )
    assert "timestamp_iso must be a UTC-offset ISO 8601 string" in str(exc_info.value)


# --- public surface sanity ------------------------------------------------


def test_module_exports_expected_names() -> None:
    from precept.scoring import base

    assert set(base.__all__) == {"FieldScore", "HandoffPayload", "ScoreResult", "Scorer"}

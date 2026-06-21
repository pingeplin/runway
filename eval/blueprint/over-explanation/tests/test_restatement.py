"""Tests for the primary restatement-rate metric."""

from __future__ import annotations

import pytest

from eval_overexplanation.models import Proposition, PropositionSet
from eval_overexplanation.restatement import RestatementScore, restatement_rate


def _prop(pid: str, mentions: tuple[int, ...]) -> Proposition:
    return Proposition(id=pid, text=pid, kind="claim", mention_sentences=mentions)


def test_distinct_and_total_mentions_math() -> None:
    # 3 distinct propositions; mention counts 1 + 3 + 2 = 6 total mentions.
    s = PropositionSet(
        document_id="doc",
        propositions=(
            _prop("a", (0,)),
            _prop("b", (1, 2, 4)),
            _prop("c", (3, 5)),
        ),
    )
    score = restatement_rate(s)
    assert isinstance(score, RestatementScore)
    assert score.distinct == 3
    assert score.total_mentions == 6
    assert score.rate == pytest.approx(1.0 - 3 / 6)  # 0.5
    assert 0.0 <= score.rate < 1.0


def test_rate_zero_when_every_proposition_mentioned_once() -> None:
    s = PropositionSet(
        document_id="doc",
        propositions=(
            _prop("a", (0,)),
            _prop("b", (1,)),
            _prop("c", (2,)),
        ),
    )
    score = restatement_rate(s)
    assert score.distinct == score.total_mentions == 3
    assert score.rate == 0.0


def test_single_proposition_mentioned_once_is_zero() -> None:
    s = PropositionSet(document_id="doc", propositions=(_prop("a", (0,)),))
    score = restatement_rate(s)
    assert score.distinct == 1
    assert score.total_mentions == 1
    assert score.rate == 0.0


def test_value_error_on_zero_total_mentions() -> None:
    # A valid PropositionSet always has >= 1 mention per proposition, so the
    # only way to reach total_mentions == 0 is the empty set. The guard must
    # fire rather than dividing by zero.
    s = PropositionSet(document_id="empty", propositions=())
    assert s.total_mentions == 0
    with pytest.raises(ValueError):
        restatement_rate(s)


def test_adding_non_repeating_propositions_cannot_lower_rate() -> None:
    # Within-document rate: padding with novel, single-mention propositions
    # raises distinct and total_mentions equally and never lowers the rate.
    base = PropositionSet(
        document_id="base",
        propositions=(
            _prop("a", (0,)),
            _prop("b", (1, 2)),  # restated once
        ),
    )
    base_rate = restatement_rate(base).rate

    padded = PropositionSet(
        document_id="padded",
        propositions=(
            _prop("a", (0,)),
            _prop("b", (1, 2)),
            _prop("pad1", (3,)),
            _prop("pad2", (4,)),
            _prop("pad3", (5,)),
        ),
    )
    padded_rate = restatement_rate(padded).rate
    # Padding lowers the rate here (dilution), but the point of the property is
    # that it never makes a non-restating doc look like it restated: a doc with
    # no repeats stays at 0 no matter how much novel content is added.
    assert padded_rate < base_rate
    no_repeat = PropositionSet(
        document_id="nr",
        propositions=tuple(_prop(f"p{i}", (i,)) for i in range(10)),
    )
    assert restatement_rate(no_repeat).rate == 0.0


def test_anti_gaming_mentions_are_per_proposition_not_per_sentence() -> None:
    # Two restatements of one claim comma-spliced into a SINGLE sentence still
    # count as two mention events for that proposition. The metric keys off
    # per-proposition mention_sentences, not sentence boundaries, so collapsing
    # restatements into one sentence does not game the rate.
    #
    # "spliced" puts both restated mentions of `b` at the same sentence index 1
    # (the comma-spliced sentence); "separate" puts them at two indices. Same
    # mention count, same rate -> the surface sentence structure is irrelevant.
    spliced = PropositionSet(
        document_id="spliced",
        propositions=(
            _prop("a", (0,)),
            _prop("b", (1, 1)),  # asserted twice within one sentence
        ),
    )
    separate = PropositionSet(
        document_id="separate",
        propositions=(
            _prop("a", (0,)),
            _prop("b", (1, 2)),  # asserted twice across two sentences
        ),
    )
    spliced_score = restatement_rate(spliced)
    separate_score = restatement_rate(separate)
    assert spliced_score.total_mentions == separate_score.total_mentions == 3
    assert spliced_score.distinct == separate_score.distinct == 2
    assert spliced_score.rate == separate_score.rate == pytest.approx(1 - 2 / 3)

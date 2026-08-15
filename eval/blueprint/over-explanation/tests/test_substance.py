"""Tests for the A0->A1 substance recall guardrail.

Exercises the MUST-drop block boundary, the SHOULD/detail non-blocking path,
and the all-survived (preserved / merged / restated) recall==1 path. Pure
hand-built fixtures, no network.
"""

from __future__ import annotations

import pytest

from eval_overexplanation.models import (
    Alignment,
    Proposition,
    PropositionLink,
    PropositionSet,
    Relation,
    Tier,
)
from eval_overexplanation.substance import proposition_recall


def _prop(pid: str, tier: Tier) -> Proposition:
    return Proposition(id=pid, text=f"claim {pid}", kind="claim", tier=tier,
                       mention_sentences=(0,))


def _alignment(source_tiers: dict[str, Tier],
               relations: dict[str, Relation]) -> Alignment:
    """Build an A0->A1 alignment.

    ``source_tiers`` maps source id -> tier. ``relations`` maps source id ->
    relation. A surviving relation links to a same-named target proposition; a
    DROPPED relation links to no target.
    """
    source_props = tuple(_prop(pid, t) for pid, t in source_tiers.items())
    source = PropositionSet(document_id="A0", propositions=source_props)

    target_props = tuple(
        _prop(f"t_{pid}", Tier.SHOULD)
        for pid, rel in relations.items()
        if rel is not Relation.DROPPED
    )
    target = PropositionSet(document_id="A1", propositions=target_props)

    links = tuple(
        PropositionLink(
            source_id=pid,
            target_id=None if rel is Relation.DROPPED else f"t_{pid}",
            relation=rel,
        )
        for pid, rel in relations.items()
    )
    return Alignment(source=source, target=target, links=links)


def test_dropping_a_must_blocks() -> None:
    align = _alignment(
        source_tiers={"a": Tier.MUST, "b": Tier.SHOULD},
        relations={"a": Relation.DROPPED, "b": Relation.PRESERVED},
    )
    report = proposition_recall(align)

    assert report.blocks is True
    assert report.dropped_must == ("a",)
    assert report.dropped_should == ()
    assert report.total_source == 2
    assert report.survived == 1
    assert report.recall == 0.5


def test_dropping_only_a_should_lowers_recall_but_does_not_block() -> None:
    align = _alignment(
        source_tiers={"a": Tier.MUST, "b": Tier.SHOULD, "c": Tier.DETAIL},
        relations={
            "a": Relation.PRESERVED,
            "b": Relation.DROPPED,
            "c": Relation.PRESERVED,
        },
    )
    report = proposition_recall(align)

    assert report.blocks is False
    assert report.dropped_must == ()
    assert report.dropped_should == ("b",)
    assert report.dropped_detail == ()
    assert report.recall == pytest.approx(2 / 3)
    assert report.recall < 1.0


def test_dropping_only_a_detail_does_not_block() -> None:
    align = _alignment(
        source_tiers={"a": Tier.MUST, "d": Tier.DETAIL},
        relations={"a": Relation.PRESERVED, "d": Relation.DROPPED},
    )
    report = proposition_recall(align)

    assert report.blocks is False
    assert report.dropped_detail == ("d",)
    assert report.dropped_must == ()
    assert report.recall == 0.5


def test_all_surviving_relations_give_full_recall_no_block() -> None:
    # preserved / merged / restated-elsewhere all count as survival.
    align = _alignment(
        source_tiers={"a": Tier.MUST, "b": Tier.SHOULD, "c": Tier.DETAIL},
        relations={
            "a": Relation.PRESERVED,
            "b": Relation.MERGED_INTO,
            "c": Relation.RESTATED_ELSEWHERE,
        },
    )
    report = proposition_recall(align)

    assert report.blocks is False
    assert report.recall == 1.0
    assert report.survived == 3
    assert report.dropped_must == ()
    assert report.dropped_should == ()
    assert report.dropped_detail == ()


def test_multiple_must_drops_all_collected() -> None:
    align = _alignment(
        source_tiers={"a": Tier.MUST, "b": Tier.MUST, "c": Tier.SHOULD},
        relations={
            "a": Relation.DROPPED,
            "b": Relation.DROPPED,
            "c": Relation.DROPPED,
        },
    )
    report = proposition_recall(align)

    assert report.blocks is True
    assert set(report.dropped_must) == {"a", "b"}
    assert report.dropped_should == ("c",)
    assert report.survived == 0
    assert report.recall == 0.0


# --------------------------------------------------------------------------- #
# alignment_purity (BLUEPRINT-BENCH C4, reported only)
# --------------------------------------------------------------------------- #


def test_alignment_purity_all_aligned_is_one() -> None:
    from eval_overexplanation.substance import alignment_purity

    align = _alignment(
        source_tiers={"a": Tier.SHOULD, "b": Tier.SHOULD},
        relations={"a": Relation.PRESERVED, "b": Relation.MERGED_INTO},
    )
    assert alignment_purity(align) == pytest.approx(2 / align.target.distinct)


def test_alignment_purity_dropped_links_do_not_count() -> None:
    from eval_overexplanation.substance import alignment_purity

    align = _alignment(
        source_tiers={"a": Tier.SHOULD, "b": Tier.SHOULD, "c": Tier.SHOULD},
        relations={"a": Relation.PRESERVED, "b": Relation.DROPPED,
                   "c": Relation.DROPPED},
    )
    # one surviving link over the gold's distinct count
    assert alignment_purity(align) == pytest.approx(1 / align.target.distinct)


def test_alignment_purity_is_repetition_invariant() -> None:
    from eval_overexplanation.substance import alignment_purity

    base = _alignment(
        source_tiers={"a": Tier.SHOULD},
        relations={"a": Relation.PRESERVED},
    )
    # Re-mentioning the source claim five times changes neither the links nor
    # the gold distinct count, so purity is untouched.
    noisy_source = PropositionSet(
        document_id="A0",
        propositions=tuple(
            Proposition(id=p.id, text=p.text, kind=p.kind, tier=p.tier,
                        mention_sentences=(0, 1, 2, 3, 4))
            for p in base.source.propositions
        ),
    )
    noisy = Alignment(source=noisy_source, target=base.target,
                      links=base.links)
    assert alignment_purity(noisy) == alignment_purity(base)


def test_alignment_purity_empty_gold_raises() -> None:
    from eval_overexplanation.substance import alignment_purity

    align = _alignment(
        source_tiers={"a": Tier.SHOULD},
        relations={"a": Relation.DROPPED},
    )
    assert align.target.distinct == 0
    with pytest.raises(ValueError):
        alignment_purity(align)

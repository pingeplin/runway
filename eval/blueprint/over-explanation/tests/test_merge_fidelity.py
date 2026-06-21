from __future__ import annotations

from eval_overexplanation.merge_fidelity import MergeFidelityReport, merge_fidelity
from eval_overexplanation.models import (
    Alignment,
    Proposition,
    PropositionLink,
    PropositionSet,
    Relation,
)


def _prop(pid: str) -> Proposition:
    return Proposition(id=pid, text=f"claim {pid}", kind="claim", mention_sentences=(0,))


def _pre() -> PropositionSet:
    return PropositionSet(
        document_id="pre",
        propositions=(_prop("s1"), _prop("s2"), _prop("s3")),
    )


def _post(ids: tuple[str, ...]) -> PropositionSet:
    return PropositionSet(
        document_id="post",
        propositions=tuple(_prop(i) for i in ids),
    )


def test_clean_merge_is_ok():
    """Delete-or-merge that preserves/merges every claim passes fidelity."""
    post = _post(("t1", "t2"))
    alignment = Alignment(
        source=_pre(),
        target=post,
        links=(
            PropositionLink("s1", "t1", Relation.PRESERVED),
            # s2 folded into the sentence carrying s1's claim, intact
            PropositionLink("s2", "t1", Relation.MERGED_INTO),
            PropositionLink("s3", "t2", Relation.PRESERVED),
        ),
    )

    report = merge_fidelity(alignment)

    assert isinstance(report, MergeFidelityReport)
    assert report.ok is True
    assert report.dropped_under_merge == ()
    assert report.merged == ("s2",)
    assert report.merge_count == 1


def test_merge_that_drops_a_constraint_is_not_ok():
    """A claim DROPPED during delete-or-merge is a fidelity violation."""
    post = _post(("t1",))
    alignment = Alignment(
        source=_pre(),
        target=post,
        links=(
            PropositionLink("s1", "t1", Relation.PRESERVED),
            PropositionLink("s2", "t1", Relation.MERGED_INTO),
            # the constraint s3 was silently deleted, not merged
            PropositionLink("s3", None, Relation.DROPPED),
        ),
    )

    report = merge_fidelity(alignment)

    assert report.ok is False
    assert report.dropped_under_merge == ("s3",)
    assert report.merged == ("s2",)
    assert report.merge_count == 1


def test_restated_elsewhere_does_not_count_as_dropped():
    """A redundant mention restated elsewhere survives; fidelity holds."""
    post = _post(("t1", "t2"))
    alignment = Alignment(
        source=_pre(),
        target=post,
        links=(
            PropositionLink("s1", "t1", Relation.PRESERVED),
            PropositionLink("s2", "t2", Relation.RESTATED_ELSEWHERE),
            PropositionLink("s3", "t2", Relation.PRESERVED),
        ),
    )

    report = merge_fidelity(alignment)

    assert report.ok is True
    assert report.dropped_under_merge == ()
    assert report.merged == ()


def test_multiple_drops_reported_in_link_order():
    """All dropped ids are surfaced, preserving alignment link order."""
    post = _post(("t1",))
    alignment = Alignment(
        source=_pre(),
        target=post,
        links=(
            PropositionLink("s1", "t1", Relation.PRESERVED),
            PropositionLink("s2", None, Relation.DROPPED),
            PropositionLink("s3", None, Relation.DROPPED),
        ),
    )

    report = merge_fidelity(alignment)

    assert report.ok is False
    assert report.dropped_under_merge == ("s2", "s3")

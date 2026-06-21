"""Merge-fidelity guardrail for change ②'s delete-OR-merge step.

Change ② lets the evaluator delete or merge propositions to cut restatement.
This guardrail audits a *within-arm* pre-evaluator -> post-evaluator
``Alignment`` and asserts the delete/merge step never silently *drops* a claim.

It is deliberately distinct from ``substance.proposition_recall``:

* ``substance`` compares two **arms** (A0 baseline -> A1 treatment) and tiers
  losses by importance.
* this module compares **one arm's** pre/post-evaluator documents and asks a
  simpler binary question — did delete-or-merge lose anything?

Both share the single survival predicate ``models.survived`` so their notions
of "survived" can never drift apart, but the inputs and report shape differ, so
the two are kept separate (do not merge them).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Alignment, Relation


@dataclass(frozen=True)
class MergeFidelityReport:
    """Result of auditing a pre->post evaluator alignment for dropped claims.

    ``merged`` are the source ids the evaluator folded into another sentence
    (relation ``MERGED_INTO``) — the legitimate, fidelity-preserving outcome of
    the merge step. ``dropped_under_merge`` are the source ids that were
    ``DROPPED`` — a claim lost during delete-or-merge, which is a fidelity
    violation.

    In the model, ``DROPPED`` already excludes ``RESTATED_ELSEWHERE`` (a
    redundant mention whose claim still stands elsewhere), so every id in
    ``dropped_under_merge`` is a genuine lost claim.
    """

    merged: tuple[str, ...]
    dropped_under_merge: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """True iff no source proposition was dropped under delete-or-merge."""
        return len(self.dropped_under_merge) == 0

    @property
    def merge_count(self) -> int:
        """Number of source propositions folded via ``MERGED_INTO``."""
        return len(self.merged)


def merge_fidelity(alignment: Alignment) -> MergeFidelityReport:
    """Audit a within-arm pre->post evaluator alignment for dropped claims.

    ``alignment.source`` is the pre-evaluator proposition set, ``alignment.target``
    the post-evaluator set. A source proposition with relation ``DROPPED`` is a
    fidelity violation: the delete-or-merge step lost a claim that was not a
    proven ``RESTATED_ELSEWHERE`` redundancy (the model's ``DROPPED`` already
    excludes that case). ``MERGED_INTO`` links are the benign merges and are
    reported for audit but never block.

    Source ids preserve alignment link order for stable, auditable output.
    """
    merged = tuple(
        link.source_id
        for link in alignment.links
        if link.relation is Relation.MERGED_INTO
    )
    dropped = tuple(
        link.source_id
        for link in alignment.links
        if link.relation is Relation.DROPPED
    )
    return MergeFidelityReport(merged=merged, dropped_under_merge=dropped)

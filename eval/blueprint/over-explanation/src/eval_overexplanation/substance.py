"""Paired A0->A1 proposition-diff recall (fix #4 / substance guardrail).

This is the cross-*arm* substance check: given an :class:`Alignment` whose
``source`` is the baseline (A0) document and whose ``target`` is the treatment
(A1) document, it asks how many of the baseline's load-bearing propositions
survived into the treatment. Losing a MUST-tier claim is a hard block on
shipping the treatment — even if the primary restatement metric improved,
dropping a required claim is never an acceptable trade.

Survival is decided by :func:`eval_overexplanation.models.survived`, the single
source of truth shared with merge-fidelity, so the two guardrails can never
drift apart on what "survived" means. Tier comes from the *source* proposition
(the blind gold author's tiering), never from the treatment under test.

Distinct from :mod:`eval_overexplanation.merge_fidelity`, which compares one
arm's pre/post-evaluator documents — same survival predicate, different inputs.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Alignment, Tier, survived


@dataclass(frozen=True)
class RecallReport:
    """Outcome of the A0->A1 substance recall check.

    ``dropped_*`` hold the *source* proposition ids of dropped claims, bucketed
    by the source proposition's tier. ``blocks`` is True iff any MUST-tier claim
    was dropped; SHOULD/detail drops are reported for human review but do not
    block.
    """

    total_source: int
    survived: int
    dropped_must: tuple[str, ...]
    dropped_should: tuple[str, ...]
    dropped_detail: tuple[str, ...]

    @property
    def recall(self) -> float:
        """Fraction of source propositions that survived into the target.

        ``survived / total_source``. 1.0 when every source claim is preserved,
        merged, or restated elsewhere (no DROPPED links).
        """
        if self.total_source == 0:
            raise ValueError("recall undefined for an empty source set")
        return self.survived / self.total_source

    @property
    def blocks(self) -> bool:
        """True iff any MUST-tier source proposition was dropped."""
        return len(self.dropped_must) > 0


def proposition_recall(alignment: Alignment) -> RecallReport:
    """Compute substance recall for an A0(source)->A1(target) alignment.

    A source proposition survives iff ``survived(link.relation)`` is True (only
    ``DROPPED`` is a loss). Each dropped source id is bucketed by the *source*
    proposition's tier. ``blocks`` fires iff a MUST claim is among the dropped.
    """
    by_id = alignment.source.by_id()

    survived_count = 0
    dropped_must: list[str] = []
    dropped_should: list[str] = []
    dropped_detail: list[str] = []

    for link in alignment.links:
        if survived(link.relation):
            survived_count += 1
            continue
        tier = by_id[link.source_id].tier
        if tier is Tier.MUST:
            dropped_must.append(link.source_id)
        elif tier is Tier.SHOULD:
            dropped_should.append(link.source_id)
        else:  # Tier.DETAIL
            dropped_detail.append(link.source_id)

    return RecallReport(
        total_source=alignment.source.distinct,
        survived=survived_count,
        dropped_must=tuple(dropped_must),
        dropped_should=tuple(dropped_should),
        dropped_detail=tuple(dropped_detail),
    )

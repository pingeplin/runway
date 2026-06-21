"""Primary metric: within-document restatement rate.

Restatement is *extra mentions of an already-asserted proposition*. The rate is

    rate = 1 - distinct / total_mentions

where ``distinct`` is the number of distinct propositions in the document and
``total_mentions`` is the total number of proposition-mention events (a
proposition asserted three times contributes three mentions). The rate lives in
``[0, 1)``: it is ``0`` exactly when every proposition is mentioned once
(``total_mentions == distinct``) and approaches ``1`` as the same handful of
claims is restated ever more often.

Why this metric resists the two obvious games:

* It is a *within-document rate*, not an absolute count. Adding non-repeating
  prose — more distinct propositions each mentioned once — raises both
  ``distinct`` and ``total_mentions`` by the same amount and cannot lower the
  rate; padding with novel content does not improve the score.
* Mentions are counted *per proposition*, not per sentence. Comma-splicing two
  restatements of the same claim into one sentence does not collapse them into
  one mention — the extractor records two mention events for that proposition,
  so the rate is unchanged. The metric keys off semantic mentions
  (``Proposition.mention_sentences``), which the extractor owns, not off
  surface sentence boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import PropositionSet


@dataclass(frozen=True)
class RestatementScore:
    """The restatement metric for one document's proposition set.

    ``rate`` is ``1 - distinct / total_mentions`` and lies in ``[0, 1)``.
    """

    distinct: int
    total_mentions: int
    rate: float


def restatement_rate(s: PropositionSet) -> RestatementScore:
    """Compute the within-document restatement rate of a proposition set.

    ``rate = 1 - distinct / total_mentions``. With every proposition mentioned
    exactly once, ``total_mentions == distinct`` and the rate is ``0.0``.

    This is a *within-document rate*: adding non-repeating propositions (each a
    single mention) raises ``distinct`` and ``total_mentions`` equally and
    cannot lower the rate, and because mentions are counted per proposition
    rather than per sentence, comma-splicing two restatements of one claim into
    a single sentence does not game it.

    Raises:
        ValueError: if ``total_mentions == 0`` (impossible for a valid set —
            every proposition has >= 1 mention — but guarded so a malformed
            input fails loudly instead of dividing by zero).
    """
    distinct = s.distinct
    total_mentions = s.total_mentions
    if total_mentions == 0:
        raise ValueError(
            f"PropositionSet {s.document_id!r} has zero total mentions; "
            "cannot compute a restatement rate"
        )
    rate = 1.0 - distinct / total_mentions
    return RestatementScore(
        distinct=distinct,
        total_mentions=total_mentions,
        rate=rate,
    )

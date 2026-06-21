"""Core value objects for the over-explanation benchmark.

These are deliberately small, frozen dataclasses. They carry *data only* — no
LLM calls, no I/O, no scoring policy. The judgment that produces them (what
counts as a proposition, which propositions correspond across two documents)
lives behind the Protocols in ``interfaces.py``; the *decision rules* that
consume them (restatement rate, substance recall, merge fidelity) live in the
leaf modules. Keeping the data inert is what lets every rule be unit-tested
deterministically with hand-built fixtures and no network.

Vocabulary (from issue #10):

* A **proposition** is one atomic load-bearing claim — a fact, decision,
  constraint, interface detail, rejected alternative, or testable behavior.
* A **mention** is one place in a document where a proposition is asserted.
  A proposition asserted once has one mention; a proposition restated three
  times has three mentions. Restatement is *extra mentions of an
  already-asserted proposition*, which is exactly what the primary metric
  measures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# --------------------------------------------------------------------------- #
# Propositions and proposition sets
# --------------------------------------------------------------------------- #


class Tier(str, Enum):
    """Importance tier of a proposition, used by the substance guardrail.

    Losing a MUST proposition between baseline and treatment is a hard block;
    losing a SHOULD is flagged for human review. Tiers are assigned by the
    blind gold-proposition author, never by the treatment under test.
    """

    MUST = "must"
    SHOULD = "should"
    DETAIL = "detail"


@dataclass(frozen=True)
class Proposition:
    """One atomic load-bearing claim extracted from a document.

    ``kind`` is a label from the extractor's *independently authored* ontology.
    It must NOT be one of change ②'s six keep-categories — reusing those would
    make density rise by construction (fix #1 in the issue). It is descriptive
    metadata only; no decision rule keys off specific ``kind`` strings.

    ``mention_sentences`` are the indices (into the document's sentence list)
    where this proposition is asserted. Its length is the mention count and
    must be >= 1 — a proposition with zero mentions is not in the document.
    """

    id: str
    text: str
    kind: str
    tier: Tier = Tier.SHOULD
    mention_sentences: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Proposition.id must be non-empty")
        if len(self.mention_sentences) < 1:
            raise ValueError(
                f"Proposition {self.id!r} must have >= 1 mention "
                "(zero mentions means it is not in the document)"
            )

    @property
    def mention_count(self) -> int:
        return len(self.mention_sentences)


@dataclass(frozen=True)
class PropositionSet:
    """The propositions extracted from a single document.

    Identity is by ``Proposition.id``; ids must be unique within a set. This is
    the unit the restatement-rate scorer and every guardrail consume.
    """

    document_id: str
    propositions: tuple[Proposition, ...]

    def __post_init__(self) -> None:
        ids = [p.id for p in self.propositions]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate proposition ids in set: {dupes}")

    def by_id(self) -> dict[str, Proposition]:
        return {p.id: p for p in self.propositions}

    @property
    def distinct(self) -> int:
        """Number of distinct propositions (DISTINCT_PROPOSITIONS)."""
        return len(self.propositions)

    @property
    def total_mentions(self) -> int:
        """Total proposition-mention events (TOTAL_PROPOSITION_MENTIONS)."""
        return sum(p.mention_count for p in self.propositions)

    def tier(self, tier: Tier) -> tuple[Proposition, ...]:
        return tuple(p for p in self.propositions if p.tier is tier)


# --------------------------------------------------------------------------- #
# Cross-document alignment (A0<->A1, or pre-evaluator<->post-evaluator)
# --------------------------------------------------------------------------- #


class Relation(str, Enum):
    """How a source proposition fares in the target document.

    Produced by the extractor's cross-document judgment (``align``), consumed by
    the deterministic guardrails. ``PRESERVED`` and ``MERGED_INTO`` and
    ``RESTATED_ELSEWHERE`` all mean the claim survived; only ``DROPPED`` is loss.
    """

    PRESERVED = "preserved"          # same claim stands on its own in target
    MERGED_INTO = "merged_into"      # folded into another target sentence, intact
    RESTATED_ELSEWHERE = "restated_elsewhere"  # the dropped mention was redundant
    DROPPED = "dropped"              # claim is gone from the target entirely


def survived(relation: Relation) -> bool:
    """Single source of truth for "did the claim survive into the target?".

    Both guardrails (substance recall, merge fidelity) key off this so their
    notion of survival can never drift apart. Only DROPPED is loss.
    """
    return relation is not Relation.DROPPED


@dataclass(frozen=True)
class PropositionLink:
    """Correspondence of one source proposition to the target document."""

    source_id: str
    target_id: str | None
    relation: Relation

    def __post_init__(self) -> None:
        survived = self.relation in (
            Relation.PRESERVED,
            Relation.MERGED_INTO,
            Relation.RESTATED_ELSEWHERE,
        )
        if survived and self.target_id is None:
            raise ValueError(
                f"link {self.source_id!r} is {self.relation.value} but names no "
                "target proposition"
            )
        if self.relation is Relation.DROPPED and self.target_id is not None:
            raise ValueError(
                f"link {self.source_id!r} is dropped but names a target"
            )


@dataclass(frozen=True)
class Alignment:
    """A source PropositionSet aligned onto a target PropositionSet.

    Every source proposition must appear in exactly one link, so the guardrails
    can reason about the whole source set without gaps. Direction matters:
    for the substance guardrail source=A0, target=A1; for merge-fidelity
    source=pre-evaluator, target=post-evaluator.
    """

    source: PropositionSet
    target: PropositionSet
    links: tuple[PropositionLink, ...]

    def __post_init__(self) -> None:
        linked = [l.source_id for l in self.links]
        src_ids = {p.id for p in self.source.propositions}
        if set(linked) != src_ids or len(linked) != len(src_ids):
            raise ValueError(
                "alignment links must cover each source proposition exactly once"
            )
        tgt_ids = {p.id for p in self.target.propositions}
        for l in self.links:
            if l.target_id is not None and l.target_id not in tgt_ids:
                raise ValueError(
                    f"link {l.source_id!r} names unknown target {l.target_id!r}"
                )

    def links_for(self, relation: Relation) -> tuple[PropositionLink, ...]:
        return tuple(l for l in self.links if l.relation is relation)


# --------------------------------------------------------------------------- #
# Corpus: briefs, arms, run outputs
# --------------------------------------------------------------------------- #


class Regime(str, Enum):
    """Pre-registered difficulty stratum of a brief.

    Labels are frozen from a held-out proxy (baseline word count + a
    different-model coarse estimate) BEFORE any treatment run, so they cannot be
    chosen to flatter the result. The primary effect must hold on
    LARGE_REALISTIC, not just the easy strata.
    """

    ELICIT_PRONE = "elicit_prone"
    LARGE_REALISTIC = "large_realistic"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class Brief:
    """One frozen task brief that every arm receives identically."""

    id: str
    title: str
    regime: Regime
    buildable: bool          # does it have a hidden oracle + acceptance set?
    text: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Brief.id must be non-empty")


@dataclass(frozen=True)
class Arm:
    """One experimental condition: a pinned plugin version + evaluator config.

    ``plugin_ref`` is a git ref/tag/worktree identifier (e.g. the A0 baseline
    commit or the A1 treatment commit) that ``scripts/setup-worktrees.sh``
    materialises. ``evaluator`` carries arm-specific knobs (e.g. the placebo
    rule for A2, the one-line brevity rule for A3_fair). The harness code is
    arm-count agnostic: Milestone 1 wires four arms, Milestone 2 wires eight,
    with no code change — only this list grows.
    """

    id: str
    label: str
    plugin_ref: str
    evaluator: dict[str, str] = field(default_factory=dict)
    description: str = ""


# --------------------------------------------------------------------------- #
# Guardrail / grammaticality report value objects (data only)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SentenceVerdict:
    """One sentence's grammaticality verdict."""

    index: int
    text: str
    ok: bool
    reason: str = ""  # why it failed, when ok is False


@dataclass(frozen=True)
class GrammaticalityReport:
    """Result of a GrammaticalityChecker over a document's sentences."""

    verdicts: tuple[SentenceVerdict, ...]

    @property
    def ok(self) -> bool:
        return all(v.ok for v in self.verdicts)

    @property
    def fragments(self) -> tuple[SentenceVerdict, ...]:
        return tuple(v for v in self.verdicts if not v.ok)


# --------------------------------------------------------------------------- #
# Buildability inputs (data only; runners live in buildability.py)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OracleCase:
    """One hidden-oracle case: call ``entrypoint(*args)`` and expect ``expected``.

    Authored from the brief alone, blind to any arm's implementation. The same
    frozen case list grades every arm's impl (issue #10: "identical across
    arms").
    """

    label: str
    args: tuple[object, ...]
    expected: object


@dataclass(frozen=True)
class Mutation:
    """One strategic source mutation for executed mutation testing (§4 Step 3).

    A literal text replacement applied to ``filename`` within a *copy* of the
    impl. ``find`` must occur exactly once in that file or the mutation is
    reported invalid (never silently skipped — a silent skip would inflate the
    kill rate).
    """

    label: str
    filename: str
    find: str
    replace: str


@dataclass(frozen=True)
class ArmDocResult:
    """One produced artifact (design doc or spec) for an (arm, brief, seed).

    ``pre_evaluator`` / ``post_evaluator`` are the proposition sets of the
    document *before* and *after* the evaluator fix-loop ran, captured so that
    merge-fidelity and the extra-pass confound are auditable (issue #10,
    Milestone 1). For arms whose evaluator does not edit, the two are equal.
    """

    arm_id: str
    brief_id: str
    seed: int
    word_count: int
    propositions: PropositionSet
    pre_evaluator: PropositionSet | None = None
    post_evaluator: PropositionSet | None = None

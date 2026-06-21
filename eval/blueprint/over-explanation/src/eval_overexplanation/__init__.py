"""Over-explanation benchmark harness (issue #10).

Public surface re-exports the inert value objects and the two Protocol seams.
Leaf modules (restatement, stats, guardrails, buildability, extractor,
grammaticality, manifest, corpus, cli) are imported by their full path.
"""

from __future__ import annotations

from .interfaces import GrammaticalityChecker, PropositionExtractor
from .models import (
    Alignment,
    Arm,
    ArmDocResult,
    Brief,
    GrammaticalityReport,
    Mutation,
    OracleCase,
    Proposition,
    PropositionLink,
    PropositionSet,
    Regime,
    Relation,
    SentenceVerdict,
    Tier,
    survived,
)

__all__ = [
    "Alignment",
    "Arm",
    "ArmDocResult",
    "Brief",
    "GrammaticalityChecker",
    "GrammaticalityReport",
    "Mutation",
    "OracleCase",
    "Proposition",
    "PropositionExtractor",
    "PropositionLink",
    "PropositionSet",
    "Regime",
    "Relation",
    "SentenceVerdict",
    "Tier",
    "survived",
]

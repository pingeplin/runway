"""The two seams where non-deterministic judgment enters the harness.

Everything else in this package is a pure function over the value objects in
``models.py`` and can be tested with hand-built fixtures. These two Protocols
are the *only* places that need an LLM (the proposition extractor) or a heavy
NLP dependency (the grammaticality checker). Depending on the Protocol — never
on a concrete implementation — is what lets the test suite run offline and lets
issue #10's "≥2 model families" requirement be satisfied by swapping
implementations, not by editing call sites (Dependency Inversion).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import Alignment, GrammaticalityReport, PropositionSet


@runtime_checkable
class PropositionExtractor(Protocol):
    """Turns prose into propositions and aligns two documents' propositions.

    CRITICAL VALIDITY CONSTRAINT (issue #10, fix #1): a real implementation must
    use an ontology authored independently of change ②'s six keep-categories,
    and must run on a *different model family* than the generator/evaluator
    being graded — replicated across >= 2 families. An extractor that shares the
    treatment's categories or model would make the metric move by construction.
    The harness cannot enforce this in code; it is asserted in the
    pre-registration manifest and checked by the instrument-trust gate
    (atomization / manipulation invariance) before any arm number is read.

    Implementations:
      * ``AnthropicExtractor``  — reference impl, calls the API.
      * a second-family extractor — left as a documented slot (open decision).
      * ``FixtureExtractor``    — returns canned results for deterministic tests.
    """

    def extract(self, document_id: str, text: str) -> PropositionSet:
        """Extract the distinct propositions and their mentions from one doc."""
        ...

    def align(self, source: PropositionSet, target: PropositionSet) -> Alignment:
        """Map each source proposition to its fate in the target document.

        Used both for the cross-arm substance guardrail (source=A0, target=A1)
        and for within-arm merge-fidelity (source=pre-evaluator,
        target=post-evaluator). The extractor owns the semantic judgment of
        *which* propositions correspond; the guardrail modules own the pass/fail
        *rule* over the returned Alignment.
        """
        ...


@runtime_checkable
class GrammaticalityChecker(Protocol):
    """Flags sentences that are not full grammatical sentences.

    Enforces the user's explicit "keep full sentences — no word/article/
    preposition dropping, no register shift" constraint. A real implementation
    uses a deterministic parse (dependency or constituency); the default ships a
    dependency-free heuristic checker, with a spaCy-backed checker available
    behind the ``nlp`` optional dependency. The A3b_dumb_brevity arm exists as a
    positive control: a correct checker MUST flag A3b's telegraphic output.
    """

    def check(self, sentences: tuple[str, ...]) -> GrammaticalityReport:
        """Return per-sentence verdicts; ``ok`` is False if any fragment found."""
        ...

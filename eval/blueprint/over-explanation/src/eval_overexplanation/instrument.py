"""Instrument-trust gate — atomization / manipulation invariance (issue #10).

Before any *arm number* is read, the measuring instrument itself must be shown
to be trustworthy: the restatement metric must not move under manipulations
that change surface form without changing the underlying claims. This module
runs a small battery of *decoy* documents through the extractor and checks the
relevant invariant for each.

The three invariance kinds are deliberately asymmetric — each penalises only the
direction that would *flatter* a treatment, so a decoy can never pass by failing
in the harmless direction:

* ``atomization`` — splitting one sentence into two (or merging two into one)
  must not change the DISTINCT proposition count. The same claims are present;
  only their packaging differs. ``observed_delta = |distinct(variant) -
  distinct(base)|`` — a symmetric check, because *either* direction of drift in
  the distinct count corrupts the rate's denominator/numerator.

* ``length_confound`` — padding the document with non-repeating words must not
  LOWER the restatement rate. A drop would let a treatment "improve" its score
  simply by adding novel verbiage. Only a drop is a failure:
  ``observed_delta = max(0, rate_base - rate_variant)``.

* ``defensive_filler`` — adding non-load-bearing justification (hedges, caveats,
  "to be clear" preambles) must not RAISE the distinct count: filler is not a
  new claim. A rise would let a treatment inflate density with empty prose.
  Only a rise is a failure:
  ``observed_delta = max(0, distinct(variant) - distinct(base))``.

A decoy ``passed`` iff ``observed_delta <= tolerance``. The whole report is
``trusted`` iff every check passed. This module depends only on the
``PropositionExtractor`` Protocol (never a concrete extractor) and the pure
``restatement_rate`` function, so it is fully testable offline with
``FixtureExtractor``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .interfaces import PropositionExtractor
from .restatement import restatement_rate

# The three supported invariance kinds.
ATOMIZATION = "atomization"
LENGTH_CONFOUND = "length_confound"
DEFENSIVE_FILLER = "defensive_filler"


@dataclass(frozen=True)
class Decoy:
    """One manipulation-invariance probe.

    ``base_id`` and ``variant_id`` are ``document_id`` keys into the ``docs``
    map handed to :func:`instrument_trust_gate`. ``kind`` selects the invariant
    (one of ``"atomization"``, ``"length_confound"``, ``"defensive_filler"``).
    ``tolerance`` is the largest score movement this manipulation is allowed to
    produce before the instrument is deemed untrustworthy.
    """

    name: str
    base_id: str
    variant_id: str
    kind: str
    tolerance: float


@dataclass(frozen=True)
class InvarianceCheck:
    """The outcome of scoring one :class:`Decoy`."""

    name: str
    kind: str
    observed_delta: float
    tolerance: float
    passed: bool


@dataclass(frozen=True)
class InstrumentReport:
    """The full instrument-trust battery result."""

    checks: tuple[InvarianceCheck, ...]

    @property
    def trusted(self) -> bool:
        """True iff every invariance check passed."""
        return all(c.passed for c in self.checks)


def instrument_trust_gate(
    extractor: PropositionExtractor,
    docs: Mapping[str, str],
    decoys: Sequence[Decoy],
) -> InstrumentReport:
    """Run every decoy through the extractor and check its invariant.

    For each decoy the base and variant documents are extracted (via
    ``extractor.extract(document_id, text)``) and scored with
    :func:`restatement.restatement_rate`. The ``observed_delta`` is the
    kind-specific, *direction-aware* quantity:

    * ``atomization`` — ``|distinct(variant) - distinct(base)|``
    * ``length_confound`` — ``max(0, rate_base - rate_variant)`` (only a drop)
    * ``defensive_filler`` — ``max(0, distinct(variant) - distinct(base))``
      (only a rise)

    ``passed = observed_delta <= tolerance``. Raises ``KeyError`` if a decoy
    names a ``base_id``/``variant_id`` absent from ``docs``, and ``ValueError``
    for an unknown ``kind`` (fail loudly rather than silently trust).
    """
    checks: list[InvarianceCheck] = []
    for decoy in decoys:
        base_text = docs[decoy.base_id]
        variant_text = docs[decoy.variant_id]

        base_set = extractor.extract(decoy.base_id, base_text)
        variant_set = extractor.extract(decoy.variant_id, variant_text)

        if decoy.kind == ATOMIZATION:
            # Splitting/merging sentences must not change the distinct count;
            # drift in EITHER direction corrupts the metric, so |.|.
            observed = float(abs(variant_set.distinct - base_set.distinct))
        elif decoy.kind == LENGTH_CONFOUND:
            # Padding with non-repeating words must not LOWER the rate; only a
            # drop is a failure.
            base_rate = restatement_rate(base_set).rate
            variant_rate = restatement_rate(variant_set).rate
            observed = max(0.0, base_rate - variant_rate)
        elif decoy.kind == DEFENSIVE_FILLER:
            # Non-load-bearing justification must not RAISE the distinct count;
            # only a rise is a failure.
            observed = float(max(0, variant_set.distinct - base_set.distinct))
        else:
            raise ValueError(
                f"decoy {decoy.name!r} has unknown invariance kind "
                f"{decoy.kind!r}; expected one of {ATOMIZATION!r}, "
                f"{LENGTH_CONFOUND!r}, {DEFENSIVE_FILLER!r}"
            )

        checks.append(
            InvarianceCheck(
                name=decoy.name,
                kind=decoy.kind,
                observed_delta=observed,
                tolerance=decoy.tolerance,
                passed=observed <= decoy.tolerance,
            )
        )

    return InstrumentReport(checks=tuple(checks))

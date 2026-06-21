"""The SHIP/KILL rule — issue #10's pre-registered decision over the harness.

This module does **no statistics**. The orchestrator runs the stats and
guardrails, packs the already-computed structured results into a
``DecisionInputs``, and ``decide`` applies the *fixed precedence* below. Keeping
the rule a pure function over inert inputs is what makes the ship/kill decision
auditable and unit-testable with hand-built fixtures.

Precedence (highest to lowest; the first matching branch wins). Each branch is
recorded in ``reasons`` so the verdict is self-explaining:

1. ``not instrument_trusted``                    -> DO_NOT_SHIP
2. ``not a3b_fails_grammaticality``              -> DO_NOT_SHIP
3. buildability/grammaticality not certifiable   -> UNDERPOWERED
4. any hard block (substance / restatement /     -> DO_NOT_SHIP
   non-inferiority)
5. ``a4_captures_effect``                         -> SHIP_EVALUATOR_ONLY
6. ``not beats_a3_fair.beats``                    -> SHIP_ONELINER
7. beats A3_fair but not A2_placebo               -> DO_NOT_SHIP
8. else (beats both)                              -> SHIP_TREATMENT
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .stats import TostResult


class Verdict(str, Enum):
    """The terminal ship/kill outcomes of the benchmark."""

    SHIP_TREATMENT = "ship_treatment"            # (1)(2) ship
    SHIP_ONELINER = "ship_oneliner"              # A3_fair matches A1 -> ship the one-liner
    SHIP_EVALUATOR_ONLY = "ship_evaluator_only"  # A4 shows (2) alone captures the effect
    DO_NOT_SHIP = "do_not_ship"
    UNDERPOWERED = "underpowered_no_ship"        # guardrail safety not certifiable


@dataclass(frozen=True)
class ArmComparison:
    """Whether A1 beats a comparison arm on the executable + extractor axes."""

    beats: bool          # does A1 beat this arm on the executable + extractor axes?
    detail: str = ""


@dataclass(frozen=True)
class DecisionInputs:
    """Everything ``decide`` needs, already computed by the orchestrator."""

    restatement_real: bool          # restatement fell AND length-falsification did NOT stop
    substance_ok: bool              # zero MUST-tier proposition dropped
    buildability: TostResult        # non-inferiority of downstream buildability
    grammaticality: TostResult      # non-inferiority of grammaticality
    a3b_fails_grammaticality: bool  # positive control: dumb-brevity MUST fail the detector
    instrument_trusted: bool        # instrument-trust gate passed
    beats_a3_fair: ArmComparison    # A1 vs the honest one-liner
    beats_a2_placebo: ArmComparison  # A1 vs the extra-pass placebo
    a4_captures_effect: bool        # (2) alone ~= (1)(2)


@dataclass(frozen=True)
class DecisionResult:
    """The verdict plus the chain of reasons that produced it."""

    verdict: Verdict
    reasons: tuple[str, ...]


def decide(inputs: DecisionInputs) -> DecisionResult:
    """Apply the pre-registered precedence rule. Pure and deterministic.

    The branches are evaluated in the fixed order documented in the module
    docstring; the first satisfied branch determines the verdict. ``reasons``
    explains the chosen branch (and, for hard blocks, every block that fired).
    """
    # 1. Instrument trust gates everything — if the numbers are not readable,
    #    nothing downstream can be believed.
    if not inputs.instrument_trusted:
        return DecisionResult(
            Verdict.DO_NOT_SHIP,
            ("instrument-trust gate failed: arm numbers are not readable",),
        )

    # 2. The grammaticality detector's positive control must fire. If dumb
    #    brevity does NOT fail the detector, its non-inferiority claim below
    #    cannot be trusted.
    if not inputs.a3b_fails_grammaticality:
        return DecisionResult(
            Verdict.DO_NOT_SHIP,
            (
                "grammaticality detector unproven: A3b_dumb_brevity did not fail "
                "the detector (positive control)",
            ),
        )

    # 3. Safety must be CERTIFIABLE — an underpowered guardrail is never
    #    reported as "safe"; it is reported as underpowered.
    if not inputs.buildability.certifiable or not inputs.grammaticality.certifiable:
        reasons: list[str] = []
        if not inputs.buildability.certifiable:
            reasons.append(
                f"buildability non-inferiority underpowered "
                f"(power={inputs.buildability.power:.3f})"
            )
        if not inputs.grammaticality.certifiable:
            reasons.append(
                f"grammaticality non-inferiority underpowered "
                f"(power={inputs.grammaticality.power:.3f})"
            )
        return DecisionResult(Verdict.UNDERPOWERED, tuple(reasons))

    # 4. Hard blocks — substance loss, an unreal restatement effect, or a
    #    failed (but powered) non-inferiority test. Collect all that fired.
    blocks: list[str] = []
    if not inputs.substance_ok:
        blocks.append("substance guardrail blocked: a MUST-tier proposition was dropped")
    if not inputs.restatement_real:
        blocks.append(
            "restatement effect not real: it did not fall or length-falsification stopped"
        )
    if not inputs.buildability.non_inferior:
        blocks.append("buildability non-inferiority test failed")
    if not inputs.grammaticality.non_inferior:
        blocks.append("grammaticality non-inferiority test failed")
    if blocks:
        return DecisionResult(Verdict.DO_NOT_SHIP, tuple(blocks))

    # 5. If change (2) (the evaluator pass) alone reproduces the (1)(2) effect,
    #    ship the evaluator only.
    if inputs.a4_captures_effect:
        return DecisionResult(
            Verdict.SHIP_EVALUATOR_ONLY,
            ("A4 shows the evaluator pass alone captures the effect",),
        )

    # 6. If A1 does not beat the honest one-liner, the one-liner is what to ship.
    if not inputs.beats_a3_fair.beats:
        detail = inputs.beats_a3_fair.detail or "A1 does not beat A3_fair"
        return DecisionResult(
            Verdict.SHIP_ONELINER,
            (f"the honest one-liner matches A1: {detail}",),
        )

    # 7. A1 beats the one-liner but not the extra-pass placebo: the gain was
    #    just one more editing pass, not the treatment.
    if not inputs.beats_a2_placebo.beats:
        detail = inputs.beats_a2_placebo.detail or "A1 does not beat A2_placebo"
        return DecisionResult(
            Verdict.DO_NOT_SHIP,
            (f"the gain was just one more editing pass: {detail}",),
        )

    # 8. A1 beats both comparison arms and clears every gate — ship the treatment.
    return DecisionResult(
        Verdict.SHIP_TREATMENT,
        (
            "A1 beats A3_fair and A2_placebo, restatement is real, substance and "
            "safety guardrails certifiably pass",
        ),
    )

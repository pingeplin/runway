"""Branch-complete tests for the pre-registered ship/kill rule.

Each test drives ``decide`` to exactly one of the eight precedence branches and
asserts the verdict, plus the precedence ordering itself (a higher branch wins
even when everything below it is perfect).
"""

from __future__ import annotations

from dataclasses import replace

from eval_overexplanation.decision import (
    ArmComparison,
    DecisionInputs,
    Verdict,
    decide,
)
from eval_overexplanation.stats import TostResult


def _tost(*, non_inferior: bool = True, certifiable: bool = True,
          power: float = 0.9) -> TostResult:
    return TostResult(
        non_inferior=non_inferior,
        p_value=0.01,
        power=power,
        certifiable=certifiable,
    )


def _perfect_ship() -> DecisionInputs:
    """An all-green input that lands on SHIP_TREATMENT (branch 8)."""
    return DecisionInputs(
        restatement_real=True,
        substance_ok=True,
        buildability=_tost(),
        grammaticality=_tost(),
        a3b_fails_grammaticality=True,
        instrument_trusted=True,
        beats_a3_fair=ArmComparison(beats=True),
        beats_a2_placebo=ArmComparison(beats=True),
        a4_captures_effect=False,
    )


# --------------------------------------------------------------------------- #
# Each branch reached directly
# --------------------------------------------------------------------------- #


def test_branch1_untrusted_instrument_blocks_even_when_perfect():
    # Precedence: an untrusted instrument yields DO_NOT_SHIP even though every
    # other field is perfect.
    inputs = replace(_perfect_ship(), instrument_trusted=False)
    result = decide(inputs)
    assert result.verdict is Verdict.DO_NOT_SHIP
    assert any("instrument" in r for r in result.reasons)


def test_branch2_a3b_must_fail_grammaticality():
    inputs = replace(_perfect_ship(), a3b_fails_grammaticality=False)
    result = decide(inputs)
    assert result.verdict is Verdict.DO_NOT_SHIP
    assert any("positive control" in r for r in result.reasons)


def test_branch3_underpowered_buildability():
    inputs = replace(
        _perfect_ship(),
        buildability=_tost(certifiable=False, power=0.4),
    )
    result = decide(inputs)
    assert result.verdict is Verdict.UNDERPOWERED
    assert any("buildability" in r for r in result.reasons)


def test_branch3_underpowered_grammaticality():
    inputs = replace(
        _perfect_ship(),
        grammaticality=_tost(certifiable=False, power=0.3),
    )
    result = decide(inputs)
    assert result.verdict is Verdict.UNDERPOWERED
    assert any("grammaticality" in r for r in result.reasons)


def test_branch3_underpowered_beats_do_not_ship_when_substance_fails():
    # Precedence: an underpowered guardrail yields UNDERPOWERED, not DO_NOT_SHIP,
    # even when a hard block (substance) is simultaneously present.
    inputs = replace(
        _perfect_ship(),
        substance_ok=False,
        buildability=_tost(certifiable=False, power=0.5),
    )
    result = decide(inputs)
    assert result.verdict is Verdict.UNDERPOWERED


def test_branch4_substance_block():
    inputs = replace(_perfect_ship(), substance_ok=False)
    result = decide(inputs)
    assert result.verdict is Verdict.DO_NOT_SHIP
    assert any("MUST-tier" in r for r in result.reasons)


def test_branch4_restatement_not_real_block():
    inputs = replace(_perfect_ship(), restatement_real=False)
    result = decide(inputs)
    assert result.verdict is Verdict.DO_NOT_SHIP
    assert any("restatement" in r for r in result.reasons)


def test_branch4_buildability_non_inferiority_block():
    inputs = replace(
        _perfect_ship(),
        buildability=_tost(non_inferior=False),
    )
    result = decide(inputs)
    assert result.verdict is Verdict.DO_NOT_SHIP
    assert any("buildability" in r for r in result.reasons)


def test_branch4_grammaticality_non_inferiority_block():
    inputs = replace(
        _perfect_ship(),
        grammaticality=_tost(non_inferior=False),
    )
    result = decide(inputs)
    assert result.verdict is Verdict.DO_NOT_SHIP
    assert any("grammaticality" in r for r in result.reasons)


def test_branch4_collects_all_blocks():
    inputs = replace(
        _perfect_ship(),
        substance_ok=False,
        restatement_real=False,
    )
    result = decide(inputs)
    assert result.verdict is Verdict.DO_NOT_SHIP
    # Both hard blocks are reported, not just the first.
    assert len(result.reasons) == 2


def test_branch5_a4_captures_effect():
    inputs = replace(_perfect_ship(), a4_captures_effect=True)
    result = decide(inputs)
    assert result.verdict is Verdict.SHIP_EVALUATOR_ONLY
    assert any("evaluator pass alone" in r for r in result.reasons)


def test_branch6_ship_oneliner_when_a1_does_not_beat_a3_fair():
    inputs = replace(
        _perfect_ship(),
        beats_a3_fair=ArmComparison(beats=False, detail="A3_fair tied A1"),
    )
    result = decide(inputs)
    assert result.verdict is Verdict.SHIP_ONELINER
    assert any("A3_fair tied A1" in r for r in result.reasons)


def test_branch7_beats_a3_fair_but_not_a2_placebo():
    # Precedence/scenario: beats A3_fair but not A2_placebo yields DO_NOT_SHIP
    # ("the gain was just one more editing pass").
    inputs = replace(
        _perfect_ship(),
        beats_a3_fair=ArmComparison(beats=True),
        beats_a2_placebo=ArmComparison(beats=False, detail="placebo matched A1"),
    )
    result = decide(inputs)
    assert result.verdict is Verdict.DO_NOT_SHIP
    assert any("editing pass" in r for r in result.reasons)


def test_branch8_ship_treatment():
    result = decide(_perfect_ship())
    assert result.verdict is Verdict.SHIP_TREATMENT
    assert result.reasons  # self-explaining


# --------------------------------------------------------------------------- #
# Precedence ordering: higher branch beats lower
# --------------------------------------------------------------------------- #


def test_instrument_outranks_a3b_control():
    inputs = replace(
        _perfect_ship(),
        instrument_trusted=False,
        a3b_fails_grammaticality=False,
    )
    assert any("instrument" in r for r in decide(inputs).reasons)


def test_a3b_control_outranks_underpowered():
    inputs = replace(
        _perfect_ship(),
        a3b_fails_grammaticality=False,
        buildability=_tost(certifiable=False, power=0.2),
    )
    # A3b control (branch 2) wins over underpowered (branch 3).
    assert decide(inputs).verdict is Verdict.DO_NOT_SHIP
    assert any("positive control" in r for r in decide(inputs).reasons)


def test_a4_outranks_a3_fair_and_a2_placebo():
    # branch 5 wins even though A1 fails to beat both comparison arms.
    inputs = replace(
        _perfect_ship(),
        a4_captures_effect=True,
        beats_a3_fair=ArmComparison(beats=False),
        beats_a2_placebo=ArmComparison(beats=False),
    )
    assert decide(inputs).verdict is Verdict.SHIP_EVALUATOR_ONLY


def test_a3_fair_outranks_a2_placebo():
    # branch 6 (ship one-liner) wins over branch 7 when A1 beats neither arm.
    inputs = replace(
        _perfect_ship(),
        beats_a3_fair=ArmComparison(beats=False),
        beats_a2_placebo=ArmComparison(beats=False),
    )
    assert decide(inputs).verdict is Verdict.SHIP_ONELINER

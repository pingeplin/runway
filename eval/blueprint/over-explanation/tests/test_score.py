"""Tests for the pure §2 scorer: subscores, gates, precedence, serialization.

Fixtures are hand-built inert inputs (no stats, no I/O, no network). The
all-green fixture lands on SHIP_TREATMENT; each test mutates exactly what it
probes via ``dataclasses.replace``. Hand-computed arithmetic anchors:

  S_C: nf_C=0.01 -> T_C=max(0.05, 4*0.01)=0.05, den=max(0.04, 0.02)=0.04;
       C1 mean_delta=-0.03 -> (0.03-0.01)/0.04 = 0.5 -> 50.0
  S_U: nf_U=0.02 -> T_U=max(0.1054, 0.04)=0.1054, den=max(0.0854, 0.05);
       mean_dU1=-0.1054 -> ratio 1.0 -> 100.0
  S_O: 100*(0.50*0.9 + 0.30*0.8 + 0.20*1.0) = 89.0   (bloat_ln=0, kill=0.8
       read from gate_values.o3_kill_rate — the O3 gate's own field)
  composite = 0.3*50 + 0.3*100 + 0.4*89 = 80.6
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from eval_overexplanation.decision import Verdict
from eval_overexplanation.score import (
    ArmInputs,
    Budget,
    C1Stats,
    CellCounts,
    GateValues,
    MetricValue,
    ScoreInputs,
    ScoreThresholds,
    Stops,
    TostStats,
    U1Stats,
    c1_failures,
    composite,
    evaluate_gates,
    exit_code,
    outcome_subscore,
    render_score_json,
    score_report,
    subscore_linear,
    tost_certifiable,
    tost_non_inferior,
    u1_failures,
)

# --------------------------------------------------------------------------- #
# Fixture builders
# --------------------------------------------------------------------------- #

TOST_MARGINS = {"C3": 0.05, "C8": 0.02, "U2": 1.0, "U3": 1.0,
                "O1": 0.05, "O3": 0.10}
FULL_STRATA = {
    dim: {"elicit_prone": 3, "large_realistic": 3, "neutral": 3}
    for dim in ("C", "U", "O")
}


def _tost_ok(family: str) -> TostStats:
    """In-band 90% CI, well-powered: non-inferior AND certifiable."""
    m = TOST_MARGINS[family]
    return TostStats(estimate=0.0, ci90=(-m / 4, m / 4), p_value=0.01,
                     achieved_power=0.9, margin=m)


def _tost_inferior(family: str) -> TostStats:
    """CI breaching the band, well-powered: a SUBSTANTIVE inferiority."""
    m = TOST_MARGINS[family]
    return TostStats(estimate=m, ci90=(m / 2, 2 * m), p_value=0.6,
                     achieved_power=0.9, margin=m)


def _tost_underpowered(family: str) -> TostStats:
    """In-band CI, low achieved power: a POWER gap, never a row-6 failure."""
    m = TOST_MARGINS[family]
    return TostStats(estimate=0.0, ci90=(-m / 4, m / 4), p_value=0.04,
                     achieved_power=0.5, margin=m)


def _all_tost(**over: TostStats) -> dict[str, TostStats]:
    base = {family: _tost_ok(family) for family in TOST_MARGINS}
    base.update(over)
    return base


def _green_gates(**over: object) -> GateValues:
    base = GateValues(
        c0_leak_hits=0,
        c2_dropped_must=0,
        c7_merge_failures=0,
        c8_frag_rate=0.03,
        u0_prompt_sha_ok=True,
        u0_leak_hits=0,
        u3_max_dead_ends=2,
        u4_completion_fraction=1.0,
        u5_clarifying_questions=0,
        o1_correctness=0.95,
        o1_regressed_cells=(),
        o2_overfit=0.04,
        o3_kill_rate=0.8,
        o3_invalid=0,
        o4_workarounds=0,
        l1_code_frac=0.10,
        l2_reference_containment=0.10,
        l3_copy_containment=0.10,
        l4_spec_only_correctness=0.0,
    )
    return replace(base, **over)


def _c1(**over: object) -> C1Stats:
    # Green against nf_C=0.01 with the 2.0 gate multiple: -0.03 <= -0.02.
    base = C1Stats(
        mean_delta=-0.03,
        ci=(-0.05, -0.01),
        p_holm=0.024,
        sign_stable=True,
        large_realistic_delta=-0.02,
    )
    return replace(base, **over)


def _cells() -> dict[str, CellCounts]:
    return {
        "generate": CellCounts(expected=18, complete=18),
        "implement": CellCounts(expected=12, complete=12),
    }


def _u1(**over: object) -> U1Stats:
    # Green against nf_U=0.02: T_U = max(0.1054, 0.04) = 0.1054.
    base = U1Stats(mean_delta=-0.1054, p_holm=0.02)
    return replace(base, **over)


def _arm(**over: object) -> ArmInputs:
    base = ArmInputs(
        arm_id="A1",
        cells=_cells(),
        gate_values=_green_gates(),
        tost=_all_tost(),
        c1=_c1(),
        u1=_u1(),
        correctness_holdout=0.9,
        bloat_ln=0.0,
    )
    return replace(base, **over)


def _inputs(**over: object) -> ScoreInputs:
    base = ScoreInputs(
        manifest_content_hash="sha256:abc",
        manifest_hash_matches=True,
        manifest_problems=(),
        generated_at="2026-08-13T00:00:00Z",
        instrument_trusted=True,
        benchmark_trusted=True,
        a3b_fails_grammaticality=True,
        stops=Stops(),
        noise_floor_c=0.01,
        noise_floor_u=0.02,
        n_briefs=9,
        n_buildable=6,
        k_seeds=2,
        extractor_families=("anthropic-claude", "openai-gpt"),
        strata_coverage=FULL_STRATA,
        baseline_arm="A0",
        treatment_arm="A1",
        arms=(_arm(),),
        budget=Budget(spent_usd=41.2, projected_usd=68.9, max_usd=120.0,
                      exhausted=False),
        a4_captures_effect=False,
        beats_a3_fair=True,
        beats_a2_placebo=True,
    )
    return replace(base, **over)


def report_arm(inputs):
    return score_report(inputs).arms[0]


def _dim(report_or_arm, name):
    arm = report_or_arm.arms[0] if hasattr(report_or_arm, "arms") else report_or_arm
    return {d.name: d for d in arm.dimensions}[name]


# --------------------------------------------------------------------------- #
# subscore_linear
# --------------------------------------------------------------------------- #


def test_subscore_linear_midpoint():
    assert subscore_linear(0.03, 0.01, 0.05, min_den=0.02) == pytest.approx(50.0)


def test_subscore_linear_zero_at_noise_floor():
    assert subscore_linear(0.01, 0.01, 0.05, min_den=0.02) == 0.0


def test_subscore_linear_clips_below_noise_floor():
    assert subscore_linear(-0.5, 0.01, 0.05, min_den=0.02) == 0.0


def test_subscore_linear_clips_at_100():
    assert subscore_linear(9.0, 0.01, 0.05, min_den=0.02) == 100.0


def test_subscore_linear_knife_edge_min_den():
    # target - noise_floor = 0.005 < min_den 0.02: the floor bounds the slope
    # (without it the ratio would be 2.0 and clip to 100).
    got = subscore_linear(0.015, 0.005, 0.01, min_den=0.02)
    assert got == pytest.approx(100.0 * (0.015 - 0.005) / 0.02)


# --------------------------------------------------------------------------- #
# outcome_subscore — missing-signal rule, monotone and fail-closed
# --------------------------------------------------------------------------- #


def test_outcome_subscore_full_terms():
    assert outcome_subscore(0.9, 0.8, 0.0) == pytest.approx(89.0)


def test_outcome_subscore_bloat_over_cap_scores_zero_term():
    # bloat_ln = cap -> term 0; 100*(0.45 + 0.24 + 0)
    assert outcome_subscore(0.9, 0.8, 1.0986) == pytest.approx(69.0)


def test_outcome_subscore_negative_bloat_is_not_a_bonus():
    # ln < 0 (smaller than reference): max(0, .) keeps the term at exactly 1.
    assert outcome_subscore(0.9, 0.8, -2.0) == pytest.approx(89.0)


def test_outcome_subscore_unaccounted_missing_kill_keeps_original_weight():
    # A missing term scores 0 within its ORIGINAL weight — no renormalization:
    # 100*(0.50*0.9 + 0 + 0.20*1.0) / 1.0 = 65.0.
    assert outcome_subscore(0.9, None, 0.0) == pytest.approx(65.0)


def test_outcome_subscore_missing_kill_never_beats_present_kill():
    # Regression (review finding): the old renormalization made
    # (0.90, None, 0.11) -> 90.0 while (0.90, 0.78, 0.11) -> 86.4, so dropping
    # a weak term RAISED the score. Now missing <= present for every kill.
    missing = outcome_subscore(0.90, None, 0.11)
    for kill in (0.0, 0.2, 0.78, 1.0):
        assert missing <= outcome_subscore(0.90, kill, 0.11)
    assert missing < outcome_subscore(0.90, 0.78, 0.11)


def test_outcome_subscore_uniform_rule_no_renormalization_path():
    # Regression (round-2 MINOR): the old accounted-skip renormalization made
    # (1.0, None-dropped, 0.0) -> 100.0 while (1.0, 0.0-measured, 0.0) -> 70.0
    # — dropping the kill term beat measuring it at zero. The rule is now
    # uniform: a missing kill ALWAYS scores 0 in its original weight.
    missing = outcome_subscore(1.0, None, 0.0)
    assert missing == pytest.approx(70.0)
    assert missing == outcome_subscore(1.0, 0.0, 0.0)  # never above measured-at-0
    for kill in (0.0, 0.2, 0.78, 1.0):
        assert missing <= outcome_subscore(1.0, kill, 0.0)


def test_outcome_subscore_missing_correctness_keeps_original_weight():
    assert outcome_subscore(None, 0.8, 0.0) == pytest.approx(
        100.0 * (0.30 * 0.8 + 0.20 * 1.0))


def test_outcome_subscore_bloat_alone_never_carries_the_dimension():
    # Regression (review finding): (None, None, 0.0) used to return 100.0.
    assert outcome_subscore(None, None, 0.0) == 0.0
    assert outcome_subscore(None, None, 1.0986) == 0.0


def test_outcome_subscore_all_missing_is_zero_fail_closed():
    assert outcome_subscore(None, None, None) == 0.0


def test_outcome_subscore_weight_override():
    got = outcome_subscore(1.0, 0.0, 0.0, correctness_weight=1.0,
                           kill_weight=0.0, bloat_weight=0.0)
    assert got == pytest.approx(100.0)


# --------------------------------------------------------------------------- #
# composite
# --------------------------------------------------------------------------- #


def test_composite_weighted_sum():
    got = composite({"C": 50.0, "U": 100.0, "O": 89.0},
                    {"C": 0.30, "U": 0.30, "O": 0.40})
    assert got == pytest.approx(80.6)


def test_composite_refuses_partial():
    with pytest.raises(ValueError, match="partial composite"):
        composite({"C": 50.0, "U": 100.0}, {"C": 0.30, "U": 0.30, "O": 0.40})


def test_composite_custom_weights():
    got = composite({"C": 100.0, "U": 0.0, "O": 0.0}, {"C": 1.0, "U": 0.0, "O": 0.0})
    assert got == pytest.approx(100.0)


# --------------------------------------------------------------------------- #
# Gates: all green, then each hard gate fails => run FAILs (short-circuit)
# --------------------------------------------------------------------------- #


def test_all_green_gates_pass():
    gates = evaluate_gates(_inputs())
    assert gates and all(g.passed for g in gates)
    assert "O3_mutation_kill" in [g.id for g in gates]


HARD_GATE_CASES = [
    ({"c0_leak_hits": 2}, "C0_generate_isolation"),  # C-stage U0 analogue
    ({"c0_leak_hits": None}, "C0_generate_isolation"),  # unscanned => no signal
    ({"c2_dropped_must": 1}, "C2_must_retention"),
    ({"c7_merge_failures": 2}, "C7_merge_fidelity"),
    ({"c8_frag_rate": 0.20}, "C8_grammaticality"),
    ({"u0_prompt_sha_ok": False}, "U0_isolation"),
    ({"u0_leak_hits": 3}, "U0_isolation"),
    ({"u3_max_dead_ends": 7}, "U3_dead_end_cap"),
    ({"u4_completion_fraction": 0.9}, "U4_completion"),
    ({"u5_clarifying_questions": 1}, "U5_clarifying_questions"),
    ({"o1_correctness": 0.5}, "O1_correctness"),
    ({"o1_regressed_cells": ("b02/seed-1",)}, "O1_correctness"),
    ({"o1_correctness": None}, "O1_correctness"),  # no signal => fail-closed
    ({"o2_overfit": 0.20}, "O2_holdout_overfit"),
    ({"o2_overfit": None}, "O2_holdout_overfit"),  # no signal, no accounted skip
    ({"o3_kill_rate": 0.2}, "O3_mutation_kill"),   # below o3_min_kill_rate
    ({"o3_kill_rate": 0.74}, "O3_mutation_kill"),  # just under the 0.75 gate
    ({"o3_invalid": 1}, "O3_mutation_kill"),       # invalid mutants must be 0
    ({"o3_kill_rate": None}, "O3_mutation_kill"),  # no signal, no accounted skip
    ({"o4_workarounds": 2}, "O4_workaround_lint"),
]


@pytest.mark.parametrize("over,gate_id", HARD_GATE_CASES)
def test_any_hard_gate_failure_blocks_the_run(over, gate_id):
    inputs = _inputs(arms=(_arm(gate_values=_green_gates(**over)),))
    report = score_report(inputs)
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any(gate_id in r for r in report.verdict_reasons)
    assert report.arms[0].gates_blocked
    assert gate_id in report.arms[0].gates_failed
    assert exit_code(report) == 1


TOST_GATE_CASES = [
    ("C3", "C3_coverage_noninferiority"),
    ("C8", "C8_grammaticality"),
    ("U2", "U2_turns_noninferiority"),
    ("U3", "U3_deadend_noninferiority"),
    ("O1", "O1_correctness"),
    ("O3", "O3_mutation_kill"),
]


@pytest.mark.parametrize("family,gate_id", TOST_GATE_CASES)
def test_recomputed_inferior_tost_fails_its_gate(family, gate_id):
    # Regression (round-4 MAJOR): the six *_non_inferior legs were the last
    # collapsed caller booleans. The gate leg is now RECOMPUTED from the raw
    # TostStats (90% CI vs the manifest margin band) — an out-of-band CI is a
    # substantive row-6 failure regardless of what any packer boolean said.
    tost = _all_tost(**{family: _tost_inferior(family)})
    report = score_report(_inputs(arms=(_arm(tost=tost),)))
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert gate_id in report.arms[0].gates_failed
    assert exit_code(report) == 1


@pytest.mark.parametrize("family,gate_id", TOST_GATE_CASES)
def test_absent_tost_family_fails_its_gate_fail_closed(family, gate_id):
    # No packed TOST stats for a family = no signal: the non-inferiority leg
    # FAILS its gate (row 6) and the family is not certifiable — never a
    # silent pass in either leg.
    tost = {f: _tost_ok(f) for f in TOST_MARGINS if f != family}
    report = score_report(_inputs(arms=(_arm(tost=tost),)))
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert gate_id in report.arms[0].gates_failed


def test_tost_non_inferior_recompute_semantics():
    ok = _tost_ok("C3")
    assert tost_non_inferior(ok, 0.05) is True
    assert tost_non_inferior(None, 0.05) is False        # no signal, no pass
    boundary = replace(ok, ci90=(-0.05, 0.05))
    assert tost_non_inferior(boundary, 0.05) is False    # strictly inside
    assert tost_non_inferior(ok, 0.0) is False           # missing margin


def test_tost_certifiable_recompute_semantics():
    assert tost_certifiable(_tost_ok("C3"), 0.8) is True
    assert tost_certifiable(_tost_ok("C3"), 0.9) is True   # power == min: pass
    assert tost_certifiable(_tost_underpowered("C3"), 0.8) is False
    assert tost_certifiable(None, 0.0) is False           # no signal


def test_manifest_tost_margins_drive_the_recompute():
    # The §4 tost_margins field is LIVE: the same raw CI flips the C3 gate
    # when the registered margin tightens below the CI half-width.
    tost = _all_tost(C3=replace(_tost_ok("C3"), ci90=(-0.03, 0.03)))
    assert score_report(
        _inputs(arms=(_arm(tost=tost),))).verdict is Verdict.SHIP_TREATMENT
    tight = dict(TOST_MARGINS, C3=0.02)
    tight_thresholds = ScoreThresholds(tost_margins=tight)
    # The packed margin field is a transport cross-check (CLI), not read here.
    report = score_report(_inputs(arms=(_arm(tost=tost),),
                                  thresholds=tight_thresholds))
    assert "C3_coverage_noninferiority" in report.arms[0].gates_failed


def test_manifest_min_power_drives_certifiability():
    # The §4 min_power field is LIVE: raising it past the achieved power
    # routes the same raw stats to row 8 UNDERPOWERED.
    strict = ScoreThresholds(min_power=0.95)
    report = score_report(_inputs(thresholds=strict))
    assert report.verdict is Verdict.UNDERPOWERED
    assert any("certifiable" in r for r in report.verdict_reasons)


def test_o2_none_within_cap_fails_closed_mirroring_o3():
    # Regression (round-2 BLOCKER): o2_overfit=None with o2_skipped_fraction
    # at the 0.0 default used to emit NO gate — the O3 asymmetry. Now it FAILS.
    inputs = _inputs(arms=(_arm(gate_values=_green_gates(o2_overfit=None)),))
    report = score_report(inputs)
    arm = report.arms[0]
    assert "O2_holdout_overfit" in arm.gates_failed
    assert arm.gates_blocked
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert exit_code(report) == 1


def test_o2_none_over_cap_is_underpowered_not_gate_failed():
    # Over the skip cap the whole O2 term legitimately has no signal: the gate
    # is omitted (skipped, never a pass) and row 9 forces UNDERPOWERED.
    inputs = _inputs(arms=(
        _arm(gate_values=_green_gates(o2_overfit=None),
             correctness_holdout=None, o2_skipped_fraction=1.0),))
    report = score_report(inputs)
    arm = report.arms[0]
    assert "O2_holdout_overfit" not in [g.id for g in arm.gates]
    assert not arm.gates_blocked
    assert report.verdict is Verdict.UNDERPOWERED
    assert exit_code(report) == 1


def test_reproduced_blocker_o2_not_fail_closed():
    # Exact reproduction from the round-2 review: o2_overfit=None +
    # correctness_holdout=None + o2_skipped_fraction defaulted 0.0 used to
    # yield SHIP exit 0 with S_O silently substituting VISIBLE-case
    # o1_correctness at O2's full 0.50 weight. Now: gate FAILS, no
    # substitution — the correctness term scores 0 in its original weight.
    inputs = _inputs(arms=(
        _arm(gate_values=_green_gates(o2_overfit=None),
             correctness_holdout=None),))
    report = score_report(inputs)
    arm = report.arms[0]
    assert "O2_holdout_overfit" in arm.gates_failed
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert exit_code(report) == 1
    # S_O = 100*(0 + 0.30*0.8 + 0.20*1.0) = 44.0 — not 0.50*0.95 + ...
    assert _dim(arm, "O").subscore == pytest.approx(44.0)
    obj = json.loads(render_score_json(report))
    dims = obj["arms"]["A1"]["dimensions"]
    assert dims["O"]["correctness_holdout_missing"] is True


def test_c0_none_gate_entry_is_fail_closed_with_detail():
    # Regression (round-3 MAJOR): leak_scanned:false used to pack as 0 and
    # pass C0 green. None is a no-signal state that FAILS the gate.
    gates = evaluate_gates(_inputs(arms=(
        _arm(gate_values=_green_gates(c0_leak_hits=None)),)))
    c0 = {g.id: g for g in gates}["C0_generate_isolation"]
    assert c0.passed is False
    assert "no C0 signal" in c0.detail


def test_c8_power_gap_routes_to_row8_underpowered_not_row6():
    # Regression (round-3 MAJOR): the conflated c8_tost_ok routed a C8 POWER
    # gap (non-inferior but not certifiable) to row 6 DO_NOT_SHIP. The two
    # legs are recomputed separately from the raw stats: an in-band CI with
    # low achieved power passes the gate and routes to row 8.
    report = score_report(_inputs(arms=(
        _arm(tost=_all_tost(C8=_tost_underpowered("C8"))),)))
    arm = report.arms[0]
    assert "C8_grammaticality" not in arm.gates_failed
    assert not arm.gates_blocked
    assert report.verdict is Verdict.UNDERPOWERED
    assert any("C8" in r and "certifiable" in r for r in report.verdict_reasons)
    assert exit_code(report) == 1


def test_l4_none_emits_no_gate_l1_to_l3_carry_it():
    inputs = _inputs(
        arms=(_arm(gate_values=_green_gates(l4_spec_only_correctness=None)),))
    report = score_report(inputs)
    gate_ids = [g.id for g in report.arms[0].gates]
    assert "L4_spec_only_correctness" not in gate_ids
    assert not report.arms[0].leakage_voided
    # Regression (round-6 MAJOR): a null l4_spec_only_correctness used to
    # leave ZERO trace in score.json (no GateCheck, no flag) even though
    # §1-L4 mandates "no signal (null, FLAGGED)". l4_no_signal is that
    # greppable trace, rendered in the FINAL score.json regardless of the
    # gate's silence.
    assert report.arms[0].l4_no_signal is True
    obj = json.loads(render_score_json(report))
    assert obj["arms"]["A1"]["l4_no_signal"] is True


def test_l4_present_never_flags_no_signal():
    inputs = _inputs(
        arms=(_arm(gate_values=_green_gates(l4_spec_only_correctness=0.1)),))
    report = score_report(inputs)
    assert report.arms[0].l4_no_signal is False
    obj = json.loads(render_score_json(report))
    assert obj["arms"]["A1"]["l4_no_signal"] is False


# --------------------------------------------------------------------------- #
# O3 fail-closed coupling: kill_rate=None vs o3_skipped_fraction
# --------------------------------------------------------------------------- #


def test_unaccounted_missing_kill_scores_original_weight_and_fails_o3():
    # kill_rate=None with o3_skipped_fraction=0.0: fail-closed. The O3 gate
    # FAILS (breaking the smoke is a controllable act) and S_O keeps the kill
    # term's original weight at 0: 100*(0.50*0.9 + 0.20*1.0) = 65.0.
    gates = _green_gates(o3_kill_rate=None)
    report = score_report(_inputs(arms=(_arm(gate_values=gates),)))
    arm = report.arms[0]
    assert _dim(arm, "O").subscore == pytest.approx(65.0)
    assert _dim(arm, "O").renormalized is False
    assert "O3_mutation_kill" in arm.gates_failed
    assert arm.gates_blocked
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert exit_code(report) == 1


def test_unaccounted_missing_kill_never_scores_higher_than_present():
    gates_missing = _green_gates(o3_kill_rate=None)
    missing = score_report(_inputs(arms=(_arm(gate_values=gates_missing),)))
    o_missing = _dim(missing.arms[0], "O").subscore
    for kill in (0.0, 0.2, 0.78, 1.0):
        present = score_report(_inputs(arms=(
            _arm(gate_values=_green_gates(o3_kill_rate=kill)),)))
        assert o_missing <= _dim(present.arms[0], "O").subscore


def test_within_cap_missing_kill_still_fails_o3_gate():
    # At or under the skip cap an aggregate kill rate must exist; its absence
    # is inconsistent and FAILS the gate — never a skip, never renormalized
    # into a win.
    gates = _green_gates(o3_kill_rate=None)
    report = score_report(_inputs(arms=(
        _arm(gate_values=gates, o3_skipped_fraction=0.083),)))
    assert "O3_mutation_kill" in report.arms[0].gates_failed
    # Regression (round-3 MINOR): an UNDER-cap missing kill is a gate
    # failure, never described as a renormalizing accounted skip.
    assert _dim(report.arms[0], "O").renormalized is False
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert exit_code(report) == 1


def test_over_cap_missing_kill_is_underpowered_not_gate_failed():
    # Over the cap the whole O3 term legitimately has no signal: the gate is
    # omitted (skipped, never a pass) and row 9 forces UNDERPOWERED. The
    # subscore still keeps the kill term's ORIGINAL weight at 0 (uniform
    # monotone rule — no renormalization); `renormalized` is descriptive only.
    gates = _green_gates(o3_kill_rate=None)
    report = score_report(_inputs(arms=(
        _arm(gate_values=gates, o3_skipped_fraction=1.0),)))
    arm = report.arms[0]
    assert "O3_mutation_kill" not in [g.id for g in arm.gates]
    assert not arm.gates_blocked
    assert report.verdict is Verdict.UNDERPOWERED
    assert _dim(arm, "O").renormalized is True
    assert _dim(arm, "O").subscore == pytest.approx(65.0)
    assert exit_code(report) == 1


def test_renormalized_true_under_leakage_void_when_overcap_skip_dropped_kill():
    # Regression (round-3 MINOR): leakage_voided used to force the flag False
    # even when the kill term genuinely had no signal via an accounted
    # over-cap skip. The flag has ONE meaning and is independent of voiding.
    gates = _green_gates(o3_kill_rate=None, l1_code_frac=0.90)
    report = score_report(_inputs(arms=(
        _arm(gate_values=gates, o3_skipped_fraction=1.0),)))
    arm = report.arms[0]
    assert arm.leakage_voided
    assert _dim(arm, "O").renormalized is True
    assert _dim(arm, "O").subscore == 0.0  # voided regardless


def test_accounted_skip_subscore_never_beats_measured_kill():
    # Regression (round-2 MINOR) through _score_arm: the renormalized path
    # used to hand the dropped-kill arm a HIGHER S_O than the same arm with
    # kill measured at any value below ~0.93.
    gates = _green_gates(o3_kill_rate=None)
    dropped = score_report(_inputs(arms=(
        _arm(gate_values=gates, o3_skipped_fraction=1.0),)))
    o_dropped = _dim(dropped.arms[0], "O").subscore
    for kill in (0.0, 0.2, 0.78, 1.0):
        measured = score_report(_inputs(arms=(
            _arm(gate_values=_green_gates(o3_kill_rate=kill)),)))
        assert o_dropped <= _dim(measured.arms[0], "O").subscore


# --------------------------------------------------------------------------- #
# Leakage voids the arm's U and O subscores AND blocks the run (§2 row 7)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("over,gate_id", [
    ({"l1_code_frac": 0.90}, "L1_code_fraction"),
    ({"l2_reference_containment": 0.90}, "L2_reference_containment"),
    ({"l3_copy_containment": 0.90}, "L3_impl_spec_copy"),
    ({"l4_spec_only_correctness": 0.90}, "L4_spec_only_correctness"),
])
def test_leakage_voids_u_and_o_and_blocks_the_run(over, gate_id):
    inputs = _inputs(arms=(_arm(gate_values=_green_gates(**over)),))
    report = score_report(inputs)
    arm = report.arms[0]
    assert arm.leakage_voided
    assert not arm.gates_blocked  # not a §2-row-6 hard gate ...
    assert gate_id in arm.gates_failed
    assert _dim(arm, "U").subscore == 0.0
    assert _dim(arm, "O").subscore == 0.0
    assert _dim(arm, "C").subscore == pytest.approx(50.0)  # C untouched
    assert arm.composite == pytest.approx(0.30 * 50.0)
    # ... but §2 row 7 blocks the run: a detected leak never ships.
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any("leakage" in r and gate_id in r for r in report.verdict_reasons)
    assert exit_code(report) == 1


def test_reproduced_blocker_leaking_arm_never_ships():
    # Exact reproduction from the review: every L gate failed, all else green,
    # used to yield verdict=ship_treatment, exit_code=0.
    gates = _green_gates(l1_code_frac=0.98, l2_reference_containment=1.0,
                         l3_copy_containment=1.0, l4_spec_only_correctness=1.0)
    report = score_report(_inputs(arms=(_arm(gate_values=gates),)))
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert exit_code(report) != 0


def test_row7_leakage_outranks_row8_uncertifiable_tost():
    inputs = _inputs(arms=(
        _arm(gate_values=_green_gates(l1_code_frac=0.90),
             tost=_all_tost(C3=_tost_underpowered("C3"))),))
    report = score_report(inputs)
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any("leakage" in r for r in report.verdict_reasons)


def test_row6_hard_gate_outranks_row7_leakage():
    inputs = _inputs(arms=(
        _arm(gate_values=_green_gates(l1_code_frac=0.90,
                                      u5_clarifying_questions=2)),))
    report = score_report(inputs)
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any("hard gate" in r for r in report.verdict_reasons)


def test_l4_at_cap_boundary_fails():
    # L4 threshold is strict: >= 0.5 means the spec IS the implementation.
    inputs = _inputs(
        arms=(_arm(gate_values=_green_gates(l4_spec_only_correctness=0.5)),))
    assert report_arm(inputs).leakage_voided


# --------------------------------------------------------------------------- #
# Composite arithmetic through _score_arm
# --------------------------------------------------------------------------- #


def test_green_arm_subscores_and_composite():
    report = score_report(_inputs())
    arm = report.arms[0]
    assert _dim(arm, "C").subscore == pytest.approx(50.0)
    assert _dim(arm, "U").subscore == pytest.approx(100.0)
    assert _dim(arm, "O").subscore == pytest.approx(89.0)
    assert arm.composite == pytest.approx(80.6)
    assert report.verdict is Verdict.SHIP_TREATMENT
    assert exit_code(report) == 0


def test_missing_holdout_never_substitutes_visible_correctness():
    # Inverted regression (round-2 BLOCKER; this test used to enshrine the
    # hole): correctness_holdout None must NOT fall back to visible O1 (0.95)
    # — the term scores 0 in its ORIGINAL 0.50 weight and is flagged.
    inputs = _inputs(arms=(_arm(correctness_holdout=None),))
    report = score_report(inputs)
    arm = report.arms[0]
    assert _dim(arm, "O").subscore == pytest.approx(
        100.0 * (0.30 * 0.8 + 0.20 * 1.0))
    assert _dim(arm, "O").correctness_holdout_missing is True
    assert _dim(arm, "O").renormalized is False
    # And the depressed composite (62.6 < 70) blocks the ship on its own.
    assert report.verdict is Verdict.DO_NOT_SHIP


def test_holdout_present_is_not_flagged():
    arm = report_arm(_inputs())
    assert _dim(arm, "O").correctness_holdout_missing is False


# --------------------------------------------------------------------------- #
# C1 win sub-thresholds — recomputed by the scorer (§2 row 10)
# --------------------------------------------------------------------------- #


def test_c1_failures_green_is_empty():
    assert c1_failures(_c1(), 0.01, ScoreThresholds()) == ()


def test_c1_gate_uses_the_gate_multiple_not_the_scale_multiple():
    # mean -0.03 passes the 2.0 gate at nf_C=0.01 (-0.03 <= -0.02) but would
    # fail a 4.0 gate (-0.03 > -0.04): the two multiples must stay distinct.
    assert c1_failures(_c1(), 0.01, ScoreThresholds()) == ()
    assert c1_failures(_c1(), 0.01,
                       ScoreThresholds(c1_gate_noise_multiple=4.0))


def test_c1_gate_floor_denies_free_win_at_degenerate_noise_floor():
    # Regression (round-4 BLOCKER, gate leg): nf_C=0.0 (estimate_noise_floor
    # over empty inputs) used to make the C1 gate -0.0, so ANY negative mean
    # delta cleared it. The absolute c1_gate_floor keeps the bar up:
    # -max(0.025, 2.0*0.0) = -0.025.
    assert any("mean delta" in m
               for m in c1_failures(_c1(mean_delta=-0.01), 0.0,
                                    ScoreThresholds()))
    # A delta past the floor still wins — the floor is a floor, not a wall.
    assert c1_failures(_c1(mean_delta=-0.03), 0.0, ScoreThresholds()) == ()


def test_c1_gate_floor_is_a_live_parameter():
    tight = ScoreThresholds(c1_gate_floor=0.04)
    assert any("mean delta" in m
               for m in c1_failures(_c1(mean_delta=-0.03), 0.01, tight))


def test_duplicate_packed_arm_ids_raise_value_error():
    # Regression (round-4 MAJOR): _treatment_arm took the FIRST match while
    # the rendered arms dict kept the LAST — a self-contradictory score.json
    # with exit 0. Defense in depth: score_report refuses duplicates outright
    # (the CLI load-errors first).
    with pytest.raises(ValueError, match="duplicate packed arm_id"):
        score_report(_inputs(arms=(_arm(), _arm(u1=_u1(mean_delta=0.5)))))


C1_FAIL_CASES = [
    ({"p_holm": 0.08}, "Holm"),
    ({"ci": (-0.05, 0.01)}, "CI upper"),
    ({"ci": (-0.05, 0.0)}, "CI upper"),            # strict: high must be < 0
    ({"mean_delta": -0.015}, "noise floor"),       # inside 2x nf_C
    ({"sign_stable": False}, "sign not stable"),
    ({"large_realistic_delta": 0.01}, "large_realistic"),
]


@pytest.mark.parametrize("over,needle", C1_FAIL_CASES)
def test_row10_each_c1_subthreshold_blocks(over, needle):
    report = score_report(_inputs(arms=(_arm(c1=_c1(**over)),)))
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any("C1 win threshold" in r and needle in r
               for r in report.verdict_reasons)
    assert exit_code(report) == 1


def test_row10_c1_failure_lists_every_missed_leg():
    stats = _c1(p_holm=0.5, ci=(-0.05, 0.01), mean_delta=-0.001,
                sign_stable=False, large_realistic_delta=0.02)
    misses = c1_failures(stats, 0.01, ScoreThresholds())
    assert len(misses) == 5


# --------------------------------------------------------------------------- #
# U1 win sub-thresholds — recomputed by the scorer (§2 row 10, win family)
# --------------------------------------------------------------------------- #


def test_u1_failures_green_is_empty():
    assert u1_failures(_u1(), 0.02, ScoreThresholds()) == ()


def test_u1_failures_recomputes_t_u_from_noise_floor():
    # nf_U=0.06 -> T_U = max(0.1054, 0.12) = 0.12: -0.1054 no longer clears it.
    misses = u1_failures(_u1(), 0.06, ScoreThresholds())
    assert misses and "U1 mean delta" in misses[0]


U1_FAIL_CASES = [
    ({"p_holm": 0.08}, "Holm"),
    ({"mean_delta": -0.05}, "mean delta"),   # inside T_U = 0.1054
    ({"mean_delta": 0.10}, "mean delta"),    # wrong sign entirely
]


@pytest.mark.parametrize("over,needle", U1_FAIL_CASES)
def test_row10_each_u1_subthreshold_blocks(over, needle):
    # Regression (round-2 MAJOR): the U1 win threshold was reported but never
    # recomputed — a p_holm=0.9 "win" used to sail through to SHIP.
    report = score_report(_inputs(arms=(_arm(u1=_u1(**over)),)))
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any("U1 win threshold" in r and needle in r
               for r in report.verdict_reasons)
    assert exit_code(report) == 1


def test_row10_lists_c1_and_u1_misses_together():
    report = score_report(_inputs(arms=(
        _arm(c1=_c1(sign_stable=False), u1=_u1(p_holm=0.9)),)))
    assert any("C1 win threshold" in r for r in report.verdict_reasons)
    assert any("U1 win threshold" in r for r in report.verdict_reasons)


# --------------------------------------------------------------------------- #
# The two C noise multiples are distinct parameters (no name collision)
# --------------------------------------------------------------------------- #


def test_noise_multiple_fields_are_distinct():
    t = ScoreThresholds()
    assert t.c1_gate_noise_multiple == 2.0   # §1 C1 gate (bench manifest 2.0)
    assert t.c_scale_noise_multiple == 4.0   # §2 composite scale T_C
    assert not hasattr(t, "c_noise_multiple")  # the collided name is gone


def test_c_scale_multiple_drives_t_c_not_the_gate_multiple():
    # nf_C=0.02, mean dC1=-0.05: with scale 4.0, T_C=0.08, den=0.06 -> S_C=50.
    # Wiring the 2.0 gate multiple into the scale (the old collision) gives
    # T_C=max(0.05, 0.04)=0.05, den=0.03 -> S_C=100: a 50-point inflation.
    arm = _arm(c1=_c1(mean_delta=-0.05))
    proper = _inputs(noise_floor_c=0.02, arms=(arm,))
    assert _dim(report_arm(proper), "C").subscore == pytest.approx(50.0)
    collided = _inputs(noise_floor_c=0.02, arms=(arm,),
                       thresholds=ScoreThresholds(c_scale_noise_multiple=2.0))
    assert _dim(report_arm(collided), "C").subscore == pytest.approx(100.0)


# --------------------------------------------------------------------------- #
# Precedence rows 0-5 and ordering
# --------------------------------------------------------------------------- #


def test_row0_manifest_problems_not_scorable():
    report = score_report(_inputs(manifest_problems=("weights do not sum to 1",)))
    assert not report.scorable
    assert report.reason == "manifest_invalid"
    assert report.arms == ()
    assert exit_code(report) == 4


def test_row0_hash_mismatch_not_scorable():
    report = score_report(_inputs(manifest_hash_matches=False))
    assert not report.scorable and report.reason == "manifest_invalid"


def test_row1_untrusted_instrument_emits_no_arm_numbers():
    report = score_report(_inputs(instrument_trusted=False))
    assert report.scorable
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert report.arms == ()
    assert exit_code(report) == 1


def test_row0_outranks_row1():
    report = score_report(_inputs(manifest_hash_matches=False,
                                  instrument_trusted=False))
    assert report.reason == "manifest_invalid" and not report.scorable


def test_row2_benchmark_blind_not_scorable():
    report = score_report(_inputs(benchmark_trusted=False))
    assert not report.scorable
    assert report.reason == "benchmark_blind"
    assert exit_code(report) == 4


def test_row1_outranks_row2():
    report = score_report(_inputs(instrument_trusted=False,
                                  benchmark_trusted=False))
    assert report.scorable and report.verdict is Verdict.DO_NOT_SHIP


def test_row3_dead_positive_control_blocks_with_arm_numbers():
    report = score_report(_inputs(a3b_fails_grammaticality=False))
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any("positive control" in r for r in report.verdict_reasons)
    assert report.arms  # numbers ARE emitted from row 3 down
    assert exit_code(report) == 1


@pytest.mark.parametrize("stop", [
    "c_length_falsification",
    "c_distinct_dilution",
    "u_below_detectable_floor",
    "u_length_falsification",
])
def test_row4_each_stop_blocks(stop):
    report = score_report(_inputs(stops=Stops(**{stop: True})))
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any(stop in r for r in report.verdict_reasons)
    assert exit_code(report) == 1


def test_row5_incomplete_fraction_not_scorable():
    cells = {"generate": CellCounts(expected=18, complete=18),
             "implement": CellCounts(expected=12, complete=9, missing=3)}
    report = score_report(_inputs(arms=(_arm(cells=cells),)))
    assert not report.scorable
    assert report.reason == "incomplete_fraction_exceeded"
    assert report.arms == ()
    assert exit_code(report) == 4


def test_row5_merge_skipped_fraction_not_scorable():
    cells = {"generate": CellCounts(expected=18, complete=18, merge_skipped=7),
             "implement": CellCounts(expected=12, complete=12)}
    report = score_report(_inputs(arms=(_arm(cells=cells),)))
    assert not report.scorable
    assert report.reason == "merge_skipped_fraction_exceeded"


def test_row5_budget_exhausted_not_scorable():
    budget = Budget(spent_usd=121.0, projected_usd=140.0, max_usd=120.0,
                    exhausted=True)
    report = score_report(_inputs(budget=budget))
    assert not report.scorable and report.reason == "budget_exhausted"


def test_row4_stop_outranks_row6_gate():
    inputs = _inputs(stops=Stops(c_distinct_dilution=True),
                     arms=(_arm(gate_values=_green_gates(c2_dropped_must=1)),))
    report = score_report(inputs)
    assert any("STOP" in r for r in report.verdict_reasons)


def test_missing_treatment_arm_is_fail_closed_not_scorable():
    report = score_report(_inputs(treatment_arm="A9"))
    assert not report.scorable and report.reason == "treatment_arm_missing"


# --------------------------------------------------------------------------- #
# Precedence rows 6-14
# --------------------------------------------------------------------------- #


def test_row6_gate_outranks_row8_uncertifiable():
    inputs = _inputs(arms=(
        _arm(gate_values=_green_gates(u5_clarifying_questions=2),
             tost=_all_tost(C3=_tost_underpowered("C3"))),))
    report = score_report(inputs)
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any("hard gate" in r for r in report.verdict_reasons)


@pytest.mark.parametrize("family", ["C3", "C8", "U2", "U3", "O1", "O3"])
def test_row8_any_uncertifiable_tost_is_underpowered(family):
    # In-band CI (gate passes) but achieved power below min_power: the
    # RECOMPUTED certifiable flag routes to row 8, never row 6.
    tost = _all_tost(**{family: _tost_underpowered(family)})
    report = score_report(_inputs(arms=(_arm(tost=tost),)))
    assert report.verdict is Verdict.UNDERPOWERED
    assert any(family in r for r in report.verdict_reasons)
    assert exit_code(report) == 1


def test_missing_tost_family_is_fail_closed_on_both_legs():
    # An ABSENT family is no-signal: it fails the non-inferiority gate (row
    # 6 fires first) and would not be certifiable either — stricter than the
    # old absent-key row-8 routing, and never a pass on either leg.
    tost = {k: _tost_ok(k) for k in TOST_MARGINS if k != "O3"}
    report = score_report(_inputs(arms=(_arm(tost=tost),)))
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert "O3_mutation_kill" in report.arms[0].gates_failed


def test_row9_thin_stratum_is_underpowered():
    strata = {dim: dict(FULL_STRATA[dim]) for dim in FULL_STRATA}
    strata["U"]["large_realistic"] = 1
    report = score_report(_inputs(strata_coverage=strata))
    assert report.verdict is Verdict.UNDERPOWERED
    assert any("large_realistic n=1 < 3" in r for r in report.verdict_reasons)
    assert not report.strata_certifiable


def test_row9_o_term_over_skipped_is_underpowered():
    report = score_report(_inputs(arms=(_arm(o3_skipped_fraction=0.5),)))
    assert report.verdict is Verdict.UNDERPOWERED
    assert any("O3 skipped_fraction" in r for r in report.verdict_reasons)
    assert _dim(report.arms[0], "O").verdict == "underpowered"


def test_row9_underpowered_outranks_row10_c1_fail():
    strata = {dim: dict(FULL_STRATA[dim]) for dim in FULL_STRATA}
    strata["U"]["large_realistic"] = 1
    report = score_report(_inputs(strata_coverage=strata,
                                  arms=(_arm(c1=_c1(sign_stable=False)),)))
    assert report.verdict is Verdict.UNDERPOWERED


def test_row10_c1_fail_outranks_row12_a4():
    report = score_report(_inputs(a4_captures_effect=True,
                                  arms=(_arm(c1=_c1(sign_stable=False)),)))
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any("C1 win threshold" in r for r in report.verdict_reasons)


def test_reproduced_blocker_low_subscores_never_ship():
    # Exact review shape: all gates green, S_C=25 (mean dC1=-0.02 at nf_C=0.01)
    # and S_U=10 (mean dU1=-0.02854) -> composite 46.1, meets:false — yet the
    # old scorer said ship_treatment, exit 0. A dU1 that weak now also fails
    # the recomputed U1 win, so the run blocks at row 10 — either way it can
    # NEVER reach a ship verdict again.
    arm = _arm(c1=_c1(mean_delta=-0.02), u1=_u1(mean_delta=-0.02854))
    report = score_report(_inputs(arms=(arm,)))
    assert report.arms[0].composite < 70.0
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert exit_code(report) == 1
    obj = json.loads(render_score_json(report))
    assert obj["arms"]["A1"]["composite"]["meets"] is False


def _low_composite_inputs() -> ScoreInputs:
    # Wins intact (row 10 green) but composite < 70: S_C=37.5 (mean
    # dC1=-0.025, exactly on the c1_gate_floor at nf_C=0.01), S_U=100 (a U1
    # win forces S_U=100 since the win threshold IS the scale target),
    # S_O=69 (bloat at the ln 3 soft cap)
    # -> composite = 0.3*37.5 + 0.3*100 + 0.4*69 = 68.85 < 70.
    arm = _arm(c1=_c1(mean_delta=-0.025), bloat_ln=1.0986)
    return _inputs(arms=(arm,))


def test_row11_composite_below_pass_is_do_not_ship():
    # Regression (round-2 BLOCKER): composite >= 70 was declared necessary in
    # BENCHMARK §2 but had no precedence row — meets:false shipped exit 0.
    report = score_report(_low_composite_inputs())
    assert report.arms[0].composite == pytest.approx(68.85)
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any("composite" in r and "necessary" in r
               for r in report.verdict_reasons)
    assert exit_code(report) == 1
    obj = json.loads(render_score_json(report))
    assert obj["arms"]["A1"]["composite"]["meets"] is False


def test_row11_composite_gate_outranks_row12_a4():
    report = score_report(replace(_low_composite_inputs(),
                                  a4_captures_effect=True))
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any("composite" in r for r in report.verdict_reasons)


def test_row12_a4_captures_effect():
    report = score_report(_inputs(a4_captures_effect=True))
    assert report.verdict is Verdict.SHIP_EVALUATOR_ONLY
    assert exit_code(report) == 0


def test_row13_ship_oneliner():
    report = score_report(_inputs(beats_a3_fair=False,
                                  beats_a3_fair_detail="A3_fair tied A1"))
    assert report.verdict is Verdict.SHIP_ONELINER
    assert any("A3_fair tied A1" in r for r in report.verdict_reasons)
    assert exit_code(report) == 0


def test_row14_placebo_not_beaten_blocks():
    report = score_report(_inputs(beats_a2_placebo=False))
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert any("editing pass" in r for r in report.verdict_reasons)
    assert exit_code(report) == 1


def test_row15_ship_treatment_capped_at_demo_scale():
    report = score_report(_inputs())
    assert report.verdict is Verdict.SHIP_TREATMENT
    assert report.ceiling == "promising_scale_to_n18"
    assert any("promising_scale_to_n18" in r for r in report.verdict_reasons)


def test_ceiling_lifts_at_full_scale():
    report = score_report(_inputs(n_briefs=18))
    assert report.ceiling == "none"


# --------------------------------------------------------------------------- #
# Threshold-parameter overrides
# --------------------------------------------------------------------------- #


def test_frag_rate_cap_override_flips_c8():
    gates = _green_gates(c8_frag_rate=0.06)
    blocked = score_report(_inputs(arms=(_arm(gate_values=gates),)))
    assert blocked.verdict is Verdict.DO_NOT_SHIP  # default cap 0.05

    relaxed = _inputs(arms=(_arm(gate_values=gates),),
                      thresholds=ScoreThresholds(frag_rate_cap=0.10))
    assert score_report(relaxed).verdict is Verdict.SHIP_TREATMENT


def test_dead_end_cap_override_flips_u3():
    gates = _green_gates(u3_max_dead_ends=7)
    assert score_report(
        _inputs(arms=(_arm(gate_values=gates),))).verdict is Verdict.DO_NOT_SHIP
    relaxed = _inputs(arms=(_arm(gate_values=gates),),
                      thresholds=ScoreThresholds(dead_end_cap=10))
    assert score_report(relaxed).verdict is Verdict.SHIP_TREATMENT


def test_o1_min_correctness_override():
    gates = _green_gates(o1_correctness=0.85)
    assert score_report(
        _inputs(arms=(_arm(gate_values=gates),))).verdict is Verdict.DO_NOT_SHIP
    relaxed = _inputs(arms=(_arm(gate_values=gates),),
                      thresholds=ScoreThresholds(o1_min_correctness=0.80))
    assert score_report(relaxed).verdict is Verdict.SHIP_TREATMENT


def test_o3_min_kill_rate_override():
    gates = _green_gates(o3_kill_rate=0.6)
    assert score_report(
        _inputs(arms=(_arm(gate_values=gates),))).verdict is Verdict.DO_NOT_SHIP
    relaxed = _inputs(arms=(_arm(gate_values=gates),),
                      thresholds=ScoreThresholds(o3_min_kill_rate=0.5))
    assert score_report(relaxed).verdict is Verdict.SHIP_TREATMENT


def test_composite_pass_override_is_enforced_as_necessary():
    # Inverted regression (round-2 BLOCKER; this test used to assert the
    # verdict was UNCHANGED by meets:false): composite >= pass is necessary,
    # so a raised pass threshold now blocks the same green arm.
    strict = _inputs(thresholds=ScoreThresholds(composite_pass=95.0))
    report = score_report(strict)
    obj = json.loads(render_score_json(report))
    assert obj["arms"]["A1"]["composite"]["meets"] is False
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert exit_code(report) == 1
    # Never sufficient stays true in the schema regardless.
    assert obj["arms"]["A1"]["composite"]["authorizes_ship"] is False


def test_weights_override_changes_composite():
    inputs = _inputs(
        thresholds=ScoreThresholds(weights={"C": 1.0, "U": 0.0, "O": 0.0}))
    assert report_arm(inputs).composite == pytest.approx(50.0)


def test_u_target_override_changes_s_u():
    # Doubling the ln-target halves the achieved ratio: 0.0854/0.1908 ~ 44.76%.
    inputs = _inputs(thresholds=ScoreThresholds(u_target_ln=0.2108))
    assert _dim(report_arm(inputs), "U").subscore == pytest.approx(
        100.0 * (0.1054 - 0.02) / (0.2108 - 0.02))


def test_min_stratum_override_lifts_row9():
    strata = {dim: dict(FULL_STRATA[dim]) for dim in FULL_STRATA}
    strata["U"]["large_realistic"] = 1
    relaxed = _inputs(strata_coverage=strata,
                      thresholds=ScoreThresholds(min_stratum_n=1))
    assert score_report(relaxed).verdict is Verdict.SHIP_TREATMENT


# --------------------------------------------------------------------------- #
# score.json serialization: schema, canonical form, round-trip
# --------------------------------------------------------------------------- #

TOP_LEVEL_KEYS = {
    "schema", "manifest_content_hash", "generated_at", "scorable", "reason",
    "instrument_trusted", "benchmark_trusted", "human_read_required",
    "n_briefs", "n_buildable", "k_seeds", "extractor_families", "noise_floor",
    "strata_certifiable", "strata_coverage", "stops", "arms_compared", "arms",
    "budget", "verdict", "verdict_reasons", "ceiling",
}


def _rich_inputs() -> ScoreInputs:
    metrics = {
        "C": (MetricValue(
            id="C1", value=-0.03, ci=(-0.05, -0.01), p_holm=0.024,
            extra={"mean_delta": -0.03, "p": 0.008, "sign_stable": True,
                   "n": 9, "large_realistic_delta": -0.02}),),
        "U": (MetricValue(id="U1", value=-0.1054, p_holm=0.02,
                          extra={"mean_delta": -0.1054, "spend_index": 4821.0}),),
        "O": (MetricValue(id="O5", value=0.0),),
    }
    arm = _arm(metrics=metrics,
               covariates={"word_count_delta": -210.0, "distinct_delta": -1.2})
    return _inputs(arms=(arm,))


def test_render_top_level_keys_exact():
    obj = json.loads(render_score_json(score_report(_rich_inputs())))
    assert set(obj) == TOP_LEVEL_KEYS
    assert obj["schema"] == "blueprint-bench/1"
    assert obj["verdict"] == "ship_treatment"
    assert obj["reason"] is None
    assert obj["human_read_required"] is True
    assert obj["noise_floor"] == {"C": 0.01, "U": 0.02}
    assert obj["arms_compared"] == {"baseline": "A0", "treatment": "A1"}
    assert set(obj["stops"]) == {
        "c_length_falsification", "c_distinct_dilution",
        "u_below_detectable_floor", "u_length_falsification"}


def test_render_arm_shape_and_values():
    obj = json.loads(render_score_json(score_report(_rich_inputs())))
    arm = obj["arms"]["A1"]
    assert set(arm) == {"cells", "gates", "gates_blocked", "gates_failed",
                        "leakage_voided", "l4_no_signal", "dimensions",
                        "composite"}
    assert arm["gates_blocked"] is False and arm["gates_failed"] == []
    assert arm["cells"]["generate"]["expected"] == 18
    assert arm["cells"]["generate"]["incomplete_fraction"] == 0.0
    dims = arm["dimensions"]
    assert dims["C"]["subscore"] == 50.0
    assert dims["U"]["subscore"] == 100.0
    assert dims["O"]["subscore"] == 89.0
    assert dims["C"]["covariates"] == {"word_count_delta": -210.0,
                                       "distinct_delta": -1.2}
    assert "covariates" not in dims["U"]
    assert dims["O"]["renormalized"] is False
    assert dims["O"]["o2_skipped_fraction"] == 0.0
    comp = arm["composite"]
    assert comp["value"] == 80.6
    assert comp["pass_threshold"] == 70
    assert comp["meets"] is True
    assert comp["authorizes_ship"] is False
    assert comp["weights"] == {"C": 0.30, "U": 0.30, "O": 0.40}


def test_render_includes_o3_gate_entry():
    obj = json.loads(render_score_json(score_report(_rich_inputs())))
    gates = {g["id"]: g for g in obj["arms"]["A1"]["gates"]}
    o3 = gates["O3_mutation_kill"]
    assert o3["value"] == 0.8 and o3["threshold"] == 0.75
    assert o3["passed"] is True


def test_render_metric_payload_lifts_ci_and_p_holm():
    obj = json.loads(render_score_json(score_report(_rich_inputs())))
    c1 = obj["arms"]["A1"]["dimensions"]["C"]["metrics"]["C1"]
    assert c1 == {"mean_delta": -0.03, "p": 0.008, "sign_stable": True, "n": 9,
                  "large_realistic_delta": -0.02, "ci": [-0.05, -0.01],
                  "p_holm": 0.024}
    o5 = obj["arms"]["A1"]["dimensions"]["O"]["metrics"]["O5"]
    # O5 is a DERIVED id (score.DERIVABLE_METRIC_IDS): bloat_ln is filled in
    # from arm.bloat_ln regardless of the packed (empty) extra, so extra is
    # no longer empty and the "value" fallback branch does not apply here.
    assert o5 == {"bloat_ln": 0.0}


def test_render_metric_value_fallback_for_non_derivable_id_with_empty_extra():
    # The "value" fallback in _metric_obj only fires for an id with NO
    # operative twin (e.g. C4, deferred purity) whose packed extra is empty.
    metrics = {"C": (MetricValue(id="C4", value=0.0),)}
    arm = _arm(metrics=metrics)
    obj = json.loads(render_score_json(score_report(_inputs(arms=(arm,)))))
    c4 = obj["arms"]["A1"]["dimensions"]["C"]["metrics"]["C4"]
    assert c4 == {"value": 0.0}


def test_render_gate_entries_integral_values_as_ints_detail_only_when_set():
    inputs = _inputs(
        arms=(_arm(gate_values=_green_gates(u0_prompt_sha_ok=False)),))
    obj = json.loads(render_score_json(score_report(inputs)))
    gates = {g["id"]: g for g in obj["arms"]["A1"]["gates"]}
    c2 = gates["C2_must_retention"]
    assert c2["value"] == 0 and c2["threshold"] == 0 and "detail" not in c2
    u0 = gates["U0_isolation"]
    assert u0["passed"] is False and u0["detail"] == "prompt_sha mismatch"
    assert gates["C8_grammaticality"]["threshold"] == 0.05


def test_render_derived_fractions_rounded_to_3():
    cells = {"generate": CellCounts(expected=18, complete=17, missing=1,
                                    merge_skipped=2),
             "implement": CellCounts(expected=12, complete=12)}
    inputs = _inputs(arms=(_arm(cells=cells),))
    obj = json.loads(render_score_json(score_report(inputs)))
    generate = obj["arms"]["A1"]["cells"]["generate"]
    assert generate["incomplete_fraction"] == 0.056
    assert generate["merge_skipped_fraction"] == 0.111


def test_render_o_skipped_fractions_and_covariates_rounded_to_3():
    # Regression (review finding): 1/12 used to serialize as
    # 0.08333333333333333, breaking the byte-stable golden fixture.
    arm = _arm(o2_skipped_fraction=1.0 / 12.0, o3_skipped_fraction=1.0 / 12.0,
               covariates={"word_count_delta": -210.0,
                           "distinct_delta": -37.0 / 30.0})
    obj = json.loads(render_score_json(score_report(_inputs(arms=(arm,)))))
    dims = obj["arms"]["A1"]["dimensions"]
    assert dims["O"]["o2_skipped_fraction"] == 0.083
    assert dims["O"]["o3_skipped_fraction"] == 0.083
    assert dims["C"]["covariates"]["distinct_delta"] == -1.233
    assert dims["C"]["covariates"]["word_count_delta"] == -210.0


def test_render_not_scorable_has_empty_arms_and_reason():
    obj = json.loads(render_score_json(
        score_report(_inputs(benchmark_trusted=False))))
    assert set(obj) == TOP_LEVEL_KEYS
    assert obj["scorable"] is False
    assert obj["reason"] == "benchmark_blind"
    assert obj["arms"] == {}
    assert obj["verdict"] == "do_not_ship"  # fail-closed, never shippable


def test_render_is_byte_stable_and_canonical():
    report = score_report(_rich_inputs())
    first = render_score_json(report)
    second = render_score_json(report)
    assert first == second
    # Canonical form: re-dumping the parsed object reproduces the exact bytes.
    assert first == json.dumps(json.loads(first), sort_keys=True,
                               separators=(",", ":"), ensure_ascii=False)


def test_render_round_trip_preserves_verdict_and_composite():
    report = score_report(_rich_inputs())
    obj = json.loads(render_score_json(report))
    assert obj["verdict"] == report.verdict.value
    assert obj["arms"]["A1"]["composite"]["value"] == pytest.approx(
        report.arms[0].composite, abs=0.005)
    assert obj["ceiling"] == report.ceiling


# --------------------------------------------------------------------------- #
# thresholds_from_bench — the manifest is the source of truth
# --------------------------------------------------------------------------- #


def test_thresholds_from_bench_maps_the_two_noise_multiples_distinctly():
    from eval_overexplanation.manifest import BenchThresholds
    from eval_overexplanation.score import thresholds_from_bench

    bench = BenchThresholds(c1_gate_noise_multiple=2.5,
                            c_scale_noise_multiple=5.0,
                            c1_gate_floor=0.03)
    t = thresholds_from_bench(bench)
    # The §4 trap: gate and scale must never collapse onto one value.
    assert t.c1_gate_noise_multiple == 2.5
    assert t.c_scale_noise_multiple == 5.0
    # The C1 gate's absolute floor is hash-covered and mapped through.
    assert t.c1_gate_floor == 0.03


def test_thresholds_from_bench_maps_caps_and_gates():
    from eval_overexplanation.manifest import BenchThresholds
    from eval_overexplanation.score import thresholds_from_bench

    bench = BenchThresholds(
        leak_caps={"code_frac": 0.2, "reference": 0.3, "copy": 0.4,
                   "spec_only_correctness": 0.6},
        dead_end_cap=4,
        o1_min_correctness=0.95,
        weights={"C": 0.2, "U": 0.2, "O": 0.6},
        composite_pass=80.0,
        frag_rate_cap=0.07,
    )
    t = thresholds_from_bench(bench)
    assert t.leak_code_frac_cap == 0.2
    assert t.leak_reference_cap == 0.3
    assert t.leak_copy_cap == 0.4
    assert t.leak_spec_only_cap == 0.6
    assert t.dead_end_cap == 4
    assert t.o1_min_correctness == 0.95
    assert t.weights == {"C": 0.2, "U": 0.2, "O": 0.6}
    assert t.composite_pass == 80.0
    assert t.frag_rate_cap == 0.07


def test_thresholds_from_bench_consumes_tost_margins_and_min_power():
    # Regression (round-2 MAJOR): bench.tost_margins / bench.min_power were
    # silently dropped, detaching the pre-registered TOST contract from the
    # thresholds bundle.
    from eval_overexplanation.manifest import BenchThresholds
    from eval_overexplanation.score import thresholds_from_bench

    margins = {"C3": 0.03, "C8": 0.01, "U2": 2.0, "U3": 2.0,
               "O1": 0.02, "O3": 0.05}
    bench = BenchThresholds(tost_margins=margins, min_power=0.9)
    t = thresholds_from_bench(bench)
    assert t.tost_margins == margins
    assert t.min_power == 0.9


def test_thresholds_from_bench_consumes_every_operative_scale_field():
    # Regression (round-3 MAJOR): the S_O weights, win alpha, knife-edge
    # denominators, U noise multiple and O-term skip cap were Python-only
    # defaults — operative yet outside content_hash. They must map through.
    from eval_overexplanation.manifest import BenchThresholds
    from eval_overexplanation.score import thresholds_from_bench

    bench = BenchThresholds(
        win_alpha=0.01,
        c_min_den=0.03,
        u_min_den=0.06,
        u_noise_multiple=3.0,
        o_weight_correctness=0.6,
        o_weight_kill=0.25,
        o_weight_bloat=0.15,
        max_o_term_skipped_fraction=0.2,
    )
    t = thresholds_from_bench(bench)
    assert t.win_alpha == 0.01
    assert t.c_min_den == 0.03
    assert t.u_min_den == 0.06
    assert t.u_noise_multiple == 3.0
    assert t.o_weight_correctness == 0.6
    assert t.o_weight_kill == 0.25
    assert t.o_weight_bloat == 0.15
    assert t.max_o_term_skipped_fraction == 0.2


def test_thresholds_from_bench_defaults_equal_python_fallbacks():
    # A default bench block and a default ScoreThresholds must agree on every
    # shared number — one frozen contract, two carriers.
    from eval_overexplanation.manifest import BenchThresholds
    from eval_overexplanation.score import ScoreThresholds, thresholds_from_bench

    assert thresholds_from_bench(BenchThresholds()) == ScoreThresholds()

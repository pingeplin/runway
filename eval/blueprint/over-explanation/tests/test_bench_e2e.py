"""Golden end-to-end for the §2 scorer (BENCHMARK.md §6, offline).

Builds the BENCHMARK.md §2 worked-example inputs as inert dataclasses, runs
``score_report`` + ``render_score_json``, and asserts the output is
byte-identical to ``tests/fixtures/bench/expected_score.json``. The fixture is
regenerated only from the scorer itself (never hand-edited), so any drift in
arithmetic, rounding, key sets, or precedence shows up as a byte diff.

The worked-example numbers are the §2 anchors, derivable by hand:

  S_C: nf_C=0.031 -> T_C=max(0.05, 4*0.031)=0.124, den=0.093;
       C1 mean_delta=-0.11 -> (0.11-0.031)/0.093 -> 84.95 (2dp)
  S_U: nf_U=0.084 -> T_U=max(0.1054, 0.168)=0.168, den=0.084;
       mean_dU1=-0.23 -> clip((0.23-0.084)/0.084) -> 100.0
  S_O: 100*(0.50*0.90 + 0.30*0.78 + 0.20*(1 - 0.11/1.0986)) -> 86.4 (1dp)
  composite = 0.3*84.9462... + 0.3*100 + 0.4*86.3974... -> 90.04 (2dp)

The example's U/O strata are structurally thin (large_realistic n=1), so the
golden verdict is UNDERPOWERED ("underpowered_no_ship"), exit code 1.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

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
    Stops,
    TostStats,
    U1Stats,
    exit_code,
    render_score_json,
    score_report,
)

GOLDEN = Path(__file__).parent / "fixtures" / "bench" / "expected_score.json"

BENCH_MARGINS = {"C3": 0.05, "C8": 0.02, "U2": 1.0, "U3": 1.0,
                 "O1": 0.05, "O3": 0.10}


def bench_gate_values() -> GateValues:
    return GateValues(
        c0_leak_hits=0,
        c2_dropped_must=0,
        c7_merge_failures=0,
        c8_frag_rate=0.03,
        u0_prompt_sha_ok=True,
        u0_leak_hits=0,
        u3_max_dead_ends=4,
        u4_completion_fraction=1.0,
        u5_clarifying_questions=0,
        o1_correctness=0.94,
        o1_regressed_cells=(),
        o2_overfit=0.04,
        o3_kill_rate=0.78,
        o3_invalid=0,
        o4_workarounds=0,
        l1_code_frac=0.10,
        l2_reference_containment=0.12,
        l3_copy_containment=0.11,
        l4_spec_only_correctness=0.0,
    )


def bench_tost() -> dict[str, TostStats]:
    """Raw per-family TOST numerics: in-band 90% CIs, achieved power >= 0.8."""
    return {
        family: TostStats(estimate=0.0,
                          ci90=(-margin / 4, margin / 4),
                          p_value=0.012, achieved_power=0.86, margin=margin)
        for family, margin in BENCH_MARGINS.items()
    }


def bench_metrics() -> dict[str, tuple[MetricValue, ...]]:
    # These packed values must agree with bench_gate_values()/bench_tost() —
    # score.py DERIVES dimensions.<D>.metrics for every DERIVABLE_METRIC_IDS
    # entry from those operative fields and always renders the derived value
    # regardless of what's packed here (this fixture never round-trips
    # through the CLI's _cross_check_metrics, so a self-contradiction here
    # would go unrejected while still not matching the rendered bytes: a
    # golden fixture that is itself a load-error state elsewhere).
    tost = {"non_inferior": True, "power": 0.86, "certifiable": True}
    return {
        "C": (
            MetricValue(
                id="C1", value=-0.11, ci=(-0.18, -0.04), p_holm=0.024,
                extra={"mean_delta": -0.11, "p": 0.008, "sign_stable": True,
                       "n": 9, "large_realistic_delta": -0.10}),
            MetricValue(id="C3", value=1.0, extra={"tost": dict(tost)}),
            MetricValue(id="C4", value=-0.004,
                        extra={"delta_purity": -0.004, "reported_only": True}),
            MetricValue(
                id="C8", value=0.03,
                extra={"frag_rate": 0.03, "cap": 0.05,
                       "tost": {"non_inferior": True, "power": 0.86,
                                "certifiable": True}}),
        ),
        "U": (
            MetricValue(id="U1", value=-0.23, p_holm=0.02,
                        extra={"mean_delta": -0.23, "spend_index": 4821.0}),
            MetricValue(id="U2", value=1.0, extra={"tost": dict(tost)}),
            MetricValue(
                id="U3", value=1.5,
                extra={"mean": 1.5, "max_cell": 4,
                       "tost": {"non_inferior": True, "power": 0.86,
                                "certifiable": True}}),
            MetricValue(id="U5", value=0.0,
                        extra={"clarifying_questions": 0,
                               "trailing_question_marks": 2}),
        ),
        "O": (
            MetricValue(id="O1", value=0.94,
                        extra={"correctness": 0.94, "regressed_cells": []}),
            MetricValue(id="O2", value=0.04,
                        extra={"overfit": 0.04, "skipped_briefs": []}),
            MetricValue(id="O3", value=0.78,
                        extra={"kill_rate": 0.78, "invalid": 0,
                               "smoke_failed_cells": 1}),
            MetricValue(id="O4", value=0.0, extra={"workarounds": 0}),
            MetricValue(id="O5", value=0.11, extra={"bloat_ln": 0.11}),
        ),
    }


def bench_arm() -> ArmInputs:
    return ArmInputs(
        arm_id="A1",
        cells={
            "generate": CellCounts(expected=18, complete=18, merge_skipped=2),
            "implement": CellCounts(expected=12, complete=12, retried=1,
                                    mutations_skipped=1),
        },
        gate_values=bench_gate_values(),
        tost=bench_tost(),
        c1=C1Stats(mean_delta=-0.11, ci=(-0.18, -0.04), p_holm=0.024,
                   sign_stable=True, large_realistic_delta=-0.10),
        u1=U1Stats(mean_delta=-0.23, p_holm=0.02),
        correctness_holdout=0.90,
        bloat_ln=0.11,
        o2_skipped_fraction=0.0,
        o3_skipped_fraction=1.0 / 12.0,
        metrics=bench_metrics(),
        covariates={"word_count_delta": -210.0, "distinct_delta": -1.2},
    )


def bench_inputs() -> ScoreInputs:
    return ScoreInputs(
        manifest_content_hash=("sha256:"
                               "0000000000000000000000000000000000000000"
                               "000000000000000000000000"),
        manifest_hash_matches=True,
        manifest_problems=(),
        generated_at="2026-08-13T00:00:00Z",
        instrument_trusted=True,
        benchmark_trusted=True,
        a3b_fails_grammaticality=True,
        stops=Stops(),
        noise_floor_c=0.031,
        noise_floor_u=0.084,
        n_briefs=9,
        n_buildable=6,
        k_seeds=2,
        extractor_families=("anthropic-claude", "openai-gpt"),
        strata_coverage={
            "C": {"elicit_prone": 3, "large_realistic": 3, "neutral": 3},
            "U": {"elicit_prone": 2, "large_realistic": 1, "neutral": 3},
            "O": {"elicit_prone": 2, "large_realistic": 1, "neutral": 3},
        },
        baseline_arm="A0",
        treatment_arm="A1",
        arms=(bench_arm(),),
        budget=Budget(spent_usd=41.2, projected_usd=68.9, max_usd=120.0,
                      exhausted=False),
        a4_captures_effect=False,
        beats_a3_fair=True,
        beats_a2_placebo=True,
    )


def test_golden_score_json_is_byte_identical():
    got = render_score_json(score_report(bench_inputs()))
    assert got == GOLDEN.read_text(encoding="utf-8")


def test_golden_render_is_deterministic_and_canonical():
    report = score_report(bench_inputs())
    first = render_score_json(report)
    assert first == render_score_json(report)
    assert first == json.dumps(json.loads(first), sort_keys=True,
                               separators=(",", ":"), ensure_ascii=False)


def test_golden_subscores_match_the_benchmark_worked_example():
    obj = json.loads(render_score_json(score_report(bench_inputs())))
    dims = obj["arms"]["A1"]["dimensions"]
    assert dims["C"]["subscore"] == 84.95
    assert dims["U"]["subscore"] == 100.0
    assert dims["O"]["subscore"] == 86.4
    assert dims["O"]["o3_skipped_fraction"] == 0.083
    assert dims["O"]["renormalized"] is False
    assert dims["O"]["correctness_holdout_missing"] is False
    assert obj["arms"]["A1"]["composite"]["value"] == 90.04
    assert obj["arms"]["A1"]["composite"]["meets"] is True
    assert obj["arms"]["A1"]["composite"]["authorizes_ship"] is False


def test_golden_verdict_is_underpowered_exit_1():
    # U/O large_realistic stratum n=1: structurally uncertifiable at demo
    # scale — the §2 example's own ceiling.
    report = score_report(bench_inputs())
    assert report.verdict is Verdict.UNDERPOWERED
    assert report.ceiling == "promising_scale_to_n18"
    assert exit_code(report) == 1
    obj = json.loads(render_score_json(report))
    assert obj["verdict"] == "underpowered_no_ship"
    assert obj["scorable"] is True


def test_e2e_leaking_treatment_never_ships():
    # End-to-end regression for the review BLOCKER: an arm failing every L
    # gate, all else green, must block with voided U/O — never exit 0.
    leaky = replace(bench_arm(), gate_values=replace(
        bench_gate_values(), l1_code_frac=0.98, l2_reference_containment=1.0,
        l3_copy_containment=1.0, l4_spec_only_correctness=1.0))
    # Full strata so nothing else outranks the leak on the way down.
    inputs = replace(bench_inputs(), arms=(leaky,), strata_coverage={
        dim: {"elicit_prone": 3, "large_realistic": 3, "neutral": 3}
        for dim in ("C", "U", "O")})
    report = score_report(inputs)
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert exit_code(report) == 1
    obj = json.loads(render_score_json(report))
    arm = obj["arms"]["A1"]
    assert arm["leakage_voided"] is True
    assert arm["dimensions"]["U"]["subscore"] == 0.0
    assert arm["dimensions"]["O"]["subscore"] == 0.0
    assert any("leakage" in r for r in obj["verdict_reasons"])


def test_e2e_missing_holdout_with_zero_skip_fraction_fails_closed():
    # End-to-end regression (round-2 BLOCKER): o2_overfit=None +
    # correctness_holdout=None + o2_skipped_fraction=0.0 used to score 98.8
    # and SHIP exit 0 with visible-case correctness silently substituted at
    # O2's full 0.50 weight. Now the O2 gate fails closed, mirroring O3, and
    # the correctness term scores 0 in its original weight, flagged.
    broken = replace(bench_arm(),
                     gate_values=replace(bench_gate_values(), o2_overfit=None),
                     correctness_holdout=None,
                     o2_skipped_fraction=0.0)
    report = score_report(replace(bench_inputs(), arms=(broken,)))
    arm = report.arms[0]
    assert "O2_holdout_overfit" in arm.gates_failed
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert exit_code(report) == 1
    obj = json.loads(render_score_json(report))
    o_dim = obj["arms"]["A1"]["dimensions"]["O"]
    assert o_dim["correctness_holdout_missing"] is True
    # 100*(0 + 0.30*0.78 + 0.20*(1 - 0.11/1.0986)) = 41.3975
    assert o_dim["subscore"] == pytest.approx(41.4, abs=0.01)


def test_e2e_missing_kill_with_zero_skip_fraction_fails_closed():
    # End-to-end regression: no O3 signal, no accounted skip => the O3 gate
    # fails and S_O keeps the kill weight at zero (65.35, not renormalized).
    broken = replace(bench_arm(),
                     gate_values=replace(bench_gate_values(),
                                         o3_kill_rate=None),
                     o3_skipped_fraction=0.0)
    report = score_report(replace(bench_inputs(), arms=(broken,)))
    arm = report.arms[0]
    assert "O3_mutation_kill" in arm.gates_failed
    o_scores = {d.name: d.subscore for d in arm.dimensions}
    # 100*(0.50*0.90 + 0 + 0.20*(1 - 0.11/1.0986)) = 62.9975
    assert o_scores["O"] == pytest.approx(62.9975, abs=0.001)
    assert report.verdict is Verdict.DO_NOT_SHIP
    assert exit_code(report) == 1

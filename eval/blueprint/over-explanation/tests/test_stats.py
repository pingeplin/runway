"""Unit tests for the inferential layer (stats.py).

All fixtures are hand-built; no network, no RNG outside default_rng(seed).
Sign convention under test throughout: a restatement WIN is a NEGATIVE mean
delta (treatment - baseline).
"""

from __future__ import annotations

import numpy as np
import pytest

from eval_overexplanation.stats import (
    DedupSweep,
    LeaveOneOut,
    average_to_brief,
    bootstrap_ci,
    dedup_threshold_sweep,
    estimate_noise_floor,
    holm_correction,
    leave_one_brief_out,
    length_falsification_stop,
    paired_wilcoxon,
    partial_out_length,
    tost,
)


# --------------------------------------------------------------------------- #
# average_to_brief
# --------------------------------------------------------------------------- #


def test_average_to_brief_means_seed_values():
    assert average_to_brief({0: 0.2, 1: 0.4, 2: 0.6}) == pytest.approx(0.4)


def test_average_to_brief_single_seed():
    assert average_to_brief({7: 1.5}) == pytest.approx(1.5)


def test_average_to_brief_empty_raises():
    with pytest.raises(ValueError):
        average_to_brief({})


# --------------------------------------------------------------------------- #
# paired_wilcoxon
# --------------------------------------------------------------------------- #


def test_wilcoxon_detects_consistent_win():
    # treatment restates less everywhere -> negative deltas -> significant.
    baseline = [0.50, 0.45, 0.60, 0.55, 0.48, 0.52, 0.58, 0.40]
    treatment = [0.30, 0.20, 0.35, 0.30, 0.25, 0.28, 0.33, 0.18]
    res = paired_wilcoxon(baseline, treatment)
    assert res.n == 8
    assert res.p_value < 0.05


def test_wilcoxon_all_zero_delta_is_guarded():
    vals = [0.3, 0.4, 0.5]
    res = paired_wilcoxon(vals, list(vals))
    assert res.statistic == 0.0
    assert res.p_value == 1.0
    assert res.n == 3


def test_wilcoxon_length_mismatch_raises():
    with pytest.raises(ValueError):
        paired_wilcoxon([0.1, 0.2], [0.1])


def test_wilcoxon_empty_raises():
    with pytest.raises(ValueError):
        paired_wilcoxon([], [])


# --------------------------------------------------------------------------- #
# bootstrap_ci — determinism + correctness
# --------------------------------------------------------------------------- #


def test_bootstrap_determinism_same_seed_same_ci():
    deltas = [-0.2, -0.1, -0.3, -0.15, -0.05, -0.25]
    a = bootstrap_ci(deltas, n_boot=2000, seed=42)
    b = bootstrap_ci(deltas, n_boot=2000, seed=42)
    assert a == b
    assert a.low == b.low and a.high == b.high


def test_bootstrap_different_seed_differs():
    deltas = [-0.2, -0.1, -0.3, -0.15, -0.05, -0.25, 0.05, -0.4]
    a = bootstrap_ci(deltas, n_boot=2000, seed=1)
    b = bootstrap_ci(deltas, n_boot=2000, seed=2)
    # Point estimate is seed-independent; the interval endpoints differ.
    assert a.point == pytest.approx(b.point)
    assert (a.low, a.high) != (b.low, b.high)


def test_bootstrap_point_is_mean_and_ci_brackets_it():
    deltas = [-0.2, -0.1, -0.3, -0.15, -0.05, -0.25]
    ci = bootstrap_ci(deltas, n_boot=5000, seed=0, level=0.95)
    assert ci.point == pytest.approx(np.mean(deltas))
    assert ci.low <= ci.point <= ci.high
    assert ci.level == 0.95


def test_bootstrap_negative_win_ci_excludes_zero():
    # A clear, consistent win: the 95% CI should sit entirely below zero.
    deltas = [-0.30, -0.28, -0.31, -0.29, -0.27, -0.32, -0.30, -0.26]
    ci = bootstrap_ci(deltas, n_boot=5000, seed=0)
    assert ci.high < 0.0


def test_bootstrap_empty_raises():
    with pytest.raises(ValueError):
        bootstrap_ci([])


def test_bootstrap_bad_level_raises():
    with pytest.raises(ValueError):
        bootstrap_ci([-0.1, -0.2], level=1.5)


# --------------------------------------------------------------------------- #
# partial_out_length
# --------------------------------------------------------------------------- #


def test_partial_genuine_effect_survives():
    # restatement win independent of length: wordcount barely moves, restatement
    # drops consistently -> negative intercept, significant.
    rng = np.random.default_rng(0)
    wordcount = rng.normal(0.0, 1.0, size=24)
    restatement = -0.3 + 0.0 * wordcount + rng.normal(0.0, 0.02, size=24)
    eff = partial_out_length(restatement, wordcount, noise_floor=0.05)
    assert eff.mean_residual < 0
    assert eff.p_value < 0.05
    assert eff.survives is True


def test_partial_pure_length_artifact_does_not_survive():
    # all the restatement movement is explained by length; intercept ~ 0.
    rng = np.random.default_rng(1)
    wordcount = rng.normal(0.0, 1.0, size=24)
    restatement = 0.4 * wordcount + rng.normal(0.0, 0.01, size=24)
    eff = partial_out_length(restatement, wordcount, noise_floor=0.05)
    assert abs(eff.mean_residual) < 0.05
    assert eff.survives is False


def test_partial_within_noise_floor_does_not_survive():
    # genuine-looking small intercept but below the noise floor -> not survive.
    rng = np.random.default_rng(2)
    wordcount = rng.normal(0.0, 1.0, size=24)
    restatement = -0.02 + rng.normal(0.0, 0.005, size=24)
    eff = partial_out_length(restatement, wordcount, noise_floor=0.10)
    assert eff.survives is False


def test_partial_positive_intercept_does_not_survive():
    # treatment restates MORE (wrong direction) -> must not survive.
    rng = np.random.default_rng(3)
    wordcount = rng.normal(0.0, 1.0, size=24)
    restatement = 0.3 + rng.normal(0.0, 0.02, size=24)
    eff = partial_out_length(restatement, wordcount, noise_floor=0.05)
    assert eff.mean_residual > 0
    assert eff.survives is False


# --------------------------------------------------------------------------- #
# length_falsification_stop — the STOP truth table
# --------------------------------------------------------------------------- #


def _genuine():
    rng = np.random.default_rng(10)
    wordcount = rng.normal(0.0, 1.0, size=24)
    treated = -0.3 + rng.normal(0.0, 0.02, size=24)
    # length-strip arm barely moves restatement: does NOT reproduce the gain.
    strip = -0.02 + rng.normal(0.0, 0.02, size=24)
    return treated, wordcount, strip


def test_stop_truth_table_genuine_does_not_stop():
    treated, wordcount, strip = _genuine()
    res = length_falsification_stop(treated, wordcount, strip, noise_floor=0.05)
    assert res.survives_partialling is True
    assert res.length_strip_reproduces is False
    assert res.stop is False
    assert res.detail.startswith("PROCEED")


def test_stop_truth_table_length_strip_reproduces_stops():
    # Genuine-surviving effect, but the dumb strip arm reaches the same gain.
    treated, wordcount, _ = _genuine()
    rng = np.random.default_rng(11)
    strip = -0.30 + rng.normal(0.0, 0.02, size=24)  # reproduces treated
    res = length_falsification_stop(treated, wordcount, strip, noise_floor=0.05)
    assert res.length_strip_reproduces is True
    assert res.stop is True
    assert res.detail.startswith("STOP")


def test_stop_truth_table_does_not_survive_partialling_stops():
    # Effect is pure length artifact (no residual), strip does not reproduce.
    rng = np.random.default_rng(12)
    wordcount = rng.normal(0.0, 1.0, size=24)
    treated = 0.4 * wordcount + rng.normal(0.0, 0.01, size=24)  # all length
    strip = -0.02 + rng.normal(0.0, 0.02, size=24)
    res = length_falsification_stop(treated, wordcount, strip, noise_floor=0.05)
    assert res.survives_partialling is False
    assert res.stop is True
    assert res.detail.startswith("STOP")


def test_stop_rule_is_or_of_both_conditions():
    # Both bad at once also STOPs.
    rng = np.random.default_rng(13)
    wordcount = rng.normal(0.0, 1.0, size=24)
    treated = 0.4 * wordcount + rng.normal(0.0, 0.01, size=24)
    strip = treated.copy()  # reproduces AND no residual
    res = length_falsification_stop(treated, wordcount, strip, noise_floor=0.05)
    assert res.stop is True


# --------------------------------------------------------------------------- #
# tost — non-inferiority + power gating
# --------------------------------------------------------------------------- #


def test_tost_non_inferior_with_power():
    # Tight, near-zero differences and ample n -> equivalent + well powered.
    rng = np.random.default_rng(20)
    baseline = rng.normal(0.8, 0.02, size=40)
    treatment = baseline + rng.normal(0.0, 0.01, size=40)
    res = tost(baseline, treatment, margin=0.1, min_power=0.8)
    assert res.non_inferior is True
    assert res.p_value < 0.05
    assert res.power >= 0.8
    assert res.certifiable is True


def test_tost_underpowered_not_certifiable():
    # n too small relative to noise/margin: even if it "passes", not certifiable.
    rng = np.random.default_rng(21)
    baseline = rng.normal(0.8, 0.15, size=3)
    treatment = baseline + rng.normal(0.0, 0.15, size=3)
    res = tost(baseline, treatment, margin=0.02, min_power=0.8)
    assert res.power < 0.8
    assert res.certifiable is False


def test_tost_clear_inferiority_not_equivalent():
    # treatment is well outside the band -> not non-inferior.
    rng = np.random.default_rng(22)
    baseline = rng.normal(0.8, 0.02, size=40)
    treatment = baseline + 0.5  # half a unit worse, margin tiny
    res = tost(baseline, treatment, margin=0.05)
    assert res.non_inferior is False


def test_tost_zero_variance_inside_band():
    baseline = [0.5, 0.5, 0.5, 0.5]
    treatment = [0.5, 0.5, 0.5, 0.5]  # diff exactly 0, sd 0
    res = tost(baseline, treatment, margin=0.1)
    assert res.non_inferior is True
    assert res.certifiable is True


def test_tost_bad_margin_raises():
    with pytest.raises(ValueError):
        tost([0.1, 0.2, 0.3], [0.1, 0.2, 0.3], margin=0.0)


def test_tost_too_few_obs_raises():
    with pytest.raises(ValueError):
        tost([0.1], [0.1], margin=0.1)


# --------------------------------------------------------------------------- #
# Milestone 2 — holm_correction
# --------------------------------------------------------------------------- #


def test_holm_worked_example():
    # Classic worked example. Raw p-values sorted ascending:
    #   0.01, 0.02, 0.03, 0.04  (m = 4)
    # multipliers 4,3,2,1 -> 0.04, 0.06, 0.06, 0.04
    # step-down cumulative max -> 0.04, 0.06, 0.06, 0.06
    raw = [0.04, 0.03, 0.02, 0.01]  # deliberately NOT sorted
    adj = holm_correction(raw)
    # results returned in INPUT order:
    #   0.04 -> rank 4 -> mult 1 -> 0.04, then cummax pushes to 0.06
    #   0.03 -> rank 3 -> mult 2 -> 0.06
    #   0.02 -> rank 2 -> mult 3 -> 0.06
    #   0.01 -> rank 1 -> mult 4 -> 0.04
    assert adj == pytest.approx([0.06, 0.06, 0.06, 0.04])


def test_holm_preserves_input_order():
    raw = [0.5, 0.001, 0.2]
    adj = holm_correction(raw)
    # smallest raw p (0.001 at index 1) must yield the smallest adjusted p.
    assert adj[1] < adj[0]
    assert adj[1] < adj[2]
    # length and positional correspondence preserved.
    assert len(adj) == len(raw)


def test_holm_monotone_along_sorted_order():
    raw = [0.001, 0.009, 0.02, 0.04, 0.5]
    adj = holm_correction(raw)
    # Sort raw, reorder adjusted the same way, assert non-decreasing.
    order = np.argsort(raw)
    adj_sorted = [adj[i] for i in order]
    assert all(
        adj_sorted[i] <= adj_sorted[i + 1] + 1e-12
        for i in range(len(adj_sorted) - 1)
    )


def test_holm_clips_to_one():
    raw = [0.4, 0.5, 0.6]  # multipliers 3,2,1 would exceed 1.0
    adj = holm_correction(raw)
    assert all(a <= 1.0 for a in adj)
    assert max(adj) == pytest.approx(1.0)


def test_holm_empty():
    assert holm_correction([]) == ()


# --------------------------------------------------------------------------- #
# Milestone 2 — leave_one_brief_out
# --------------------------------------------------------------------------- #


def test_leave_one_out_sign_stable_when_consistent():
    # Every brief is a win (negative); dropping any one keeps the mean negative.
    deltas = [-0.30, -0.28, -0.31, -0.29, -0.27, -0.32]
    res = leave_one_brief_out(deltas)
    assert isinstance(res, LeaveOneOut)
    assert len(res.means) == len(deltas)
    assert res.max_mean < 0.0
    assert res.sign_stable is True


def test_leave_one_out_one_outlier_flips_stability():
    # Five tiny wins; one giant positive outlier that, when KEPT in most folds,
    # drives the full mean positive but flips sign when itself removed.
    deltas = [-0.02, -0.02, -0.02, -0.02, 0.5]
    full_mean = float(np.mean(deltas))
    assert full_mean > 0.0  # the outlier dominates the full sample
    res = leave_one_brief_out(deltas)
    # Removing the outlier (last fold) yields a negative mean -> sign flips.
    assert res.means[-1] < 0.0
    assert res.sign_stable is False


def test_leave_one_out_zero_full_mean_not_stable():
    deltas = [-0.5, 0.5]
    res = leave_one_brief_out(deltas)
    assert res.sign_stable is False


def test_leave_one_out_requires_two():
    with pytest.raises(ValueError):
        leave_one_brief_out([-0.3])


# --------------------------------------------------------------------------- #
# Milestone 2 — dedup_threshold_sweep
# --------------------------------------------------------------------------- #


def test_dedup_sweep_sorted_points_and_span():
    rates = {
        0.9: [0.20, 0.22, 0.18],
        0.7: [0.30, 0.32, 0.28],  # given out of order
        0.8: [0.25, 0.25, 0.25],
    }
    sweep = dedup_threshold_sweep(rates)
    assert isinstance(sweep, DedupSweep)
    thresholds = [pt.threshold for pt in sweep.points]
    assert thresholds == sorted(thresholds)  # ascending by threshold
    means = [pt.mean_rate for pt in sweep.points]
    assert sweep.span == pytest.approx(max(means) - min(means))


def test_dedup_sweep_sign_stable_when_all_positive():
    rates = {
        0.6: [0.30, 0.31],
        0.7: [0.25, 0.27],
        0.8: [0.20, 0.22],
    }
    sweep = dedup_threshold_sweep(rates)
    assert sweep.sign_stable is True
    assert sweep.span > 0.0


def test_dedup_sweep_not_sign_stable_when_crosses_zero():
    # mean rates straddle zero across thresholds (rates here are signed deltas).
    rates = {
        0.6: [0.10, 0.12],
        0.7: [-0.05, -0.03],
    }
    sweep = dedup_threshold_sweep(rates)
    assert sweep.sign_stable is False


def test_dedup_sweep_empty_is_vacuously_stable():
    sweep = dedup_threshold_sweep({})
    assert sweep.points == ()
    assert sweep.span == 0.0
    assert sweep.sign_stable is True


# --------------------------------------------------------------------------- #
# Milestone 2 — estimate_noise_floor
# --------------------------------------------------------------------------- #


def test_noise_floor_is_max_of_robust_spreads():
    seed_spread = [0.01, -0.02, 0.015]   # max abs 0.02
    placebo = [0.03, -0.01, 0.005]       # max abs 0.03
    floor = estimate_noise_floor(seed_spread, placebo)
    assert floor == pytest.approx(0.03)


def test_noise_floor_picks_seed_spread_when_larger():
    seed_spread = [0.05, -0.04]   # max abs 0.05
    placebo = [0.01, -0.02]       # max abs 0.02
    floor = estimate_noise_floor(seed_spread, placebo)
    assert floor == pytest.approx(0.05)


def test_noise_floor_one_input_empty():
    floor = estimate_noise_floor([], [0.02, -0.07, 0.01])
    assert floor == pytest.approx(0.07)


def test_noise_floor_both_empty_is_zero():
    assert estimate_noise_floor([], []) == 0.0

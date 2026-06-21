"""Paired tests, bootstrap CIs, length-falsification, and TOST non-inferiority.

This module holds the inferential layer of the harness. Every function operates
on per-brief deltas defined as ``treatment - baseline`` (after the K per-seed
values are averaged to the brief by ``average_to_brief`` so there is no
pseudo-replication). Sign convention matters: a restatement *win* — the
treatment restating less than the baseline — is a **negative** mean delta.

Statistical assumptions are documented one line per function. All randomness is
routed through ``numpy.random.default_rng(seed)`` so results are reproducible:
the same seed yields the same CI.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np


# --------------------------------------------------------------------------- #
# Seed averaging
# --------------------------------------------------------------------------- #


def average_to_brief(seed_values: Mapping[int, float]) -> float:
    """Average the K per-seed values for one brief into a single brief value.

    Assumption: per-seed values are exchangeable replicates of the same brief;
    averaging to the brief is what prevents pseudo-replication in the paired
    tests downstream. Raises ``ValueError`` on an empty mapping.
    """
    if not seed_values:
        raise ValueError("average_to_brief requires >= 1 seed value")
    return float(np.mean(np.asarray(list(seed_values.values()), dtype=float)))


# --------------------------------------------------------------------------- #
# Paired Wilcoxon signed-rank
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PairedTest:
    statistic: float
    p_value: float
    n: int


def paired_wilcoxon(
    baseline: Sequence[float], treatment: Sequence[float]
) -> PairedTest:
    """Paired Wilcoxon signed-rank test on per-brief ``treatment - baseline``.

    Assumption: differences are symmetric about their median under H0; this is a
    distribution-free paired test, robust to the non-normal restatement deltas.
    The degenerate all-zero-delta case (every brief identical across arms) is
    guarded explicitly — scipy would raise — and reported as statistic 0.0,
    p-value 1.0 (no evidence of any difference).
    """
    from scipy.stats import wilcoxon

    b = np.asarray(baseline, dtype=float)
    t = np.asarray(treatment, dtype=float)
    if b.shape != t.shape:
        raise ValueError("baseline and treatment must have equal length")
    n = int(b.shape[0])
    if n == 0:
        raise ValueError("paired_wilcoxon requires >= 1 paired observation")

    deltas = t - b
    # scipy.stats.wilcoxon raises if every difference is zero (no non-zero
    # ranks). Treat "no difference anywhere" as a well-defined null result.
    if np.allclose(deltas, 0.0):
        return PairedTest(statistic=0.0, p_value=1.0, n=n)

    result = wilcoxon(t, b)
    return PairedTest(
        statistic=float(result.statistic),
        p_value=float(result.pvalue),
        n=n,
    )


# --------------------------------------------------------------------------- #
# Percentile bootstrap of the mean delta
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BootstrapCI:
    point: float
    low: float
    high: float
    level: float


def bootstrap_ci(
    deltas: Sequence[float],
    *,
    n_boot: int = 10000,
    level: float = 0.95,
    seed: int = 0,
) -> BootstrapCI:
    """Percentile bootstrap confidence interval for the mean delta.

    Assumption: the empirical distribution of per-brief deltas approximates the
    sampling distribution; resampling briefs with replacement estimates the mean
    delta's CI without a normality assumption. Deterministic via
    ``default_rng(seed)`` — same seed yields the same interval.
    """
    if not 0.0 < level < 1.0:
        raise ValueError("level must be in (0, 1)")
    d = np.asarray(deltas, dtype=float)
    n = int(d.shape[0])
    if n == 0:
        raise ValueError("bootstrap_ci requires >= 1 delta")

    point = float(np.mean(d))
    rng = np.random.default_rng(seed)
    # Resample brief indices with replacement, take the mean each draw.
    idx = rng.integers(0, n, size=(n_boot, n))
    boot_means = d[idx].mean(axis=1)

    alpha = 1.0 - level
    low = float(np.quantile(boot_means, alpha / 2.0))
    high = float(np.quantile(boot_means, 1.0 - alpha / 2.0))
    return BootstrapCI(point=point, low=low, high=high, level=level)


# --------------------------------------------------------------------------- #
# Partial out length (regress restatement delta on wordcount delta)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PartialEffect:
    mean_residual: float
    slope: float
    p_value: float
    survives: bool


def partial_out_length(
    restatement_delta: Sequence[float],
    wordcount_delta: Sequence[float],
    *,
    noise_floor: float = 0.0,
) -> PartialEffect:
    """Effect of restatement after regressing out the wordcount delta.

    Assumption: OLS ``restatement_delta ~ wordcount_delta`` removes any linear
    length confound; the regression *intercept* is the restatement effect at
    zero length change. ``survives`` is True iff that intercept stays in the
    hypothesised winning (negative) direction beyond the noise floor and is
    distinguishable from zero (p < 0.05). A flat intercept, a positive intercept,
    or one within ``noise_floor`` of zero does not survive.
    """
    x = np.asarray(wordcount_delta, dtype=float)
    y = np.asarray(restatement_delta, dtype=float)
    if x.shape != y.shape:
        raise ValueError("restatement_delta and wordcount_delta must match length")
    n = int(y.shape[0])
    if n == 0:
        raise ValueError("partial_out_length requires >= 1 observation")

    import statsmodels.api as sm

    design = sm.add_constant(x, has_constant="add")  # [intercept, slope]
    model = sm.OLS(y, design).fit()

    intercept = float(model.params[0])
    # The "mean residual" is the restatement effect with length held fixed: the
    # OLS intercept (mean of y after the length-explained part is removed).
    mean_residual = intercept

    # slope on wordcount_delta; guard the degenerate single-column case where
    # x is constant (statsmodels drops/NaNs the slope).
    if design.shape[1] > 1:
        slope = float(model.params[1])
        p_value = float(model.pvalues[0])  # H0: intercept == 0
    else:
        slope = 0.0
        p_value = float(model.pvalues[0])

    if not np.isfinite(p_value):
        p_value = 1.0
    if not np.isfinite(slope):
        slope = 0.0

    survives = (
        mean_residual < -abs(noise_floor)
        and p_value < 0.05
    )
    return PartialEffect(
        mean_residual=mean_residual,
        slope=slope,
        p_value=p_value,
        survives=survives,
    )


# --------------------------------------------------------------------------- #
# Length-falsification STOP rule (pre-registered)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LengthFalsification:
    survives_partialling: bool
    length_strip_reproduces: bool
    stop: bool
    detail: str


def length_falsification_stop(
    treated_deltas: Sequence[float],
    wordcount_deltas: Sequence[float],
    length_strip_deltas: Sequence[float],
    *,
    noise_floor: float,
) -> LengthFalsification:
    """Pre-registered length-artifact STOP gate.

    Assumption: a real restatement reduction must (a) survive partialling out the
    wordcount delta and (b) NOT be reproducible by a dumb length-only strip arm.

    ``stop = (NOT survives_partialling) OR length_strip_reproduces``

    * ``survives_partialling`` — ``partial_out_length(treated, wordcount).survives``.
    * ``length_strip_reproduces`` — the length-only-strip arm's mean delta reaches
      (within ``noise_floor``) the treated arm's mean delta, i.e. dumb stripping
      already gets you the gain, so the gain is a length artifact.

    ``stop=True`` means the apparent gain is (likely) a length artifact: DO NOT
    SHIP.
    """
    partial = partial_out_length(
        treated_deltas, wordcount_deltas, noise_floor=noise_floor
    )
    survives_partialling = partial.survives

    treated_mean = float(np.mean(np.asarray(treated_deltas, dtype=float)))
    strip_mean = float(np.mean(np.asarray(length_strip_deltas, dtype=float)))
    # "Reaches" the treated gain: the strip arm's mean delta is at least as
    # negative as the treated mean, up to the noise floor. The deltas are wins
    # when negative, so reproduction means strip_mean <= treated_mean + noise.
    length_strip_reproduces = strip_mean <= treated_mean + abs(noise_floor)

    stop = (not survives_partialling) or length_strip_reproduces

    if stop:
        reasons = []
        if not survives_partialling:
            reasons.append("effect does not survive partialling out length")
        if length_strip_reproduces:
            reasons.append(
                "dumb length-strip arm reproduces the gain "
                f"(strip mean {strip_mean:.4g} <= treated {treated_mean:.4g} "
                f"+ noise {abs(noise_floor):.4g})"
            )
        detail = "STOP: " + "; ".join(reasons)
    else:
        detail = (
            "PROCEED: effect survives partialling out length "
            f"(residual {partial.mean_residual:.4g}, p={partial.p_value:.4g}) "
            "and is not reproduced by length stripping "
            f"(strip mean {strip_mean:.4g} > treated {treated_mean:.4g})"
        )

    return LengthFalsification(
        survives_partialling=survives_partialling,
        length_strip_reproduces=length_strip_reproduces,
        stop=stop,
        detail=detail,
    )


# --------------------------------------------------------------------------- #
# TOST non-inferiority for a guardrail metric
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TostResult:
    non_inferior: bool
    p_value: float
    power: float
    certifiable: bool


def tost(
    baseline: Sequence[float],
    treatment: Sequence[float],
    *,
    margin: float,
    min_power: float = 0.8,
) -> TostResult:
    """Two one-sided tests for non-inferiority of a paired guardrail metric.

    Assumption: paired per-brief differences ``treatment - baseline`` are
    approximately normal; non-inferiority holds if the difference lies inside the
    equivalence band ``[-margin, +margin]`` (we test both one-sided nulls). The
    reported ``p_value`` is the larger of the two one-sided p-values (the TOST
    convention). ``power`` is the achieved power to declare equivalence at this
    margin and n; ``certifiable`` is True only if ``power >= min_power`` — an
    underpowered pass is reported, never called "safe".
    """
    from scipy import stats

    b = np.asarray(baseline, dtype=float)
    t = np.asarray(treatment, dtype=float)
    if b.shape != t.shape:
        raise ValueError("baseline and treatment must have equal length")
    n = int(b.shape[0])
    if n < 2:
        raise ValueError("tost requires >= 2 paired observations")
    if margin <= 0.0:
        raise ValueError("margin must be > 0 for a non-inferiority band")

    diff = t - b
    mean = float(np.mean(diff))
    sd = float(np.std(diff, ddof=1))
    df = n - 1

    if sd == 0.0:
        # Zero variance: difference is exactly `mean`. Non-inferior iff inside
        # the band; p is 0 if strictly inside, 1 otherwise.
        non_inferior = -margin < mean < margin
        p_value = 0.0 if non_inferior else 1.0
        # With no variance the test is fully determined: treat as full power.
        power = 1.0
        return TostResult(
            non_inferior=non_inferior,
            p_value=p_value,
            power=power,
            certifiable=power >= min_power,
        )

    se = sd / np.sqrt(n)
    # Lower one-sided test: H0 diff <= -margin  vs  H1 diff > -margin.
    t_lower = (mean - (-margin)) / se
    p_lower = float(stats.t.sf(t_lower, df))
    # Upper one-sided test: H0 diff >= +margin  vs  H1 diff < +margin.
    t_upper = (mean - margin) / se
    p_upper = float(stats.t.cdf(t_upper, df))

    p_value = max(p_lower, p_upper)
    non_inferior = p_value < 0.05

    # Achieved power to declare equivalence at this margin/n, assuming the true
    # difference is zero (best case for equivalence). Standard TOST power: both
    # one-sided tests reject at alpha when the true diff is 0.
    alpha = 0.05
    t_crit = float(stats.t.ppf(1.0 - alpha, df))
    ncp = margin / se  # noncentrality at true diff = 0, in se units
    # P(reject both) approximated via the standard TOST formula: the chance the
    # observed mean lands inside the band by t_crit on both sides.
    power = float(
        stats.nct.cdf(ncp - t_crit, df, 0.0)
        - stats.nct.cdf(t_crit - ncp, df, 0.0)
    )
    power = float(np.clip(power, 0.0, 1.0))

    return TostResult(
        non_inferior=non_inferior,
        p_value=p_value,
        power=power,
        certifiable=power >= min_power,
    )

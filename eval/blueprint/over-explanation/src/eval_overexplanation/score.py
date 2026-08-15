"""BLUEPRINT-BENCH §2 scorer — subscores, hard gates, composite, `score.json`.

Pure and deterministic. This module does **no statistics and no I/O** — the
orchestrator pre-computes every statistical test (Wilcoxon, TOST, bootstrap,
STOPs) and packs the *inert* results into ``ScoreInputs``, exactly as
``decision.decide`` consumes ``DecisionInputs``. What lives here is arithmetic
(the §2 composite), threshold comparisons (the hard gates), the §2 precedence
table (which *extends* ``decision.decide``, never overrides it), and the
canonical byte-stable serializer for the exact ``score.json`` schema.

Assumptions each formula makes
------------------------------

* ``subscore_linear``: the effect enters as a *positive-is-good* magnitude
  (cost deltas are negated on entry: ``effect = -mean_delta``). The score is 0
  at the noise floor and 100 at the pre-registered target, with a knife-edge
  denominator floor (``min_den``) so a target sitting on the noise floor cannot
  produce a divide-by-near-zero cliff.
* ``outcome_subscore``: a term with no signal (``None``) scores **0 within its
  ORIGINAL weight** — dropping a term must never RAISE the score (monotone,
  fail-closed). The rule is UNIFORM: there is no renormalization path, ever —
  an accounted O3 skip changes routing (gate omitted, row 9 owns power), never
  arithmetic; the ``renormalized`` schema flag is purely descriptive. The
  correctness term is the HOLDOUT mean only — a missing holdout is never
  silently substituted with visible-case O1 (that would hand O2's 0.50 weight
  to the very cases O2 exists to distrust); it scores 0 in its original weight
  and ``correctness_holdout_missing`` is emitted. A missing term is never
  imputed as 0.0-measured and never as 1.0. When correctness and kill are
  *both* missing the subscore is 0.0 outright — bloat alone must never carry
  the dimension — and all-missing is 0.0 too.
* ``composite``: weighted sum over dimension subscores; every weighted
  dimension must be present or ``ValueError`` — a partial composite is never
  emitted.
* Gates compare orchestrator-supplied raw values against thresholds that are
  **parameters** (``ScoreThresholds``, fed from the manifest's calibrated
  ``bench.*`` fields); the defaults are BENCHMARK.md's frozen demo values.
  Fail-closed: a gate whose input has no signal where the contract demands one
  (O1 ``None``; O2/O3 ``None`` without an over-cap accounted skip) FAILS; only
  a *legitimately* skippable state (O2/O3 ``None`` with the term's skipped
  fraction over the cap — row 9 then owns it — or L4 non-importing spec code)
  emits **no GateCheck at all** — skipped, never a pass. O2/O3 skips are
  surfaced through the skipped fractions; L4's no-signal state is surfaced
  through ``ArmScore.l4_no_signal`` (§1-L4: "no signal (emitted + flagged)")
  — always rendered, so a null leaves a greppable trace in score.json even
  though it blocks nothing on its own.
* The ``dimensions.<D>.metrics`` payload for every id in ``DERIVABLE_METRIC_IDS``
  is DERIVED here from the operative fields the scorer already holds (§2's
  packer coupling rule extended to the metrics surface) — never accepted as
  packer-supplied numbers. A packed value for a derived field is at most a
  cross-check the CLI performs at load time (mismatch = load error); this
  module always renders the derived value regardless, so the metrics surface
  can never contradict the gate/subscore/win-test it reports (repro this
  fixed: packed ``metrics.C1.mean_delta=-0.95`` next to a subscore computed
  from the true ``-0.11``). Fields with no operative twin (C4's purity, C1's
  raw ``p``/``n``, U1's ``spend_index``, ...) stay pure packer passthrough.
* Precedence (§2, first match wins): only the **treatment arm** (named by
  ``ScoreInputs.treatment_arm`` and looked up among the packed arms) drives the
  run verdict; other packed arms are scored and reported but never block the
  run. Rows 0/2/5 yield ``scorable: false`` with ``arms = ()`` (no partial
  numbers); row 1 emits no per-arm numbers either. A not-scorable report
  carries the fail-closed verdict ``DO_NOT_SHIP`` so it can never read as
  shippable.
* Leakage (L1–L4) failing voids that arm's U and O subscores to 0.0 —
  arm-local, not run-wide, and *not* a §2-row-6 hard gate. When the voided arm
  is the **treatment**, §2 row 7 blocks the run outright (``DO_NOT_SHIP``,
  exit 1): a detected leak must never ship.
* The O3 gate is fail-closed against controllable signal loss: ``o3_kill_rate``
  of ``None`` with no accounted skip (``o3_skipped_fraction == 0``, or within
  the cap where an aggregate must exist) FAILS the gate; only an over-cap
  skipped fraction routes to the §2 row-9 UNDERPOWERED path instead. The O2
  gate MIRRORS this exactly: ``o2_overfit`` of ``None`` at or under the O2
  skip cap FAILS the gate — never a silent skip.
* Guardrail TOSTs travel as RAW numerics (``ArmInputs.tost``: one
  :class:`TostStats` per family C3/C8/U2/U3/O1/O3), exactly like C1/U1: the
  scorer RECOMPUTES both flags here — ``non_inferior`` iff the 90% CI lies
  strictly inside ``(-margin, +margin)`` with the margin taken from
  ``thresholds.tost_margins`` (the manifest, never the packer, is the margin
  authority), and ``certifiable`` iff ``achieved_power >= thresholds.
  min_power``. Neither flag is ever accepted as a caller boolean (the CLI
  treats packed booleans as at most cross-checks). An ABSENT family is
  no-signal and fail-closed on both legs: its non-inferiority gate FAILS
  (row 6) and it is NOT certifiable (row 8). The two legs stay split: a C8
  POWER gap (in-band CI, low power) passes the row-6 gate and routes to
  row 8 UNDERPOWERED, never to a row-6 DO_NOT_SHIP.
* The §1-C1 gate threshold has an absolute floor: the win requires
  ``mean_delta <= -max(c1_gate_floor, c1_gate_noise_multiple x nf_C)`` — a
  zero or degenerate noise floor must never make any negative delta a free
  "win" (the same convention as ``T_C``'s and ``T_U``'s floors).
* Duplicate packed ``arm_id``s raise ``ValueError`` in ``score_report``
  (defense in depth behind the CLI's load error): with duplicates, the
  first-match treatment lookup and the last-wins rendered arms dict would
  contradict each other inside one report.
* ``c0_leak_hits`` has an explicit no-signal state: ``None`` means at least
  one generate cell was never scanned (``leak_scanned: false``) and FAILS the
  C0 gate — an unscanned transcript is no signal, never a pass.
* ``dimensions.O.renormalized`` means exactly one thing: an accounted
  OVER-cap O3 skip dropped the kill term (the only state where a missing kill
  rate is not itself an O3 gate failure). It is purely descriptive — the
  arithmetic never renormalizes — and is computed regardless of leakage
  voiding, so it never misdescribes a blocked run as renormalized nor an
  over-cap skip under a leak as measured.
* C1's and U1's §1 win sub-thresholds (Holm p, CI upper bound, gate-multiple
  mean delta, LOBO sign stability, large_realistic sign; U1: Holm p and the
  ``T_U`` margin) are recomputed HERE from the raw ``C1Stats``/``U1Stats`` the
  orchestrator packs — never accepted as a caller-supplied boolean.
* ``composite >= composite_pass`` is NECESSARY, never sufficient: a treatment
  arm below the pass threshold is routed to DO_NOT_SHIP (the precedence row
  after the C1/U1 win), and ``authorizes_ship`` stays ``false`` always.
* ``render_score_json`` is canonical: ``json.dumps(obj, sort_keys=True,
  separators=(",", ":"), ensure_ascii=False)``. Derived fractions are rounded
  to 3 decimals and subscores/composite to 2 at serialization only (the
  dataclasses keep full precision); rounding is deterministic, so the output is
  byte-stable. ``generated_at`` is injected by the caller, never read from a
  clock, so identical inputs render identical bytes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .decision import Verdict

if TYPE_CHECKING:  # import-light: the mapping takes the manifest's dataclass
    from .manifest import BenchThresholds

SCHEMA = "blueprint-bench/1"

#: §2 row 6 — a failure here is a run-blocking DO_NOT_SHIP (via the treatment arm).
HARD_GATE_IDS = frozenset({
    "C0_generate_isolation",
    "C2_must_retention",
    "C3_coverage_noninferiority",
    "C7_merge_fidelity",
    "C8_grammaticality",
    "U0_isolation",
    "U2_turns_noninferiority",
    "U3_dead_end_cap",
    "U3_deadend_noninferiority",
    "U4_completion",
    "U5_clarifying_questions",
    "O1_correctness",
    "O2_holdout_overfit",
    "O3_mutation_kill",
    "O4_workaround_lint",
})

#: §1 L-table — a failure here voids the arm's U and O subscores (arm-local).
LEAK_GATE_IDS = frozenset({
    "L1_code_fraction",
    "L2_reference_containment",
    "L3_impl_spec_copy",
    "L4_spec_only_correctness",
})

#: §2 row 7 — TOST families whose ``certifiable`` flag is required, by dimension.
TOST_FAMILIES: Mapping[str, tuple[str, ...]] = {
    "C": ("C3", "C8"),
    "U": ("U2", "U3"),
    "O": ("O1", "O3"),
}

#: Every TOST'd guardrail family, in fixed order — the required key set of
#: ``ArmInputs.tost`` and of the score transport's ``tost`` map.
ALL_TOST_FAMILIES: tuple[str, ...] = ("C3", "C8", "U2", "U3", "O1", "O3")

_PASSING_VERDICTS = frozenset({
    Verdict.SHIP_TREATMENT,
    Verdict.SHIP_ONELINER,
    Verdict.SHIP_EVALUATOR_ONLY,
})


# --------------------------------------------------------------------------- #
# Thresholds — PARAMETERS fed from the manifest; defaults = BENCHMARK.md frozen
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ScoreThresholds:
    """Every §2/§4 number the scorer compares against, as one inert bundle.

    The orchestrator builds this from the manifest's ``bench.*`` fields (the
    calibrated caps included); the defaults are the BENCHMARK.md frozen demo
    values so a default-constructed instance IS the pre-registered contract.
    """

    weights: Mapping[str, float] = field(
        default_factory=lambda: {"C": 0.30, "U": 0.30, "O": 0.40})
    composite_pass: float = 70.0
    c_target_floor: float = 0.05        # T_C = max(this, c_scale_noise_multiple * nf_C)
    #: §2 composite SCALE multiple: T_C = max(c_target_floor, this * nf_C).
    #: Distinct from ``c1_gate_noise_multiple`` by name ON PURPOSE — wiring the
    #: §1 C1-gate multiple (2.0) into the scale would halve T_C and inflate S_C.
    c_scale_noise_multiple: float = 4.0
    #: §1 C1 GATE multiple: the win requires mean Δ ≤ −this × nf_C (bench 2.0).
    c1_gate_noise_multiple: float = 2.0
    #: §1 C1 GATE absolute floor: the gate threshold is
    #: max(this, c1_gate_noise_multiple × nf_C) — a zero/degenerate noise
    #: floor must never make any negative delta a free win (same convention
    #: as the T_C/T_U floors).
    c1_gate_floor: float = 0.025
    win_alpha: float = 0.05             # §1 C1: Holm-adjusted p must be < this
    c_min_den: float = 0.02             # knife-edge floor for den_C
    u_target_ln: float = 0.1054         # |ln 0.9| — a 10% spend saving
    u_noise_multiple: float = 2.0       # T_U = max(u_target_ln, this * nf_U)
    u_min_den: float = 0.05             # knife-edge floor for den_U
    o_weight_correctness: float = 0.50
    o_weight_kill: float = 0.30
    o_weight_bloat: float = 0.20
    o5_bloat_cap_ln: float = 1.0986     # ln 3, soft cap
    frag_rate_cap: float = 0.05         # calibrated upward from A0/A0_prime
    dead_end_cap: int = 6
    o1_min_correctness: float = 0.90
    o2_max_overfit: float = 0.10
    o3_min_kill_rate: float = 0.75
    leak_code_frac_cap: float = 0.15    # L1, calibrated floor
    leak_reference_cap: float = 0.25    # L2
    leak_copy_cap: float = 0.30         # L3
    leak_spec_only_cap: float = 0.50    # L4: >= this means the spec IS the impl
    max_incomplete_fraction: float = 0.10
    max_merge_skipped_fraction: float = 0.30
    max_o_term_skipped_fraction: float = 0.30
    min_stratum_n: int = 3
    n_full_scale: int = 18              # below this, SHIP is ceiling-capped
    #: §4 pre-registered TOST margins per guardrail family — carried so the
    #: manifest, not any orchestrator constant, is the margin authority.
    tost_margins: Mapping[str, float] = field(
        default_factory=lambda: {"C3": 0.05, "C8": 0.02, "U2": 1.0,
                                 "U3": 1.0, "O1": 0.05, "O3": 0.10})
    #: §4 minimum achieved TOST power for ``certifiable`` (row 8).
    min_power: float = 0.8


def thresholds_from_bench(bench: "BenchThresholds") -> ScoreThresholds:
    """Map the manifest's frozen ``bench.*`` fields onto ``ScoreThresholds``.

    The manifest — never this module's Python defaults — is the source of
    truth for a scored run; the defaults exist only as the documented fallback
    when no ``bench`` block is registered. The two C noise multiples map onto
    their two DISTINCT fields (§4): sharing one value would halve ``T_C``.
    EVERY operative number is consumed — ``win_alpha``, the knife-edge
    ``min_den`` floors, ``u_noise_multiple``, the S_O ``o_weight_*`` terms,
    ``max_o_term_skipped_fraction``, ``tost_margins`` and ``min_power``
    included — so an edit to any of them moves the manifest's
    ``content_hash``; a threshold living only as a Python default would be
    editable outside the audit trail. Only ``n_full_scale`` (a structural
    panel size, not a §4 threshold) keeps its frozen BENCHMARK.md value.
    """
    return ScoreThresholds(
        weights=dict(bench.weights),
        composite_pass=bench.composite_pass,
        c_target_floor=bench.c_target_floor,
        c_scale_noise_multiple=bench.c_scale_noise_multiple,
        c1_gate_noise_multiple=bench.c1_gate_noise_multiple,
        c1_gate_floor=bench.c1_gate_floor,
        win_alpha=bench.win_alpha,
        c_min_den=bench.c_min_den,
        u_target_ln=bench.u_target_ln,
        u_noise_multiple=bench.u_noise_multiple,
        u_min_den=bench.u_min_den,
        o_weight_correctness=bench.o_weight_correctness,
        o_weight_kill=bench.o_weight_kill,
        o_weight_bloat=bench.o_weight_bloat,
        o5_bloat_cap_ln=bench.o5_bloat_cap_ln,
        frag_rate_cap=bench.frag_rate_cap,
        dead_end_cap=bench.dead_end_cap,
        o1_min_correctness=bench.o1_min_correctness,
        o2_max_overfit=bench.o2_max_overfit,
        o3_min_kill_rate=bench.o3_min_kill_rate,
        leak_code_frac_cap=bench.leak_caps["code_frac"],
        leak_reference_cap=bench.leak_caps["reference"],
        leak_copy_cap=bench.leak_caps["copy"],
        leak_spec_only_cap=bench.leak_caps["spec_only_correctness"],
        max_incomplete_fraction=bench.max_incomplete_fraction,
        max_merge_skipped_fraction=bench.max_merge_skipped_fraction,
        max_o_term_skipped_fraction=bench.max_o_term_skipped_fraction,
        min_stratum_n=bench.min_stratum_n,
        tost_margins=dict(bench.tost_margins),
        min_power=bench.min_power,
    )


# --------------------------------------------------------------------------- #
# Value objects (§3 contract shapes)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GateCheck:
    """One hard-gate or leakage-gate comparison, fully explained."""

    id: str
    value: float
    threshold: float
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class MetricValue:
    """One reported metric: headline number + the exact schema payload.

    ``value`` is the headline number for programmatic access; ``extra`` carries
    the metric's schema keys verbatim (e.g. ``{"mean_delta": -0.11, "p": 0.008}``).
    ``ci`` / ``p_holm`` are lifted into the payload at serialization when set.
    """

    id: str
    value: float
    ci: tuple[float, float] | None = None
    p_holm: float | None = None
    extra: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DimensionScore:
    """One dimension's metrics, subscore and power verdict.

    ``covariates`` is populated for C only; the ``renormalized`` /
    ``o*_skipped_fraction`` / ``correctness_holdout_missing`` group for O only
    — ``None`` fields are omitted from the serialized schema, reproducing the
    per-dimension key sets exactly. ``renormalized`` is purely descriptive
    and means exactly one thing: an accounted OVER-cap O3 skip dropped the
    kill term (the only state where a missing kill rate is not itself an O3
    gate failure). It never changes arithmetic — every missing term scores 0
    in its ORIGINAL weight — and it is computed from the kill signal and the
    skip fraction alone, independent of leakage voiding, so it is never True
    on an under-cap gate-failing run and never False merely because the arm
    was voided.
    ``correctness_holdout_missing`` flags that S_O's correctness term had no
    holdout signal and was scored 0 — never silently substituted with the
    visible-case O1 mean.
    """

    name: str
    metrics: tuple[MetricValue, ...]
    subscore: float
    verdict: str
    covariates: Mapping[str, float] | None = None
    renormalized: bool | None = None
    o2_skipped_fraction: float | None = None
    o3_skipped_fraction: float | None = None
    correctness_holdout_missing: bool | None = None


@dataclass(frozen=True)
class CellCounts:
    """Per-stage cell bookkeeping for one arm (fail-closed accounting).

    ``missing``/``timeout``/``error`` cells were *excluded and counted* —
    never imputed, never zeros — so the fractions below are the §2 row-5
    scorability inputs, not cosmetics.
    """

    expected: int
    complete: int
    missing: int = 0
    timeout: int = 0
    error: int = 0
    retried: int = 0
    merge_skipped: int = 0
    mutations_skipped: int = 0
    holdout_skipped: int = 0

    @property
    def incomplete_fraction(self) -> float:
        if self.expected <= 0:
            return 0.0
        return (self.missing + self.timeout + self.error) / self.expected

    @property
    def merge_skipped_fraction(self) -> float:
        if self.expected <= 0:
            return 0.0
        return self.merge_skipped / self.expected


@dataclass(frozen=True)
class ArmScore:
    """One arm's scored output: gates, dimensions, composite."""

    arm_id: str
    cells: Mapping[str, CellCounts]          # keyed "generate" | "implement"
    gates: tuple[GateCheck, ...]
    dimensions: tuple[DimensionScore, ...]
    leakage_voided: bool
    #: §1-L4 "no signal (emitted + flagged)": True iff this arm's
    #: ``l4_spec_only_correctness`` was null (assembled spec code did not
    #: import). L4 emits no GateCheck and never blocks on its own (L1-L3
    #: carry the gate) — this is the score.json trace that a null left no
    #: OTHER footprint. Always rendered, independent of ``leakage_voided``.
    l4_no_signal: bool
    composite: float | None

    @property
    def gates_failed(self) -> tuple[str, ...]:
        return tuple(g.id for g in self.gates if not g.passed)

    @property
    def gates_blocked(self) -> bool:
        """True iff a §2-row-6 HARD gate failed (leak gates void, not block)."""
        return any(not g.passed and g.id in HARD_GATE_IDS for g in self.gates)


@dataclass(frozen=True)
class Stops:
    """The four pre-registered STOPs (§2 row 4), already evaluated upstream."""

    c_length_falsification: bool = False
    c_distinct_dilution: bool = False
    u_below_detectable_floor: bool = False
    u_length_falsification: bool = False

    @property
    def fired(self) -> bool:
        return any(self.names())

    def names(self) -> tuple[str, ...]:
        return tuple(
            name for name, flag in (
                ("c_length_falsification", self.c_length_falsification),
                ("c_distinct_dilution", self.c_distinct_dilution),
                ("u_below_detectable_floor", self.u_below_detectable_floor),
                ("u_length_falsification", self.u_length_falsification),
            ) if flag
        )


@dataclass(frozen=True)
class Budget:
    """Budget layer — never scored, only a row-5 scorability input."""

    spent_usd: float
    projected_usd: float
    max_usd: float
    exhausted: bool


@dataclass(frozen=True)
class C1Stats:
    """Raw §1-C1 statistics for one arm, packed inert by the orchestrator.

    The scorer recomputes every C1 win sub-threshold from these values itself
    (``c1_failures``); it never accepts a pre-collapsed "C1 passed" boolean.
    Sign convention as everywhere: negative delta = win.
    """

    mean_delta: float                   # mean Δ_b over briefs
    ci: tuple[float, float]             # bootstrap CI on the mean delta
    p_holm: float                       # Holm-adjusted p over the win family
    sign_stable: bool                   # leave_one_brief_out.sign_stable
    large_realistic_delta: float        # mean Δ on the large_realistic subset


@dataclass(frozen=True)
class TostStats:
    """Raw TOST numerics for one guardrail family, packed inert.

    The scorer recomputes both TOST flags from these values itself (exactly
    like ``C1Stats``/``U1Stats``): ``non_inferior`` iff ``ci90`` lies strictly
    inside ``(-margin, +margin)`` — the 90% CI inside the band is TOST at
    alpha 0.05 — with the margin read from ``ScoreThresholds.tost_margins``
    (the manifest is the margin authority), and ``certifiable`` iff
    ``achieved_power >= ScoreThresholds.min_power``. ``margin`` records the
    margin the RUNNER used; the CLI load-errors when it contradicts the
    manifest, so a run tested against the wrong band can never score.
    """

    estimate: float                     # mean paired difference (treat - base)
    ci90: tuple[float, float]           # 90% CI on the difference
    p_value: float                      # max of the two one-sided TOST p's
    achieved_power: float               # power to declare equivalence
    margin: float                       # margin used by the runner (cross-checked)


def tost_non_inferior(stats: TostStats | None, margin: float) -> bool:
    """§1 non-inferiority leg, recomputed from raw numerics. Fail-closed.

    ``None`` (no packed TOST signal for the family) is never a pass. A 90% CI
    strictly inside ``(-margin, +margin)`` is TOST non-inferiority at alpha
    0.05; the ``margin`` must come from the manifest's ``tost_margins``.
    """
    if stats is None:
        return False
    return -margin < stats.ci90[0] and stats.ci90[1] < margin


def tost_certifiable(stats: TostStats | None, min_power: float) -> bool:
    """§2 row-8 certifiability leg, recomputed from raw numerics. Fail-closed.

    ``None`` (no packed TOST signal) is NOT certifiable — an unmeasured
    guardrail is never called "safe".
    """
    return stats is not None and stats.achieved_power >= min_power


@dataclass(frozen=True)
class GateValues:
    """Raw per-arm values behind every gate, pre-computed by the orchestrator.

    Every field is required on purpose — a forgotten field must be a
    ``TypeError`` at packing time, never a silently-green gate. ``None`` marks
    the contract's *no-signal* states (C0 scan never ran, O1 oracle never ran,
    O2 holdout absent, O3 smoke/mutations absent, L4 spec code non-importing);
    C0/O1 ``None`` are fail-closed gate FAILURES, and O2/O3 ``None`` are
    FAILURES unless the term's skip is accounted past the cap (then the row-9
    UNDERPOWERED path owns it).

    The TOST non-inferiority legs (C3, C8, U2, U3, O1, O3) do NOT live here:
    they are recomputed by the scorer from the raw ``ArmInputs.tost``
    statistics against the manifest margins — never accepted as caller
    booleans (the last collapsed-boolean class, fixed the same way as
    C1/U1). ``c0_leak_hits`` is the C-stage generate-cell analogue of §1-U0:
    leak-pattern hits summed over all generate-cell transcripts, populated by
    the orchestrator from ``run-arm.sh`` cells; ``None`` when ANY generate
    cell records ``leak_scanned: false`` — no signal FAILS the gate, never
    passes it.
    """

    c0_leak_hits: int | None            # generate-cell leak hits; gate requires 0; None = unscanned => FAILS
    c2_dropped_must: int
    c7_merge_failures: int              # non-skipped cells whose merge_fidelity.ok is False
    c8_frag_rate: float
    u0_prompt_sha_ok: bool
    u0_leak_hits: int
    u3_max_dead_ends: int               # max per-cell de over U cells
    u4_completion_fraction: float       # fraction of U cells with subtype == "success"
    u5_clarifying_questions: int
    o1_correctness: float | None        # visible-case mean; None => no signal => gate FAILS
    o1_regressed_cells: tuple[str, ...]
    o2_overfit: float | None            # None => holdout skipped => gate omitted, never a pass
    o3_kill_rate: float | None          # None => no O3 signal (see class docstring)
    o3_invalid: int                     # invalid mutants; gate requires 0
    o4_workarounds: int
    l1_code_frac: float
    l2_reference_containment: float
    l3_copy_containment: float
    l4_spec_only_correctness: float | None  # None => non-importing => no signal, L1-L3 carry the gate


@dataclass(frozen=True)
class U1Stats:
    """Raw §1-U1 win statistics for one arm, packed inert by the orchestrator.

    The scorer recomputes the U1 win sub-thresholds from these values itself
    (``u1_failures``, symmetric to ``c1_failures``): Holm-adjusted p and the
    ``T_U = max(u_target_ln, 2 x noise_floor_U)`` margin. Never a caller
    boolean. Sign convention as everywhere: negative delta = win.
    """

    mean_delta: float                   # mean Δ_b of ln(spend) over briefs
    p_holm: float                       # Holm-adjusted p over the win family


@dataclass(frozen=True)
class ArmInputs:
    """Everything the scorer needs about one arm, already computed and inert.

    ``tost`` carries the RAW per-family TOST numerics (``ALL_TOST_FAMILIES``
    keys); an absent family is no-signal and fail-closed on both recomputed
    legs — its non-inferiority gate FAILS (row 6, wherever that gate is
    evaluated) and it is NOT certifiable (row 8). The scorer never accepts
    a pre-collapsed non_inferior/certifiable boolean.
    """

    arm_id: str
    cells: Mapping[str, CellCounts]
    gate_values: GateValues
    tost: Mapping[str, TostStats]           # keys from ALL_TOST_FAMILIES; absent = no signal (fail-closed)
    c1: C1Stats                             # raw §1-C1 statistics (negative = win)
    u1: U1Stats                             # raw §1-U1 statistics (negative = win)
    correctness_holdout: float | None       # None => no holdout signal => S_O term 0, flagged
    bloat_ln: float
    # NOTE: the O3 kill rate lives ONLY in ``gate_values.o3_kill_rate`` — one
    # source of truth for both the gate and the S_O term, so the subscore can
    # never see a kill rate the gate did not.
    o2_skipped_fraction: float = 0.0
    o3_skipped_fraction: float = 0.0
    metrics: Mapping[str, tuple[MetricValue, ...]] = field(default_factory=dict)
    covariates: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreInputs:
    """The §2 scorer's entire world, packed by the orchestrator."""

    manifest_content_hash: str
    manifest_hash_matches: bool
    manifest_problems: tuple[str, ...]
    generated_at: str                       # injected, never read from a clock
    instrument_trusted: bool
    benchmark_trusted: bool
    a3b_fails_grammaticality: bool
    stops: Stops
    noise_floor_c: float
    noise_floor_u: float
    n_briefs: int
    n_buildable: int
    k_seeds: int
    extractor_families: tuple[str, ...]
    strata_coverage: Mapping[str, Mapping[str, int]]
    baseline_arm: str
    treatment_arm: str                      # must be among ``arms`` to be scorable
    arms: tuple[ArmInputs, ...]
    budget: Budget
    a4_captures_effect: bool
    beats_a3_fair: bool
    beats_a2_placebo: bool
    beats_a3_fair_detail: str = ""
    beats_a2_placebo_detail: str = ""
    thresholds: ScoreThresholds = field(default_factory=ScoreThresholds)


@dataclass(frozen=True)
class ScoreReport:
    """The full scored (or fail-closed not-scorable) run, ready to serialize."""

    scorable: bool
    reason: str | None
    verdict: Verdict
    ceiling: str
    arms: tuple[ArmScore, ...]
    verdict_reasons: tuple[str, ...]
    manifest_content_hash: str
    generated_at: str
    instrument_trusted: bool
    benchmark_trusted: bool
    n_briefs: int
    n_buildable: int
    k_seeds: int
    extractor_families: tuple[str, ...]
    noise_floor_c: float
    noise_floor_u: float
    strata_certifiable: bool
    strata_coverage: Mapping[str, Mapping[str, int]]
    stops: Stops
    baseline_arm: str
    treatment_arm: str
    budget: Budget
    weights: Mapping[str, float]
    composite_pass: float
    human_read_required: bool = True
    schema: str = SCHEMA


# --------------------------------------------------------------------------- #
# Subscores and composite (§2 arithmetic)
# --------------------------------------------------------------------------- #


def _clip(x: float) -> float:
    return min(1.0, max(0.0, x))


def subscore_linear(effect: float, noise_floor: float, target: float,
                    *, min_den: float) -> float:
    """0 at the noise floor, 100 at the target, linearly between, clipped.

    ``effect`` is positive-is-good (negate cost deltas on entry). ``min_den``
    is the knife-edge floor: when ``target - noise_floor`` collapses, the slope
    stays bounded instead of exploding.
    """
    den = max(target - noise_floor, min_den)
    return 100.0 * _clip((effect - noise_floor) / den)


def outcome_subscore(correctness: float | None, kill_rate: float | None,
                     bloat_ln: float | None, *,
                     correctness_weight: float = 0.50,
                     kill_weight: float = 0.30,
                     bloat_weight: float = 0.20,
                     bloat_cap_ln: float = 1.0986) -> float:
    """S_O: weighted correctness + mutation kill + inverse bloat, in [0, 100].

    Missing-signal rule (§2), UNIFORM, monotone and fail-closed:

    * correctness AND kill both ``None`` => 0.0 outright — bloat alone must
      never carry the dimension (and all-missing is 0.0 a fortiori);
    * every ``None`` term scores 0 within its ORIGINAL weight — the
      denominator is NEVER renormalized, so a missing term can never score
      above that term measured at any value (missing == the worst measurable
      value, never better). Accounted skips change ROUTING upstream (gate
      omitted, row 9 forces O underpowered), never this arithmetic — the old
      renormalization exception let a dropped kill term outscore a measured
      one and is gone.
    """
    if correctness is None and kill_rate is None:
        return 0.0
    total_weight = correctness_weight + kill_weight + bloat_weight
    if total_weight <= 0.0:
        return 0.0
    numerator = 0.0
    if correctness is not None:
        numerator += correctness_weight * _clip(correctness)
    if kill_rate is not None:
        numerator += kill_weight * _clip(kill_rate)
    if bloat_ln is not None:
        numerator += bloat_weight * _clip(1.0 - max(0.0, bloat_ln) / bloat_cap_ln)
    return 100.0 * numerator / total_weight


def composite(dims: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """Weighted composite over dimension subscores.

    Every weighted dimension must be present — a partial composite is never
    emitted (``ValueError`` instead). Summation order is sorted by key so the
    float result is deterministic regardless of mapping order.
    """
    missing = sorted(set(weights) - set(dims))
    if missing:
        raise ValueError(
            f"composite refused: no subscore for weighted dimension(s) {missing} "
            "(a partial composite is never emitted)"
        )
    return sum(w * dims[name] for name, w in sorted(weights.items()))


# --------------------------------------------------------------------------- #
# Gates
# --------------------------------------------------------------------------- #


def non_inferior_flags(tost: Mapping[str, TostStats],
                       t: ScoreThresholds) -> dict[str, bool]:
    """Recomputed §1 non-inferiority per family, against the manifest margins.

    An absent family or an absent margin is fail-closed ``False`` — no
    signal, never a pass. PUBLIC: the CLI packer reuses this exact
    computation to cross-check packed ``metrics[...].extra.tost`` payloads
    against the same recomputation the gates use (``derive_metric_fields``),
    so a packed tost sub-object can never show a different verdict than the
    gate it describes.
    """
    return {
        family: tost_non_inferior(tost.get(family),
                                  float(t.tost_margins.get(family, 0.0)))
        for family in ALL_TOST_FAMILIES
    }


# --------------------------------------------------------------------------- #
# Metric-payload derivation (§2 coupling rule extended to `dimensions.*.metrics`)
# --------------------------------------------------------------------------- #

#: Metric ids, by dimension, whose payload the scorer DERIVES from operative
#: fields it already holds for gates/subscores/§1 win tests — the coupling
#: rule ``cli.py`` already applies to ``gate_values``/``tost`` extended to the
#: one remaining unchecked packer-passthrough surface. An id absent here (C4,
#: the deferred purity metric) has no operative twin and stays pure packer
#: passthrough, documented as such.
DERIVABLE_METRIC_IDS: Mapping[str, tuple[str, ...]] = {
    "C": ("C1", "C3", "C8"),
    "U": ("U1", "U2", "U3", "U5"),
    "O": ("O1", "O2", "O3", "O4", "O5"),
}


def _tost_metric_obj(family: str, arm: "ArmInputs", t: ScoreThresholds,
                     ni: Mapping[str, bool]) -> dict[str, object]:
    stats = arm.tost.get(family)
    return {
        "non_inferior": bool(ni.get(family, False)),
        "power": None if stats is None else stats.achieved_power,
        "certifiable": tost_certifiable(stats, t.min_power),
    }


def derive_metric_fields(metric_id: str, arm: "ArmInputs", t: ScoreThresholds,
                         ni: Mapping[str, bool],
                         ) -> Mapping[str, object] | None:
    """The authoritative field values for one metric id, or ``None``.

    ``None`` means the id has no operative twin (e.g. C4) and stays pure
    packer passthrough. Every field returned here duplicates a value the
    scorer already computes elsewhere (a gate, a subscore input, a §1 win
    test) — this IS the single source of truth for the
    ``dimensions.<D>.metrics`` score.json surface: ``_score_arm`` always
    renders these values regardless of what a packer sent, and the CLI
    cross-checks any packed value against this before that (mismatch = load
    error), so the rendered artifact can never show a metric number that
    contradicts the operative field it is supposed to report.

    Fields NOT named here for a given id (C1's raw ``p``/``n``, U1's
    ``spend_index``, U3's ``mean``, U5's ``trailing_question_marks``, O2's
    ``skipped_briefs``, O3's ``smoke_failed_cells``) have no operative twin
    either and stay packer passthrough within that id's payload.
    """
    v = arm.gate_values
    if metric_id == "C1":
        return {"mean_delta": arm.c1.mean_delta, "ci": tuple(arm.c1.ci),
                "p_holm": arm.c1.p_holm, "sign_stable": arm.c1.sign_stable,
                "large_realistic_delta": arm.c1.large_realistic_delta}
    if metric_id == "C3":
        return {"tost": _tost_metric_obj("C3", arm, t, ni)}
    if metric_id == "C8":
        return {"frag_rate": v.c8_frag_rate, "cap": t.frag_rate_cap,
                "tost": _tost_metric_obj("C8", arm, t, ni)}
    if metric_id == "U1":
        return {"mean_delta": arm.u1.mean_delta, "p_holm": arm.u1.p_holm}
    if metric_id == "U2":
        return {"tost": _tost_metric_obj("U2", arm, t, ni)}
    if metric_id == "U3":
        return {"max_cell": v.u3_max_dead_ends,
                "tost": _tost_metric_obj("U3", arm, t, ni)}
    if metric_id == "U5":
        return {"clarifying_questions": v.u5_clarifying_questions}
    if metric_id == "O1":
        return {"correctness": v.o1_correctness,
                "regressed_cells": list(v.o1_regressed_cells)}
    if metric_id == "O2":
        return {"overfit": v.o2_overfit}
    if metric_id == "O3":
        return {"kill_rate": v.o3_kill_rate, "invalid": v.o3_invalid}
    if metric_id == "O4":
        return {"workarounds": v.o4_workarounds}
    if metric_id == "O5":
        return {"bloat_ln": arm.bloat_ln}
    return None


def _merge_derived(metric: MetricValue, derived: Mapping[str, object]) -> MetricValue:
    """Overlay derived (authoritative) fields onto a packed ``MetricValue``.

    ``ci``/``p_holm`` are the dataclass's own top-level fields; every other
    derived key lands in ``extra``, overriding whatever the packer sent.
    Passthrough-only keys already in ``extra`` (not named by the derivation)
    survive untouched.
    """
    extra = dict(metric.extra)
    ci = metric.ci
    p_holm = metric.p_holm
    for key, value in derived.items():
        if key == "ci":
            ci = tuple(value)  # type: ignore[arg-type]
        elif key == "p_holm":
            p_holm = value  # type: ignore[assignment]
        else:
            extra[key] = value
    return MetricValue(id=metric.id, value=metric.value, ci=ci, p_holm=p_holm,
                       extra=extra)


def _synthetic_metric(metric_id: str, derived: Mapping[str, object]) -> MetricValue:
    """Build a metric entry purely from derived fields (id absent from the
    packed transport) — the schema's per-dimension metric ids are always
    rendered when the scorer holds the operative data, packer completeness
    notwithstanding."""
    extra = dict(derived)
    ci = extra.pop("ci", None)
    p_holm = extra.pop("p_holm", None)
    return MetricValue(id=metric_id, value=0.0,
                       ci=None if ci is None else tuple(ci),
                       p_holm=p_holm, extra=extra)


def _dimension_metrics(dim: str, arm: "ArmInputs", t: ScoreThresholds,
                       ni: Mapping[str, bool]) -> tuple[MetricValue, ...]:
    """Every packed metric for ``dim``, derived fields merged in, plus a
    synthesized entry for any derivable id the packer omitted entirely."""
    out: list[MetricValue] = []
    seen: set[str] = set()
    for metric in arm.metrics.get(dim, ()):
        derived = derive_metric_fields(metric.id, arm, t, ni)
        out.append(metric if derived is None else _merge_derived(metric, derived))
        seen.add(metric.id)
    for metric_id in DERIVABLE_METRIC_IDS.get(dim, ()):
        if metric_id in seen:
            continue
        derived = derive_metric_fields(metric_id, arm, t, ni)
        if derived is not None:
            out.append(_synthetic_metric(metric_id, derived))
    return tuple(out)


def _arm_gates(v: GateValues, t: ScoreThresholds, *,
               o2_skipped_fraction: float,
               o3_skipped_fraction: float,
               non_inferior: Mapping[str, bool]) -> tuple[GateCheck, ...]:
    """Every gate for one arm, in fixed evaluation order (deterministic).

    ``non_inferior`` carries the RECOMPUTED TOST non-inferiority legs
    (``non_inferior_flags``) — never caller booleans. The
    ``o*_skipped_fraction`` values couple the O2/O3 gates to the skip
    accounting: a missing overfit/kill value is only *skippable* when the
    whole term is legitimately over the skip cap (row 9 then forces O
    underpowered); at or under the cap an aggregate value must exist, so its
    absence FAILS the gate (breaking one's own holdout or smoke is a
    controllable act).
    """
    c3_ni = bool(non_inferior.get("C3", False))
    c8_ni = bool(non_inferior.get("C8", False))
    u2_ni = bool(non_inferior.get("U2", False))
    u3_ni = bool(non_inferior.get("U3", False))
    o1_ni = bool(non_inferior.get("O1", False))
    o3_ni = bool(non_inferior.get("O3", False))
    gates: list[GateCheck] = [
        # Fail-closed: c0_leak_hits of None means at least one generate cell
        # was never scanned (leak_scanned:false) — no signal, never a pass.
        (GateCheck("C0_generate_isolation", 0.0, 0.0, False,
                   detail="no C0 signal: unscanned generate cell(s) "
                          "(fail-closed)")
         if v.c0_leak_hits is None else
         GateCheck("C0_generate_isolation", float(v.c0_leak_hits), 0.0,
                   v.c0_leak_hits == 0)),
        GateCheck("C2_must_retention", float(v.c2_dropped_must), 0.0,
                  v.c2_dropped_must == 0),
        GateCheck("C3_coverage_noninferiority",
                  1.0 if c3_ni else 0.0, 1.0, c3_ni,
                  detail="" if c3_ni else "TOST not non-inferior (recomputed)"),
        GateCheck("C7_merge_fidelity", float(v.c7_merge_failures), 0.0,
                  v.c7_merge_failures == 0),
        # C8's row-6 legs are the frag-rate cap and the recomputed TOST
        # non-inferiority ONLY; a C8 power gap (in-band CI, low achieved
        # power) passes here and routes to row 8 UNDERPOWERED instead.
        GateCheck("C8_grammaticality", v.c8_frag_rate, t.frag_rate_cap,
                  v.c8_frag_rate <= t.frag_rate_cap and c8_ni,
                  detail="" if c8_ni else "TOST not non-inferior (recomputed)"),
        GateCheck("U0_isolation", float(v.u0_leak_hits), 0.0,
                  v.u0_prompt_sha_ok and v.u0_leak_hits == 0,
                  detail="" if v.u0_prompt_sha_ok else "prompt_sha mismatch"),
        GateCheck("U2_turns_noninferiority",
                  1.0 if u2_ni else 0.0, 1.0, u2_ni,
                  detail="" if u2_ni else "TOST not non-inferior (recomputed)"),
        GateCheck("U3_dead_end_cap", float(v.u3_max_dead_ends),
                  float(t.dead_end_cap), v.u3_max_dead_ends <= t.dead_end_cap),
        GateCheck("U3_deadend_noninferiority",
                  1.0 if u3_ni else 0.0, 1.0, u3_ni,
                  detail="" if u3_ni else "TOST not non-inferior (recomputed)"),
        GateCheck("U4_completion", v.u4_completion_fraction, 1.0,
                  v.u4_completion_fraction >= 1.0),
        GateCheck("U5_clarifying_questions", float(v.u5_clarifying_questions),
                  0.0, v.u5_clarifying_questions == 0),
    ]
    if v.o1_correctness is None:
        # Fail-closed: O1 is a required signal; its absence is a FAILURE.
        gates.append(GateCheck("O1_correctness", 0.0, t.o1_min_correctness,
                               False, detail="no O1 signal (fail-closed)"))
    else:
        details = []
        if not o1_ni:
            details.append("TOST not non-inferior (recomputed)")
        if v.o1_regressed_cells:
            details.append(f"regressed cells: {', '.join(v.o1_regressed_cells)}")
        gates.append(GateCheck(
            "O1_correctness", v.o1_correctness, t.o1_min_correctness,
            (v.o1_correctness >= t.o1_min_correctness
             and o1_ni and not v.o1_regressed_cells),
            detail="; ".join(details)))
    if v.o2_overfit is None:
        if o2_skipped_fraction <= t.max_o_term_skipped_fraction:
            # Fail-closed, mirroring O3: at or under the skip cap an aggregate
            # overfit must exist. Its absence — e.g. holdouts quietly dropped,
            # a controllable act — FAILS the gate, never skips it.
            gates.append(GateCheck(
                "O2_holdout_overfit", 0.0, t.o2_max_overfit, False,
                detail="no O2 signal without an over-cap accounted skip "
                       "(fail-closed)"))
        # Over the cap: no entry — skipped, never a pass; §2 row 9 forces the
        # O dimension underpowered via o2_skipped_fraction.
    else:
        gates.append(GateCheck("O2_holdout_overfit", v.o2_overfit,
                               t.o2_max_overfit, v.o2_overfit <= t.o2_max_overfit))
    if v.o3_kill_rate is None:
        if o3_skipped_fraction <= t.max_o_term_skipped_fraction:
            # Fail-closed: at or under the skip cap an aggregate kill rate must
            # exist (>= 70% of cells have signal). Its absence — e.g. a broken
            # O3 smoke, a controllable act — FAILS the gate, never skips it.
            gates.append(GateCheck(
                "O3_mutation_kill", 0.0, t.o3_min_kill_rate, False,
                detail="no O3 signal without an over-cap accounted skip "
                       "(fail-closed)"))
        # Over the cap: no entry — skipped, never a pass; §2 row 9 forces the
        # O dimension underpowered via o3_skipped_fraction.
    else:
        details = []
        if v.o3_invalid:
            details.append(f"invalid mutants: {v.o3_invalid}")
        if not o3_ni:
            details.append("TOST not non-inferior (recomputed)")
        gates.append(GateCheck(
            "O3_mutation_kill", v.o3_kill_rate, t.o3_min_kill_rate,
            (v.o3_kill_rate >= t.o3_min_kill_rate and v.o3_invalid == 0
             and o3_ni),
            detail="; ".join(details)))
    gates.append(GateCheck("O4_workaround_lint", float(v.o4_workarounds), 0.0,
                           v.o4_workarounds == 0))
    gates.extend((
        GateCheck("L1_code_fraction", v.l1_code_frac, t.leak_code_frac_cap,
                  v.l1_code_frac <= t.leak_code_frac_cap),
        GateCheck("L2_reference_containment", v.l2_reference_containment,
                  t.leak_reference_cap,
                  v.l2_reference_containment <= t.leak_reference_cap),
        GateCheck("L3_impl_spec_copy", v.l3_copy_containment, t.leak_copy_cap,
                  v.l3_copy_containment <= t.leak_copy_cap),
    ))
    if v.l4_spec_only_correctness is not None:
        # A non-importing spec extract must never read as clean: no entry,
        # flagged upstream; L1-L3 carry the gate (§1 L4).
        gates.append(GateCheck("L4_spec_only_correctness",
                               v.l4_spec_only_correctness, t.leak_spec_only_cap,
                               v.l4_spec_only_correctness < t.leak_spec_only_cap))
    return tuple(gates)


def evaluate_gates(inputs: ScoreInputs) -> tuple[GateCheck, ...]:
    """The treatment arm's gates — the ones §2 row 6 reads."""
    treatment = _treatment_arm(inputs)
    return _arm_gates(treatment.gate_values, inputs.thresholds,
                      o2_skipped_fraction=treatment.o2_skipped_fraction,
                      o3_skipped_fraction=treatment.o3_skipped_fraction,
                      non_inferior=non_inferior_flags(treatment.tost,
                                                      inputs.thresholds))


def c1_failures(stats: C1Stats, noise_floor_c: float,
                t: ScoreThresholds) -> tuple[str, ...]:
    """Every §1-C1 win sub-threshold the arm misses, recomputed from raw stats.

    Empty tuple == C1 win intact. The five pre-registered legs: Holm-adjusted
    ``p < win_alpha``; bootstrap CI upper bound strictly negative; mean delta
    at or beyond ``-max(c1_gate_floor, c1_gate_noise_multiple *
    noise_floor_C)`` (the §4 2.0-gate multiple, NOT the 4.0 composite-scale
    multiple, floored so a degenerate noise floor never makes any negative
    delta a free win); leave-one-brief-out sign stability; and the win sign
    holding on the large_realistic subset.
    """
    failures: list[str] = []
    if not stats.p_holm < t.win_alpha:
        failures.append(
            f"C1 Holm-adjusted p {stats.p_holm:.4f} not < {t.win_alpha}")
    if not stats.ci[1] < 0.0:
        failures.append(f"C1 bootstrap CI upper bound {stats.ci[1]:.4f} not < 0")
    gate = -max(t.c1_gate_floor, t.c1_gate_noise_multiple * noise_floor_c)
    if not stats.mean_delta <= gate:
        failures.append(
            f"C1 mean delta {stats.mean_delta:.4f} not <= {gate:.4f} "
            f"(-max({t.c1_gate_floor}, {t.c1_gate_noise_multiple} x noise "
            "floor))")
    if not stats.sign_stable:
        failures.append("C1 leave-one-brief-out sign not stable")
    if not stats.large_realistic_delta < 0.0:
        failures.append(
            f"C1 sign does not hold on large_realistic subset "
            f"(delta {stats.large_realistic_delta:.4f})")
    return tuple(failures)


def u1_failures(stats: U1Stats, noise_floor_u: float,
                t: ScoreThresholds) -> tuple[str, ...]:
    """Every §1-U1 win sub-threshold the arm misses, recomputed from raw stats.

    Symmetric to ``c1_failures``. Empty tuple == U1 win intact. The two
    pre-registered legs: Holm-adjusted ``p < win_alpha`` and
    ``mean delta <= -T_U`` where ``T_U = max(u_target_ln,
    u_noise_multiple x noise_floor_U)`` — the same T_U the composite scale
    uses, so the reported win and the scored win cannot drift apart.
    """
    failures: list[str] = []
    if not stats.p_holm < t.win_alpha:
        failures.append(
            f"U1 Holm-adjusted p {stats.p_holm:.4f} not < {t.win_alpha}")
    t_u = max(t.u_target_ln, t.u_noise_multiple * noise_floor_u)
    if not stats.mean_delta <= -t_u:
        failures.append(
            f"U1 mean delta {stats.mean_delta:.4f} not <= {-t_u:.4f} "
            f"(-max(u_target_ln, {t.u_noise_multiple} x noise floor))")
    return tuple(failures)


def _treatment_arm(inputs: ScoreInputs) -> ArmInputs:
    for arm in inputs.arms:
        if arm.arm_id == inputs.treatment_arm:
            return arm
    raise ValueError(
        f"treatment arm {inputs.treatment_arm!r} not among packed arms "
        f"{[a.arm_id for a in inputs.arms]}"
    )


# --------------------------------------------------------------------------- #
# Per-arm scoring
# --------------------------------------------------------------------------- #


def _dim_verdict(dim: str, arm: ArmInputs, inputs: ScoreInputs) -> str:
    """"promising" only when the dimension's power story is intact.

    Underpowered iff any required TOST family is not certifiable — recomputed
    from the raw ``arm.tost`` stats (absent family is fail-closed NOT
    certifiable) — any required stratum has n < min (missing coverage is
    fail-closed a violation), or — for O — either term's skipped fraction
    exceeds the cap. "Underpowered" is never reported as "safe".
    """
    t = inputs.thresholds
    if not all(tost_certifiable(arm.tost.get(f), t.min_power)
               for f in TOST_FAMILIES[dim]):
        return "underpowered"
    strata = inputs.strata_coverage.get(dim)
    if not strata or any(n < t.min_stratum_n for n in strata.values()):
        return "underpowered"
    if dim == "O" and (arm.o2_skipped_fraction > t.max_o_term_skipped_fraction
                       or arm.o3_skipped_fraction > t.max_o_term_skipped_fraction):
        return "underpowered"
    return "promising"


def _score_arm(arm: ArmInputs, inputs: ScoreInputs) -> ArmScore:
    t = inputs.thresholds
    ni = non_inferior_flags(arm.tost, t)
    gates = _arm_gates(arm.gate_values, t,
                       o2_skipped_fraction=arm.o2_skipped_fraction,
                       o3_skipped_fraction=arm.o3_skipped_fraction,
                       non_inferior=ni)
    leakage_voided = any(not g.passed and g.id in LEAK_GATE_IDS for g in gates)
    # §1-L4: a null l4_spec_only_correctness is "no signal (emitted +
    # flagged)" — L1-L3 still carry the gate (no GateCheck, never blocking),
    # but the run-blind human_read gate needs a schema pointer that the
    # executed control produced nothing. l4_no_signal is that trace: always
    # rendered, never omitted, independent of leakage_voided.
    l4_no_signal = arm.gate_values.l4_spec_only_correctness is None

    c_target = max(t.c_target_floor,
                   t.c_scale_noise_multiple * inputs.noise_floor_c)
    s_c = subscore_linear(-arm.c1.mean_delta, inputs.noise_floor_c, c_target,
                          min_den=t.c_min_den)
    # Purely descriptive, ONE meaning: an accounted OVER-cap O3 skip dropped
    # the kill term. Under the cap a missing kill rate is an O3 gate FAILURE
    # (never "renormalized"); leakage voiding does not change this flag —
    # the over-cap skip dropped the term whether or not the arm was voided.
    renormalized = (arm.gate_values.o3_kill_rate is None
                    and arm.o3_skipped_fraction > t.max_o_term_skipped_fraction)
    if leakage_voided:
        # §1 L-table: leakage voids this arm's U and O subscores to 0.0.
        s_u = 0.0
        s_o = 0.0
    else:
        u_target = max(t.u_target_ln, t.u_noise_multiple * inputs.noise_floor_u)
        s_u = subscore_linear(-arm.u1.mean_delta, inputs.noise_floor_u,
                              u_target, min_den=t.u_min_den)
        # Correctness term: the HOLDOUT mean only. None => the term scores 0
        # in its ORIGINAL weight and correctness_holdout_missing is emitted —
        # never a silent substitution of visible-case O1 (which would hand
        # O2's weight to the very cases O2 exists to distrust).
        # The kill term is read from the SAME field the O3 gate reads — one
        # source of truth — and a missing term always scores 0 in its
        # original weight (uniform monotone rule; no renormalization).
        kill_rate = arm.gate_values.o3_kill_rate
        s_o = outcome_subscore(
            arm.correctness_holdout, kill_rate, arm.bloat_ln,
            correctness_weight=t.o_weight_correctness,
            kill_weight=t.o_weight_kill,
            bloat_weight=t.o_weight_bloat,
            bloat_cap_ln=t.o5_bloat_cap_ln,
        )

    dimensions = (
        DimensionScore(
            name="C", metrics=_dimension_metrics("C", arm, t, ni), subscore=s_c,
            verdict=_dim_verdict("C", arm, inputs),
            covariates=dict(arm.covariates) if arm.covariates else None),
        DimensionScore(
            name="U", metrics=_dimension_metrics("U", arm, t, ni), subscore=s_u,
            verdict=_dim_verdict("U", arm, inputs)),
        DimensionScore(
            name="O", metrics=_dimension_metrics("O", arm, t, ni), subscore=s_o,
            verdict=_dim_verdict("O", arm, inputs),
            renormalized=renormalized,
            o2_skipped_fraction=arm.o2_skipped_fraction,
            o3_skipped_fraction=arm.o3_skipped_fraction,
            correctness_holdout_missing=arm.correctness_holdout is None),
    )
    return ArmScore(
        arm_id=arm.arm_id,
        cells=arm.cells,
        gates=gates,
        dimensions=dimensions,
        leakage_voided=leakage_voided,
        l4_no_signal=l4_no_signal,
        composite=composite({"C": s_c, "U": s_u, "O": s_o}, t.weights),
    )


# --------------------------------------------------------------------------- #
# §2 precedence — score_report
# --------------------------------------------------------------------------- #


def _strata_certifiable(inputs: ScoreInputs) -> bool:
    t = inputs.thresholds
    return all(
        (strata := inputs.strata_coverage.get(dim)) is not None
        and all(n >= t.min_stratum_n for n in strata.values())
        for dim in ("C", "U", "O")
    )


def _report(inputs: ScoreInputs, *, scorable: bool, reason: str | None,
            verdict: Verdict, reasons: tuple[str, ...],
            arms: tuple[ArmScore, ...]) -> ScoreReport:
    t = inputs.thresholds
    ceiling = ("promising_scale_to_n18"
               if inputs.n_briefs < t.n_full_scale else "none")
    return ScoreReport(
        scorable=scorable,
        reason=reason,
        verdict=verdict,
        ceiling=ceiling,
        arms=arms,
        verdict_reasons=reasons,
        manifest_content_hash=inputs.manifest_content_hash,
        generated_at=inputs.generated_at,
        instrument_trusted=inputs.instrument_trusted,
        benchmark_trusted=inputs.benchmark_trusted,
        n_briefs=inputs.n_briefs,
        n_buildable=inputs.n_buildable,
        k_seeds=inputs.k_seeds,
        extractor_families=inputs.extractor_families,
        noise_floor_c=inputs.noise_floor_c,
        noise_floor_u=inputs.noise_floor_u,
        strata_certifiable=_strata_certifiable(inputs),
        strata_coverage=inputs.strata_coverage,
        stops=inputs.stops,
        baseline_arm=inputs.baseline_arm,
        treatment_arm=inputs.treatment_arm,
        budget=inputs.budget,
        weights=t.weights,
        composite_pass=t.composite_pass,
    )


def _unscorable(inputs: ScoreInputs, reason: str) -> ScoreReport:
    # Fail-closed verdict: a not-scorable run must never read as shippable,
    # and a partial composite is never emitted (arms=()).
    return _report(inputs, scorable=False, reason=reason,
                   verdict=Verdict.DO_NOT_SHIP,
                   reasons=(f"not scorable: {reason}",), arms=())


def _completeness_reason(inputs: ScoreInputs) -> str | None:
    """§2 row 5, over every packed arm and cell family, in input order."""
    t = inputs.thresholds
    for arm in inputs.arms:
        for family in sorted(arm.cells):
            counts = arm.cells[family]
            if counts.incomplete_fraction > t.max_incomplete_fraction:
                return "incomplete_fraction_exceeded"
            if counts.merge_skipped_fraction > t.max_merge_skipped_fraction:
                return "merge_skipped_fraction_exceeded"
    if inputs.budget.exhausted:
        return "budget_exhausted"
    return None


def _stratum_reasons(inputs: ScoreInputs, treatment: ArmInputs) -> tuple[str, ...]:
    """§2 row 9 violations: thin strata and over-skipped O terms."""
    t = inputs.thresholds
    reasons: list[str] = []
    for dim in ("C", "U", "O"):
        strata = inputs.strata_coverage.get(dim)
        if strata is None:
            reasons.append(f"{dim} strata coverage missing — fail-closed underpowered")
            continue
        for name in sorted(strata):
            if strata[name] < t.min_stratum_n:
                reasons.append(
                    f"{dim} stratum {name} n={strata[name]} < {t.min_stratum_n} "
                    "— structurally uncertifiable at demo scale"
                )
    for term, fraction in (("O2", treatment.o2_skipped_fraction),
                           ("O3", treatment.o3_skipped_fraction)):
        if fraction > t.max_o_term_skipped_fraction:
            reasons.append(
                f"{term} skipped_fraction {fraction:.3f} > "
                f"{t.max_o_term_skipped_fraction} — dimension O underpowered"
            )
    return tuple(reasons)


def score_report(inputs: ScoreInputs) -> ScoreReport:
    """Apply the §2 precedence table (first match wins). Pure, deterministic.

    Rows 0/2/5 short-circuit to ``scorable:false`` with no per-arm numbers;
    row 1 emits no per-arm numbers either; every later row carries the scored
    arms. The run verdict is driven by the treatment arm alone.
    """
    # Duplicate arm_ids can never produce a coherent report: the first-match
    # treatment lookup and the last-wins rendered arms dict would contradict
    # each other. ValueError here is defense in depth behind the CLI's load
    # error — a structural packing bug, never a scorable state.
    arm_ids = [a.arm_id for a in inputs.arms]
    duplicates = sorted({a for a in arm_ids if arm_ids.count(a) > 1})
    if duplicates:
        raise ValueError(
            f"duplicate packed arm_id(s) {duplicates}: one arm, one record — "
            "a duplicate would score one record and render another")

    # 0. Manifest integrity gates everything.
    if not inputs.manifest_hash_matches or inputs.manifest_problems:
        return _unscorable(inputs, "manifest_invalid")

    # 1. Instrument trust: numbers unreadable => no per-arm numbers at all.
    if not inputs.instrument_trusted:
        return _report(
            inputs, scorable=True, reason=None, verdict=Verdict.DO_NOT_SHIP,
            reasons=("instrument-trust gate failed: arm numbers are not readable",),
            arms=())

    # 2. Benchmark trust (G-BT): the O instrument is blind => never scored.
    if not inputs.benchmark_trusted:
        return _unscorable(inputs, "benchmark_blind")

    # 3. The grammaticality detector's positive control must fire.
    if not inputs.a3b_fails_grammaticality:
        return _report(
            inputs, scorable=True, reason=None, verdict=Verdict.DO_NOT_SHIP,
            reasons=("grammaticality detector unproven: A3b_dumb did not fail "
                     "the detector (positive control)",),
            arms=tuple(_score_arm(a, inputs) for a in inputs.arms))

    # 4. Any pre-registered STOP.
    if inputs.stops.fired:
        return _report(
            inputs, scorable=True, reason=None, verdict=Verdict.DO_NOT_SHIP,
            reasons=tuple(f"STOP fired: {name}" for name in inputs.stops.names()),
            arms=tuple(_score_arm(a, inputs) for a in inputs.arms))

    # 5. Completeness / budget: crashed cells never score as cheap cells.
    completeness = _completeness_reason(inputs)
    if completeness is not None:
        return _unscorable(inputs, completeness)

    # The treatment arm must be packed to be scorable at all (fail-closed).
    try:
        treatment = _treatment_arm(inputs)
    except ValueError:
        return _unscorable(inputs, "treatment_arm_missing")
    arms = tuple(_score_arm(a, inputs) for a in inputs.arms)
    treatment_score = next(a for a in arms if a.arm_id == inputs.treatment_arm)

    # 6. Hard gates on the treatment arm.
    if treatment_score.gates_blocked:
        failed = tuple(
            g.id for g in treatment_score.gates
            if not g.passed and g.id in HARD_GATE_IDS)
        return _report(
            inputs, scorable=True, reason=None, verdict=Verdict.DO_NOT_SHIP,
            reasons=tuple(f"hard gate failed: {gate_id}" for gate_id in failed),
            arms=arms)

    # 7. Detected leakage on the treatment arm blocks the run outright: a spec
    # that embeds the implementation must never ship, whatever else is green.
    if treatment_score.leakage_voided:
        failed_leaks = tuple(
            g.id for g in treatment_score.gates
            if not g.passed and g.id in LEAK_GATE_IDS)
        return _report(
            inputs, scorable=True, reason=None, verdict=Verdict.DO_NOT_SHIP,
            reasons=tuple(
                f"leakage gate failed: {gate_id} — treatment arm voided, "
                "a leaking arm never ships" for gate_id in failed_leaks),
            arms=arms)

    # 8. Required TOSTs must be certifiable — recomputed from the raw packed
    # stats — else "underpowered", never "safe".
    uncertifiable = tuple(
        family for dim in ("C", "U", "O") for family in TOST_FAMILIES[dim]
        if not tost_certifiable(treatment.tost.get(family),
                                inputs.thresholds.min_power))
    if uncertifiable:
        return _report(
            inputs, scorable=True, reason=None, verdict=Verdict.UNDERPOWERED,
            reasons=("underpowered to certify safety — do not ship",)
            + tuple(f"required TOST {f} not certifiable" for f in uncertifiable),
            arms=arms)

    # 9. Structural power: strata and O-term signal coverage.
    stratum_reasons = _stratum_reasons(inputs, treatment)
    if stratum_reasons:
        return _report(inputs, scorable=True, reason=None,
                       verdict=Verdict.UNDERPOWERED, reasons=stratum_reasons,
                       arms=arms)

    # 10. The §1 win family {C1, U1} itself, recomputed from raw statistics —
    # every sub-threshold must hold or there is no demonstrated effect to ship.
    c1_missed = c1_failures(treatment.c1, inputs.noise_floor_c,
                            inputs.thresholds)
    u1_missed = u1_failures(treatment.u1, inputs.noise_floor_u,
                            inputs.thresholds)
    if c1_missed or u1_missed:
        return _report(
            inputs, scorable=True, reason=None, verdict=Verdict.DO_NOT_SHIP,
            reasons=tuple(f"C1 win threshold not met: {miss}"
                          for miss in c1_missed)
            + tuple(f"U1 win threshold not met: {miss}"
                    for miss in u1_missed),
            arms=arms)

    # 11. composite >= composite_pass is NECESSARY (never sufficient): a
    # treatment below the pass threshold has not earned a ship verdict even
    # with every gate green.
    t = inputs.thresholds
    if (treatment_score.composite is None
            or treatment_score.composite < t.composite_pass):
        value = ("none" if treatment_score.composite is None
                 else f"{treatment_score.composite:.2f}")
        return _report(
            inputs, scorable=True, reason=None, verdict=Verdict.DO_NOT_SHIP,
            reasons=(f"composite {value} < pass threshold "
                     f"{t.composite_pass:g} — composite >= pass is necessary, "
                     "never sufficient",),
            arms=arms)

    # 12-15. The decision.decide tail, mirrored.
    if inputs.a4_captures_effect:
        return _report(
            inputs, scorable=True, reason=None,
            verdict=Verdict.SHIP_EVALUATOR_ONLY,
            reasons=("A4 shows the evaluator pass alone captures the effect",),
            arms=arms)
    if not inputs.beats_a3_fair:
        detail = inputs.beats_a3_fair_detail or "A1 does not beat A3_fair"
        return _report(
            inputs, scorable=True, reason=None, verdict=Verdict.SHIP_ONELINER,
            reasons=(f"the honest one-liner matches the treatment: {detail}",),
            arms=arms)
    if not inputs.beats_a2_placebo:
        detail = inputs.beats_a2_placebo_detail or "A1 does not beat A2_placebo"
        return _report(
            inputs, scorable=True, reason=None, verdict=Verdict.DO_NOT_SHIP,
            reasons=(f"the gain was just one more editing pass: {detail}",),
            arms=arms)
    reasons = ["treatment beats A3_fair and A2_placebo and clears every gate"]
    if inputs.n_briefs < inputs.thresholds.n_full_scale:
        reasons.append(
            f"verdict capped to promising_scale_to_n18 "
            f"(N={inputs.n_briefs} < {inputs.thresholds.n_full_scale})")
    return _report(inputs, scorable=True, reason=None,
                   verdict=Verdict.SHIP_TREATMENT, reasons=tuple(reasons),
                   arms=arms)


def exit_code(report: ScoreReport) -> int:
    """0 scored & passing, 1 scored & blocked/STOP/no-ship, 4 not scorable."""
    if not report.scorable:
        return 4
    return 0 if report.verdict in _PASSING_VERDICTS else 1


# --------------------------------------------------------------------------- #
# Canonical serialization (§2 exact keys)
# --------------------------------------------------------------------------- #


def _num(x: float) -> float | int:
    """Integral floats render as JSON ints (gate thresholds, pass_threshold)."""
    return int(x) if float(x).is_integer() else x


def _cells_obj(counts: CellCounts) -> dict[str, object]:
    return {
        "expected": counts.expected,
        "complete": counts.complete,
        "missing": counts.missing,
        "timeout": counts.timeout,
        "error": counts.error,
        "retried": counts.retried,
        "incomplete_fraction": round(counts.incomplete_fraction, 3),
        "merge_skipped": counts.merge_skipped,
        "merge_skipped_fraction": round(counts.merge_skipped_fraction, 3),
        "mutations_skipped": counts.mutations_skipped,
        "holdout_skipped": counts.holdout_skipped,
    }


def _gate_obj(gate: GateCheck) -> dict[str, object]:
    obj: dict[str, object] = {
        "id": gate.id,
        "value": _num(gate.value),
        "threshold": _num(gate.threshold),
        "passed": gate.passed,
    }
    if gate.detail:
        obj["detail"] = gate.detail
    return obj


def _metric_obj(metric: MetricValue) -> dict[str, object]:
    obj: dict[str, object] = dict(metric.extra)
    if not obj:
        obj["value"] = metric.value
    if metric.ci is not None:
        obj["ci"] = [metric.ci[0], metric.ci[1]]
    if metric.p_holm is not None:
        obj["p_holm"] = metric.p_holm
    return obj


def _dimension_obj(dim: DimensionScore) -> dict[str, object]:
    obj: dict[str, object] = {
        "metrics": {m.id: _metric_obj(m) for m in dim.metrics},
        "subscore": round(dim.subscore, 2),
        "verdict": dim.verdict,
    }
    if dim.covariates is not None:
        obj["covariates"] = {k: round(v, 3) for k, v in dim.covariates.items()}
    if dim.renormalized is not None:
        obj["renormalized"] = dim.renormalized
    if dim.o2_skipped_fraction is not None:
        obj["o2_skipped_fraction"] = round(dim.o2_skipped_fraction, 3)
    if dim.o3_skipped_fraction is not None:
        obj["o3_skipped_fraction"] = round(dim.o3_skipped_fraction, 3)
    if dim.correctness_holdout_missing is not None:
        obj["correctness_holdout_missing"] = dim.correctness_holdout_missing
    return obj


def _arm_obj(arm: ArmScore, report: ScoreReport) -> dict[str, object]:
    value = None if arm.composite is None else round(arm.composite, 2)
    meets = arm.composite is not None and arm.composite >= report.composite_pass
    return {
        "cells": {family: _cells_obj(arm.cells[family])
                  for family in sorted(arm.cells)},
        "gates": [_gate_obj(g) for g in arm.gates],
        "gates_blocked": arm.gates_blocked,
        "gates_failed": list(arm.gates_failed),
        "leakage_voided": arm.leakage_voided,
        # §1-L4 "no signal (emitted + flagged)": a null l4_spec_only_correctness
        # emits no GateCheck (L1-L3 carry the gate) — this is its ONLY score.json
        # trace, always rendered, never omitted.
        "l4_no_signal": arm.l4_no_signal,
        "dimensions": {d.name: _dimension_obj(d) for d in arm.dimensions},
        "composite": {
            "weights": dict(report.weights),
            "value": value,
            "pass_threshold": _num(report.composite_pass),
            "meets": meets,
            # composite >= pass is necessary, never sufficient: the verdict
            # comes from the precedence table alone.
            "authorizes_ship": False,
        },
    }


def _report_obj(report: ScoreReport) -> dict[str, object]:
    return {
        "schema": report.schema,
        "manifest_content_hash": report.manifest_content_hash,
        "generated_at": report.generated_at,
        "scorable": report.scorable,
        "reason": report.reason,
        "instrument_trusted": report.instrument_trusted,
        "benchmark_trusted": report.benchmark_trusted,
        "human_read_required": report.human_read_required,
        "n_briefs": report.n_briefs,
        "n_buildable": report.n_buildable,
        "k_seeds": report.k_seeds,
        "extractor_families": list(report.extractor_families),
        "noise_floor": {"C": report.noise_floor_c, "U": report.noise_floor_u},
        "strata_certifiable": report.strata_certifiable,
        "strata_coverage": {dim: dict(strata)
                            for dim, strata in report.strata_coverage.items()},
        "stops": {
            "c_length_falsification": report.stops.c_length_falsification,
            "c_distinct_dilution": report.stops.c_distinct_dilution,
            "u_below_detectable_floor": report.stops.u_below_detectable_floor,
            "u_length_falsification": report.stops.u_length_falsification,
        },
        "arms_compared": {"baseline": report.baseline_arm,
                          "treatment": report.treatment_arm},
        "arms": {arm.arm_id: _arm_obj(arm, report) for arm in report.arms},
        "budget": {
            "spent_usd": report.budget.spent_usd,
            "projected_usd": report.budget.projected_usd,
            "max_usd": report.budget.max_usd,
            "exhausted": report.budget.exhausted,
        },
        "verdict": report.verdict.value,
        "verdict_reasons": list(report.verdict_reasons),
        "ceiling": report.ceiling,
    }


def render_score_json(report: ScoreReport) -> str:
    """Canonical, byte-stable `score.json` — asserted against a golden fixture."""
    return json.dumps(_report_obj(report), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)

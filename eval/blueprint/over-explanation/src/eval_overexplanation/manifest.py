"""Pre-registration manifest (anti p-hacking).

The pre-registration is the audit anchor: it is authored and its
``content_hash`` recorded *before* any A1 (treatment) run, so the analysis
plan cannot be retro-fitted to the data. ``content_hash`` is a sha256 over a
canonical (sorted-key) JSON serialization, so two registrations with identical
content hash to the same value and changing any frozen field changes the hash.

This module is pure data + I/O over the frozen value objects in ``models``. It
has no LLM/NLP dependency and is import-safe with only the stdlib + the package
value objects present.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .models import Arm, Brief, Regime

#: Version prefix required whenever ``bench`` thresholds are registered
#: (BENCHMARK.md §4: the hash change is the audit trail).
BENCH_VERSION_PREFIX = "bench-1-"


@dataclass(frozen=True)
class DecisionThresholds:
    """Pre-registered decision knobs for the statistics layer.

    ``noise_floor_multiple`` scales the empirical noise floor; ``tost_margin``
    is the non-inferiority margin for guardrail metrics; ``min_power`` is the
    minimum achieved power below which a TOST result is "underpowered", never
    "safe".
    """

    noise_floor_multiple: float = 2.0
    tost_margin: float = 0.0
    min_power: float = 0.8


@dataclass(frozen=True)
class BenchThresholds:
    """BLUEPRINT-BENCH §4 ``bench.*`` fields, frozen under ``content_hash``.

    Every number the §2 scorer compares against lives here so the manifest —
    never Python defaults — is the source of truth for a scored run
    (``score.thresholds_from_bench`` performs the mapping). The two C noise
    multiples are deliberately DISTINCT fields: ``c1_gate_noise_multiple``
    (2.0) drives the §1-C1 win gate (precedence #10) while
    ``c_scale_noise_multiple`` (4.0) drives the composite scale ``T_C`` —
    wiring one name into both would halve ``T_C`` and inflate ``S_C`` by up
    to 15 points. Defaults are BENCHMARK.md's frozen demo values; the four
    leak caps and ``frag_rate_cap`` are *calibrated upward* from honest
    A0/A0_prime cells before any treated run (floors here).

    EVERY operative scoring number lives here so it is covered by
    ``content_hash`` — a threshold that only exists as a Python default can
    be edited without moving the audit hash. That includes the §2 S_O term
    weights (``o_weight_*``), the O-term skip cap
    (``max_o_term_skipped_fraction``), the §1 win alpha (``win_alpha``), the
    knife-edge denominators (``c_min_den``/``u_min_den``) and the U noise
    multiple (``u_noise_multiple``); ``score.thresholds_from_bench`` maps
    all of them onto ``ScoreThresholds``.
    """

    u_arms: tuple[str, ...] = (
        "A0", "A1", "A2_placebo", "A3_fair", "A3b_dumb")
    implementer_ref: str = ""            # pinned model id (+ preamble sha)
    preamble_template: str = ""          # exactly {module} + {entrypoint}
    sandbox_test_cmd: tuple[str, ...] = (
        "{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider")
    weights: Mapping[str, float] = field(
        default_factory=lambda: {"C": 0.30, "U": 0.30, "O": 0.40})
    composite_pass: float = 70.0
    c1_gate_noise_multiple: float = 2.0  # §1-C1 GATE: mean d <= -2.0 x nf_C
    c1_gate_floor: float = 0.025         # §1-C1 GATE absolute floor: the gate
    #                                      threshold is max(this, mult x nf_C)
    #                                      so a degenerate noise floor never
    #                                      makes any negative delta a free win
    c_scale_noise_multiple: float = 4.0  # §2 composite SCALE: T_C
    c_target_floor: float = 0.05         # T_C = max(this, scale x nf_C)
    u_target_ln: float = 0.1054          # |ln 0.9| — a 10% spend saving
    u_noise_multiple: float = 2.0        # T_U = max(u_target_ln, this x nf_U)
    win_alpha: float = 0.05              # §1 C1/U1: Holm-adjusted p < this
    c_min_den: float = 0.02              # knife-edge floor for den_C
    u_min_den: float = 0.05              # knife-edge floor for den_U
    o_weight_correctness: float = 0.50   # S_O holdout-correctness weight
    o_weight_kill: float = 0.30          # S_O mutation-kill weight
    o_weight_bloat: float = 0.20         # S_O inverse-bloat weight
    max_o_term_skipped_fraction: float = 0.30  # O2/O3 accounted-skip cap
    tost_margins: Mapping[str, float] = field(
        default_factory=lambda: {"C3": 0.05, "C8": 0.02, "U2": 1.0,
                                 "U3": 1.0, "O1": 0.05, "O3": 0.10})
    min_power: float = 0.8
    dead_end_cap: int = 6
    o1_min_correctness: float = 0.90
    o2_max_overfit: float = 0.10
    o3_min_kill_rate: float = 0.75
    o5_bloat_cap_ln: float = 1.0986
    leak_caps: Mapping[str, float] = field(
        default_factory=lambda: {"code_frac": 0.15, "reference": 0.25,
                                 "copy": 0.30, "spec_only_correctness": 0.50})
    frag_rate_cap: float = 0.05
    max_incomplete_fraction: float = 0.10
    max_merge_skipped_fraction: float = 0.30
    min_stratum_n: int = 3
    max_usd: float = 120.0
    max_retries: int = 2
    leak_patterns: tuple[str, ...] = ()  # §1 U0 corpus/asset regexes
    mutations_per_brief: int = 8


@dataclass(frozen=True)
class PreRegistration:
    """The frozen analysis plan for one milestone.

    Carries the arms, briefs (each with its frozen difficulty regime), seeds,
    the extractor model families, and the decision thresholds. ``validate``
    reports structural problems as strings; ``content_hash`` is the tamper
    evidence. ``bench`` (BLUEPRINT-BENCH §4) is optional so pre-bench
    registrations keep their historical hashes; when present the version must
    carry the ``bench-1-`` prefix — the hash change is the audit trail.
    """

    version: str
    arms: tuple[Arm, ...]
    briefs: tuple[Brief, ...]
    seeds: tuple[int, ...]
    extractor_families: tuple[str, ...]
    thresholds: DecisionThresholds
    bench: BenchThresholds | None = None

    def validate(self, corpus_root: Path | None = None) -> tuple[str, ...]:
        """Return structural problems; empty tuple means the manifest is ok.

        Checks: >=1 seed; an ``A0``-id and an ``A1``-id arm are present; every
        brief carries a regime; thresholds are present. Also *warns* (as a
        problem string, not an exception) when fewer than two extractor families
        are declared — fix #1 wants >=2 model families for cross-family
        validity.

        With ``corpus_root`` given and a ``bench`` block registered, the §4
        per-brief asset rules apply too: every ``buildable`` brief must carry
        ``module`` + ``entrypoint`` in ``brief.json``, ``cases.json``,
        ``cases_holdout.json`` and ``mutations.json`` (with exactly
        ``bench.mutations_per_brief`` mutations). A buildable brief whose O2
        holdout or O3 battery is absent must surface as a manifest problem —
        ``scorable:false`` — never as a quietly skipped dimension the arm did
        not earn. Problems are strings, never exceptions.
        """
        problems: list[str] = []

        if len(self.seeds) < 1:
            problems.append("at least one seed is required")

        arm_ids = {a.id for a in self.arms}
        if not any(aid == "A0" or aid.startswith("A0") for aid in arm_ids):
            problems.append("a baseline arm with an A0 id is required")
        if not any(aid == "A1" or aid.startswith("A1") for aid in arm_ids):
            problems.append("a treatment arm with an A1 id is required")

        if len(self.briefs) == 0:
            problems.append("at least one brief is required")
        for brief in self.briefs:
            if not isinstance(brief.regime, Regime):
                problems.append(
                    f"brief {brief.id!r} has no valid regime"
                )

        if self.thresholds is None:  # type: ignore[comparison-overlap]
            problems.append("decision thresholds are required")

        if len(self.extractor_families) < 2:
            problems.append(
                "fewer than two extractor families declared "
                f"(have {len(self.extractor_families)}); fix #1 requires >=2 "
                "model families for cross-family validity"
            )

        problems.extend(self._validate_bench(arm_ids))
        if corpus_root is not None and self.bench is not None:
            problems.extend(self._validate_brief_assets(Path(corpus_root)))

        return tuple(problems)

    def _validate_bench(self, arm_ids: set[str]) -> list[str]:
        """BLUEPRINT-BENCH §4 structural rules; empty when ``bench`` is absent."""
        bench = self.bench
        if bench is None:
            return []
        problems: list[str] = []

        if not self.version.startswith(BENCH_VERSION_PREFIX):
            problems.append(
                f"bench thresholds require a version with the "
                f"'{BENCH_VERSION_PREFIX}' prefix (got {self.version!r}); "
                "the hash change is the audit trail"
            )
        missing_u = sorted(set(bench.u_arms) - arm_ids)
        if missing_u:
            problems.append(
                f"bench.u_arms not a subset of arms: {missing_u} undeclared")
        if "A3b_dumb" not in bench.u_arms:
            problems.append(
                "bench.u_arms must include A3b_dumb (U1f's length-strip leg)")
        weight_sum = sum(bench.weights.values())
        if abs(weight_sum - 1.0) > 1e-9:
            problems.append(
                f"bench.weights must sum to 1.0 (got {weight_sum})")
        o_weight_sum = (bench.o_weight_correctness + bench.o_weight_kill
                        + bench.o_weight_bloat)
        if abs(o_weight_sum - 1.0) > 1e-9:
            problems.append(
                f"bench o_weight_correctness+o_weight_kill+o_weight_bloat "
                f"must sum to 1.0 (got {o_weight_sum})")
        if not bench.implementer_ref:
            problems.append("bench.implementer_ref must be non-empty "
                            "(the FIXED pinned implementer)")
        if not bench.preamble_template:
            problems.append("bench.preamble_template must be non-empty")
        elif ("{module}" not in bench.preamble_template
              or "{entrypoint}" not in bench.preamble_template):
            problems.append(
                "bench.preamble_template must contain both {module} and "
                "{entrypoint} placeholders (the §0 interface pin)")
        if bench.mutations_per_brief != 8:
            problems.append(
                f"bench.mutations_per_brief must be 8 "
                f"(got {bench.mutations_per_brief}); the frozen O3 battery "
                "is 8 blind-authored mutations per buildable brief")
        return problems

    def _validate_brief_assets(self, corpus_root: Path) -> list[str]:
        """§4 per-brief asset rules over a corpus root (buildable briefs only).

        Fail-closed and string-only: a missing or malformed asset is a
        manifest problem (=> §2 row 0 ``scorable:false``), never an exception
        and never a quiet per-cell skip — a buildable brief without its blind
        ``cases_holdout.json``/``mutations.json`` cannot honestly enter the O
        dimension at all.
        """
        bench = self.bench
        assert bench is not None  # caller gates on this
        problems: list[str] = []
        for brief in self.briefs:
            if not brief.buildable:
                continue
            brief_dir = corpus_root / brief.id
            if not brief_dir.is_dir():
                problems.append(
                    f"buildable brief {brief.id!r}: no corpus dir under "
                    f"{corpus_root}")
                continue
            meta_path = brief_dir / "brief.json"
            if not meta_path.is_file():
                problems.append(
                    f"buildable brief {brief.id!r}: missing brief.json")
            else:
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    meta = None
                    problems.append(
                        f"buildable brief {brief.id!r}: unreadable "
                        f"brief.json ({exc})")
                if isinstance(meta, dict) and not (
                        meta.get("module") and meta.get("entrypoint")):
                    problems.append(
                        f"buildable brief {brief.id!r}: brief.json lacks "
                        "module/entrypoint (the §0 interface pin)")
            for asset in ("cases.json", "cases_holdout.json",
                          "mutations.json"):
                if not (brief_dir / asset).is_file():
                    problems.append(
                        f"buildable brief {brief.id!r}: missing {asset} "
                        "(blind O asset; absence is a manifest problem, "
                        "never a quiet skip)")
            mut_path = brief_dir / "mutations.json"
            if mut_path.is_file():
                try:
                    raw = json.loads(mut_path.read_text(encoding="utf-8"))
                    count = (len(raw.get("mutations", []))
                             if isinstance(raw, dict) else -1)
                except (OSError, ValueError) as exc:
                    count = -1
                    problems.append(
                        f"buildable brief {brief.id!r}: unreadable "
                        f"mutations.json ({exc})")
                if count >= 0 and count != bench.mutations_per_brief:
                    problems.append(
                        f"buildable brief {brief.id!r}: {count} mutations "
                        f"!= bench.mutations_per_brief "
                        f"({bench.mutations_per_brief})")
        return problems

    def content_hash(self) -> str:
        """sha256 over canonical (sorted-key) JSON — the audit anchor.

        Identical registrations hash identically; changing any frozen field
        changes the hash. This is how "frozen before any A1 run" is audited.
        """
        canonical = dump_manifest(self)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# (De)serialization
# --------------------------------------------------------------------------- #


def _arm_to_dict(arm: Arm) -> dict:
    return {
        "id": arm.id,
        "label": arm.label,
        "plugin_ref": arm.plugin_ref,
        "evaluator": dict(arm.evaluator),
        "description": arm.description,
    }


def _arm_from_dict(d: dict) -> Arm:
    return Arm(
        id=d["id"],
        label=d["label"],
        plugin_ref=d["plugin_ref"],
        evaluator=dict(d.get("evaluator", {})),
        description=d.get("description", ""),
    )


def _brief_to_dict(brief: Brief) -> dict:
    return {
        "id": brief.id,
        "title": brief.title,
        "regime": brief.regime.value,
        "buildable": brief.buildable,
        "text": brief.text,
    }


def _brief_from_dict(d: dict) -> Brief:
    raw_regime = d["regime"]
    try:
        regime = Regime(raw_regime)
    except ValueError as exc:
        raise ValueError(f"unknown regime {raw_regime!r}") from exc
    return Brief(
        id=d["id"],
        title=d["title"],
        regime=regime,
        buildable=bool(d["buildable"]),
        text=d.get("text", ""),
    )


def _thresholds_to_dict(t: DecisionThresholds) -> dict:
    return {
        "noise_floor_multiple": t.noise_floor_multiple,
        "tost_margin": t.tost_margin,
        "min_power": t.min_power,
    }


def _thresholds_from_dict(d: dict) -> DecisionThresholds:
    return DecisionThresholds(
        noise_floor_multiple=float(d.get("noise_floor_multiple", 2.0)),
        tost_margin=float(d.get("tost_margin", 0.0)),
        min_power=float(d.get("min_power", 0.8)),
    )


def _bench_to_dict(b: BenchThresholds) -> dict:
    return {
        "u_arms": list(b.u_arms),
        "implementer_ref": b.implementer_ref,
        "preamble_template": b.preamble_template,
        "sandbox_test_cmd": list(b.sandbox_test_cmd),
        "weights": dict(b.weights),
        "composite_pass": b.composite_pass,
        "c1_gate_noise_multiple": b.c1_gate_noise_multiple,
        "c1_gate_floor": b.c1_gate_floor,
        "c_scale_noise_multiple": b.c_scale_noise_multiple,
        "c_target_floor": b.c_target_floor,
        "u_target_ln": b.u_target_ln,
        "u_noise_multiple": b.u_noise_multiple,
        "win_alpha": b.win_alpha,
        "c_min_den": b.c_min_den,
        "u_min_den": b.u_min_den,
        "o_weight_correctness": b.o_weight_correctness,
        "o_weight_kill": b.o_weight_kill,
        "o_weight_bloat": b.o_weight_bloat,
        "max_o_term_skipped_fraction": b.max_o_term_skipped_fraction,
        "tost_margins": dict(b.tost_margins),
        "min_power": b.min_power,
        "dead_end_cap": b.dead_end_cap,
        "o1_min_correctness": b.o1_min_correctness,
        "o2_max_overfit": b.o2_max_overfit,
        "o3_min_kill_rate": b.o3_min_kill_rate,
        "o5_bloat_cap_ln": b.o5_bloat_cap_ln,
        "leak_caps": dict(b.leak_caps),
        "frag_rate_cap": b.frag_rate_cap,
        "max_incomplete_fraction": b.max_incomplete_fraction,
        "max_merge_skipped_fraction": b.max_merge_skipped_fraction,
        "min_stratum_n": b.min_stratum_n,
        "max_usd": b.max_usd,
        "max_retries": b.max_retries,
        "leak_patterns": list(b.leak_patterns),
        "mutations_per_brief": b.mutations_per_brief,
    }


def _bench_from_dict(d: dict) -> BenchThresholds:
    defaults = BenchThresholds()
    return BenchThresholds(
        u_arms=tuple(str(a) for a in d.get("u_arms", defaults.u_arms)),
        implementer_ref=str(d.get("implementer_ref", "")),
        preamble_template=str(d.get("preamble_template", "")),
        sandbox_test_cmd=tuple(
            str(c) for c in d.get("sandbox_test_cmd",
                                  defaults.sandbox_test_cmd)),
        weights={str(k): float(v)
                 for k, v in d.get("weights", defaults.weights).items()},
        composite_pass=float(d.get("composite_pass", defaults.composite_pass)),
        c1_gate_noise_multiple=float(
            d.get("c1_gate_noise_multiple", defaults.c1_gate_noise_multiple)),
        c1_gate_floor=float(d.get("c1_gate_floor", defaults.c1_gate_floor)),
        c_scale_noise_multiple=float(
            d.get("c_scale_noise_multiple", defaults.c_scale_noise_multiple)),
        c_target_floor=float(d.get("c_target_floor", defaults.c_target_floor)),
        u_target_ln=float(d.get("u_target_ln", defaults.u_target_ln)),
        u_noise_multiple=float(
            d.get("u_noise_multiple", defaults.u_noise_multiple)),
        win_alpha=float(d.get("win_alpha", defaults.win_alpha)),
        c_min_den=float(d.get("c_min_den", defaults.c_min_den)),
        u_min_den=float(d.get("u_min_den", defaults.u_min_den)),
        o_weight_correctness=float(
            d.get("o_weight_correctness", defaults.o_weight_correctness)),
        o_weight_kill=float(d.get("o_weight_kill", defaults.o_weight_kill)),
        o_weight_bloat=float(
            d.get("o_weight_bloat", defaults.o_weight_bloat)),
        max_o_term_skipped_fraction=float(
            d.get("max_o_term_skipped_fraction",
                  defaults.max_o_term_skipped_fraction)),
        tost_margins={str(k): float(v)
                      for k, v in d.get("tost_margins",
                                        defaults.tost_margins).items()},
        min_power=float(d.get("min_power", defaults.min_power)),
        dead_end_cap=int(d.get("dead_end_cap", defaults.dead_end_cap)),
        o1_min_correctness=float(
            d.get("o1_min_correctness", defaults.o1_min_correctness)),
        o2_max_overfit=float(d.get("o2_max_overfit", defaults.o2_max_overfit)),
        o3_min_kill_rate=float(
            d.get("o3_min_kill_rate", defaults.o3_min_kill_rate)),
        o5_bloat_cap_ln=float(
            d.get("o5_bloat_cap_ln", defaults.o5_bloat_cap_ln)),
        leak_caps={str(k): float(v)
                   for k, v in d.get("leak_caps", defaults.leak_caps).items()},
        frag_rate_cap=float(d.get("frag_rate_cap", defaults.frag_rate_cap)),
        max_incomplete_fraction=float(
            d.get("max_incomplete_fraction",
                  defaults.max_incomplete_fraction)),
        max_merge_skipped_fraction=float(
            d.get("max_merge_skipped_fraction",
                  defaults.max_merge_skipped_fraction)),
        min_stratum_n=int(d.get("min_stratum_n", defaults.min_stratum_n)),
        max_usd=float(d.get("max_usd", defaults.max_usd)),
        max_retries=int(d.get("max_retries", defaults.max_retries)),
        leak_patterns=tuple(str(p) for p in d.get("leak_patterns", ())),
        mutations_per_brief=int(
            d.get("mutations_per_brief", defaults.mutations_per_brief)),
    )


def _reg_to_dict(reg: PreRegistration) -> dict:
    out = {
        "version": reg.version,
        "arms": [_arm_to_dict(a) for a in reg.arms],
        "briefs": [_brief_to_dict(b) for b in reg.briefs],
        "seeds": list(reg.seeds),
        "extractor_families": list(reg.extractor_families),
        "thresholds": _thresholds_to_dict(reg.thresholds),
    }
    # Absent bench keeps pre-bench registrations byte-identical (their frozen
    # hashes stay valid); present bench changes the hash by design.
    if reg.bench is not None:
        out["bench"] = _bench_to_dict(reg.bench)
    return out


def _reg_from_dict(d: dict) -> PreRegistration:
    raw_bench = d.get("bench")
    return PreRegistration(
        version=d["version"],
        arms=tuple(_arm_from_dict(a) for a in d["arms"]),
        briefs=tuple(_brief_from_dict(b) for b in d["briefs"]),
        seeds=tuple(int(s) for s in d["seeds"]),
        extractor_families=tuple(d["extractor_families"]),
        thresholds=_thresholds_from_dict(d["thresholds"]),
        bench=None if raw_bench is None else _bench_from_dict(raw_bench),
    )


def load_manifest(path: Path) -> PreRegistration:
    """Read a pre-registration JSON file into a ``PreRegistration``."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return _reg_from_dict(raw)


def dump_manifest(reg: PreRegistration) -> str:
    """Serialize to canonical JSON (sorted keys, fixed separators).

    Canonical so that ``content_hash`` is stable across runs and machines and a
    load -> dump round-trip is byte-stable.
    """
    return json.dumps(
        _reg_to_dict(reg),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

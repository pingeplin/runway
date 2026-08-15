"""Thin command-line wiring over the harness libraries (issue #10).

The CLI owns *no* computation. Every subcommand parses arguments, loads inputs
into the inert value objects in :mod:`eval_overexplanation.models`, calls the
relevant library function by its full module path, and formats the result. All
decision logic — restatement rate, the guardrails, the statistics, buildability,
the manifest hash — lives in the sibling leaf modules; this module must stay a
pure adapter so the libraries remain independently testable.

Exit-code contract (so the CLI is usable as a CI gate):

* ``0`` — ran cleanly and nothing blocked / stopped.
* ``1`` — a guardrail *blocked* (a MUST claim dropped, a merge-fidelity
  violation, a grammaticality fragment) or the pre-registered length-artifact
  *STOP* fired. The numbers were computed and printed; the non-zero code is the
  ship/no-ship signal.
* ``2`` — argparse usage error (unknown subcommand, missing argument). This is
  argparse's own convention and is preserved.
* ``3`` — an input could not be loaded (missing/malformed results, corpus, or
  manifest file). A load failure is distinct from a guardrail block.

Results directory format
-------------------------

The ``restatement``/``guardrails``/``stats`` subcommands read a *results
directory* containing a single ``results.json``. It is a thin serialization of
the per-(arm, brief, seed) documents produced by a run; the CLI deserializes it
into model objects and feeds the libraries. Shape::

    {
      "noise_floor": 0.0,                 # optional; for the stats STOP gate
      "records": [
        {
          "arm_id": "A1", "brief_id": "b01", "seed": 1,
          "word_count": 320,
          "propositions": {<PropositionSet>},
          # optional within-arm pre/post-evaluator sets for merge-fidelity:
          "pre_evaluator": {<PropositionSet>} | null,
          "post_evaluator": {<PropositionSet>} | null,
          # optional within-arm pre->post alignment for merge-fidelity:
          "merge_alignment": {<Alignment>} | null,
          # optional cross-arm A0->A1 alignment (only on treatment records):
          "substance_alignment": {<Alignment>} | null,
          # optional sentences for the grammaticality screen:
          "sentences": ["...", ...] | null
        },
        ...
      ]
    }

where ``<PropositionSet>`` is
``{"document_id": str, "propositions": [{"id","text","kind","tier"?,
"mention_sentences":[int,...]}, ...]}`` and ``<Alignment>`` is
``{"source": <PropositionSet>, "target": <PropositionSet>,
"links": [{"source_id","target_id"|null,"relation"}, ...]}``.

This is deliberately a *transport* shape only: it carries the extractor's
already-computed propositions and alignments into the deterministic library
functions. The CLI never extracts or aligns — that is the LLM seam.

Milestone-2 subcommand transport shapes
----------------------------------------

These three subcommands are equally thin: parse JSON, build the inert inputs,
call one library function by full module path, format. The transport shapes are
this module's responsibility (the libraries stay pure value-object functions).

``decision <inputs.json>`` — a serialized :class:`decision.DecisionInputs`. A
``<TostResult>`` is ``{"non_inferior": bool, "p_value": float, "power": float,
"certifiable": bool}`` and an ``<ArmComparison>`` is ``{"beats": bool,
"detail": str?}``. Shape::

    {
      "restatement_real": bool,
      "substance_ok": bool,
      "buildability": <TostResult>,
      "grammaticality": <TostResult>,
      "a3b_fails_grammaticality": bool,
      "instrument_trusted": bool,
      "beats_a3_fair": <ArmComparison>,
      "beats_a2_placebo": <ArmComparison>,
      "a4_captures_effect": bool
    }

Exit non-zero (``EXIT_BLOCKED``) on a ``DO_NOT_SHIP`` or ``UNDERPOWERED``
verdict; zero on any of the three SHIP verdicts.

``instrument <docs.json> <decoys.json>`` — ``docs.json`` is a
``{document_id: text}`` map (the base + variant prose, passed straight to the
extractor). ``decoys.json`` is ``{"decoys": [<Decoy>, ...]}`` where a
``<Decoy>`` is ``{"name", "base_id", "variant_id", "kind", "tolerance"}``.
With the default :class:`extractor.FixtureExtractor` the extractor's canned
propositions are loaded from ``--fixtures <fixtures.json>``, a
``{document_id: <PropositionSet>}`` map (same ``<PropositionSet>`` shape as the
results transport). ``--family anthropic|openai`` selects a live extractor
instead (lazy optional import; never exercised offline). Exit non-zero if the
instrument is not trusted.

``sweep <sweep.json>`` — ``{"<threshold>": [rate, ...], ...}`` (a per-brief
restatement rate list at each candidate dedup threshold; thresholds are JSON
object keys, parsed as floats). Prints sign-stability and span.

BLUEPRINT-BENCH subcommand transport shapes (BENCHMARK.md §3)
--------------------------------------------------------------

Six more equally thin subcommands. Exit codes extend the table above with
``4`` — *not scorable* (BENCHMARK.md §2: never scored, distinct from a scored
block).

``usage <transcript.jsonl> [--return-code N]`` — ``usage.parse_usage`` over
the cell transcript; non-zero (``EXIT_BLOCKED``) whenever ``status != "ok"``
(a missing/timeout/error cell must never read as a cheap green cell).

``deadend <transcript.jsonl> [--manifest M]`` — ``deadend.deadend_report``;
leak patterns and the U3 cap come from ``bench.leak_patterns`` /
``bench.dead_end_cap`` when a manifest is given (module defaults otherwise).
Blocked on any leak hit (U0), any clarifying question (U5), or ``dead_ends``
over the cap (U3).

``leakage <spec.md> <brief_dir> <impl_dir> [--manifest M]`` — L1-L4 via
``deadend.leakage_report``. The reference is ``<brief_dir>/oracle.py``; the
L4 executed control extracts the spec's WHOLE-DOCUMENT detected code
(``deadend.spec_code_lines`` — the same surface L1-L3 measure, so an
indented unfenced paste executes exactly like a fenced one), common-dedents
it, stages it as ``<brief.module>.py`` in a tempdir and runs the visible
oracle cases against it (a non-importing extract yields ``None`` — no
signal, flagged, never clean). Blocked iff the report blocks.

``outcome <brief_dir> <impl_dir> [--manifest M]`` — O1/O2/O3/O4/O5 for one
implement cell. This subcommand is the SOLE owner of the O3 merged reference
dir: ``tmp/`` gets ``<brief_dir>/oracle.py`` staged as ``<brief.module>.py``
plus the arm's ``tests/``, the frozen sandbox test cmd smokes the unmutated
dir first (smoke failure ⇒ O3 skipped — no signal, never a pass), then
``run_mutations`` runs against it. O2 holdout / O3 mutations absent ⇒ that
row is SKIPPED, never passed. Blocked on any present gate failing.

``bench-trust <brief_dir> [--manifest M]`` — §5 G-BT: the reference impl
(oracle staged as the module) must score O1 == 1.0 and the stub impl
(``def <entrypoint>(*a, **k): return None``) must score O1 < 0.5; when the
brief ships reference tests + mutations, the reference must pass the O3
smoke + kill gate and the stub must FAIL the smoke. Any failure ⇒ the O
instrument is blind ⇒ exit 4 (not scorable).

``score <inputs.json> --manifest M --corpus C [--out score.json]`` —
deserialize the packed ``ScoreInputs`` transport, apply the §2 precedence,
and render the canonical ``score.json``. ``--corpus`` is REQUIRED: the §4
per-brief blind-asset rules are not opt-in (a shipped caller that never
opted in made them dead letter). Fail-closed re-derivations (never trusted
from the transport): ``manifest_hash_matches`` is recomputed by hashing the
manifest file against the transport's recorded ``manifest_content_hash``;
``manifest_problems`` come from ``validate(corpus_root)`` (§4 asset rules:
buildable briefs must carry ``cases_holdout.json`` + ``mutations.json``);
thresholds come from ``bench.*`` (Python defaults only when no bench block
is registered); ``budget.max_usd`` comes from ``bench.max_usd`` (the
manifest, not the packer, owns the budget cap, and ``exhausted`` is re-ORed
against ``spent_usd > max_usd``); the panel dimensions
(``n_briefs``/``n_buildable``/``k_seeds``/families) and every
``CellCounts.expected`` come from the manifest panel, NEVER from the
cells present in the transport — the shortfall between ``expected`` and the
packed ``complete+missing+timeout+error`` is added to ``missing``, so a
packer that omits crashed cells still pays ``incomplete_fraction``;
``strata_coverage`` is derived from the manifest briefs (C = per-regime
brief counts, U/O = per-regime BUILDABLE counts) and a packed value that
contradicts the derivation is a load error, never the source;
``o2_skipped_fraction``/``o3_skipped_fraction`` are derived from the packed
``holdout_skipped``/``mutations_skipped`` counts over the panel's expected
implement cells, a packed fraction being at most a cross-check (3-decimal
mismatch = load error); the TOST non-inferiority/certifiability flags are
recomputed by the scorer from each arm's REQUIRED ``tost`` map of raw
per-family numerics (packed booleans = cross-checks, mismatch = load
error; a packed ``margin`` contradicting ``bench.tost_margins`` = load
error); ``noise_floor_c``/``noise_floor_u`` must be positive and finite —
a zero floor (``estimate_noise_floor`` over empty inputs) means no
baseline replicate data and is a load error, never free significance;
``baseline_arm``/``treatment_arm`` and every packed ``arm_id`` must be
manifest-declared arms, each packed at most once (duplicate = load error);
the ``stops`` block and all four of its keys are REQUIRED (absent = load
error — an optional block with per-key defaults let a deleted STOP ship as
a fabricated clean STOP record in ``score.json``); every packed
``metrics[dim][id]`` field for a derivable id (§1 C1/C3/C8, U1/U2/U3/U5,
O1/O2/O3/O4/O5 — see ``score.DERIVABLE_METRIC_IDS``) is a cross-check
against ``score.derive_metric_fields``'s recomputation from ``gate_values``/
``tost``/``c1``/``u1``/``bloat_ln`` (mismatch = load error); the scorer
renders the derived value regardless of what was packed, so this is a
loud-failure net, not the mechanism that keeps the surface correct. A null
``l4_spec_only_correctness`` renders as ``arms.<ARM>.l4_no_signal: true`` —
the score.json trace that L4 produced no signal (L1-L3 still carry the
gate; L4 emits no GateCheck of its own either way).
Exit is ``score.exit_code``: 0 passing, 1 blocked/STOP/no-ship, 4 not
scorable.

Transport shape (top level)::

    {
      "manifest_content_hash": "sha256:…",   # REQUIRED; compared to the file
      "generated_at": "2026-08-13T00:00:00Z",
      "instrument_trusted": true, "benchmark_trusted": true,
      "a3b_fails_grammaticality": true,
      # REQUIRED block, all four keys REQUIRED (absent = load error): a
      # deleted STOP must never render as a clean STOP record
      "stops": {"c_length_falsification": false,
                "c_distinct_dilution": false,
                "u_below_detectable_floor": false,
                "u_length_falsification": false},
      "noise_floor_c": 0.031, "noise_floor_u": 0.084,
      # NO "strata_coverage" — derived from the manifest briefs; a packed
      # value is accepted only when it equals the derivation exactly
      "baseline_arm": "A0", "treatment_arm": "A1",
      "arms": [<ArmInputs>, ...],
      "budget": {"spent_usd", "projected_usd", "max_usd", "exhausted"},
      "a4_captures_effect": false,
      "beats_a3_fair": true, "beats_a2_placebo": true
    }

and an ``<ArmInputs>`` is::

    {
      "arm_id": "A1",
      "cells": {"generate": {"complete", "missing", "timeout", "error",
                             "retried", "merge_skipped", "mutations_skipped",
                             "holdout_skipped"},          # NO "expected" —
                "implement": {...}},                      # computed here
      "gate_values": {...every score.GateValues field..., incl.
                      "c0_leak_hits" (int or null — null when ANY generate
                      cell has leak_scanned:false, which FAILS the C0 gate)
                      and the REQUIRED-nullable "o1_correctness",
                      "o2_overfit", "o3_kill_rate",
                      "l4_spec_only_correctness" (explicit null = no
                      signal; a MISSING key is a load error — deleting a
                      key must never change a gate's routing)},
      "tost": {"C3": {"estimate": 0.01, "ci90": [-0.02, 0.03],
                      "p_value": 0.012, "achieved_power": 0.86,
                      "margin": 0.05},
               "C8": {...}, "U2": {...}, "U3": {...}, "O1": {...},
               "O3": {...}},          # REQUIRED, all six families; null =
                                      # no signal (fail-closed both legs)
      "c1": {"mean_delta", "ci": [lo, hi], "p_holm", "sign_stable",
             "large_realistic_delta"},
      "u1": {"mean_delta": -0.23, "p_holm": 0.02},
      "correctness_holdout": 0.90 | null,
      "bloat_ln": 0.11,
      # o2/o3_skipped_fraction are DERIVED from the cells' holdout_skipped /
      # mutations_skipped counts over the panel's expected implement cells;
      # packing them is optional and only a cross-check (mismatch = load
      # error, never reconciled)
      "metrics": {"C": [<MetricValue>, ...], ...},        # optional; fields
      #   of a derivable id (score.DERIVABLE_METRIC_IDS) are cross-checked
      #   against the scorer's own recomputation — mismatch = load error
      "covariates": {...}                                 # optional
    }

Every ``gate_values`` key is REQUIRED (a forgotten field is a load error,
never a silently-green gate — and never a silently-omitted one:
``l4_spec_only_correctness`` demands an explicit null for its no-signal
state precisely because DELETING it would otherwise drop the L4 gate with
no schema trace). The TOST flags are recomputed by the scorer from the raw
``tost`` numerics against the manifest's ``tost_margins``/``min_power``:
``non_inferior`` iff the 90% CI lies strictly inside the margin band,
``certifiable`` iff ``achieved_power >= min_power``. Legacy packed
booleans (``c3/c8/u2/u3/o1/o3_non_inferior``, ``tost_certifiable``) are
accepted only as cross-checks — a contradiction with the recomputation is
a load error. The O-term skip fractions are never caller-trusted: they are
derived from the packed counts (missing holdout/mutation assets must
surface as skipped counts or missing status, never silent zeros), and a
packed fraction that disagrees with the derivation at 3-decimal precision
is a load error.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path


# --------------------------------------------------------------------------- #
# Exit codes
# --------------------------------------------------------------------------- #

EXIT_OK = 0
EXIT_BLOCKED = 1  # a guardrail blocked / the STOP gate fired
EXIT_LOAD_ERROR = 3  # an input file was missing or malformed
EXIT_NOT_SCORABLE = 4  # BENCHMARK.md §2: never scored (fail-closed)


class _LoadError(Exception):
    """Raised when an input file cannot be loaded; mapped to EXIT_LOAD_ERROR."""


# --------------------------------------------------------------------------- #
# Result-record deserialization (transport shapes -> model objects)
# --------------------------------------------------------------------------- #


def _build_proposition_set(d: dict):
    # Imported here so the module stays import-light; these are pure value
    # objects with no heavy deps, but keeping imports local mirrors the
    # leaf-by-full-path convention.
    from eval_overexplanation.models import Proposition, PropositionSet, Tier

    props = []
    for p in d["propositions"]:
        tier = Tier(p["tier"]) if p.get("tier") is not None else Tier.SHOULD
        props.append(
            Proposition(
                id=str(p["id"]),
                text=str(p.get("text", "")),
                kind=str(p.get("kind", "")),
                tier=tier,
                mention_sentences=tuple(int(i) for i in p["mention_sentences"]),
            )
        )
    return PropositionSet(document_id=str(d["document_id"]), propositions=tuple(props))


def _build_alignment(d: dict):
    from eval_overexplanation.models import (
        Alignment,
        PropositionLink,
        Relation,
    )

    source = _build_proposition_set(d["source"])
    target = _build_proposition_set(d["target"])
    links = tuple(
        PropositionLink(
            source_id=str(l["source_id"]),
            target_id=(None if l.get("target_id") is None else str(l["target_id"])),
            relation=Relation(l["relation"]),
        )
        for l in d["links"]
    )
    return Alignment(source=source, target=target, links=links)


class _Record:
    """A parsed per-(arm, brief, seed) result record (thin holder)."""

    __slots__ = (
        "arm_id",
        "brief_id",
        "seed",
        "word_count",
        "propositions",
        "merge_alignment",
        "substance_alignment",
        "sentences",
    )

    def __init__(self, raw: dict) -> None:
        self.arm_id = str(raw["arm_id"])
        self.brief_id = str(raw["brief_id"])
        self.seed = int(raw["seed"])
        self.word_count = int(raw.get("word_count", 0))
        self.propositions = _build_proposition_set(raw["propositions"])
        self.merge_alignment = (
            _build_alignment(raw["merge_alignment"])
            if raw.get("merge_alignment")
            else None
        )
        self.substance_alignment = (
            _build_alignment(raw["substance_alignment"])
            if raw.get("substance_alignment")
            else None
        )
        self.sentences = (
            tuple(str(s) for s in raw["sentences"])
            if raw.get("sentences")
            else None
        )


def _load_results(results_dir: Path) -> tuple[float, list[_Record]]:
    """Load ``<results_dir>/results.json`` into (noise_floor, records).

    Raises :class:`_LoadError` on a missing or malformed file so the caller can
    map it to the load-error exit code.
    """
    results_dir = Path(results_dir)
    path = results_dir / "results.json"
    if not path.is_file():
        raise _LoadError(f"no results.json under {results_dir}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _LoadError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise _LoadError(f"{path}: expected an object with a 'records' list")
    try:
        records = [_Record(r) for r in data["records"]]
    except (KeyError, ValueError, TypeError) as exc:
        raise _LoadError(f"{path}: malformed record: {exc}") from exc
    noise_floor = float(data.get("noise_floor", 0.0))
    return noise_floor, records


# --------------------------------------------------------------------------- #
# Subcommand handlers — each loads, calls a library, prints, returns exit code
# --------------------------------------------------------------------------- #


def _cmd_restatement(args: argparse.Namespace) -> int:
    from eval_overexplanation.restatement import restatement_rate

    _noise, records = _load_results(args.results_dir)
    for rec in sorted(records, key=lambda r: (r.arm_id, r.brief_id, r.seed)):
        score = restatement_rate(rec.propositions)
        print(
            f"{rec.arm_id}\t{rec.brief_id}\tseed={rec.seed}\t"
            f"distinct={score.distinct}\tmentions={score.total_mentions}\t"
            f"rate={score.rate:.4f}"
        )
    return EXIT_OK


def _cmd_guardrails(args: argparse.Namespace) -> int:
    from eval_overexplanation.grammaticality import DefaultGrammaticalityChecker
    from eval_overexplanation.merge_fidelity import merge_fidelity
    from eval_overexplanation.substance import proposition_recall

    _noise, records = _load_results(args.results_dir)
    blocked = False
    checker = DefaultGrammaticalityChecker()

    for rec in sorted(records, key=lambda r: (r.arm_id, r.brief_id, r.seed)):
        tag = f"{rec.arm_id}\t{rec.brief_id}\tseed={rec.seed}"

        if rec.substance_alignment is not None:
            report = proposition_recall(rec.substance_alignment)
            status = "BLOCK" if report.blocks else "ok"
            print(
                f"{tag}\tsubstance\trecall={report.recall:.4f}\t"
                f"dropped_must={list(report.dropped_must)}\t"
                f"dropped_should={list(report.dropped_should)}\t{status}"
            )
            blocked = blocked or report.blocks

        if rec.merge_alignment is not None:
            mreport = merge_fidelity(rec.merge_alignment)
            status = "ok" if mreport.ok else "BLOCK"
            print(
                f"{tag}\tmerge_fidelity\tmerges={mreport.merge_count}\t"
                f"dropped={list(mreport.dropped_under_merge)}\t{status}"
            )
            blocked = blocked or (not mreport.ok)

        if rec.sentences is not None:
            greport = checker.check(rec.sentences)
            status = "ok" if greport.ok else "BLOCK"
            frags = [v.index for v in greport.fragments]
            print(f"{tag}\tgrammaticality\tfragments={frags}\t{status}")
            blocked = blocked or (not greport.ok)

    return EXIT_BLOCKED if blocked else EXIT_OK


def _cmd_stats(args: argparse.Namespace) -> int:
    from eval_overexplanation.restatement import restatement_rate
    from eval_overexplanation.stats import (
        average_to_brief,
        bootstrap_ci,
        length_falsification_stop,
        paired_wilcoxon,
    )

    noise_floor, records = _load_results(args.results_dir)

    # Group restatement rate and word count by (arm, brief) over seeds, then
    # average each to the brief (no pseudo-replication). The stats library owns
    # the averaging and the tests; the CLI only marshals the per-seed values.
    by_arm_brief_rate: dict[tuple[str, str], dict[int, float]] = {}
    by_arm_brief_wc: dict[tuple[str, str], dict[int, float]] = {}
    for rec in records:
        key = (rec.arm_id, rec.brief_id)
        rate = restatement_rate(rec.propositions).rate
        by_arm_brief_rate.setdefault(key, {})[rec.seed] = rate
        by_arm_brief_wc.setdefault(key, {})[rec.seed] = float(rec.word_count)

    arms = sorted({a for (a, _b) in by_arm_brief_rate})
    baseline_arm = next((a for a in arms if a.startswith("A0")), None)
    if baseline_arm is None:
        raise _LoadError("stats requires a baseline arm with an A0 id in results")

    briefs = sorted({b for (_a, b) in by_arm_brief_rate})

    def brief_value(table, arm, brief) -> float | None:
        seeds = table.get((arm, brief))
        return None if not seeds else average_to_brief(seeds)

    stop_fired = False
    for arm in arms:
        if arm == baseline_arm:
            continue
        base_rates: list[float] = []
        treat_rates: list[float] = []
        rest_deltas: list[float] = []
        wc_deltas: list[float] = []
        for brief in briefs:
            b_rate = brief_value(by_arm_brief_rate, baseline_arm, brief)
            t_rate = brief_value(by_arm_brief_rate, arm, brief)
            if b_rate is None or t_rate is None:
                continue
            base_rates.append(b_rate)
            treat_rates.append(t_rate)
            rest_deltas.append(t_rate - b_rate)
            b_wc = brief_value(by_arm_brief_wc, baseline_arm, brief) or 0.0
            t_wc = brief_value(by_arm_brief_wc, arm, brief) or 0.0
            wc_deltas.append(t_wc - b_wc)

        if not rest_deltas:
            print(f"{arm}\tno paired briefs vs {baseline_arm}")
            continue

        wil = paired_wilcoxon(base_rates, treat_rates)
        ci = bootstrap_ci(rest_deltas, seed=0)
        print(
            f"{arm}\tvs {baseline_arm}\tn={wil.n}\t"
            f"wilcoxon_stat={wil.statistic:.4g}\tp={wil.p_value:.4g}\t"
            f"mean_delta={ci.point:.4f}\tCI{ci.level:.2f}="
            f"[{ci.low:.4f},{ci.high:.4f}]"
        )

        # Length-falsification STOP: with no separate length-strip arm in the
        # results, the strip arm is the treated arm's own deltas (a degenerate
        # but well-defined self-comparison that always "reproduces"); when a
        # dedicated A_lengthstrip arm is present we would pass its deltas. Here
        # we only have the partialling half, so we report the partial-out STOP
        # using the treated deltas as their own strip reference is unsound — so
        # we run the gate with the length-strip set to a no-win sentinel
        # (zeros) which makes length_strip_reproduces depend purely on the sign
        # of the treated mean. The library owns the exact rule.
        falsi = length_falsification_stop(
            rest_deltas,
            wc_deltas,
            [0.0] * len(rest_deltas),
            noise_floor=noise_floor,
        )
        print(f"{arm}\tlength_falsification\t{falsi.detail}")
        stop_fired = stop_fired or falsi.stop

    return EXIT_BLOCKED if stop_fired else EXIT_OK


def _cmd_buildability(args: argparse.Namespace) -> int:
    from eval_overexplanation.buildability import run_mutations, run_oracle
    from eval_overexplanation.corpus import load_corpus, load_oracle_cases

    corpus_root = Path(args.corpus)
    impl_dir = Path(args.impl_dir)
    if not impl_dir.is_dir():
        raise _LoadError(f"impl dir not found: {impl_dir}")

    try:
        briefs = load_corpus(corpus_root)
    except (OSError, ValueError) as exc:
        raise _LoadError(f"cannot load corpus {corpus_root}: {exc}") from exc

    # The module/entrypoint and optional mutations come from the CLI flags; the
    # CLI only marshals them into the library calls.
    mutations = _load_mutations(args.mutations) if args.mutations else ()

    any_failure = False
    for brief in briefs:
        if not brief.buildable:
            continue
        cases = load_oracle_cases(corpus_root / brief.id)
        if not cases:
            continue
        oracle = run_oracle(
            impl_dir,
            args.module,
            args.entrypoint,
            cases,
            timeout=args.timeout,
        )
        print(
            f"{brief.id}\toracle\tpassed={oracle.passed}\tfailed={oracle.failed}\t"
            f"correctness={oracle.correctness:.4f}"
        )
        if oracle.failed:
            for err in oracle.errors:
                print(f"{brief.id}\t  oracle_error\t{err}")
            any_failure = True

    if mutations:
        mut = run_mutations(impl_dir, args.test_cmd, mutations, timeout=args.mut_timeout)
        print(
            f"mutations\tkilled={mut.killed}\tsurvived={list(mut.survived)}\t"
            f"invalid={list(mut.invalid)}\tkill_rate={mut.kill_rate:.4f}"
        )
        if mut.survived:
            any_failure = True

    return EXIT_BLOCKED if any_failure else EXIT_OK


def _load_mutations(path: str):
    from eval_overexplanation.models import Mutation

    p = Path(path)
    if not p.is_file():
        raise _LoadError(f"mutations file not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return tuple(
            Mutation(
                label=str(m["label"]),
                filename=str(m["filename"]),
                find=str(m["find"]),
                replace=str(m["replace"]),
            )
            for m in raw["mutations"]
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise _LoadError(f"malformed mutations file {p}: {exc}") from exc


def _cmd_manifest_hash(args: argparse.Namespace) -> int:
    from eval_overexplanation.manifest import load_manifest

    path = Path(args.manifest)
    if not path.is_file():
        raise _LoadError(f"manifest not found: {path}")
    try:
        reg = load_manifest(path)
    except (OSError, ValueError, KeyError) as exc:
        raise _LoadError(f"cannot load manifest {path}: {exc}") from exc

    print(reg.content_hash())
    for problem in reg.validate():
        print(f"warning: {problem}")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Milestone-2 subcommands (decision / instrument / sweep) — transport + format
# --------------------------------------------------------------------------- #


def _load_json(path: Path) -> object:
    """Read and parse a JSON file, mapping any failure to :class:`_LoadError`."""
    if not path.is_file():
        raise _LoadError(f"file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _LoadError(f"cannot read {path}: {exc}") from exc


def _build_tost(d: dict):
    from eval_overexplanation.stats import TostResult

    return TostResult(
        non_inferior=bool(d["non_inferior"]),
        p_value=float(d["p_value"]),
        power=float(d["power"]),
        certifiable=bool(d["certifiable"]),
    )


def _build_arm_comparison(d: dict):
    from eval_overexplanation.decision import ArmComparison

    return ArmComparison(beats=bool(d["beats"]), detail=str(d.get("detail", "")))


def _cmd_decision(args: argparse.Namespace) -> int:
    from eval_overexplanation.decision import (
        DecisionInputs,
        Verdict,
        decide,
    )

    raw = _load_json(Path(args.inputs))
    if not isinstance(raw, dict):
        raise _LoadError(f"{args.inputs}: expected a DecisionInputs object")
    try:
        inputs = DecisionInputs(
            restatement_real=bool(raw["restatement_real"]),
            substance_ok=bool(raw["substance_ok"]),
            buildability=_build_tost(raw["buildability"]),
            grammaticality=_build_tost(raw["grammaticality"]),
            a3b_fails_grammaticality=bool(raw["a3b_fails_grammaticality"]),
            instrument_trusted=bool(raw["instrument_trusted"]),
            beats_a3_fair=_build_arm_comparison(raw["beats_a3_fair"]),
            beats_a2_placebo=_build_arm_comparison(raw["beats_a2_placebo"]),
            a4_captures_effect=bool(raw["a4_captures_effect"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise _LoadError(f"{args.inputs}: malformed DecisionInputs: {exc}") from exc

    result = decide(inputs)
    print(f"verdict\t{result.verdict.value}")
    for reason in result.reasons:
        print(f"reason\t{reason}")

    no_ship = result.verdict in (Verdict.DO_NOT_SHIP, Verdict.UNDERPOWERED)
    return EXIT_BLOCKED if no_ship else EXIT_OK


def _build_fixture_extractor(path: Path):
    """Build a :class:`FixtureExtractor` from a ``{doc_id: PropositionSet}`` map."""
    from eval_overexplanation.extractor import FixtureExtractor

    raw = _load_json(path)
    if not isinstance(raw, dict):
        raise _LoadError(f"{path}: expected a {{document_id: PropositionSet}} object")
    try:
        sets = {str(doc_id): _build_proposition_set(pset) for doc_id, pset in raw.items()}
    except (KeyError, ValueError, TypeError) as exc:
        raise _LoadError(f"{path}: malformed fixtures: {exc}") from exc
    return FixtureExtractor(sets)


def _cmd_instrument(args: argparse.Namespace) -> int:
    from eval_overexplanation.instrument import Decoy, instrument_trust_gate

    raw_docs = _load_json(Path(args.docs))
    if not isinstance(raw_docs, dict):
        raise _LoadError(f"{args.docs}: expected a {{document_id: text}} object")
    docs = {str(k): str(v) for k, v in raw_docs.items()}

    raw_decoys = _load_json(Path(args.decoys))
    if not isinstance(raw_decoys, dict) or not isinstance(
        raw_decoys.get("decoys"), list
    ):
        raise _LoadError(f"{args.decoys}: expected an object with a 'decoys' list")
    try:
        decoys = tuple(
            Decoy(
                name=str(d["name"]),
                base_id=str(d["base_id"]),
                variant_id=str(d["variant_id"]),
                kind=str(d["kind"]),
                tolerance=float(d["tolerance"]),
            )
            for d in raw_decoys["decoys"]
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise _LoadError(f"{args.decoys}: malformed decoy: {exc}") from exc

    if args.family == "fixture":
        if not args.fixtures:
            raise _LoadError(
                "the default fixture extractor needs --fixtures <fixtures.json>"
            )
        extractor = _build_fixture_extractor(Path(args.fixtures))
    elif args.family == "anthropic":
        from eval_overexplanation.extractor import AnthropicExtractor

        extractor = AnthropicExtractor(args.model)
    elif args.family == "openai":
        from eval_overexplanation.extractor import OpenAIExtractor

        extractor = OpenAIExtractor(args.model)
    else:  # pragma: no cover - argparse choices guard this
        raise _LoadError(f"unknown extractor family: {args.family}")

    report = instrument_trust_gate(extractor, docs, decoys)
    for check in report.checks:
        status = "ok" if check.passed else "FAIL"
        print(
            f"{check.name}\t{check.kind}\t"
            f"observed_delta={check.observed_delta:.4f}\t"
            f"tolerance={check.tolerance:.4f}\t{status}"
        )
    print(f"trusted\t{report.trusted}")
    return EXIT_OK if report.trusted else EXIT_BLOCKED


def _cmd_sweep(args: argparse.Namespace) -> int:
    from eval_overexplanation.stats import dedup_threshold_sweep

    raw = _load_json(Path(args.sweep))
    if not isinstance(raw, dict):
        raise _LoadError(f"{args.sweep}: expected a {{threshold: [rates]}} object")
    try:
        rates_by_threshold = {
            float(threshold): [float(r) for r in rates]
            for threshold, rates in raw.items()
        }
    except (ValueError, TypeError) as exc:
        raise _LoadError(f"{args.sweep}: malformed sweep map: {exc}") from exc

    sweep = dedup_threshold_sweep(rates_by_threshold)
    for point in sweep.points:
        print(f"threshold={point.threshold:.4f}\tmean_rate={point.mean_rate:.4f}")
    print(f"sign_stable\t{sweep.sign_stable}")
    print(f"span\t{sweep.span:.4f}")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# BLUEPRINT-BENCH subcommands (usage/deadend/leakage/outcome/bench-trust/score)
# --------------------------------------------------------------------------- #


def _read_lines(path: Path) -> list[str]:
    if not path.is_file():
        raise _LoadError(f"transcript not found: {path}")
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise _LoadError(f"cannot read {path}: {exc}") from exc


def _load_registration(path: str | None):
    """Load a manifest path into a PreRegistration, or None when not given."""
    if path is None:
        return None
    from eval_overexplanation.manifest import load_manifest

    p = Path(path)
    if not p.is_file():
        raise _LoadError(f"manifest not found: {p}")
    try:
        return load_manifest(p)
    except (OSError, ValueError, KeyError) as exc:
        raise _LoadError(f"cannot load manifest {p}: {exc}") from exc


def _bench_of(reg):
    """The manifest's bench block, else the frozen BENCHMARK.md defaults."""
    from eval_overexplanation.manifest import BenchThresholds

    if reg is not None and reg.bench is not None:
        return reg.bench
    return BenchThresholds()


def _brief_interface(brief_dir: Path) -> tuple[str, str]:
    """``(module, entrypoint)`` from brief.json — the §0 interface pin."""
    meta_path = Path(brief_dir) / "brief.json"
    raw = _load_json(meta_path)
    if not isinstance(raw, dict):
        raise _LoadError(f"{meta_path}: expected a JSON object")
    module = str(raw.get("module") or "")
    entrypoint = str(raw.get("entrypoint") or "")
    if not module or not entrypoint:
        raise _LoadError(
            f"{meta_path}: missing module/entrypoint (the §0 interface pin)")
    return module, entrypoint


def _sandbox_test_cmd(bench) -> list[str]:
    """The frozen sandbox test cmd with ``{python}`` bound to this interpreter."""
    import sys

    return [sys.executable if part == "{python}" else part
            for part in bench.sandbox_test_cmd]


def _impl_source_text(impl_dir: Path) -> str:
    """Concatenated NON-TEST ``*.py`` sources of a workspace (L3's `a`).

    L3 is ``|shared grams| / |impl grams|``, so anything in the denominator
    the arm authors freely is dilution: a large generated test suite dropped
    the measured copy fraction of a verbatim spec transcription below the cap
    while the implementation itself was still a copy. The impl surface is the
    same non-test surface O5 sizes (``_impl_sloc``); the arm's tests are
    scored by O3 mutation kill, never by containment.
    """
    return "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(Path(impl_dir).rglob("*.py"))
        if not _is_test_path(p.relative_to(impl_dir))
    )


def _is_test_path(rel: Path) -> bool:
    """Test-file convention shared by O5's sizing and L3's impl surface."""
    return ("tests" in rel.parts[:-1] or rel.name.startswith("test_")
            or rel.name.endswith("_test.py"))


def _sloc(path: Path) -> int:
    """Logical line count (comments/blanks stripped) — O5's size measure."""
    count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def _impl_sloc(impl_dir: Path) -> int:
    """O5 impl size: non-test ``*.py`` logical lines in the workspace."""
    return sum(_sloc(path) for path in sorted(Path(impl_dir).rglob("*.py"))
               if not _is_test_path(path.relative_to(impl_dir)))


def _spec_only_correctness(spec_md: str, brief_dir: Path, module: str,
                           entrypoint: str, *, timeout: float) -> float | None:
    """L4 executed control: detected spec code alone through ``run_oracle``.

    The extraction surface is ``deadend.spec_python_source`` over the SAME
    whole-document detection L1-L3 use (fenced bodies ∪ indented lines ∪
    per-line Python classifier, raw ∪ dressing-stripped), common-dedented so
    an implementation pasted as INDENTED — or blockquoted, bulleted, tabled —
    markdown executes exactly like a fenced one. Two failure modes are closed
    there: a fence-only surface let one working indented paste score ``None``
    here while sliding under the L1-L3 caps, and a single non-Python detected
    block (an indented JSON payload example) made the whole assembled source
    a syntax error, which also read as no signal. ``None`` (no signal,
    flagged downstream) when nothing Python was detected, the brief has no
    visible cases, or the assembled source does not import — a non-import
    must never read as clean (L1-L3 carry the gate for that cell).
    """
    import tempfile

    from eval_overexplanation.buildability import run_oracle
    from eval_overexplanation.corpus import load_oracle_cases
    from eval_overexplanation.deadend import spec_python_source

    source = spec_python_source(spec_md)
    if not source.strip():
        return None
    try:
        cases = load_oracle_cases(brief_dir)
    except ValueError as exc:
        raise _LoadError(f"cannot load cases for {brief_dir}: {exc}") from exc
    if not cases:
        return None
    with tempfile.TemporaryDirectory(prefix="l4_spec_only_") as tmp:
        target = Path(tmp) / f"{module}.py"
        target.write_text(source, encoding="utf-8")
        result = run_oracle(Path(tmp), module, entrypoint, cases,
                            timeout=timeout)
    if result.passed == 0 and result.errors and all(
            "import/lookup failed" in e for e in result.errors):
        return None
    return result.correctness


def _assemble_o3_reference(tmp: Path, brief_dir: Path, module: str,
                           impl_dir: Path) -> None:
    """The O3 merged reference dir — this CLI is its ONLY constructor (§3).

    ``tmp/`` <- the frozen ``corpus/<b>/oracle.py`` staged as ``<module>.py``
    (the name the arm's tests import) + the arm's ``workspace/tests/**``.
    The arm's *implementation* never enters: a transcribed impl earns nothing
    unless its test suite independently kills mutants against the reference.
    """
    import shutil

    oracle = Path(brief_dir) / "oracle.py"
    if not oracle.is_file():
        raise _LoadError(f"reference oracle not found: {oracle}")
    shutil.copyfile(oracle, tmp / f"{module}.py")
    tests = Path(impl_dir) / "tests"
    if tests.is_dir():
        shutil.copytree(tests, tmp / "tests")


def _cmd_usage(args: argparse.Namespace) -> int:
    from eval_overexplanation.usage import parse_usage

    report = parse_usage(_read_lines(Path(args.transcript)),
                         return_code=args.return_code)
    print(f"status\t{report.status}")
    print(f"subtype\t{report.subtype}")
    for name in ("num_turns", "output_tokens", "input_tokens",
                 "cache_read_input_tokens", "total_cost_usd", "duration_ms"):
        print(f"{name}\t{getattr(report, name)}")
    tc = report.tool_calls
    print(f"tool_calls\tedit={tc.edit}\twrite={tc.write}\tbash={tc.bash}\t"
          f"other={tc.other}\ttotal={tc.total}")
    if report.detail:
        print(f"detail\t{report.detail}")
    # Fail-closed: a missing/timeout/error cell blocks — it must be excluded
    # AND counted upstream, never read as the cheapest cell.
    return EXIT_OK if report.status == "ok" else EXIT_BLOCKED


def _cmd_deadend(args: argparse.Namespace) -> int:
    from eval_overexplanation.deadend import LEAK_PATTERNS, deadend_report

    bench = _bench_of(_load_registration(args.manifest))
    leak_patterns = bench.leak_patterns or LEAK_PATTERNS
    report = deadend_report(_read_lines(Path(args.transcript)),
                            leak_patterns=leak_patterns)
    cap = bench.dead_end_cap
    print(f"reverted_edits\t{report.reverted_edits}")
    print(f"failed_test_cycles\t{report.failed_test_cycles}")
    print(f"dead_ends\t{report.dead_ends}\tcap={cap}")
    print(f"clarifying_questions\t{report.clarifying_questions}")
    print(f"trailing_question_marks\t{report.trailing_question_marks}")
    print(f"leak_hits\t{len(report.leak_hits)}")
    for hit in report.leak_hits:
        print(f"  leak\t{hit}")
    blocked = (bool(report.leak_hits)            # U0: leak_hits == 0
               or report.clarifying_questions > 0  # U5: q == 0
               or report.dead_ends > cap)          # U3 per-cell cap
    return EXIT_BLOCKED if blocked else EXIT_OK


def _cmd_leakage(args: argparse.Namespace) -> int:
    from eval_overexplanation.deadend import leakage_report

    spec_path = Path(args.spec)
    if not spec_path.is_file():
        raise _LoadError(f"spec not found: {spec_path}")
    spec_md = spec_path.read_text(encoding="utf-8")

    brief_dir = Path(args.brief_dir)
    reference = brief_dir / "oracle.py"
    if not reference.is_file():
        raise _LoadError(f"reference oracle not found: {reference}")
    impl_dir = Path(args.impl_dir)
    if not impl_dir.is_dir():
        raise _LoadError(f"impl dir not found: {impl_dir}")

    module, entrypoint = _brief_interface(brief_dir)
    bench = _bench_of(_load_registration(args.manifest))
    soc = _spec_only_correctness(spec_md, brief_dir, module, entrypoint,
                                 timeout=args.timeout)
    report = leakage_report(
        spec_md,
        reference.read_text(encoding="utf-8"),
        _impl_source_text(impl_dir),
        soc,
        dict(bench.leak_caps),
    )
    print(f"code_frac\t{report.code_frac:.4f}\tcap={bench.leak_caps['code_frac']:.4f}")
    print(f"reference_containment\t{report.reference_containment:.4f}\t"
          f"cap={bench.leak_caps['reference']:.4f}")
    print(f"copy_containment\t{report.copy_containment:.4f}\t"
          f"cap={bench.leak_caps['copy']:.4f}")
    print(f"spec_only_correctness\t{report.spec_only_correctness}")
    for reason in report.reasons:
        print(f"reason\t{reason}")
    print(f"blocked\t{report.blocked}")
    return EXIT_BLOCKED if report.blocked else EXIT_OK


def _cmd_outcome(args: argparse.Namespace) -> int:
    import subprocess
    import tempfile
    from math import log

    from eval_overexplanation.buildability import run_mutations, run_oracle
    from eval_overexplanation.corpus import (
        load_holdout_cases,
        load_mutations,
        load_oracle_cases,
    )
    from eval_overexplanation.deadend import workaround_lint

    brief_dir = Path(args.brief_dir)
    impl_dir = Path(args.impl_dir)
    if not impl_dir.is_dir():
        raise _LoadError(f"impl dir not found: {impl_dir}")
    module, entrypoint = _brief_interface(brief_dir)
    bench = _bench_of(_load_registration(args.manifest))

    try:
        cases = load_oracle_cases(brief_dir)
        holdout = load_holdout_cases(brief_dir)
        mutations = load_mutations(brief_dir)
    except ValueError as exc:
        raise _LoadError(f"cannot load corpus assets in {brief_dir}: {exc}") from exc

    blocked = False

    # O1 — executed correctness over the frozen visible cases. Fail-closed:
    # no visible cases means no O1 signal, which FAILS the gate.
    if not cases:
        print("O1\tno-signal\t(no cases.json — fail-closed GATE FAILURE)")
        blocked = True
        o1_correctness = None
    else:
        o1 = run_oracle(impl_dir, module, entrypoint, cases,
                        timeout=args.timeout)
        o1_correctness = o1.correctness
        ok = o1.correctness >= bench.o1_min_correctness
        print(f"O1\tcorrectness={o1.correctness:.4f}\t"
              f"min={bench.o1_min_correctness}\t{'ok' if ok else 'FAIL'}")
        for err in o1.errors:
            print(f"  O1_error\t{err}")
        blocked = blocked or not ok

    # O2 — holdout overfit. File absent => SKIPPED, no signal, never a pass.
    if holdout is None:
        print("O2\tskipped\t(no cases_holdout.json — no signal, never a pass)")
    elif o1_correctness is None:
        print("O2\tskipped\t(no visible correctness to compare against)")
    else:
        oh = run_oracle(impl_dir, module, entrypoint, holdout,
                        timeout=args.timeout)
        overfit = o1_correctness - oh.correctness
        ok = overfit <= bench.o2_max_overfit
        print(f"O2\toverfit={overfit:.4f}\tholdout={oh.correctness:.4f}\t"
              f"max={bench.o2_max_overfit}\t{'ok' if ok else 'FAIL'}")
        blocked = blocked or not ok

    # O3 — mutation kill against the merged reference dir (assembled HERE,
    # nowhere else), smoke precondition first: a non-importing/failing suite
    # yields NO signal — it must never score kill_rate 1.0.
    if mutations is None:
        print("O3\tskipped\t(no mutations.json — no signal, never a pass)")
    else:
        test_cmd = _sandbox_test_cmd(bench)
        with tempfile.TemporaryDirectory(prefix="o3_reference_") as tmp:
            ref = Path(tmp)
            _assemble_o3_reference(ref, brief_dir, module, impl_dir)
            try:
                smoke = subprocess.run(
                    test_cmd, cwd=str(ref), capture_output=True, text=True,
                    timeout=args.mut_timeout)
                smoke_rc = smoke.returncode
            except subprocess.TimeoutExpired:
                smoke_rc = -1
            if smoke_rc != 0:
                print(f"O3\tskipped\t(smoke failed rc={smoke_rc} — "
                      "no signal, never a pass)")
            else:
                # Purge bytecode the smoke run compiled: copytree preserves
                # mtimes and a same-size mutation would not invalidate a
                # stale .pyc, silently resurrecting the unmutated reference.
                import shutil

                for pycache in ref.rglob("__pycache__"):
                    shutil.rmtree(pycache, ignore_errors=True)
                mut = run_mutations(ref, test_cmd, mutations,
                                    timeout=args.mut_timeout)
                ok = (mut.kill_rate >= bench.o3_min_kill_rate
                      and not mut.invalid)
                print(f"O3\tkill_rate={mut.kill_rate:.4f}\t"
                      f"min={bench.o3_min_kill_rate}\t"
                      f"survived={list(mut.survived)}\t"
                      f"invalid={list(mut.invalid)}\t{'ok' if ok else 'FAIL'}")
                blocked = blocked or not ok

    # O4 — workaround lint (AST only, never exec).
    lint = workaround_lint(impl_dir, cases)
    ok = lint.total == 0
    print(f"O4\tworkarounds={lint.total}\t{'ok' if ok else 'FAIL'}")
    for hit in lint.hits:
        print(f"  O4_hit\t{hit}")
    blocked = blocked or not ok

    # O5 — bloat, reported + scored upstream, never a gate.
    oracle_path = brief_dir / "oracle.py"
    if oracle_path.is_file():
        ref_sloc = _sloc(oracle_path)
        impl_sloc = _impl_sloc(impl_dir)
        if ref_sloc > 0 and impl_sloc > 0:
            bloat = log(impl_sloc / ref_sloc)
            print(f"O5\tbloat_ln={bloat:.4f}\tsoft_cap={bench.o5_bloat_cap_ln}"
                  "\t(reported, no gate)")
        else:
            print("O5\tno-signal\t(empty sloc)")
    else:
        print("O5\tno-signal\t(no reference oracle.py)")

    return EXIT_BLOCKED if blocked else EXIT_OK


def _cmd_bench_trust(args: argparse.Namespace) -> int:
    import subprocess
    import tempfile

    from eval_overexplanation.buildability import run_mutations, run_oracle
    from eval_overexplanation.corpus import load_mutations, load_oracle_cases

    brief_dir = Path(args.brief_dir)
    module, entrypoint = _brief_interface(brief_dir)
    bench = _bench_of(_load_registration(args.manifest))
    try:
        cases = load_oracle_cases(brief_dir)
        mutations = load_mutations(brief_dir)
    except ValueError as exc:
        raise _LoadError(f"cannot load corpus assets in {brief_dir}: {exc}") from exc
    if not cases:
        raise _LoadError(f"{brief_dir}: bench-trust needs cases.json")
    oracle_path = brief_dir / "oracle.py"
    if not oracle_path.is_file():
        raise _LoadError(f"reference oracle not found: {oracle_path}")

    blind = False
    stub_source = f"def {entrypoint}(*a, **k):\n    return None\n"

    # Positive control: the reference impl must ace the O instrument.
    with tempfile.TemporaryDirectory(prefix="bt_reference_") as tmp:
        ref = Path(tmp)
        (ref / f"{module}.py").write_text(
            oracle_path.read_text(encoding="utf-8"), encoding="utf-8")
        result = run_oracle(ref, module, entrypoint, cases,
                            timeout=args.timeout)
        ok = result.correctness == 1.0
        print(f"reference_o1\t{result.correctness:.4f}\t"
              f"{'ok' if ok else 'FAIL (instrument cannot see correctness)'}")
        blind = blind or not ok

    # Negative control: a stub must be SEEN failing, or the instrument is
    # blind (§5 G-BT — the U/O analogue of A3b).
    with tempfile.TemporaryDirectory(prefix="bt_stub_") as tmp:
        stub = Path(tmp)
        (stub / f"{module}.py").write_text(stub_source, encoding="utf-8")
        result = run_oracle(stub, module, entrypoint, cases,
                            timeout=args.timeout)
        ok = result.correctness < 0.5
        print(f"stub_o1\t{result.correctness:.4f}\t"
              f"{'ok (stub fails, instrument sees it)' if ok else 'FAIL (stub passes — O instrument is BLIND)'}")
        blind = blind or not ok

    # O3 legs need reference tests + the blind mutation battery.
    ref_tests = brief_dir / "tests"
    if mutations is not None and ref_tests.is_dir():
        test_cmd = _sandbox_test_cmd(bench)
        import shutil

        with tempfile.TemporaryDirectory(prefix="bt_o3_ref_") as tmp:
            ref = Path(tmp)
            (ref / f"{module}.py").write_text(
                oracle_path.read_text(encoding="utf-8"), encoding="utf-8")
            shutil.copytree(ref_tests, ref / "tests")
            try:
                smoke_rc = subprocess.run(
                    test_cmd, cwd=str(ref), capture_output=True, text=True,
                    timeout=args.mut_timeout).returncode
            except subprocess.TimeoutExpired:
                smoke_rc = -1
            if smoke_rc != 0:
                print(f"reference_o3\tFAIL (smoke rc={smoke_rc})")
                blind = True
            else:
                mut = run_mutations(ref, test_cmd, mutations,
                                    timeout=args.mut_timeout)
                ok = (mut.kill_rate >= bench.o3_min_kill_rate
                      and not mut.invalid)
                print(f"reference_o3\tkill_rate={mut.kill_rate:.4f}\t"
                      f"{'ok' if ok else 'FAIL'}")
                blind = blind or not ok
        with tempfile.TemporaryDirectory(prefix="bt_o3_stub_") as tmp:
            stub = Path(tmp)
            (stub / f"{module}.py").write_text(stub_source, encoding="utf-8")
            shutil.copytree(ref_tests, stub / "tests")
            try:
                stub_rc = subprocess.run(
                    test_cmd, cwd=str(stub), capture_output=True, text=True,
                    timeout=args.mut_timeout).returncode
            except subprocess.TimeoutExpired:
                stub_rc = -1
            ok = stub_rc != 0
            print(f"stub_o3_smoke\trc={stub_rc}\t"
                  f"{'ok (stub fails the smoke)' if ok else 'FAIL (stub passes the smoke — O3 is BLIND)'}")
            blind = blind or not ok
    else:
        print("o3_trust\tskipped\t(no reference tests/ or mutations.json — "
              "the O3 dimension is skipped upstream, never passed)")

    print(f"benchmark_trusted\t{not blind}")
    # A blind instrument means the run is NOT SCORABLE (§2 row 2), which is
    # exit 4 — never a scored block.
    return EXIT_NOT_SCORABLE if blind else EXIT_OK


# --------------------------------------------------------------------------- #
# score — transport deserialization + fail-closed re-derivations
# --------------------------------------------------------------------------- #


def _build_cell_counts(raw: dict, expected: int, *, family: str, arm_id: str):
    """Packed counts -> CellCounts with ``expected`` from the MANIFEST panel.

    Fail-closed accounting: the shortfall between the panel's ``expected`` and
    the packed ``complete+missing+timeout+error`` is added to ``missing`` — a
    packer that simply omits crashed cells still pays ``incomplete_fraction``.
    A packed ``expected`` that disagrees with the panel, or more cells than
    the panel defines, is a packing error (load error), never reconciled.
    """
    from eval_overexplanation.score import CellCounts

    complete = int(raw.get("complete", 0))
    missing = int(raw.get("missing", 0))
    timeout = int(raw.get("timeout", 0))
    error = int(raw.get("error", 0))
    if "expected" in raw and int(raw["expected"]) != expected:
        raise _LoadError(
            f"arm {arm_id} {family}: packed expected={raw['expected']} "
            f"contradicts the manifest panel ({expected}); expected is "
            "computed from the manifest, never packed")
    observed = complete + missing + timeout + error
    if observed > expected:
        raise _LoadError(
            f"arm {arm_id} {family}: {observed} cells packed but the "
            f"manifest panel defines {expected}")
    missing += expected - observed
    return CellCounts(
        expected=expected,
        complete=complete,
        missing=missing,
        timeout=timeout,
        error=error,
        retried=int(raw.get("retried", 0)),
        merge_skipped=int(raw.get("merge_skipped", 0)),
        mutations_skipped=int(raw.get("mutations_skipped", 0)),
        holdout_skipped=int(raw.get("holdout_skipped", 0)),
    )


def _opt_float_field(raw: dict, key: str) -> float | None:
    value = raw.get(key)
    return None if value is None else float(value)


def _req_nullable_float(raw: dict, key: str) -> float | None:
    """A REQUIRED key whose value may be an explicit null (no signal).

    Absence is a load error (``KeyError``, mapped by the caller): a packer
    that DELETES a no-signal-capable key must never silently change a gate's
    routing — an explicit ``null`` is the only way to say "no signal".
    """
    value = raw[key]
    return None if value is None else float(value)


def _build_gate_values(raw: dict):
    from eval_overexplanation.score import GateValues

    # Every key is REQUIRED — the nullable ones (c0_leak_hits, o1_correctness,
    # o2_overfit, o3_kill_rate, l4_spec_only_correctness) demand an explicit
    # null for their no-signal state; a missing key is a load error, never a
    # silently-green (or silently-omitted) gate.
    c0 = raw["c0_leak_hits"]
    return GateValues(
        c0_leak_hits=None if c0 is None else int(c0),
        c2_dropped_must=int(raw["c2_dropped_must"]),
        c7_merge_failures=int(raw["c7_merge_failures"]),
        c8_frag_rate=float(raw["c8_frag_rate"]),
        u0_prompt_sha_ok=bool(raw["u0_prompt_sha_ok"]),
        u0_leak_hits=int(raw["u0_leak_hits"]),
        u3_max_dead_ends=int(raw["u3_max_dead_ends"]),
        u4_completion_fraction=float(raw["u4_completion_fraction"]),
        u5_clarifying_questions=int(raw["u5_clarifying_questions"]),
        o1_correctness=_req_nullable_float(raw, "o1_correctness"),
        o1_regressed_cells=tuple(
            str(c) for c in raw["o1_regressed_cells"]),
        o2_overfit=_req_nullable_float(raw, "o2_overfit"),
        o3_kill_rate=_req_nullable_float(raw, "o3_kill_rate"),
        o3_invalid=int(raw["o3_invalid"]),
        o4_workarounds=int(raw["o4_workarounds"]),
        l1_code_frac=float(raw["l1_code_frac"]),
        l2_reference_containment=float(raw["l2_reference_containment"]),
        l3_copy_containment=float(raw["l3_copy_containment"]),
        l4_spec_only_correctness=_req_nullable_float(
            raw, "l4_spec_only_correctness"),
    )


#: Legacy collapsed-boolean transport keys -> the TOST family each one
#: shadowed. They are no longer the source of anything: if packed they must
#: MATCH the value recomputed from the raw TostStats (mismatch = load error).
_LEGACY_TOST_BOOLEANS: dict[str, str] = {
    "c3_non_inferior": "C3",
    "c8_non_inferior": "C8",
    "u2_non_inferior": "U2",
    "u3_non_inferior": "U3",
    "o1_non_inferior": "O1",
    "o3_non_inferior": "O3",
}


def _build_arm_tost(raw_arm: dict, *, arm_id: str, thresholds):
    """The REQUIRED per-family raw TOST numerics for one packed arm.

    All six ``ALL_TOST_FAMILIES`` keys are required; an explicit ``null``
    means no TOST signal for that family (fail-closed downstream: the
    non-inferiority gate FAILS and the family is not certifiable). Each
    non-null entry's ``margin`` must equal the manifest's
    ``bench.tost_margins`` value — the manifest is the margin authority, so
    a run tested against the wrong band is a load error, never scored.
    """
    from eval_overexplanation.score import ALL_TOST_FAMILIES, TostStats

    if "tost" not in raw_arm:
        raise _LoadError(
            f"arm {arm_id}: missing 'tost' — the per-family raw TOST "
            "numerics are REQUIRED (the scorer recomputes non_inferior and "
            "certifiable; booleans are never the source)")
    packed = dict(raw_arm["tost"])
    unknown = sorted(set(packed) - set(ALL_TOST_FAMILIES))
    if unknown:
        raise _LoadError(f"arm {arm_id}: unknown tost families {unknown}")
    out: dict[str, TostStats] = {}
    for family in ALL_TOST_FAMILIES:
        if family not in packed:
            raise _LoadError(
                f"arm {arm_id}: tost[{family!r}] missing — pack the raw "
                "stats or an explicit null (no signal, fail-closed); an "
                "absent key is a load error")
        entry = packed[family]
        if entry is None:
            continue
        entry = dict(entry)
        stats = TostStats(
            estimate=float(entry["estimate"]),
            ci90=(float(entry["ci90"][0]), float(entry["ci90"][1])),
            p_value=float(entry["p_value"]),
            achieved_power=float(entry["achieved_power"]),
            margin=float(entry["margin"]),
        )
        expected_margin = thresholds.tost_margins.get(family)
        if (expected_margin is None
                or abs(stats.margin - float(expected_margin)) > 1e-9):
            raise _LoadError(
                f"arm {arm_id}: tost[{family!r}] margin {stats.margin} "
                f"contradicts bench.tost_margins ({expected_margin}) — the "
                "manifest is the margin authority; a run tested against the "
                "wrong band cannot be scored")
        out[family] = stats
    return out


def _cross_check_tost_booleans(raw_arm: dict, gate_raw: dict, tost, *,
                               arm_id: str, thresholds) -> None:
    """Packed TOST booleans are at most cross-checks; mismatch = load error.

    The scorer recomputes ``non_inferior`` (90% CI strictly inside the
    manifest margin band) and ``certifiable`` (achieved power >= manifest
    min_power) from the raw stats. A packed boolean that contradicts the
    recomputation means the packer and the raw numerics disagree — a load
    error, never reconciled in either direction.
    """
    from eval_overexplanation.score import tost_certifiable, tost_non_inferior

    for key, family in _LEGACY_TOST_BOOLEANS.items():
        if key not in gate_raw:
            continue
        packed = bool(gate_raw.pop(key))
        margin = float(thresholds.tost_margins.get(family, 0.0))
        derived = tost_non_inferior(tost.get(family), margin)
        if packed != derived:
            raise _LoadError(
                f"arm {arm_id}: packed {key}={packed} contradicts the "
                f"recomputed non-inferiority {derived} (90% CI vs the "
                f"manifest {family} margin {margin}) — a packed boolean is "
                "at most a cross-check, never the source")
    if "tost_certifiable" in raw_arm:
        for family, flag in dict(raw_arm["tost_certifiable"]).items():
            derived = tost_certifiable(tost.get(str(family)),
                                       thresholds.min_power)
            if bool(flag) != derived:
                raise _LoadError(
                    f"arm {arm_id}: packed tost_certifiable[{family!r}]="
                    f"{bool(flag)} contradicts the recomputed {derived} "
                    f"(achieved_power vs min_power {thresholds.min_power}) — "
                    "a packed boolean is at most a cross-check, never the "
                    "source")


def _metric_field_matches(got: object, expected: object) -> bool:
    """Tolerant equality for a packed metric field vs its derived value.

    Floats compare within the same 1e-9 tolerance the tost-margin check
    uses (JSON round-tripping a Python float must never itself read as a
    contradiction); tuples/lists compare element-wise; dicts (the ``tost``
    sub-object) compare by key set + recursive value match.
    """
    if isinstance(expected, dict) and isinstance(got, dict):
        return set(got) == set(expected) and all(
            _metric_field_matches(got[k], expected[k]) for k in expected)
    if isinstance(expected, (list, tuple)) and isinstance(got, (list, tuple)):
        if len(got) != len(expected):
            return False
        return all(_metric_field_matches(g, e) for g, e in zip(got, expected))
    if isinstance(expected, float) or isinstance(got, float):
        try:
            return abs(float(got) - float(expected)) <= 1e-9  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return got == expected
    return got == expected


def _cross_check_metrics(arm, *, thresholds) -> None:
    """Packed ``metrics[dim][id]`` fields for derivable ids are at most
    cross-checks; mismatch = load error.

    ``score.derive_metric_fields`` is the single source of truth the
    scorer renders from regardless — this check exists so a packer whose
    numbers already disagree with the operative fields (gate_values, tost,
    c1, u1, bloat_ln) fails loud at load time instead of only being masked
    by the scorer's own re-derivation downstream.
    """
    from eval_overexplanation.score import (
        DERIVABLE_METRIC_IDS,
        derive_metric_fields,
        non_inferior_flags,
    )

    ni = non_inferior_flags(arm.tost, thresholds)
    for dim, ids in DERIVABLE_METRIC_IDS.items():
        for metric in arm.metrics.get(dim, ()):
            if metric.id not in ids:
                continue
            derived = derive_metric_fields(metric.id, arm, thresholds, ni)
            if derived is None:
                continue
            packed: dict[str, object] = dict(metric.extra)
            if "ci" in derived:
                packed["ci"] = None if metric.ci is None else list(metric.ci)
            if "p_holm" in derived:
                packed["p_holm"] = metric.p_holm
            for field, expected in derived.items():
                if field not in packed:
                    continue  # packer omitted this derivable field: fine
                got = packed[field]
                if not _metric_field_matches(got, expected):
                    raise _LoadError(
                        f"arm {arm.arm_id}: metrics[{dim!r}][{metric.id!r}]."
                        f"{field}={got!r} contradicts the derived {expected!r} "
                        "— a packed metric field is at most a cross-check "
                        "against the scorer's own recomputation, never the "
                        "source (score.py always renders the derived value)")


def _build_metric_values(raw: list):
    from eval_overexplanation.score import MetricValue

    metrics = []
    for m in raw:
        ci = m.get("ci")
        metrics.append(MetricValue(
            id=str(m["id"]),
            value=float(m.get("value", 0.0)),
            ci=None if ci is None else (float(ci[0]), float(ci[1])),
            p_holm=_opt_float_field(m, "p_holm"),
            extra=dict(m.get("extra", {})),
        ))
    return tuple(metrics)


def _build_arm_inputs(raw: dict, *, expected_generate: int,
                      expected_implement: int, u_arms: frozenset[str],
                      thresholds):
    from eval_overexplanation.score import ArmInputs, C1Stats, U1Stats

    arm_id = str(raw["arm_id"])
    raw_cells = dict(raw.get("cells", {}))
    known = set(raw_cells) - {"generate", "implement"}
    if known:
        raise _LoadError(f"arm {arm_id}: unknown cell families {sorted(known)}")
    if "implement" in raw_cells and arm_id not in u_arms:
        raise _LoadError(
            f"arm {arm_id}: implement cells packed but the arm is not in "
            "bench.u_arms")
    cells = {"generate": _build_cell_counts(
        dict(raw_cells.get("generate", {})), expected_generate,
        family="generate", arm_id=arm_id)}
    if arm_id in u_arms:
        # An absent implement family is ALL-missing, never absent-and-green.
        cells["implement"] = _build_cell_counts(
            dict(raw_cells.get("implement", {})), expected_implement,
            family="implement", arm_id=arm_id)

    # O-term skip accounting is DERIVED, never caller-trusted: the fractions
    # come from the packed cell counts themselves (skipped cells over the
    # manifest panel's expected implement cells), so a packer cannot claim a
    # small fraction over many skipped cells (the round-3 hole: packed 0.01
    # with 8 holdout_skipped cells routed past both the O2 gate and row 9).
    # A packed fraction is at most a cross-check: any mismatch with the
    # derived value (at the schema's 3-decimal precision) is a load error.
    if arm_id in u_arms:
        impl_counts = cells["implement"]
        o2_skipped = (impl_counts.holdout_skipped / expected_implement
                      if expected_implement else 0.0)
        o3_skipped = (impl_counts.mutations_skipped / expected_implement
                      if expected_implement else 0.0)
        for key, derived, count in (
                ("o2_skipped_fraction", o2_skipped,
                 impl_counts.holdout_skipped),
                ("o3_skipped_fraction", o3_skipped,
                 impl_counts.mutations_skipped)):
            if key in raw and round(float(raw[key]), 3) != round(derived, 3):
                raise _LoadError(
                    f"arm {arm_id}: packed {key}={raw[key]} contradicts the "
                    f"derived {derived:.3f} ({count} skipped cells / "
                    f"{expected_implement} expected implement cells) — the "
                    "fraction is derived from the packed counts; a packed "
                    "value is at most a cross-check, never the source")
    else:
        for key in ("o2_skipped_fraction", "o3_skipped_fraction"):
            if float(raw.get(key, 0.0) or 0.0) != 0.0:
                raise _LoadError(
                    f"arm {arm_id}: {key} packed but the arm is not in "
                    "bench.u_arms (no implement family exists to skip)")
        o2_skipped = o3_skipped = 0.0

    tost = _build_arm_tost(raw, arm_id=arm_id, thresholds=thresholds)
    gate_raw = dict(raw["gate_values"])
    # Legacy collapsed booleans (c3/c8/u2/u3/o1/o3_non_inferior and the
    # tost_certifiable map) are at most cross-checks against the recomputed
    # values; a mismatch is a load error and the keys are consumed here so
    # GateValues never sees them.
    _cross_check_tost_booleans(raw, gate_raw, tost, arm_id=arm_id,
                               thresholds=thresholds)

    c1 = dict(raw["c1"])
    u1 = dict(raw["u1"])
    arm = ArmInputs(
        arm_id=arm_id,
        cells=cells,
        gate_values=_build_gate_values(gate_raw),
        tost=tost,
        c1=C1Stats(
            mean_delta=float(c1["mean_delta"]),
            ci=(float(c1["ci"][0]), float(c1["ci"][1])),
            p_holm=float(c1["p_holm"]),
            sign_stable=bool(c1["sign_stable"]),
            large_realistic_delta=float(c1["large_realistic_delta"]),
        ),
        u1=U1Stats(
            mean_delta=float(u1["mean_delta"]),
            p_holm=float(u1["p_holm"]),
        ),
        correctness_holdout=_opt_float_field(raw, "correctness_holdout"),
        bloat_ln=float(raw["bloat_ln"]),
        o2_skipped_fraction=o2_skipped,
        o3_skipped_fraction=o3_skipped,
        metrics={str(dim): _build_metric_values(list(values))
                 for dim, values in dict(raw.get("metrics", {})).items()},
        covariates={str(k): float(v)
                    for k, v in dict(raw.get("covariates", {})).items()},
    )
    # dimensions.<D>.metrics coupling rule (§2, extended from gate_values/tost
    # to the last unchecked packer-passthrough surface): every derivable id's
    # fields are cross-checked against the scorer's own recomputation — a
    # packed value that disagrees is a load error, never reconciled toward
    # the packer. The scorer re-derives these fields at render time
    # regardless (single source of truth); this check exists so a bad
    # packer fails LOUD at load, not silently self-heals downstream.
    _cross_check_metrics(arm, thresholds=thresholds)
    return arm


def _derive_strata(reg) -> dict[str, dict[str, int]]:
    """§0 strata coverage, derived from the MANIFEST briefs — never packed.

    C strata are per-regime counts over ALL briefs; U and O strata are
    per-regime counts over the BUILDABLE briefs (the only ones with
    implement/outcome cells). Every regime key is present (zero when the
    panel has no brief in it — a zero must fail row 9, not vanish).
    """
    from eval_overexplanation.models import Regime

    def counts(briefs) -> dict[str, int]:
        out = {regime.value: 0 for regime in Regime}
        for brief in briefs:
            out[brief.regime.value] += 1
        return out

    buildable = counts(b for b in reg.briefs if b.buildable)
    return {"C": counts(reg.briefs), "U": dict(buildable),
            "O": dict(buildable)}


def _cmd_score(args: argparse.Namespace) -> int:
    from eval_overexplanation.score import (
        Budget,
        ScoreInputs,
        ScoreThresholds,
        Stops,
        exit_code,
        render_score_json,
        score_report,
        thresholds_from_bench,
    )

    raw = _load_json(Path(args.inputs))
    if not isinstance(raw, dict):
        raise _LoadError(f"{args.inputs}: expected a ScoreInputs object")

    reg = _load_registration(args.manifest)
    if reg is None:  # pragma: no cover - argparse required=True guards this
        raise _LoadError("score requires --manifest")

    # Fail-closed re-derivations: the hash match is recomputed from the
    # manifest FILE against the hash the packer recorded — never accepted as
    # a caller-supplied boolean; validate() problems come from the same file.
    recomputed = reg.content_hash()
    packed_hash = raw.get("manifest_content_hash")
    if not isinstance(packed_hash, str) or not packed_hash:
        raise _LoadError(
            f"{args.inputs}: manifest_content_hash is required (the hash the "
            "run was frozen against; the match is recomputed here)")
    normalized = packed_hash.removeprefix("sha256:")
    hash_matches = normalized == recomputed
    # --corpus is REQUIRED for score: validate() always applies the §4
    # per-brief asset rules, so a buildable brief without its blind
    # cases_holdout.json/mutations.json is a manifest problem => §2 row 0
    # scorable:false — never a quiet per-cell skip nobody opted into.
    problems = reg.validate(corpus_root=Path(args.corpus))

    thresholds = (thresholds_from_bench(reg.bench)
                  if reg.bench is not None else ScoreThresholds())
    bench = _bench_of(reg)
    u_arms = frozenset(bench.u_arms)

    # Panel dimensions from the manifest, never from the packed cells.
    n_briefs = len(reg.briefs)
    n_buildable = sum(1 for b in reg.briefs if b.buildable)
    k_seeds = len(reg.seeds)
    expected_generate = n_briefs * k_seeds
    expected_implement = n_buildable * k_seeds

    # Strata coverage is DERIVED from the manifest briefs (C = per-regime
    # brief counts, U/O = per-regime BUILDABLE counts) — never accepted from
    # the packer, whose inflated 3/3/3 once made SHIP reachable on a panel
    # that is structurally UNDERPOWERED per the pre-registration. A packed
    # value is at most a cross-check: contradiction is a load error.
    derived_strata = _derive_strata(reg)
    if "strata_coverage" in raw:
        try:
            packed_strata = {
                str(dim): {str(k): int(v) for k, v in dict(strata).items()}
                for dim, strata in dict(raw["strata_coverage"]).items()}
        except (ValueError, TypeError, AttributeError) as exc:
            raise _LoadError(
                f"{args.inputs}: malformed strata_coverage: {exc}") from exc
        if packed_strata != derived_strata:
            raise _LoadError(
                f"{args.inputs}: packed strata_coverage {packed_strata} "
                f"contradicts the manifest-derived {derived_strata} — "
                "strata are derived from the pre-registered briefs, never "
                "packed")

    # The noise floors are the denominators of every scored win: a floor of
    # zero (estimate_noise_floor over EMPTY inputs) means no baseline
    # replicate data existed — not scorable, never free significance (a
    # nf_C of 0.0 would make ANY negative mean delta clear the C1 gate and
    # scale S_C from zero).
    import math

    for key in ("noise_floor_c", "noise_floor_u"):
        try:
            floor = float(raw[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise _LoadError(
                f"{args.inputs}: {key} is required and numeric ({exc})"
            ) from exc
        if not math.isfinite(floor) or floor <= 0.0:
            raise _LoadError(
                f"{args.inputs}: {key}={raw[key]!r} is not a positive finite "
                "noise floor — a zero/degenerate floor means no baseline "
                "replicate data existed (estimate_noise_floor over empty "
                "inputs): not scorable, never free significance")

    # Arm identities must exist in the manifest — an arm the pre-registration
    # never declared can neither be scored nor drive the verdict — and each
    # may be packed at most once: with duplicates the first-match treatment
    # lookup and the last-wins rendered arms dict would contradict each
    # other inside one score.json.
    manifest_arm_ids = {arm.id for arm in reg.arms}
    for role in ("baseline_arm", "treatment_arm"):
        arm_id = str(raw.get(role, ""))
        if arm_id not in manifest_arm_ids:
            raise _LoadError(
                f"{args.inputs}: {role} {arm_id!r} is not a manifest arm "
                f"(declared: {sorted(manifest_arm_ids)})")
    seen_arm_ids: set[str] = set()
    for packed_arm in raw.get("arms", ()):
        arm_id = str(dict(packed_arm).get("arm_id", ""))
        if arm_id not in manifest_arm_ids:
            raise _LoadError(
                f"{args.inputs}: packed arm {arm_id!r} is not a manifest arm "
                f"(declared: {sorted(manifest_arm_ids)})")
        if arm_id in seen_arm_ids:
            raise _LoadError(
                f"{args.inputs}: arm {arm_id!r} packed more than once — one "
                "arm, one record; a duplicate would score one record and "
                "render another")
        seen_arm_ids.add(arm_id)

    try:
        # REQUIRED, every key explicit: a §2 row-4 STOP is the one record a
        # packer is most tempted to lose. With an optional block and per-key
        # defaults, DELETING a fired STOP shipped a fabricated clean STOP
        # record inside score.json — no schema trace, gate silently dropped.
        # Absent block or absent key = load error, exactly like the six
        # sibling booleans around it.
        raw_stops = dict(raw["stops"])
        raw_budget = dict(raw["budget"])
        inputs = ScoreInputs(
            manifest_content_hash=f"sha256:{recomputed}",
            manifest_hash_matches=hash_matches,
            manifest_problems=problems,
            generated_at=str(raw["generated_at"]),
            instrument_trusted=bool(raw["instrument_trusted"]),
            benchmark_trusted=bool(raw["benchmark_trusted"]),
            a3b_fails_grammaticality=bool(raw["a3b_fails_grammaticality"]),
            stops=Stops(
                c_length_falsification=bool(
                    raw_stops["c_length_falsification"]),
                c_distinct_dilution=bool(raw_stops["c_distinct_dilution"]),
                u_below_detectable_floor=bool(
                    raw_stops["u_below_detectable_floor"]),
                u_length_falsification=bool(
                    raw_stops["u_length_falsification"]),
            ),
            noise_floor_c=float(raw["noise_floor_c"]),
            noise_floor_u=float(raw["noise_floor_u"]),
            n_briefs=n_briefs,
            n_buildable=n_buildable,
            k_seeds=k_seeds,
            extractor_families=reg.extractor_families,
            strata_coverage=derived_strata,
            baseline_arm=str(raw["baseline_arm"]),
            treatment_arm=str(raw["treatment_arm"]),
            arms=tuple(
                _build_arm_inputs(
                    dict(arm),
                    expected_generate=expected_generate,
                    expected_implement=expected_implement,
                    u_arms=u_arms,
                    thresholds=thresholds)
                for arm in raw["arms"]),
            # bench.max_usd is the budget authority (§4): the packed max is
            # ignored and exhaustion is re-derived fail-closed, so a packer
            # cannot widen the pre-registered cap after the spend.
            budget=Budget(
                spent_usd=float(raw_budget["spent_usd"]),
                projected_usd=float(raw_budget["projected_usd"]),
                max_usd=bench.max_usd,
                exhausted=(bool(raw_budget["exhausted"])
                           or float(raw_budget["spent_usd"]) > bench.max_usd),
            ),
            a4_captures_effect=bool(raw["a4_captures_effect"]),
            beats_a3_fair=bool(raw["beats_a3_fair"]),
            beats_a2_placebo=bool(raw["beats_a2_placebo"]),
            beats_a3_fair_detail=str(raw.get("beats_a3_fair_detail", "")),
            beats_a2_placebo_detail=str(
                raw.get("beats_a2_placebo_detail", "")),
            thresholds=thresholds,
        )
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise _LoadError(f"{args.inputs}: malformed ScoreInputs: {exc}") from exc

    report = score_report(inputs)
    rendered = render_score_json(report)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    print(rendered)
    return exit_code(report)


# --------------------------------------------------------------------------- #
# Argument parser
# --------------------------------------------------------------------------- #


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval-overexplanation",
        description="Over-explanation benchmark harness CLI (thin wiring).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_rest = sub.add_parser(
        "restatement", help="per-(arm,brief,seed) restatement scores"
    )
    p_rest.add_argument("results_dir", type=Path)
    p_rest.set_defaults(func=_cmd_restatement)

    p_guard = sub.add_parser(
        "guardrails",
        help="substance recall + merge fidelity + grammaticality (non-zero on block)",
    )
    p_guard.add_argument("results_dir", type=Path)
    p_guard.set_defaults(func=_cmd_guardrails)

    p_stats = sub.add_parser(
        "stats",
        help="paired Wilcoxon + bootstrap + length-falsification STOP (non-zero on STOP)",
    )
    p_stats.add_argument("results_dir", type=Path)
    p_stats.set_defaults(func=_cmd_stats)

    p_build = sub.add_parser(
        "buildability", help="executed oracle + mutation kill-rate"
    )
    p_build.add_argument("corpus", type=Path)
    p_build.add_argument("impl_dir", type=Path)
    p_build.add_argument(
        "--module", required=True, help="impl module to import in the sandbox"
    )
    p_build.add_argument(
        "--entrypoint", required=True, help="callable to invoke per oracle case"
    )
    p_build.add_argument("--timeout", type=float, default=30.0)
    p_build.add_argument(
        "--mutations", default=None, help="optional mutations.json for mutation testing"
    )
    p_build.add_argument(
        "--test-cmd",
        dest="test_cmd",
        nargs=argparse.REMAINDER,
        default=["uv", "run", "pytest", "-q"],
        help="test command for mutation testing (default: uv run pytest -q)",
    )
    p_build.add_argument("--mut-timeout", dest="mut_timeout", type=float, default=120.0)
    p_build.set_defaults(func=_cmd_buildability)

    p_hash = sub.add_parser(
        "manifest-hash", help="print the pre-registration content_hash"
    )
    p_hash.add_argument("manifest", type=Path)
    p_hash.set_defaults(func=_cmd_manifest_hash)

    p_decision = sub.add_parser(
        "decision",
        help="run the SHIP/KILL rule over a DecisionInputs JSON "
        "(non-zero on DO_NOT_SHIP / UNDERPOWERED)",
    )
    p_decision.add_argument("inputs", type=Path)
    p_decision.set_defaults(func=_cmd_decision)

    p_instrument = sub.add_parser(
        "instrument",
        help="run the instrument-trust gate over docs + decoys "
        "(non-zero if not trusted)",
    )
    p_instrument.add_argument("docs", type=Path)
    p_instrument.add_argument("decoys", type=Path)
    p_instrument.add_argument(
        "--family",
        choices=("fixture", "anthropic", "openai"),
        default="fixture",
        help="extractor family (default: fixture, offline)",
    )
    p_instrument.add_argument(
        "--fixtures",
        default=None,
        help="{document_id: PropositionSet} JSON for the default fixture extractor",
    )
    p_instrument.add_argument(
        "--model",
        default="",
        help="model id for a live --family anthropic|openai extractor",
    )
    p_instrument.set_defaults(func=_cmd_instrument)

    p_sweep = sub.add_parser(
        "sweep",
        help="dedup-threshold stability sweep over a {threshold: [rates]} JSON",
    )
    p_sweep.add_argument("sweep", type=Path)
    p_sweep.set_defaults(func=_cmd_sweep)

    # -- BLUEPRINT-BENCH subcommands (BENCHMARK.md §3) ---------------------- #

    p_usage = sub.add_parser(
        "usage",
        help="parse one implement-cell transcript fail-closed "
        "(non-zero unless status == ok)",
    )
    p_usage.add_argument("transcript", type=Path)
    p_usage.add_argument(
        "--return-code", type=int, default=0,
        help="the cell's recorded CLI return code (124 => timeout)",
    )
    p_usage.set_defaults(func=_cmd_usage)

    p_deadend = sub.add_parser(
        "deadend",
        help="U0/U3/U5 transcript signals (non-zero on leak hit, clarifying "
        "question, or dead-end cap)",
    )
    p_deadend.add_argument("transcript", type=Path)
    p_deadend.add_argument(
        "--manifest", default=None,
        help="manifest supplying bench.leak_patterns + bench.dead_end_cap",
    )
    p_deadend.set_defaults(func=_cmd_deadend)

    p_leakage = sub.add_parser(
        "leakage",
        help="L1-L4 spec-embeds-implementation control (non-zero if blocked)",
    )
    p_leakage.add_argument("spec", type=Path, help="the arm's captured spec .md")
    p_leakage.add_argument("brief_dir", type=Path,
                           help="corpus brief dir (oracle.py + brief.json)")
    p_leakage.add_argument("impl_dir", type=Path,
                           help="the implementer workspace")
    p_leakage.add_argument("--manifest", default=None,
                           help="manifest supplying bench.leak_caps")
    p_leakage.add_argument("--timeout", type=float, default=30.0)
    p_leakage.set_defaults(func=_cmd_leakage)

    p_outcome = sub.add_parser(
        "outcome",
        help="O1-O5 for one implement cell; owns the O3 merged reference dir "
        "(non-zero on any present gate failing)",
    )
    p_outcome.add_argument("brief_dir", type=Path)
    p_outcome.add_argument("impl_dir", type=Path)
    p_outcome.add_argument("--manifest", default=None)
    p_outcome.add_argument("--timeout", type=float, default=30.0)
    p_outcome.add_argument("--mut-timeout", dest="mut_timeout", type=float,
                           default=120.0)
    p_outcome.set_defaults(func=_cmd_outcome)

    p_bt = sub.add_parser(
        "bench-trust",
        help="G-BT reference+stub controls on the O instrument "
        "(exit 4 if the instrument is blind)",
    )
    p_bt.add_argument("brief_dir", type=Path)
    p_bt.add_argument("--manifest", default=None)
    p_bt.add_argument("--timeout", type=float, default=30.0)
    p_bt.add_argument("--mut-timeout", dest="mut_timeout", type=float,
                      default=120.0)
    p_bt.set_defaults(func=_cmd_bench_trust)

    p_score = sub.add_parser(
        "score",
        help="apply the §2 precedence over a packed ScoreInputs transport and "
        "render canonical score.json (exit 0 pass / 1 blocked / 4 not scorable)",
    )
    p_score.add_argument("inputs", type=Path)
    p_score.add_argument(
        "--manifest", required=True,
        help="the pre-registration; hash match, validate(), thresholds and "
        "the cell-count panel are re-derived from THIS file",
    )
    p_score.add_argument(
        "--corpus", required=True,
        help="corpus root (REQUIRED): validate() always enforces the §4 "
        "per-brief asset rules (buildable briefs need cases_holdout.json + "
        "mutations.json) — problems make the run not scorable",
    )
    p_score.add_argument("--out", default=None,
                         help="also write the rendered score.json here")
    p_score.set_defaults(func=_cmd_score)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv``, dispatch to a subcommand, return the process exit code.

    Returns non-zero on any guardrail block / STOP (``EXIT_BLOCKED``) or input
    load failure (``EXIT_LOAD_ERROR``); argparse handles its own usage errors
    (exit code 2) for an unknown subcommand or missing argument.
    """
    import sys

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except _LoadError as exc:
        # A load failure is a clean, expected outcome (missing/malformed input),
        # not a usage error, so we return the code rather than raising SystemExit
        # — main(argv) -> int stays a pure function the tests can call directly.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_LOAD_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

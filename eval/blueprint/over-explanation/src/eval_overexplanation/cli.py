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

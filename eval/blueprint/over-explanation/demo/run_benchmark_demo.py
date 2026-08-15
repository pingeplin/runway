"""Offline BLUEPRINT-BENCH demo: pack real ScoreInputs, emit a real score.json.

This drives the *real* bench machinery end-to-end with zero network:

* the whole-document leakage detector (``deadend.spec_code_lines`` /
  ``leakage_report``) over a synthetic spec — including the ``--break leakage``
  vector, an UNFENCED indented paste of the demo oracle, which the reworked
  detector must gate (fence-only detection would wave it through);
* fail-closed transcript parsing (``usage.parse_usage`` +
  ``deadend.deadend_report``) over synthetic stream-json transcripts;
* the O4 AST workaround lint over a synthetic implementer workspace;
* the manifest's frozen ``bench.*`` thresholds (never Python defaults);
* the ``overexpl score`` CLI packer itself — manifest-hash recompute, the
  CellCounts invariant against the manifest panel, the §2 precedence, and the
  canonical byte-stable serializer.

Like ``run_demo.py`` this proves the mechanisms *compose*; the arm numbers are
synthetic, so no verdict here says anything about the real treatment.

The CLEAN run's verdict is ``UNDERPOWERED`` (exit 1), not SHIP: strata
coverage is derived from the manifest briefs (never packed), and the demo
panel is structurally underpowered for U/O by design — the buildable
``large_realistic`` stratum has n=1 < 3 (BENCHMARK.md §0 N ceiling). A SHIP
verdict is unreachable at demo scale, which is exactly the pre-registration.

Run::

    uv run python demo/run_benchmark_demo.py [--break MODE] [--out DIR]

``--break`` modes (each must exit non-zero, blocking BEFORE the structural
row-9 underpowered routing):

* ``leakage``        — unfenced oracle paste in the spec: the L1/L2 gates AND
                       the executed L4 control (whole-document extraction runs
                       the paste at correctness 1.0) trip, §2 row 7 blocks the
                       run (exit 1);
* ``workaround``     — the impl grows ``assert True`` + a TODO: O4 trips
                       (exit 1);
* ``missing-result`` — one implement transcript has no result event: the cell
                       is missing, U4 completion fails (exit 1);
* ``incomplete``     — three implement cells are simply not packed: the score
                       packer back-fills them as missing from the manifest
                       panel and the run is NOT SCORABLE (exit 4).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from eval_overexplanation import cli
from eval_overexplanation.deadend import deadend_report, leakage_report, workaround_lint
from eval_overexplanation.manifest import load_manifest
from eval_overexplanation.usage import parse_usage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MANIFEST = ROOT / "preregistration" / "manifest.demo.json"
CORPUS = ROOT / "corpus" / "demo"
ORACLE = CORPUS / "b01" / "oracle.py"

BREAK_MODES = ("leakage", "workaround", "missing-result", "incomplete")

HONEST_SPEC = """# Spec: fixed-window rate limiter

The limiter rejects requests beyond the per-tenant cap within one window.
Each tenant has an isolated bucket, and buckets reset when the window rolls.
Rejected requests are reported to the caller so it can back off.

Acceptance scenarios describe observable behaviour only: a request under the
cap is admitted, the first request past the cap is rejected, and a new window
admits again. The implementer chooses data structures freely.
"""

CLEAN_IMPL = '''"""Demo implementer output — an honest, boring implementation."""


def rate_limit(events, cap):
    admitted = []
    for window, count in events:
        admitted.append(count <= cap)
    return admitted
'''

WORKAROUND_IMPL = '''"""Demo implementer output with theater the O4 lint must catch."""


def rate_limit(events, cap):
    # TODO: actually implement the window roll
    assert True
    return []
'''


def _leaky_spec() -> str:
    """The honest spec plus the demo oracle pasted UNFENCED as indented text.

    This is gaming vector #1 in its sneakiest dress: no code fence at all, so
    a fence-only detector sees pure prose. The whole-document detector counts
    the indented lines as code and the L1/L2 gates trip.
    """
    oracle_text = ORACLE.read_text(encoding="utf-8")
    indented = "\n".join(f"    {line}" for line in oracle_text.splitlines())
    return (HONEST_SPEC
            + "\nFor reference, the implementation should look like this:\n\n"
            + indented + "\n")


def _implement_transcript(*, missing_result: bool) -> list[str]:
    """A synthetic stream-json implement-cell transcript (top-level events)."""
    lines = [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "t1", "name": "Write",
                "input": {"file_path": "rate_limiter.py",
                          "content": CLEAN_IMPL},
            }]},
        }),
        json.dumps({
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "t2", "name": "Bash",
                "input": {"command": "python -m pytest -q"},
            }]},
        }),
        json.dumps({
            "type": "user",
            "message": {"content": [{
                "type": "tool_result", "tool_use_id": "t2",
                "is_error": False,
            }]},
        }),
    ]
    if not missing_result:
        lines.append(json.dumps({
            "type": "result", "subtype": "success", "num_turns": 12,
            "usage": {"output_tokens": 2400, "input_tokens": 9000,
                      "cache_read_input_tokens": 0},
            "total_cost_usd": 0.42, "duration_ms": 80_000,
            "result": "Implemented the limiter and the test suite.",
        }))
    return lines


def _impl_workspace(tmp: Path, *, broken: bool) -> Path:
    impl = tmp / "workspace"
    (impl / "tests").mkdir(parents=True)
    (impl / "rate_limiter.py").write_text(
        WORKAROUND_IMPL if broken else CLEAN_IMPL, encoding="utf-8")
    (impl / "tests" / "test_rate_limiter.py").write_text(
        "from rate_limiter import rate_limit\n\n\n"
        "def test_under_cap_admitted():\n"
        "    assert rate_limit([(0, 1)], cap=2) == [True]\n",
        encoding="utf-8")
    return impl


def run(break_mode: str | None, out_dir: Path) -> int:
    reg = load_manifest(MANIFEST)
    bench = reg.bench
    assert bench is not None, "manifest.demo.json must carry the bench block"
    out_dir.mkdir(parents=True, exist_ok=True)

    # -- L1-L4 through the REAL whole-document detector -------------------- #
    spec_md = _leaky_spec() if break_mode == "leakage" else HONEST_SPEC
    # L4's executed control runs over the SAME whole-document detected code
    # as L1-L3 (dedented) — an unfenced indented paste of the b01 oracle
    # executes against the visible b01 cases and scores 1.0, so the leakage
    # break mode trips L4 as well as L1/L2 (a fence-only L4 saw nothing).
    soc = cli._spec_only_correctness(
        spec_md, CORPUS / "b01", "oracle", "allowed", timeout=30.0)
    with tempfile.TemporaryDirectory(prefix="bench_demo_") as tmp:
        impl_dir = _impl_workspace(Path(tmp),
                                   broken=(break_mode == "workaround"))
        impl_src = "\n".join(
            p.read_text(encoding="utf-8")
            for p in sorted(impl_dir.rglob("*.py")))
        leak = leakage_report(
            spec_md, ORACLE.read_text(encoding="utf-8"), impl_src,
            soc,  # None only when the spec has no detected code (clean spec)
            dict(bench.leak_caps))
        lint = workaround_lint(impl_dir, ())

    print("== leakage control (whole-document detector) ==")
    print(f"  code_frac             {leak.code_frac:.3f}  "
          f"(cap {bench.leak_caps['code_frac']})")
    print(f"  reference_containment {leak.reference_containment:.3f}  "
          f"(cap {bench.leak_caps['reference']})")
    print(f"  copy_containment      {leak.copy_containment:.3f}  "
          f"(cap {bench.leak_caps['copy']})")
    print(f"  blocked               {leak.blocked}")
    for reason in leak.reasons:
        print(f"    - {reason}")

    # -- U signals through the REAL fail-closed transcript parsers --------- #
    transcript = _implement_transcript(
        missing_result=(break_mode == "missing-result"))
    usage = parse_usage(transcript, return_code=0)
    dead = deadend_report(transcript, leak_patterns=bench.leak_patterns)
    print("\n== implement-cell transcript (fail-closed parse) ==")
    print(f"  status={usage.status} num_turns={usage.num_turns} "
          f"output_tokens={usage.output_tokens}")
    print(f"  dead_ends={dead.dead_ends} clarifying={dead.clarifying_questions} "
          f"leak_hits={len(dead.leak_hits)}")
    print(f"  O4 workarounds={lint.total}")

    # -- pack the ScoreInputs transport and drive `overexpl score` --------- #
    n_ok = 12 if usage.status == "ok" else 11
    implement_cells = {"complete": n_ok, "missing": 12 - n_ok}
    if break_mode == "incomplete":
        # Pack three crashed cells NOT AT ALL: the CLI must back-fill them as
        # missing from the manifest panel, never read the arm as complete.
        implement_cells = {"complete": 9}

    tost_ok = {"non_inferior": True, "power": 0.86, "certifiable": True}
    # Raw per-family TOST numerics: the CLI recomputes non_inferior (90% CI
    # strictly inside the manifest margin band) and certifiable
    # (achieved_power >= bench.min_power) from THESE — never from booleans.
    def tost_stats(family: str) -> dict:
        margin = bench.tost_margins[family]
        return {"estimate": 0.0, "ci90": [-margin / 4, margin / 4],
                "p_value": 0.012, "achieved_power": 0.86, "margin": margin}

    arm = {
        "arm_id": "A1",
        "cells": {"generate": {"complete": 18, "merge_skipped": 2},
                  "implement": implement_cells},
        "gate_values": {
            # No generate transcripts exist in this synthetic demo, so the
            # C0 scan (run-arm.sh cell.json leak fields) contributes 0 hits.
            "c0_leak_hits": 0,
            "c2_dropped_must": 0,
            "c7_merge_failures": 0,
            "c8_frag_rate": 0.03,
            "u0_prompt_sha_ok": True,
            "u0_leak_hits": len(dead.leak_hits),
            "u3_max_dead_ends": dead.dead_ends,
            "u4_completion_fraction": n_ok / 12.0,
            "u5_clarifying_questions": dead.clarifying_questions,
            "o1_correctness": 0.94,
            "o1_regressed_cells": [],
            "o2_overfit": 0.04,
            "o3_kill_rate": 0.875,
            "o3_invalid": 0,
            "o4_workarounds": lint.total,
            "l1_code_frac": leak.code_frac,
            "l2_reference_containment": leak.reference_containment,
            "l3_copy_containment": leak.copy_containment,
            # Explicit null = no signal (clean spec has no detected code);
            # in the leakage break mode this is the executed 1.0.
            "l4_spec_only_correctness": soc,
        },
        "tost": {family: tost_stats(family)
                 for family in ("C3", "C8", "U2", "U3", "O1", "O3")},
        "c1": {"mean_delta": -0.11, "ci": [-0.18, -0.04], "p_holm": 0.024,
               "sign_stable": True, "large_realistic_delta": -0.10},
        "u1": {"mean_delta": -0.23, "p_holm": 0.02},
        "correctness_holdout": 0.90,
        "bloat_ln": 0.11,
        # o2/o3_skipped_fraction are NOT packed: the CLI derives them from
        # the holdout_skipped/mutations_skipped counts (here 0) — a packed
        # value would be at most a cross-check.
        "metrics": {
            "C": [{"id": "C1", "value": -0.11, "ci": [-0.18, -0.04],
                   "p_holm": 0.024,
                   "extra": {"mean_delta": -0.11, "p": 0.008,
                             "sign_stable": True, "n": 9,
                             "large_realistic_delta": -0.10}},
                  {"id": "C3", "value": 1.0, "extra": {"tost": tost_ok}}],
            "U": [{"id": "U1", "value": -0.23, "p_holm": 0.02,
                   "extra": {"mean_delta": -0.23, "spend_index": 4821.0}}],
            "O": [{"id": "O3", "value": 0.875,
                   "extra": {"kill_rate": 0.875, "invalid": 0}}],
        },
        "covariates": {"word_count_delta": -210.0, "distinct_delta": -1.2},
    }
    inputs = {
        "manifest_content_hash": f"sha256:{reg.content_hash()}",
        "generated_at": "2026-08-13T00:00:00Z",
        "instrument_trusted": True,
        "benchmark_trusted": True,
        "a3b_fails_grammaticality": True,
        # All four STOP keys explicit: the block and every key are REQUIRED,
        # so a deleted STOP is a load error, never a clean-looking record.
        "stops": {"c_length_falsification": False,
                  "c_distinct_dilution": False,
                  "u_below_detectable_floor": False,
                  "u_length_falsification": False},
        "noise_floor_c": 0.031,
        "noise_floor_u": 0.084,
        # strata_coverage is NOT packed: the CLI derives it from the manifest
        # briefs (C 3/3/3; U/O 2/1/3 — buildable large_realistic n=1), so the
        # clean demo verdict is structurally UNDERPOWERED, per §0's N ceiling.
        "baseline_arm": "A0",
        "treatment_arm": "A1",
        "arms": [arm],
        "budget": {"spent_usd": 41.2, "projected_usd": 68.9,
                   "max_usd": bench.max_usd, "exhausted": False},
        "a4_captures_effect": False,
        "beats_a3_fair": True,
        "beats_a2_placebo": True,
    }

    inputs_path = out_dir / "score-inputs.json"
    inputs_path.write_text(json.dumps(inputs, indent=2), encoding="utf-8")
    score_path = out_dir / "score.json"

    print("\n== overexpl score (CLI packer + §2 precedence) ==")
    code = cli.main(["score", str(inputs_path), "--manifest", str(MANIFEST),
                     "--corpus", str(CORPUS), "--out", str(score_path)])

    obj = json.loads(score_path.read_text(encoding="utf-8"))
    print("\n" + "=" * 70)
    print(f"score.json: {score_path}")
    print(f"scorable={obj['scorable']} reason={obj['reason']} "
          f"verdict={obj['verdict'].upper()} exit={code}")
    for reason in obj["verdict_reasons"]:
        print(f"  - {reason}")
    if obj["arms"]:
        a1 = obj["arms"]["A1"]
        dims = a1["dimensions"]
        print(f"  subscores C={dims['C']['subscore']} U={dims['U']['subscore']} "
              f"O={dims['O']['subscore']} composite={a1['composite']['value']}")
        cells = a1["cells"]["implement"]
        print(f"  implement cells: expected={cells['expected']} "
              f"complete={cells['complete']} missing={cells['missing']} "
              f"incomplete_fraction={cells['incomplete_fraction']}")
    print("=" * 70)
    print("\nSYNTHETIC DEMO DATA — mechanism shakeout only, never a ship call.")
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline BLUEPRINT-BENCH end-to-end demo to a score.json.")
    parser.add_argument(
        "--break", dest="break_mode", default=None, choices=BREAK_MODES,
        help="flip one input to watch the matching bench gate block the run")
    parser.add_argument(
        "--out", type=Path, default=HERE / "out" / "bench",
        help="directory for score-inputs.json + score.json")
    args = parser.parse_args(argv)
    return run(args.break_mode, args.out)


if __name__ == "__main__":
    sys.exit(main())

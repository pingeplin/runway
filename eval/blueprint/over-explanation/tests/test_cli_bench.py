"""Tests for the BLUEPRINT-BENCH CLI subcommands (BENCHMARK.md §3 wiring).

The CLI owns no computation beyond the two things §3 assigns it — assembling
the O3 merged reference dir (+ smoke precondition) and the fail-closed score
packing — so these tests assert wiring, exit codes, and the fail-closed
re-derivations: manifest hash recompute, the CellCounts invariant against the
manifest panel (omitted crashed cells must still pay ``incomplete_fraction``),
and the skip-vs-pass distinction for absent holdout/mutation assets. All
offline: ``tmp_path`` fixtures, subprocess-sandboxed oracle runs only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval_overexplanation.cli import (
    EXIT_BLOCKED,
    EXIT_LOAD_ERROR,
    EXIT_NOT_SCORABLE,
    EXIT_OK,
    main,
)
from eval_overexplanation.manifest import load_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_MANIFEST = REPO_ROOT / "preregistration" / "manifest.demo.json"

ORACLE_SOURCE = '''"""Reference oracle: running total."""


def running_total(values):
    total = 0
    out = []
    for v in values:
        total += v
        out.append(total)
    return out
'''

CASES = {
    "cases": [
        {"label": "empty", "args": [[]], "expected": []},
        {"label": "one", "args": [[5]], "expected": [5]},
        {"label": "three", "args": [[1, 2, 3]], "expected": [1, 3, 6]},
    ]
}

HONEST_SPEC = """# Spec

Maintain a running total over a list of integers, returning the prefix sums
in input order. An empty input yields an empty output. The implementer is
free to choose any internal representation.
"""


def _write_transcript(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _result_event(**over: object) -> str:
    event = {
        "type": "result", "subtype": "success", "num_turns": 7,
        "usage": {"output_tokens": 900, "input_tokens": 4000},
        "total_cost_usd": 0.2, "duration_ms": 60_000,
        "result": "done",
    }
    event.update(over)
    return json.dumps(event)


def _tool_use(name: str, tool_input: dict, tool_id: str = "t1") -> str:
    return json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "id": tool_id,
                                 "name": name, "input": tool_input}]},
    })


def _brief_dir(tmp_path: Path, *, holdout: bool = False,
               mutations: bool = False) -> Path:
    brief = tmp_path / "brief"
    brief.mkdir()
    (brief / "brief.json").write_text(json.dumps({
        "id": "bX", "title": "Running total", "regime": "neutral",
        "buildable": True, "module": "running_total",
        "entrypoint": "running_total",
    }))
    (brief / "oracle.py").write_text(ORACLE_SOURCE)
    (brief / "cases.json").write_text(json.dumps(CASES))
    if holdout:
        (brief / "cases_holdout.json").write_text(json.dumps({
            "cases": [{"label": "h1", "args": [[7, 7]], "expected": [7, 14]}]
        }))
    if mutations:
        (brief / "mutations.json").write_text(json.dumps({
            "mutations": [{"label": "m1", "filename": "running_total.py",
                           "find": "total += v", "replace": "total -= v"}]
        }))
    return brief


def _impl_dir(tmp_path: Path, *, source: str = ORACLE_SOURCE,
              with_tests: bool = True) -> Path:
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / "running_total.py").write_text(source)
    if with_tests:
        (impl / "tests").mkdir()
        (impl / "tests" / "test_running_total.py").write_text(
            "from running_total import running_total\n\n\n"
            "def test_prefix_sums():\n"
            "    assert running_total([1, 2, 3]) == [1, 3, 6]\n\n\n"
            "def test_empty():\n"
            "    assert running_total([]) == []\n"
        )
    return impl


# --------------------------------------------------------------------------- #
# usage
# --------------------------------------------------------------------------- #


def test_usage_ok_exits_zero(tmp_path: Path,
                             capsys: pytest.CaptureFixture[str]) -> None:
    t = _write_transcript(tmp_path / "t.jsonl", [_result_event()])
    assert main(["usage", str(t)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "status\tok" in out
    assert "output_tokens\t900" in out


def test_usage_missing_result_event_blocks(tmp_path: Path,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    t = _write_transcript(tmp_path / "t.jsonl",
                          ['{"type":"system","subtype":"init"}'])
    assert main(["usage", str(t)]) == EXIT_BLOCKED
    assert "status\tmissing" in capsys.readouterr().out


def test_usage_timeout_rc_blocks(tmp_path: Path,
                                 capsys: pytest.CaptureFixture[str]) -> None:
    t = _write_transcript(tmp_path / "t.jsonl", [_result_event()])
    assert main(["usage", str(t), "--return-code", "124"]) == EXIT_BLOCKED
    assert "status\ttimeout" in capsys.readouterr().out


def test_usage_missing_file_is_load_error(tmp_path: Path) -> None:
    assert main(["usage", str(tmp_path / "no.jsonl")]) == EXIT_LOAD_ERROR


# --------------------------------------------------------------------------- #
# deadend
# --------------------------------------------------------------------------- #


def test_deadend_clean_transcript_exits_zero(tmp_path: Path) -> None:
    t = _write_transcript(tmp_path / "t.jsonl", [
        _tool_use("Bash", {"command": "ls"}),
        _result_event(),
    ])
    assert main(["deadend", str(t)]) == EXIT_OK


def test_deadend_leak_hit_blocks(tmp_path: Path,
                                 capsys: pytest.CaptureFixture[str]) -> None:
    t = _write_transcript(tmp_path / "t.jsonl", [
        _tool_use("Bash", {"command": "grep -r expected corpus/"}),
        _result_event(),
    ])
    assert main(["deadend", str(t)]) == EXIT_BLOCKED
    assert "leak_hits\t1" in capsys.readouterr().out


def test_deadend_clarifying_question_blocks(tmp_path: Path) -> None:
    t = _write_transcript(tmp_path / "t.jsonl", [
        _tool_use("AskUserQuestion", {"question": "which sort order?"}),
        _result_event(),
    ])
    assert main(["deadend", str(t)]) == EXIT_BLOCKED


def test_deadend_manifest_supplies_leak_patterns(tmp_path: Path) -> None:
    # The demo manifest's bench.leak_patterns must drive detection when given.
    t = _write_transcript(tmp_path / "t.jsonl", [
        _tool_use("Read", {"file_path": "/repo/corpus/b01/oracle.py"}),
        _result_event(),
    ])
    assert main(["deadend", str(t), "--manifest",
                 str(DEMO_MANIFEST)]) == EXIT_BLOCKED


# --------------------------------------------------------------------------- #
# leakage
# --------------------------------------------------------------------------- #


def test_leakage_honest_spec_exits_zero(tmp_path: Path) -> None:
    brief = _brief_dir(tmp_path)
    impl = _impl_dir(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text(HONEST_SPEC)
    assert main(["leakage", str(spec), str(brief), str(impl)]) == EXIT_OK


def test_leakage_unfenced_oracle_paste_blocks(tmp_path: Path,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    # The review's gating vector: the oracle pasted with NO fence, indented as
    # markdown code. The whole-document detector must gate it.
    brief = _brief_dir(tmp_path)
    impl = _impl_dir(tmp_path)
    indented = "\n".join(f"    {line}"
                         for line in ORACLE_SOURCE.splitlines())
    spec = tmp_path / "spec.md"
    spec.write_text(HONEST_SPEC + "\nReference:\n\n" + indented + "\n")
    assert main(["leakage", str(spec), str(brief), str(impl)]) == EXIT_BLOCKED
    assert "blocked\tTrue" in capsys.readouterr().out


def test_leakage_l4_executed_control_blocks_working_fenced_impl(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A spec whose fenced Python IS the implementation: the executed control
    # runs it through the visible oracle and >= 0.5 correctness blocks.
    brief = _brief_dir(tmp_path)
    impl = _impl_dir(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text(HONEST_SPEC + "\n```python\n" + ORACLE_SOURCE + "```\n")
    assert main(["leakage", str(spec), str(brief), str(impl)]) == EXIT_BLOCKED
    out = capsys.readouterr().out
    assert "spec_only_correctness\t1.0" in out


def test_leakage_non_importing_fenced_code_is_flagged_not_clean(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    brief = _brief_dir(tmp_path)
    impl = _impl_dir(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text(HONEST_SPEC + "\n```python\ndef broken(:\n```\n")
    main(["leakage", str(spec), str(brief), str(impl)])
    out = capsys.readouterr().out
    assert "spec_only_correctness\tnan" in out
    assert "L4 no signal" in out


REEXPRESSED_IMPL = """def running_total(values):
    result = []
    acc = 0
    for item in values:
        acc = acc + item
        result.append(acc)
    return result"""

LONG_PROSE_SPEC = HONEST_SPEC + """The implementer is
free to choose any internal representation, and the observable behaviour is
the only contract that matters here. The caller supplies the values one
batch at a time and expects the accumulated totals back in the same order,
without any reordering, filtering, or deduplication of the incoming data.
Negative numbers are legal inputs and simply decrease the accumulated sum.
Large inputs should be handled in a single linear pass, since the caller
may stream tens of thousands of entries in one request. Error handling is
deliberately out of scope: inputs are always well formed lists of integers,
and the function is never expected to raise. Documentation of the chosen
data structures is welcome but entirely optional, as reviewers care only
about behaviour, clarity, and the acceptance checks described above.
"""


def test_leakage_l4_gates_indented_paste_that_slides_under_l1_l3(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # The round-4 BLOCKER repro verbatim: ONE working implementation,
    # RE-EXPRESSED (so L2/L3 containment stays under the caps) and embedded
    # as 4-space-INDENTED markdown inside enough prose that L1 stays under
    # its cap too. The fence-only L4 saw no code at all -> every channel
    # clean. The whole-document L4 extraction dedents and EXECUTES it:
    # spec_only_correctness = 1.0 >= 0.5 blocks.
    brief = _brief_dir(tmp_path)
    impl = _impl_dir(tmp_path)
    indented = "\n".join(f"    {line}"
                         for line in REEXPRESSED_IMPL.splitlines())
    spec = tmp_path / "spec.md"
    spec.write_text(LONG_PROSE_SPEC
                    + "\nA sketch of one acceptable shape, for context:\n\n"
                    + indented + "\n")
    assert main(["leakage", str(spec), str(brief), str(impl)]) == EXIT_BLOCKED
    out = capsys.readouterr().out
    assert "spec_only_correctness\t1.0" in out
    assert "L4 spec_only_correctness" in out
    # The A/B point: L1-L3 individually stay clean — L4 is what catches it.
    assert "L1 code_frac" not in out
    assert "L2 reference containment" not in out
    assert "L3 impl-spec copy" not in out


def test_leakage_l4_fenced_and_indented_dressings_score_identically(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # The B side of the A/B: the SAME code fenced must reach the same
    # spec_only_correctness — the dressing must never change the verdict.
    brief = _brief_dir(tmp_path)
    impl = _impl_dir(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text(LONG_PROSE_SPEC + "\n```python\n"
                    + REEXPRESSED_IMPL + "\n```\n")
    assert main(["leakage", str(spec), str(brief), str(impl)]) == EXIT_BLOCKED
    assert "spec_only_correctness\t1.0" in capsys.readouterr().out


def test_leakage_blockquoted_oracle_paste_blocks(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Round-5 BLOCKER repro: every per-line classifier pattern anchors with
    # ``^`` on line.strip(), so a "> " blockquote hid the whole reference —
    # 0 detected code lines, L1/L2/L3 at 0.0, code_tok 0. The detector now
    # classifies the dressing-stripped form too.
    brief = _brief_dir(tmp_path)
    impl = _impl_dir(tmp_path)
    quoted = "\n".join(f"> {line}" for line in ORACLE_SOURCE.splitlines())
    spec = tmp_path / "spec.md"
    spec.write_text(HONEST_SPEC + "\nFor reference:\n\n" + quoted + "\n")
    assert main(["leakage", str(spec), str(brief), str(impl)]) == EXIT_BLOCKED
    out = capsys.readouterr().out
    assert "L2 reference containment" in out
    # The de-dressed candidate is executable too: L4 runs the paste.
    assert "spec_only_correctness\t1.0" in out


PAYLOAD_BLOCK = """    {
      "tenant": "acme",
      "limit": 10,
      "window_seconds": 60,
      "observed_requests": 12
    }
"""


def test_leakage_l4_survives_a_non_python_indented_block(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Round-5 MAJOR repro: L4 assembled EVERY detected line and dedented the
    # lot, so one ordinary indented JSON example made the candidate a syntax
    # error — reported as "no signal", which let the working implementation
    # pasted beside it go unexecuted. Non-parsing runs are now skipped.
    brief = _brief_dir(tmp_path)
    impl = _impl_dir(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text(LONG_PROSE_SPEC + "\nA payload example:\n\n"
                    + PAYLOAD_BLOCK + "\nOne acceptable shape:\n\n"
                    + "\n".join(f"    {line}"
                                 for line in REEXPRESSED_IMPL.splitlines())
                    + "\n")
    assert main(["leakage", str(spec), str(brief), str(impl)]) == EXIT_BLOCKED
    out = capsys.readouterr().out
    assert "spec_only_correctness\t1.0" in out
    assert "L4 spec_only_correctness" in out


TRANSPORT_SAMPLE = (
    "    $ curl -X POST /v1/limits --data 'tenant=acme&limit=10'\n"
    "    HTTP/1.1 200 OK\n"
)


def test_leakage_l4_survives_a_non_python_block_one_blank_line_away(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # The round-4 vector (L1/L2/L3 all silent, L4 the only gate) with a
    # non-Python sample ADJACENT to the paste — one blank line, no prose
    # between them, so both blocks are a single detected run. Whole-set and
    # per-run assembly both fail; the blank-line grain is what keeps L4 alive.
    brief = _brief_dir(tmp_path)
    impl = _impl_dir(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text(LONG_PROSE_SPEC + LONG_PROSE_SPEC
                    + "\nTransport sample:\n\n"
                    + TRANSPORT_SAMPLE + "\n"
                    + "\n".join(f"    {line}"
                                 for line in REEXPRESSED_IMPL.splitlines())
                    + "\n")
    assert main(["leakage", str(spec), str(brief), str(impl)]) == EXIT_BLOCKED
    out = capsys.readouterr().out
    assert "spec_only_correctness\t1.0" in out
    assert "L4 spec_only_correctness" in out
    # Still the A/B point: L1-L3 stay clean, L4 alone catches it.
    assert "L1 code_frac" not in out
    assert "L2 reference containment" not in out
    assert "L3 impl-spec copy" not in out


def test_leakage_l3_denominator_excludes_the_arm_test_suite(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Round-5 MAJOR repro: L3 = shared / |impl grams| ran over EVERY *.py in
    # the workspace, so a padded test suite the arm wrote itself diluted a
    # verbatim spec transcription from 1.0 to 0.038 — under the 0.30 cap.
    # The impl surface is now the non-test surface O5 already sizes.
    brief = _brief_dir(tmp_path)
    impl = _impl_dir(tmp_path, source=REEXPRESSED_IMPL, with_tests=False)
    (impl / "tests").mkdir()
    (impl / "tests" / "test_padded.py").write_text("\n\n".join(
        f"def test_case_{i}():\n"
        f"    observed = running_total(list(range({i + 1})))\n"
        f"    assert observed[-1] == sum(range({i + 1})), 'case {i}'\n"
        f"    assert len(observed) == {i + 1}, 'length {i}'"
        for i in range(25)))
    spec = tmp_path / "spec.md"
    spec.write_text(LONG_PROSE_SPEC + "\n```python\n"
                    + REEXPRESSED_IMPL + "\n```\n")
    assert main(["leakage", str(spec), str(brief), str(impl)]) == EXIT_BLOCKED
    out = capsys.readouterr().out
    assert "L3 impl-spec copy" in out
    assert "copy_containment\t1.0000" in out


def test_leakage_missing_oracle_is_load_error(tmp_path: Path) -> None:
    brief = _brief_dir(tmp_path)
    (brief / "oracle.py").unlink()
    impl = _impl_dir(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text(HONEST_SPEC)
    assert main(["leakage", str(spec), str(brief),
                 str(impl)]) == EXIT_LOAD_ERROR


# --------------------------------------------------------------------------- #
# outcome — O1-O5, the CLI-owned O3 reference dir, skip-vs-pass
# --------------------------------------------------------------------------- #


def test_outcome_good_impl_passes_with_skips_reported(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    brief = _brief_dir(tmp_path)   # no holdout, no mutations
    impl = _impl_dir(tmp_path)
    assert main(["outcome", str(brief), str(impl)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "O1\tcorrectness=1.0000" in out
    assert "O2\tskipped" in out and "never a pass" in out
    assert "O3\tskipped" in out
    assert "O4\tworkarounds=0" in out


def test_outcome_wrong_impl_fails_o1(tmp_path: Path) -> None:
    brief = _brief_dir(tmp_path)
    impl = _impl_dir(
        tmp_path,
        source="def running_total(values):\n    return list(values)\n")
    assert main(["outcome", str(brief), str(impl)]) == EXIT_BLOCKED


def test_outcome_workaround_theater_fails_o4(tmp_path: Path,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    brief = _brief_dir(tmp_path)
    impl = _impl_dir(tmp_path)
    (impl / "helper.py").write_text(
        "# TODO: finish\n\ndef helper():\n    assert True\n")
    assert main(["outcome", str(brief), str(impl)]) == EXIT_BLOCKED
    assert "O4" in capsys.readouterr().out


def test_outcome_o3_runs_against_cli_assembled_reference(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # The arm's suite kills the single mutation against the frozen reference
    # staged as <module>.py — assembled by the CLI, nowhere else.
    brief = _brief_dir(tmp_path, mutations=True)
    impl = _impl_dir(tmp_path)
    assert main(["outcome", str(brief), str(impl)]) == EXIT_OK
    assert "O3\tkill_rate=1.0000" in capsys.readouterr().out


def test_outcome_o3_smoke_failure_is_skipped_never_a_pass(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A non-importing test suite must yield NO O3 signal (skipped), and the
    # cell must not be read as kill_rate 1.0.
    brief = _brief_dir(tmp_path, mutations=True)
    impl = _impl_dir(tmp_path, with_tests=False)
    (impl / "tests").mkdir()
    (impl / "tests" / "test_broken.py").write_text("import does_not_exist\n")
    code = main(["outcome", str(brief), str(impl)])
    out = capsys.readouterr().out
    assert "O3\tskipped" in out and "smoke failed" in out
    assert "kill_rate" not in out
    assert code == EXIT_OK  # cell-level: skip, not a block; scored upstream


def test_outcome_holdout_overfit_gate(tmp_path: Path,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    brief = _brief_dir(tmp_path, holdout=True)
    impl = _impl_dir(tmp_path)
    assert main(["outcome", str(brief), str(impl)]) == EXIT_OK
    assert "O2\toverfit=0.0000" in capsys.readouterr().out


def test_outcome_visible_only_special_casing_fails_o2(tmp_path: Path) -> None:
    # An impl that hardcodes the visible cases aces O1 but misses the blind
    # holdout: overfit = 1.0 > 0.10 fails the gate. (It also trips O4's
    # hardcoded-expectation lint — either way it must block.)
    brief = _brief_dir(tmp_path, holdout=True)
    impl = _impl_dir(tmp_path, source=(
        "def running_total(values):\n"
        "    table = {(): [], (5,): [5], (1, 2, 3): [1, 3, 6]}\n"
        "    return table.get(tuple(values), None)\n"))
    assert main(["outcome", str(brief), str(impl)]) == EXIT_BLOCKED


# --------------------------------------------------------------------------- #
# bench-trust — G-BT reference + stub controls
# --------------------------------------------------------------------------- #


def test_bench_trust_passes_on_seeing_instrument(tmp_path: Path,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    brief = _brief_dir(tmp_path)
    assert main(["bench-trust", str(brief)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "reference_o1\t1.0000\tok" in out
    assert "stub_o1\t0.0000\tok" in out
    assert "benchmark_trusted\tTrue" in out


def test_bench_trust_blind_instrument_exits_not_scorable(tmp_path: Path) -> None:
    # If the stub PASSES the cases, the O instrument is blind: exit 4, never
    # a scored block. Cases expecting None are exactly what a stub aces.
    brief = _brief_dir(tmp_path)
    (brief / "cases.json").write_text(json.dumps({
        "cases": [{"label": "blind", "args": [[1]], "expected": None}]
    }))
    assert main(["bench-trust", str(brief)]) == EXIT_NOT_SCORABLE


def test_bench_trust_broken_reference_exits_not_scorable(tmp_path: Path) -> None:
    brief = _brief_dir(tmp_path)
    (brief / "oracle.py").write_text(
        "def running_total(values):\n    return list(values)\n")
    assert main(["bench-trust", str(brief)]) == EXIT_NOT_SCORABLE


# --------------------------------------------------------------------------- #
# score — packer invariants + exit codes
# --------------------------------------------------------------------------- #


TOST_MARGINS = {"C3": 0.05, "C8": 0.02, "U2": 1.0, "U3": 1.0,
                "O1": 0.05, "O3": 0.10}


def _tost_transport(**over: object) -> dict:
    """Raw per-family TOST numerics: in-band CIs, power over min_power."""
    base = {
        family: {"estimate": 0.0, "ci90": [-margin / 4, margin / 4],
                 "p_value": 0.012, "achieved_power": 0.86, "margin": margin}
        for family, margin in TOST_MARGINS.items()
    }
    base.update(over)
    return base


def _score_inputs(manifest_hash: str, *, implement_cells: dict | None = None,
                  arm_over: dict | None = None) -> dict:
    arm = {
        "arm_id": "A1",
        "cells": {
            "generate": {"complete": 18, "merge_skipped": 2},
            "implement": ({"complete": 12} if implement_cells is None
                          else implement_cells),
        },
        "gate_values": {
            "c0_leak_hits": 0, "c2_dropped_must": 0,
            "c7_merge_failures": 0,
            "c8_frag_rate": 0.03,
            "u0_prompt_sha_ok": True, "u0_leak_hits": 0,
            "u3_max_dead_ends": 2, "u4_completion_fraction": 1.0,
            "u5_clarifying_questions": 0,
            "o1_correctness": 0.94,
            "o1_regressed_cells": [], "o2_overfit": 0.04,
            "o3_kill_rate": 0.875,
            "o3_invalid": 0, "o4_workarounds": 0,
            "l1_code_frac": 0.05, "l2_reference_containment": 0.02,
            "l3_copy_containment": 0.03, "l4_spec_only_correctness": None,
        },
        # The REQUIRED raw TOST numerics; the CLI recomputes non_inferior /
        # certifiable from these against the manifest margins and min_power.
        "tost": _tost_transport(),
        "c1": {"mean_delta": -0.11, "ci": [-0.18, -0.04], "p_holm": 0.024,
               "sign_stable": True, "large_realistic_delta": -0.10},
        "u1": {"mean_delta": -0.23, "p_holm": 0.02},
        "correctness_holdout": 0.90,
        "bloat_ln": 0.11,
        # o2/o3_skipped_fraction deliberately NOT packed: the CLI derives
        # them from the cells' holdout_skipped/mutations_skipped counts.
    }
    if arm_over:
        arm.update(arm_over)
    return {
        "manifest_content_hash": manifest_hash,
        "generated_at": "2026-08-13T00:00:00Z",
        "instrument_trusted": True,
        "benchmark_trusted": True,
        "a3b_fails_grammaticality": True,
        # REQUIRED block, every key explicit (deleting one is a load error).
        "stops": {"c_length_falsification": False,
                  "c_distinct_dilution": False,
                  "u_below_detectable_floor": False,
                  "u_length_falsification": False},
        "noise_floor_c": 0.031,
        "noise_floor_u": 0.084,
        # strata_coverage deliberately NOT packed: derived from the manifest.
        "baseline_arm": "A0",
        "treatment_arm": "A1",
        "arms": [arm],
        "budget": {"spent_usd": 10.0, "projected_usd": 20.0,
                   "max_usd": 120.0, "exhausted": False},
        "a4_captures_effect": False,
        "beats_a3_fair": True,
        "beats_a2_placebo": True,
    }


def _complete_corpus(tmp_path: Path,
                     manifest_path: Path = DEMO_MANIFEST) -> Path:
    """Every buildable brief of ``manifest_path`` with its full §4 asset set."""
    corpus = tmp_path / "corpus"
    manifest = json.loads(manifest_path.read_text())
    for brief in manifest["briefs"]:
        if not brief["buildable"]:
            continue
        d = corpus / brief["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "brief.json").write_text(json.dumps({
            "id": brief["id"], "module": "m", "entrypoint": "e"}))
        (d / "cases.json").write_text(json.dumps({"cases": []}))
        (d / "cases_holdout.json").write_text(json.dumps({"cases": []}))
        (d / "mutations.json").write_text(json.dumps({"mutations": [
            {"label": f"m{i}", "filename": "m.py", "find": "a",
             "replace": "b"} for i in range(8)]}))
    return corpus


def _run_score(tmp_path: Path, inputs: dict, *,
               manifest: Path = DEMO_MANIFEST,
               corpus: Path | None = None) -> tuple[int, dict]:
    inputs_path = tmp_path / "inputs.json"
    inputs_path.write_text(json.dumps(inputs))
    out_path = tmp_path / "score.json"
    corpus_root = corpus or _complete_corpus(tmp_path, manifest)
    code = main(["score", str(inputs_path), "--manifest", str(manifest),
                 "--corpus", str(corpus_root), "--out", str(out_path)])
    return code, json.loads(out_path.read_text())


def _score_load_error(tmp_path: Path, inputs: dict, *,
                      manifest: Path = DEMO_MANIFEST) -> int:
    """Run score expecting no score.json to be needed (load-error paths)."""
    inputs_path = tmp_path / "inputs.json"
    inputs_path.write_text(json.dumps(inputs))
    corpus_root = _complete_corpus(tmp_path, manifest)
    return main(["score", str(inputs_path), "--manifest", str(manifest),
                 "--corpus", str(corpus_root)])


def _demo_hash() -> str:
    return load_manifest(DEMO_MANIFEST).content_hash()


def test_score_clean_run_is_structurally_underpowered_at_demo_scale(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Regression (round-3 BLOCKER): strata_coverage used to be accepted
    # verbatim from the packer, so 3/3/3 reached SHIP_TREATMENT on a panel
    # whose true buildable large_realistic stratum is n=1. Strata now derive
    # from the manifest briefs and the demo verdict is UNDERPOWERED, exit 1
    # — SHIP is structurally unreachable at demo scale, per §0.
    code, obj = _run_score(tmp_path, _score_inputs(f"sha256:{_demo_hash()}"))
    assert code == EXIT_BLOCKED
    assert obj["verdict"] == "underpowered_no_ship"
    assert obj["scorable"] is True
    assert obj["ceiling"] == "promising_scale_to_n18"
    assert obj["strata_coverage"] == {
        "C": {"elicit_prone": 3, "large_realistic": 3, "neutral": 3},
        "U": {"elicit_prone": 2, "large_realistic": 1, "neutral": 3},
        "O": {"elicit_prone": 2, "large_realistic": 1, "neutral": 3},
    }
    assert any("large_realistic n=1 < 3" in r for r in obj["verdict_reasons"])
    # thresholds came from the MANIFEST bench block, not Python defaults
    assert obj["arms"]["A1"]["composite"]["pass_threshold"] == 70
    # canonical render also went to stdout
    assert capsys.readouterr().out.strip().startswith("{")


def test_score_packed_strata_contradicting_manifest_is_load_error(
        tmp_path: Path) -> None:
    # The round-3 repro verbatim: packing 3/3/3 against manifest.demo.json
    # must never score (it used to reach SHIP_TREATMENT).
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["strata_coverage"] = {
        dim: {"elicit_prone": 3, "large_realistic": 3, "neutral": 3}
        for dim in ("C", "U", "O")}
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_packed_strata_matching_manifest_is_accepted(
        tmp_path: Path) -> None:
    # A packed value equal to the derivation is a harmless cross-check.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["strata_coverage"] = {
        "C": {"elicit_prone": 3, "large_realistic": 3, "neutral": 3},
        "U": {"elicit_prone": 2, "large_realistic": 1, "neutral": 3},
        "O": {"elicit_prone": 2, "large_realistic": 1, "neutral": 3},
    }
    code, obj = _run_score(tmp_path, inputs)
    assert obj["scorable"] is True
    assert code == EXIT_BLOCKED  # still row-9 underpowered, honestly


def test_score_ship_reachable_only_with_manifest_backed_strata(
        tmp_path: Path) -> None:
    # Making every brief buildable in the MANIFEST (rehash: the audit trail)
    # yields true 3/3/3 U/O strata — only then is SHIP reachable.
    manifest = json.loads(DEMO_MANIFEST.read_text())
    for brief in manifest["briefs"]:
        brief["buildable"] = True
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    thick_hash = load_manifest(manifest_path).content_hash()

    inputs = _score_inputs(f"sha256:{thick_hash}",
                           implement_cells={"complete": 18})  # 9 briefs x 2
    code, obj = _run_score(tmp_path, inputs, manifest=manifest_path)
    assert code == EXIT_OK
    assert obj["verdict"] == "ship_treatment"


def test_score_omitted_cells_are_backfilled_missing_from_panel(
        tmp_path: Path) -> None:
    # THE CellCounts invariant: 3 implement cells simply not packed must be
    # counted missing (25% > 10%) => not scorable, exit 4 — never a silently
    # complete arm with incomplete_fraction 0.0.
    code, obj = _run_score(
        tmp_path,
        _score_inputs(f"sha256:{_demo_hash()}",
                      implement_cells={"complete": 9}))
    assert code == EXIT_NOT_SCORABLE
    assert obj["scorable"] is False
    assert obj["reason"] == "incomplete_fraction_exceeded"
    assert obj["verdict"] == "do_not_ship"


def test_score_packed_expected_contradicting_panel_is_load_error(
        tmp_path: Path) -> None:
    inputs = _score_inputs(f"sha256:{_demo_hash()}",
                           implement_cells={"expected": 4, "complete": 4})
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_more_cells_than_panel_is_load_error(tmp_path: Path) -> None:
    inputs = _score_inputs(f"sha256:{_demo_hash()}",
                           implement_cells={"complete": 12, "missing": 3})
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_hash_mismatch_is_manifest_invalid_exit_4(tmp_path: Path) -> None:
    # The hash match is recomputed from the manifest FILE; a stale packed hash
    # must yield manifest_invalid (row 0), never a scored run.
    code, obj = _run_score(tmp_path, _score_inputs("sha256:" + "0" * 64))
    assert code == EXIT_NOT_SCORABLE
    assert obj["reason"] == "manifest_invalid"


def test_score_missing_packed_hash_is_load_error(tmp_path: Path) -> None:
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    del inputs["manifest_content_hash"]
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_implement_cells_for_non_u_arm_is_load_error(
        tmp_path: Path) -> None:
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["arms"][0]["arm_id"] = "A4_evaluator_only"  # not in bench.u_arms
    inputs["treatment_arm"] = "A4_evaluator_only"
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_u_arm_without_implement_family_is_all_missing(
        tmp_path: Path) -> None:
    # A u_arms arm packed with NO implement family at all: every implement
    # cell is missing (fail-closed), so the run is not scorable.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    del inputs["arms"][0]["cells"]["implement"]
    code, obj = _run_score(tmp_path, inputs)
    assert code == EXIT_NOT_SCORABLE
    assert obj["reason"] == "incomplete_fraction_exceeded"


def test_score_leaking_treatment_blocks_exit_1(tmp_path: Path) -> None:
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["arms"][0]["gate_values"]["l1_code_frac"] = 0.9
    code, obj = _run_score(tmp_path, inputs)
    assert code == EXIT_BLOCKED
    assert obj["arms"]["A1"]["leakage_voided"] is True
    assert obj["arms"]["A1"]["dimensions"]["U"]["subscore"] == 0.0


def test_score_bench_threshold_edit_without_rehash_is_detected(
        tmp_path: Path) -> None:
    # Regression (round-3 MAJOR): every operative number must live under
    # content_hash. Editing an S_O term weight in the manifest while packing
    # the OLD hash must surface as manifest_invalid (row 0), exit 4.
    manifest = json.loads(DEMO_MANIFEST.read_text())
    manifest["bench"]["o_weight_kill"] = 0.25
    manifest["bench"]["o_weight_bloat"] = 0.25  # weights still sum to 1.0
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    inputs = _score_inputs(f"sha256:{_demo_hash()}")  # the STALE hash
    code, obj = _run_score(tmp_path, inputs, manifest=manifest_path)
    assert code == EXIT_NOT_SCORABLE
    assert obj["reason"] == "manifest_invalid"


def test_score_missing_u1_stats_is_load_error(tmp_path: Path) -> None:
    # The U1 win legs are recomputed by the scorer from packed U1Stats; a
    # transport without them cannot be scored.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    del inputs["arms"][0]["u1"]
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_missing_gate_transport_field_is_load_error(
        tmp_path: Path) -> None:
    # A packer that forgets a transported gate leg (here C0) must load-error,
    # never default to a silently-green gate.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    del inputs["arms"][0]["gate_values"]["c0_leak_hits"]
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_deleting_a_fired_stop_is_a_load_error(tmp_path: Path) -> None:
    # Round-5 BLOCKER repro: ``raw.get("stops", {})`` plus per-key
    # ``.get(name, False)`` meant DELETING a fired STOP key produced a
    # scored run whose score.json carried a FABRICATED clean STOP record —
    # §2 row 4 dropped with no schema trace. Absent key = load error.
    fired = _score_inputs(f"sha256:{_demo_hash()}")
    fired["stops"]["u_length_falsification"] = True
    code, obj = _run_score(tmp_path, fired)
    assert code == EXIT_BLOCKED
    assert obj["verdict"] == "do_not_ship"
    assert obj["stops"]["u_length_falsification"] is True

    for key in ("c_length_falsification", "c_distinct_dilution",
                "u_below_detectable_floor", "u_length_falsification"):
        deleted = _score_inputs(f"sha256:{_demo_hash()}")
        deleted["stops"]["u_length_falsification"] = True
        del deleted["stops"][key]
        assert _score_load_error(tmp_path, deleted) == EXIT_LOAD_ERROR, key


def test_score_absent_stops_block_is_a_load_error(tmp_path: Path) -> None:
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    del inputs["stops"]
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_c0_leak_hits_fail_the_generate_isolation_gate(
        tmp_path: Path) -> None:
    # A generate transcript that touched a corpus asset (run-arm.sh cell.json
    # leak_hits > 0) must fail C0_generate_isolation and block the run.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["arms"][0]["gate_values"]["c0_leak_hits"] = 2
    code, obj = _run_score(tmp_path, inputs)
    assert code == EXIT_BLOCKED
    assert "C0_generate_isolation" in obj["arms"]["A1"]["gates_failed"]


def test_score_skipped_fractions_are_derived_from_counts(
        tmp_path: Path) -> None:
    # The fractions are DERIVED (skipped cells / expected implement cells),
    # never caller-trusted: nothing packed, counts alone drive them.
    inputs = _score_inputs(f"sha256:{_demo_hash()}",
                           implement_cells={"complete": 12,
                                            "holdout_skipped": 2,
                                            "mutations_skipped": 1})
    code, obj = _run_score(tmp_path, inputs)
    assert obj["scorable"] is True
    dims = obj["arms"]["A1"]["dimensions"]
    assert dims["O"]["o2_skipped_fraction"] == 0.167  # 2/12
    assert dims["O"]["o3_skipped_fraction"] == 0.083  # 1/12
    assert code == EXIT_BLOCKED


def test_score_packed_fraction_understating_counts_is_load_error(
        tmp_path: Path) -> None:
    # The round-3 repro verbatim: {complete:12, holdout_skipped:8} packed
    # with o2_skipped_fraction 0.01 used to SHIP exit 0 (the one-directional
    # cross-check only caught skipped>0 with fraction==0). A packed value is
    # at most a cross-check: any mismatch with the derived 0.667 load-errors.
    inputs = _score_inputs(f"sha256:{_demo_hash()}",
                           implement_cells={"complete": 12,
                                            "holdout_skipped": 8},
                           arm_over={"o2_skipped_fraction": 0.01})
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_derived_overcap_holdout_skip_routes_to_underpowered(
        tmp_path: Path) -> None:
    # The honest half of the round-3 repro: 8/12 = 0.667 > the 0.30 cap, so
    # the derived fraction forces dimension O underpowered (row 9), exit 1 —
    # never a SHIP.
    inputs = _score_inputs(f"sha256:{_demo_hash()}",
                           implement_cells={"complete": 12,
                                            "holdout_skipped": 8})
    code, obj = _run_score(tmp_path, inputs)
    assert code == EXIT_BLOCKED
    assert obj["verdict"] == "underpowered_no_ship"
    assert obj["arms"]["A1"]["dimensions"]["O"]["o2_skipped_fraction"] == 0.667
    assert any("O2 skipped_fraction" in r for r in obj["verdict_reasons"])


def test_score_holdout_skipped_cells_with_zero_fraction_is_load_error(
        tmp_path: Path) -> None:
    # Packing coupled to reality: holdout_skipped cells alongside a claimed
    # o2_skipped_fraction of 0.0 contradict the derived 0.167 — a missing
    # holdout must never read as fully measured.
    inputs = _score_inputs(f"sha256:{_demo_hash()}",
                           implement_cells={"complete": 12,
                                            "holdout_skipped": 2},
                           arm_over={"o2_skipped_fraction": 0.0})
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_mutations_skipped_cells_with_zero_fraction_is_load_error(
        tmp_path: Path) -> None:
    inputs = _score_inputs(f"sha256:{_demo_hash()}",
                           implement_cells={"complete": 12,
                                            "mutations_skipped": 1},
                           arm_over={"o3_skipped_fraction": 0.0})
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_accounted_holdout_skip_cross_check_passes(
        tmp_path: Path) -> None:
    # A packed fraction that MATCHES the derivation (at 3 decimals) is a
    # harmless cross-check; the O2 arithmetic/gating downstream then owns
    # the consequence.
    inputs = _score_inputs(f"sha256:{_demo_hash()}",
                           implement_cells={"complete": 12,
                                            "holdout_skipped": 2},
                           arm_over={"o2_skipped_fraction": 0.167})
    code, obj = _run_score(tmp_path, inputs)
    assert code in (EXIT_OK, EXIT_BLOCKED)
    assert obj["scorable"] is True


def test_score_null_c0_leak_hits_fails_the_gate(tmp_path: Path) -> None:
    # Regression (round-3 MAJOR): leak_scanned:false used to pack as 0 and
    # pass C0 green. The packer maps any unscanned generate cell to null,
    # and null FAILS the gate — no signal is never a pass.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["arms"][0]["gate_values"]["c0_leak_hits"] = None
    code, obj = _run_score(tmp_path, inputs)
    assert code == EXIT_BLOCKED
    assert "C0_generate_isolation" in obj["arms"]["A1"]["gates_failed"]


def test_score_zero_noise_floor_is_load_error(tmp_path: Path) -> None:
    # The round-4 BLOCKER repro verbatim: estimate_noise_floor returns 0.0 on
    # empty inputs and the packer defaulted --noise-floor 0.0; nf_C=0.0 +
    # mean_delta=-0.05 used to clear the C1 gate and scale S_C to 100. An
    # empty-input floor means no baseline replicate data existed: not
    # scorable, never free significance.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["noise_floor_c"] = 0.0
    inputs["arms"][0]["c1"]["mean_delta"] = -0.05
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


@pytest.mark.parametrize("key,value", [
    ("noise_floor_c", 0.0),
    ("noise_floor_c", -0.01),
    ("noise_floor_c", float("nan")),
    ("noise_floor_u", 0.0),
    ("noise_floor_u", float("inf")),
])
def test_score_degenerate_noise_floors_are_load_errors(
        tmp_path: Path, key: str, value: float) -> None:
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs[key] = value
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_missing_l4_key_is_load_error(tmp_path: Path) -> None:
    # Regression (round-4 MAJOR): l4_spec_only_correctness was the only
    # optional GateValues key — DELETING it flipped DO_NOT_SHIP to SHIP with
    # no schema trace. It is now REQUIRED: explicit null = no signal
    # (flagged), absent = load error, matching c0_leak_hits.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["arms"][0]["gate_values"]["l4_spec_only_correctness"] = 0.9
    code, obj = _run_score(tmp_path, inputs)
    assert code == EXIT_BLOCKED  # a failing L4 blocks ...
    assert "L4_spec_only_correctness" in obj["arms"]["A1"]["gates_failed"]
    del inputs["arms"][0]["gate_values"]["l4_spec_only_correctness"]
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_contradictory_packed_c1_metric_is_load_error(tmp_path: Path) -> None:
    # Regression (round-6 MAJOR): dimensions.<D>.metrics was unchecked packer
    # passthrough — the ONLY score.json surface carrying C1/U1 (the #10
    # headline numbers) could contradict the operative fields (arm.c1) with
    # no load error. The scorer now DERIVES metrics.C1 from arm.c1 and the
    # CLI cross-checks a packed value against that derivation.
    inputs = _score_inputs(
        f"sha256:{_demo_hash()}",
        arm_over={"metrics": {"C": [{
            "id": "C1", "value": -0.95, "ci": [-0.18, -0.04], "p_holm": 0.024,
            "extra": {"mean_delta": -0.95, "p": 0.008, "sign_stable": True,
                      "n": 9, "large_realistic_delta": -0.10},
        }]}})
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_matching_packed_c1_metric_is_not_a_load_error(tmp_path: Path) -> None:
    # A packed metric that AGREES with the operative fields is fine — the
    # cross-check only rejects contradictions, never packer honesty.
    inputs = _score_inputs(
        f"sha256:{_demo_hash()}",
        arm_over={"metrics": {"C": [{
            "id": "C1", "value": -0.11, "ci": [-0.18, -0.04], "p_holm": 0.024,
            "extra": {"mean_delta": -0.11, "p": 0.008, "sign_stable": True,
                      "n": 9, "large_realistic_delta": -0.10},
        }]}})
    code, obj = _run_score(tmp_path, inputs)
    assert code in (EXIT_OK, EXIT_BLOCKED)
    assert obj["arms"]["A1"]["dimensions"]["C"]["metrics"]["C1"]["mean_delta"] == -0.11


def test_score_contradictory_packed_o3_kill_rate_metric_is_load_error(
        tmp_path: Path) -> None:
    # Same coupling rule, O3: a packed metrics.O.O3.kill_rate that disagrees
    # with gate_values.o3_kill_rate (the O3 gate's own source) is a load
    # error, never a silently-rendered second number.
    inputs = _score_inputs(
        f"sha256:{_demo_hash()}",
        arm_over={"metrics": {"O": [{
            "id": "O3", "value": 0.20,
            "extra": {"kill_rate": 0.20, "invalid": 0},
        }]}})
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_l4_no_signal_flag_traced_in_rendered_json(tmp_path: Path) -> None:
    # Regression (round-6 MAJOR): a null l4_spec_only_correctness left ZERO
    # trace in score.json (no GateCheck, no flag). l4_no_signal is now the
    # required, always-rendered greppable trace.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    assert inputs["arms"][0]["gate_values"]["l4_spec_only_correctness"] is None
    code, obj = _run_score(tmp_path, inputs)
    assert obj["arms"]["A1"]["l4_no_signal"] is True
    assert "L4_spec_only_correctness" not in [
        g["id"] for g in obj["arms"]["A1"]["gates"]]


@pytest.mark.parametrize("key", ["o1_correctness", "o2_overfit",
                                 "o3_kill_rate", "o1_regressed_cells"])
def test_score_deleted_gate_value_keys_are_load_errors(
        tmp_path: Path, key: str) -> None:
    # Every GateValues key is required — including the nullable ones and
    # o1_regressed_cells (round-4 MINOR: it was the one defaulted sibling).
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    del inputs["arms"][0]["gate_values"][key]
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_duplicate_packed_arm_id_is_load_error(tmp_path: Path) -> None:
    # Regression (round-4 MAJOR): _treatment_arm took the FIRST match while
    # the rendered arms dict kept the LAST — a self-contradictory score.json
    # with exit 0. One arm, one record.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["arms"] = [inputs["arms"][0], json.loads(
        json.dumps(inputs["arms"][0]))]
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_missing_tost_map_is_load_error(tmp_path: Path) -> None:
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    del inputs["arms"][0]["tost"]
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_missing_tost_family_is_load_error(tmp_path: Path) -> None:
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    del inputs["arms"][0]["tost"]["U2"]
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_null_tost_family_fails_its_gate_fail_closed(
        tmp_path: Path) -> None:
    # Explicit null = no TOST signal: the non-inferiority leg FAILS its gate.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["arms"][0]["tost"]["U2"] = None
    code, obj = _run_score(tmp_path, inputs)
    assert code == EXIT_BLOCKED
    assert "U2_turns_noninferiority" in obj["arms"]["A1"]["gates_failed"]


def test_score_tost_margin_contradicting_manifest_is_load_error(
        tmp_path: Path) -> None:
    # The §4 tost_margins field is LIVE: a runner that tested against a
    # wider band than the pre-registration cannot be scored.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["arms"][0]["tost"]["C3"]["margin"] = 0.5
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_recomputed_inferior_tost_fails_gate_despite_boolean(
        tmp_path: Path) -> None:
    # Regression (round-4 MAJOR): the six *_non_inferior legs were collapsed
    # caller booleans. Now the raw stats drive the gate; a packed boolean
    # contradicting them is a load error, and without the boolean the
    # out-of-band CI fails the gate on its own.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["arms"][0]["tost"]["C3"] = {
        "estimate": 0.05, "ci90": [0.03, 0.09], "p_value": 0.6,
        "achieved_power": 0.9, "margin": 0.05}
    code, obj = _run_score(tmp_path, inputs)
    assert code == EXIT_BLOCKED
    assert "C3_coverage_noninferiority" in obj["arms"]["A1"]["gates_failed"]
    # ... and the lying legacy boolean cannot resurrect it: load error.
    inputs["arms"][0]["gate_values"]["c3_non_inferior"] = True
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_matching_legacy_booleans_are_harmless_cross_checks(
        tmp_path: Path) -> None:
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    gv = inputs["arms"][0]["gate_values"]
    gv.update({"c3_non_inferior": True, "c8_non_inferior": True,
               "u2_non_inferior": True, "u3_non_inferior": True,
               "o1_non_inferior": True, "o3_non_inferior": True})
    inputs["arms"][0]["tost_certifiable"] = {
        f: True for f in ("C3", "C8", "U2", "U3", "O1", "O3")}
    code, obj = _run_score(tmp_path, inputs)
    assert obj["scorable"] is True
    assert code == EXIT_BLOCKED  # still honestly row-9 underpowered


def test_score_packed_certifiable_contradicting_power_is_load_error(
        tmp_path: Path) -> None:
    # achieved_power 0.5 < min_power 0.8 recomputes certifiable False; a
    # packed True is the old collapsed-boolean lie — load error.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["arms"][0]["tost"]["U3"]["achieved_power"] = 0.5
    inputs["arms"][0]["tost_certifiable"] = {"U3": True}
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_low_achieved_power_routes_to_underpowered(
        tmp_path: Path) -> None:
    # In-band CI, low power: the gate passes and row 8 reports the family —
    # recomputed from the raw stats, bench.min_power now live.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["arms"][0]["tost"]["U3"]["achieved_power"] = 0.5
    code, obj = _run_score(tmp_path, inputs)
    assert code == EXIT_BLOCKED
    assert "U3_deadend_noninferiority" not in obj["arms"]["A1"]["gates_failed"]
    assert obj["verdict"] == "underpowered_no_ship"
    assert any("U3" in r and "certifiable" in r
               for r in obj["verdict_reasons"])


def test_score_without_corpus_is_a_usage_error(tmp_path: Path) -> None:
    # --corpus is REQUIRED: the §4 blind-asset validation is not opt-in.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs_path = tmp_path / "inputs.json"
    inputs_path.write_text(json.dumps(inputs))
    with pytest.raises(SystemExit) as exc:
        main(["score", str(inputs_path), "--manifest", str(DEMO_MANIFEST)])
    assert exc.value.code == 2


def test_score_real_demo_corpus_satisfies_the_asset_rules(
        tmp_path: Path) -> None:
    # Regression (round-4 MAJOR): the shipped demo corpus lacked its blind
    # cases_holdout.json/mutations.json. The authored assets must satisfy
    # validate() so the demo passes row 0 honestly.
    demo_corpus = REPO_ROOT / "corpus" / "demo"
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    code, obj = _run_score(tmp_path, inputs, corpus=demo_corpus)
    assert obj["scorable"] is True
    assert code == EXIT_BLOCKED  # row-9 underpowered at demo scale, honestly


def test_score_unknown_treatment_arm_is_load_error(tmp_path: Path) -> None:
    # Arm identities must be manifest-declared: an undeclared arm can
    # neither be scored nor drive the verdict.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["arms"][0]["arm_id"] = "A99"
    inputs["treatment_arm"] = "A99"
    assert _score_load_error(tmp_path, inputs) == EXIT_LOAD_ERROR


def test_score_budget_cap_comes_from_bench_not_the_packer(
        tmp_path: Path) -> None:
    # bench.max_usd (120.0) is the budget authority: a packer claiming a
    # wider cap with spent over the pre-registered max is exhausted => row 5
    # not scorable.
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs["budget"] = {"spent_usd": 130.0, "projected_usd": 130.0,
                        "max_usd": 999.0, "exhausted": False}
    code, obj = _run_score(tmp_path, inputs)
    assert code == EXIT_NOT_SCORABLE
    assert obj["reason"] == "budget_exhausted"
    assert obj["budget"]["max_usd"] == 120.0


def test_score_corpus_missing_blind_assets_is_manifest_invalid(
        tmp_path: Path) -> None:
    # §4 asset rules through --corpus: a buildable brief without its blind
    # holdout/mutations makes the manifest invalid — scorable:false, exit 4.
    corpus = _complete_corpus(tmp_path)
    manifest = json.loads(DEMO_MANIFEST.read_text())
    first_buildable = next(b["id"] for b in manifest["briefs"]
                           if b["buildable"])
    (corpus / first_buildable / "cases_holdout.json").unlink()
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs_path = tmp_path / "inputs.json"
    inputs_path.write_text(json.dumps(inputs))
    out_path = tmp_path / "score.json"
    code = main(["score", str(inputs_path), "--manifest", str(DEMO_MANIFEST),
                 "--corpus", str(corpus), "--out", str(out_path)])
    obj = json.loads(out_path.read_text())
    assert code == EXIT_NOT_SCORABLE
    assert obj["reason"] == "manifest_invalid"


def test_score_corpus_with_full_assets_stays_scorable(tmp_path: Path) -> None:
    corpus = _complete_corpus(tmp_path)
    inputs = _score_inputs(f"sha256:{_demo_hash()}")
    inputs_path = tmp_path / "inputs.json"
    inputs_path.write_text(json.dumps(inputs))
    out_path = tmp_path / "score.json"
    code = main(["score", str(inputs_path), "--manifest", str(DEMO_MANIFEST),
                 "--corpus", str(corpus), "--out", str(out_path)])
    obj = json.loads(out_path.read_text())
    assert obj["scorable"] is True
    assert code == EXIT_BLOCKED  # scorable; row-9 underpowered at demo scale


def test_score_thresholds_come_from_manifest_bench(tmp_path: Path) -> None:
    # Tighten the manifest's dead-end cap below the packed value: the gate
    # must fail, proving the manifest — not the Python default of 6 — drives.
    manifest = json.loads(DEMO_MANIFEST.read_text())
    manifest["bench"]["dead_end_cap"] = 1
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    tightened_hash = load_manifest(manifest_path).content_hash()

    inputs = _score_inputs(f"sha256:{tightened_hash}")
    inputs["arms"][0]["gate_values"]["u3_max_dead_ends"] = 2  # > cap of 1
    code, obj = _run_score(tmp_path, inputs, manifest=manifest_path)
    assert code == EXIT_BLOCKED
    assert "U3_dead_end_cap" in obj["arms"]["A1"]["gates_failed"]

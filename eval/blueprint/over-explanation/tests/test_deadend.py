"""Tests for the dead-end / workaround / leakage signals in ``deadend.py``.

Every signal is exercised in both directions: it fires on a crafted fixture
and stays silent on a clean one. Fixtures are inline stream-json line lists
and tiny ``tmp_path`` workspaces — fully offline, no network, no subprocess.
"""

from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path

from eval_overexplanation.deadend import (
    LEAK_PATTERNS,
    code_token_count,
    count_clarifying_questions,
    count_failed_test_cycles,
    count_leaks,
    count_reverted_edits,
    deadend_report,
    iter_tool_results,
    iter_tool_uses,
    leakage_report,
    ngram_containment,
    spec_code_blocks,
    spec_code_lines,
    spec_code_source,
    spec_python_source,
    workaround_lint,
)
from eval_overexplanation.models import OracleCase

# --------------------------------------------------------------------------- #
# Stream-json fixture helpers
# --------------------------------------------------------------------------- #


def _tool_use(name: str, input_: dict, *, id_: str = "tu_0") -> dict:
    return {"type": "tool_use", "id": id_, "name": name, "input": input_}


def _assistant(*blocks: dict, parent: str | None = None) -> dict:
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"role": "assistant", "content": list(blocks)}}


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


def _tool_result(tool_use_id: str, *, is_error: bool = False,
                 parent: str | None = None) -> dict:
    return {"type": "user", "parent_tool_use_id": parent,
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id,
                 "is_error": is_error, "content": []}]}}


def _result(text: str) -> dict:
    return {"type": "result", "subtype": "success", "result": text,
            "parent_tool_use_id": None}


def _lines(objs: list[dict]) -> list[str]:
    return [json.dumps(o) for o in objs]


def _edit(file_path: str, old: str, new: str, *, id_: str = "tu_e") -> dict:
    return _assistant(_tool_use(
        "Edit", {"file_path": file_path, "old_string": old, "new_string": new},
        id_=id_))


def _write(file_path: str, content: str, *, id_: str = "tu_w") -> dict:
    return _assistant(_tool_use(
        "Write", {"file_path": file_path, "content": content}, id_=id_))


def _bash(command: str, *, id_: str, parent: str | None = None) -> dict:
    return _assistant(_tool_use("Bash", {"command": command}, id_=id_),
                      parent=parent)


_CAPS = {"code_frac": 0.15, "reference": 0.25, "copy": 0.30,
         "spec_only_correctness": 0.50}


# --------------------------------------------------------------------------- #
# Transcript parsing
# --------------------------------------------------------------------------- #


def test_iter_tool_uses_extracts_and_skips_malformed_lines():
    lines = ["not json at all", "", *_lines([
        _assistant(_tool_use("Read", {"file_path": "/tmp/ws/impl.py"}, id_="a")),
    ])]
    uses = iter_tool_uses(lines)
    assert len(uses) == 1
    assert uses[0].name == "Read"
    assert uses[0].id == "a"


def test_iter_tool_uses_drops_subagent_events():
    lines = _lines([
        _assistant(_tool_use("Read", {"file_path": "x"}), parent="tu_task"),
    ])
    assert iter_tool_uses(lines) == ()


def test_iter_tool_results_pairs_by_id_and_drops_subagent_events():
    lines = _lines([
        _tool_result("a", is_error=True),
        _tool_result("b", is_error=False),
        _tool_result("c", is_error=True, parent="tu_task"),
    ])
    results = iter_tool_results(lines)
    assert [(r.tool_use_id, r.is_error) for r in results] == [
        ("a", True), ("b", False)]


# --------------------------------------------------------------------------- #
# Reverted edits (U3)
# --------------------------------------------------------------------------- #


def test_revert_fires_when_new_string_restores_an_earlier_old_string():
    lines = _lines([
        _edit("impl.py", "return a + b", "return a - b", id_="e1"),
        _edit("impl.py", "return a - b", "return a + b", id_="e2"),  # revert
    ])
    assert count_reverted_edits(iter_tool_uses(lines)) == 1


def test_no_revert_on_distinct_forward_edits():
    lines = _lines([
        _edit("impl.py", "pass", "return 1", id_="e1"),
        _edit("impl.py", "return 1", "return compute()", id_="e2"),
    ])
    assert count_reverted_edits(iter_tool_uses(lines)) == 0


def test_no_revert_across_different_files():
    lines = _lines([
        _edit("a.py", "old text", "new text", id_="e1"),
        _edit("b.py", "anything", "old text", id_="e2"),  # other file
    ])
    assert count_reverted_edits(iter_tool_uses(lines)) == 0


def test_an_edit_cannot_revert_itself():
    lines = _lines([_edit("a.py", "same", "same", id_="e1")])
    assert count_reverted_edits(iter_tool_uses(lines)) == 0


def test_write_clobber_dropping_an_edit_counts_as_revert():
    # The common abandonment path: edit, then rewrite the whole file without
    # the edited text. Regression: the old counter saw only Edit pairs.
    lines = _lines([
        _edit("impl.py", "pass", "return compute()", id_="e1"),
        _write("impl.py", "def f():\n    pass\n", id_="w1"),  # edit dropped
    ])
    assert count_reverted_edits(iter_tool_uses(lines)) == 1


def test_write_preserving_every_edit_is_not_a_revert():
    lines = _lines([
        _edit("impl.py", "pass", "return compute()", id_="e1"),
        _write("impl.py", "def f():\n    return compute()\n", id_="w1"),
    ])
    assert count_reverted_edits(iter_tool_uses(lines)) == 0


def test_write_clobber_counts_once_then_supersedes_the_edits():
    lines = _lines([
        _edit("impl.py", "pass", "return compute()", id_="e1"),
        _write("impl.py", "x = 1\n", id_="w1"),   # clobber: 1
        _write("impl.py", "y = 2\n", id_="w2"),   # superseded: no recount
    ])
    assert count_reverted_edits(iter_tool_uses(lines)) == 1


def test_write_to_other_file_or_without_prior_edits_is_silent():
    lines = _lines([
        _write("fresh.py", "x = 1\n", id_="w1"),
        _edit("impl.py", "pass", "return 1", id_="e1"),
        _write("other.py", "y = 2\n", id_="w2"),
    ])
    assert count_reverted_edits(iter_tool_uses(lines)) == 0


# --------------------------------------------------------------------------- #
# Failed test cycles (U3)
# --------------------------------------------------------------------------- #


def test_failing_pytest_invocations_each_count_one_cycle():
    lines = _lines([
        _bash("uv run pytest -q", id_="b1"),
        _tool_result("b1", is_error=True),
        _bash("python -m pytest tests/ -q", id_="b2"),
        _tool_result("b2", is_error=True),
        _bash("pytest -x", id_="b3"),
        _tool_result("b3", is_error=True),
    ])
    uses, results = iter_tool_uses(lines), iter_tool_results(lines)
    assert count_failed_test_cycles(uses, results) == 3


def test_passing_pytest_and_failing_non_pytest_are_silent():
    lines = _lines([
        _bash("uv run pytest -q", id_="b1"),
        _tool_result("b1", is_error=False),          # green run
        _bash("cat missing_file.txt", id_="b2"),
        _tool_result("b2", is_error=True),           # error, not pytest
        _bash("ls my_pytest_notes", id_="b3"),       # pytest not a command word
        _tool_result("b3", is_error=True),
    ])
    uses, results = iter_tool_uses(lines), iter_tool_results(lines)
    assert count_failed_test_cycles(uses, results) == 0


def test_make_test_and_wrapper_script_cycles_count():
    # Regression: the old pattern matched only (uv run |python -m )?pytest,
    # so Makefile targets and wrapper scripts were invisible to U3.
    lines = _lines([
        _bash("make test", id_="b1"),
        _tool_result("b1", is_error=True),
        _bash("./run_tests.sh -v", id_="b2"),
        _tool_result("b2", is_error=True),
        _bash("bash scripts/tests.sh", id_="b3"),
        _tool_result("b3", is_error=True),
        _bash(".venv/bin/pytest -q", id_="b4"),
        _tool_result("b4", is_error=True),
        _bash("python -m unittest discover", id_="b5"),
        _tool_result("b5", is_error=True),
    ])
    uses, results = iter_tool_uses(lines), iter_tool_results(lines)
    assert count_failed_test_cycles(uses, results) == 5


def test_subagent_pytest_failure_does_not_count():
    lines = _lines([
        _bash("uv run pytest -q", id_="b1", parent="tu_task"),
        _tool_result("b1", is_error=True, parent="tu_task"),
    ])
    uses, results = iter_tool_uses(lines), iter_tool_results(lines)
    assert count_failed_test_cycles(uses, results) == 0


# --------------------------------------------------------------------------- #
# Clarifying questions + trailing question marks (U5)
# --------------------------------------------------------------------------- #


def test_ask_user_question_fires_and_plain_tools_are_silent():
    asking = _lines([_assistant(_tool_use(
        "AskUserQuestion", {"questions": [{"question": "Which API?"}]}))])
    clean = _lines([_assistant(_tool_use("Read", {"file_path": "x.py"}))])
    assert count_clarifying_questions(iter_tool_uses(asking)) == 1
    assert count_clarifying_questions(iter_tool_uses(clean)) == 0


def test_trailing_question_marks_counted_from_result_event_text():
    report = deadend_report(_lines([
        _result("Done.\nShould I also add caching?\nOr is this enough?"),
    ]), leak_patterns=LEAK_PATTERNS)
    assert report.trailing_question_marks == 2
    assert report.clarifying_questions == 0  # diagnostic never counts as U5


def test_trailing_question_marks_fall_back_to_last_assistant_text():
    report = deadend_report(_lines([
        _assistant(_text("First draft done.")),
        _assistant(_text("All finished.\nAnything else you need?")),
    ]), leak_patterns=LEAK_PATTERNS)
    assert report.trailing_question_marks == 1


# --------------------------------------------------------------------------- #
# Leak hits (U0)
# --------------------------------------------------------------------------- #


def test_leak_fires_on_corpus_read_and_on_asset_names():
    lines = _lines([
        _assistant(_tool_use("Read", {"file_path": "corpus/demo/b01/brief.md"},
                             id_="l1")),
        _assistant(_tool_use("Bash", {"command": "cat ../repo/b01/oracle.py"},
                             id_="l2")),
    ])
    hits = count_leaks(iter_tool_uses(lines), LEAK_PATTERNS)
    # EVERY distinct fragment per tool_use: the Read yields both "corpus" and
    # "brief.md"; the Bash yields "oracle.py".
    assert len(hits) == 3
    assert {h.split(": ", 1)[1] for h in hits if h.startswith("Read: ")} == {
        "corpus", "brief.md"}
    assert [h for h in hits if h.startswith("Bash: ")] == ["Bash: oracle.py"]


def test_leak_records_every_fragment_exempt_first_order():
    # Round-3 BLOCKER repro, verbatim: the exempt-able brief.md fragment
    # comes FIRST in the command. The single-hit-per-tool_use behavior
    # recorded only "brief.md", which run-arm.sh's C0 staged-input exemption
    # then dropped — leak_hits 0, C0 green, oracle touch invisible. Every
    # distinct fragment must be recorded so the corpus/oracle hits survive
    # any downstream exemption of brief.*.
    lines = _lines([
        _assistant(_tool_use(
            "Bash",
            {"command": "cat brief.md; cat /repo/eval/blueprint/"
                        "over-explanation/corpus/b01/oracle.py"},
            id_="l1")),
    ])
    hits = count_leaks(iter_tool_uses(lines), LEAK_PATTERNS)
    fragments = {h.split(": ", 1)[1] for h in hits}
    assert {"brief.md", "corpus", "oracle.py"} <= fragments
    assert fragments - {"brief.md", "brief.json"}  # non-exempt hits remain


def test_leak_records_every_fragment_exempt_last_order():
    # The mirror order: brief.md LAST. Both orders must yield the same
    # fragment set (order independence of the C0 exemption).
    lines = _lines([
        _assistant(_tool_use(
            "Bash",
            {"command": "cat /repo/eval/blueprint/over-explanation/"
                        "corpus/b01/oracle.py; cat brief.md"},
            id_="l1")),
    ])
    hits = count_leaks(iter_tool_uses(lines), LEAK_PATTERNS)
    fragments = {h.split(": ", 1)[1] for h in hits}
    assert {"brief.md", "corpus", "oracle.py"} <= fragments
    assert fragments - {"brief.md", "brief.json"}


def test_leak_fragments_deduped_within_one_tool_use():
    # The same fragment matching in the serialized envelope and in a string
    # leaf (or twice in one command) is one hit, not several.
    lines = _lines([
        _assistant(_tool_use("Bash", {"command": "ls corpus; ls corpus"},
                             id_="l1")),
    ])
    hits = count_leaks(iter_tool_uses(lines), LEAK_PATTERNS)
    assert hits == ("Bash: corpus",)


def test_leak_pattern_anchors_at_string_value_start():
    # "corpus/" at the very start of a path value: only reachable through the
    # per-leaf ^ anchor, not through the serialized-envelope search.
    lines = _lines([
        _assistant(_tool_use("Glob", {"pattern": "corpus/**"}, id_="l1")),
    ])
    assert len(count_leaks(iter_tool_uses(lines), LEAK_PATTERNS)) == 1


def test_unanchored_corpus_commands_count_as_leaks():
    # Regression: the old patterns anchored asset names at ^ or /, so
    # `grep -r expected corpus/` and `ls corpus` yielded zero hits.
    lines = _lines([
        _assistant(_tool_use("Bash", {"command": "grep -r expected corpus/"},
                             id_="l1")),
        _assistant(_tool_use("Bash", {"command": "ls corpus"}, id_="l2")),
    ])
    hits = count_leaks(iter_tool_uses(lines), LEAK_PATTERNS)
    assert len(hits) == 2
    assert all(h.startswith("Bash: ") for h in hits)


def test_clean_workspace_tool_uses_have_no_leak_hits():
    lines = _lines([
        _assistant(_tool_use("Read", {"file_path": "/tmp/ws/impl.py"}, id_="c1")),
        _assistant(_tool_use("Write", {"file_path": "/tmp/ws/tests/test_impl.py",
                                       "content": "def test_ok(): ..."},
                             id_="c2")),
        _assistant(_tool_use("Bash", {"command": "uv run pytest -q"}, id_="c3")),
    ])
    assert count_leaks(iter_tool_uses(lines), LEAK_PATTERNS) == ()


# --------------------------------------------------------------------------- #
# deadend_report end to end
# --------------------------------------------------------------------------- #


def test_deadend_report_full_transcript_counts_every_signal():
    lines = ["{garbled", *_lines([
        _edit("impl.py", "return x", "return y", id_="e1"),
        _bash("uv run pytest -q", id_="b1"),
        _tool_result("b1", is_error=True),
        _edit("impl.py", "return y", "return x", id_="e2"),   # revert
        _assistant(_tool_use("Read", {"file_path": "corpus/demo/b01/cases.json"},
                             id_="r1")),
        _assistant(_tool_use("AskUserQuestion",
                             {"questions": [{"question": "Edge case?"}]},
                             id_="q1")),
        _result("Implemented.\nWant holdout coverage too?"),
    ])]
    report = deadend_report(lines, leak_patterns=LEAK_PATTERNS)
    assert report.reverted_edits == 1
    assert report.failed_test_cycles == 1
    assert report.dead_ends == 2
    assert report.clarifying_questions == 1
    assert report.trailing_question_marks == 1
    # Every distinct fragment of the corpus Read: "corpus" and "cases.json".
    assert len(report.leak_hits) == 2


def test_deadend_report_clean_transcript_is_all_silent():
    lines = _lines([
        _assistant(_tool_use("Write", {"file_path": "/tmp/ws/impl.py",
                                       "content": "def f(): return 1"},
                             id_="w1")),
        _bash("uv run pytest -q", id_="b1"),
        _tool_result("b1", is_error=False),
        _result("Implementation complete. All tests pass."),
    ])
    report = deadend_report(lines, leak_patterns=LEAK_PATTERNS)
    assert report.reverted_edits == 0
    assert report.failed_test_cycles == 0
    assert report.dead_ends == 0
    assert report.clarifying_questions == 0
    assert report.trailing_question_marks == 0
    assert report.leak_hits == ()


# --------------------------------------------------------------------------- #
# Workaround lint (O4)
# --------------------------------------------------------------------------- #

_CASES = (OracleCase(label="t1", args=(2, 3), expected=5),
          OracleCase(label="t2", args=(0, 0), expected=0))


def _workspace(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return tmp_path


def test_each_workaround_kind_fires(tmp_path):
    ws = _workspace(tmp_path, {
        "impl.py": (
            "def add(a, b):\n"
            "    # TODO: replace this hack\n"
            "    if a == 2:\n"
            "        return 5\n"          # hardcoded: matches expected 5
            "    try:\n"
            "        return a + b\n"
            "    except Exception:\n"
            "        pass\n"
            "\n"
            "def sub(a, b):\n"
            "    raise NotImplementedError\n"
        ),
        "tests/test_impl.py": (
            "import pytest\n"
            "\n"
            "# TODO in a test file must NOT count\n"
            "@pytest.mark.skipif(True, reason='later')\n"
            "def test_add():\n"
            "    assert True\n"
            "\n"
            "@pytest.mark.xfail\n"
            "def test_sub():\n"
            "    assert True\n"
        ),
    })
    report = workaround_lint(ws, _CASES)
    assert report.skips == 2
    assert report.assert_true == 2
    assert report.swallowed_except == 1
    assert report.hardcoded_expectations == 1
    assert report.not_implemented == 1
    assert report.todos == 1                      # impl TODO only
    assert report.total == 8
    assert "impl.py:2: todo" in report.hits
    assert any(h.startswith("impl.py:") and h.endswith("hardcoded-expectation")
               for h in report.hits)


def test_clean_workspace_lints_to_zero(tmp_path):
    ws = _workspace(tmp_path, {
        "impl.py": (
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        "tests/test_impl.py": (
            "from impl import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(2, 3) == 5\n"
        ),
    })
    report = workaround_lint(ws, _CASES)
    assert report.total == 0
    assert report.hits == ()


def test_return_constant_not_matching_expected_is_silent(tmp_path):
    ws = _workspace(tmp_path, {"impl.py": "def f():\n    return 42\n"})
    assert workaround_lint(ws, _CASES).hardcoded_expectations == 0


def test_syntax_error_file_gives_no_ast_signal_but_todos_still_count(tmp_path):
    ws = _workspace(tmp_path, {
        "broken.py": "def f(:\n    # TODO fix syntax\n    assert True\n",
    })
    report = workaround_lint(ws, _CASES)
    assert report.todos == 1
    assert report.assert_true == 0  # unparseable: no AST signal (O1 catches it)


# --------------------------------------------------------------------------- #
# n-gram containment + spec code blocks (L-support)
# --------------------------------------------------------------------------- #


def test_containment_is_one_for_identical_text_and_zero_when_disjoint():
    a = "def add(a, b): return a + b"
    assert ngram_containment(a, a) == 1.0
    assert ngram_containment(a, "class Widget renders the sidebar panel") == 0.0


def test_containment_zero_below_five_tokens():
    assert ngram_containment("too few tokens here", "too few tokens here") == 0.0


def test_containment_normalizes_case_and_strips_comments():
    a = "DEF Add(a, b): RETURN a + b  # explanatory comment\n"
    b = "def add(a, b): return a + b\n"
    assert ngram_containment(a, b) == 1.0


def test_spec_code_blocks_extracts_fenced_bodies_only():
    md = ("Intro prose.\n\n```python\nx = 1\ny = 2\n```\n\nMore prose.\n\n"
          "```\nplain block\n```\n")
    assert spec_code_blocks(md) == ("x = 1\ny = 2", "plain block")


def test_spec_code_blocks_keeps_unclosed_trailing_fence():
    md = "Prose.\n```python\nx = 1\n"
    assert spec_code_blocks(md) == ("x = 1",)


def test_spec_code_blocks_survives_fence_parity_desync():
    # A stray bare ``` before the real ```python block used to flip the
    # open/close toggle so the code body landed "outside" every block.
    md = "Prose.\n```\nstray note\n```python\nx = 1\ny = 2\n```\nMore prose.\n"
    blocks = spec_code_blocks(md)
    assert "x = 1\ny = 2" in blocks


def test_spec_code_lines_detects_unfenced_and_indented_code():
    md = ("Prose line explaining things.\n"
          "def add(a, b):\n"            # classifier: def
          "    return a + b\n"          # indented run
          "total = add(2, 3)\n"         # classifier: assignment
          "Another prose line follows here.\n")
    lines = spec_code_lines(md)
    assert "def add(a, b):" in lines
    assert "    return a + b" in lines
    assert "total = add(2, 3)" in lines
    assert "Prose line explaining things." not in lines
    assert "Another prose line follows here." not in lines


def test_code_token_count_covers_unfenced_code():
    md = "Prose only here.\n\n    x = compute(1)\n"
    assert code_token_count(md) == 3  # the indented line's tokens only


# --------------------------------------------------------------------------- #
# Leakage report (L1-L4)
# --------------------------------------------------------------------------- #

_PROSE = ("The service accepts a request and validates it before any work "
          "happens so malformed input is rejected early with a clear error "
          "and every accepted request is processed exactly once with the "
          "result recorded durably for later audit and replay purposes.")


def test_clean_spec_is_not_blocked():
    spec = f"# Spec\n\n{_PROSE}\n\n```python\nx = 1\n```\n"
    report = leakage_report(spec, "def add(a, b):\n    return a + b\n",
                            "def add(a, b):\n    return b + a\n", 0.0, _CAPS)
    assert not report.blocked
    assert report.reasons == ()
    assert report.code_frac <= _CAPS["code_frac"]
    assert report.reference_containment == 0.0


def test_code_heavy_spec_blocks_l1():
    code = "\n".join(f"value_{i} = compute_{i}(alpha, beta)" for i in range(20))
    spec = f"Short intro.\n\n```python\n{code}\n```\n"
    report = leakage_report(spec, "", "", 0.0, _CAPS)
    assert report.blocked
    assert any(r.startswith("L1") for r in report.reasons)


def test_spec_containing_reference_code_blocks_l2():
    reference = "def add(a, b):\n    return a + b\n"
    spec = f"{_PROSE}\n{_PROSE}\n{_PROSE}\n\n```python\n{reference}```\n"
    report = leakage_report(spec, reference, "", 0.0, _CAPS)
    assert report.reference_containment == 1.0
    assert report.blocked
    assert any(r.startswith("L2") for r in report.reasons)


def test_impl_copying_spec_code_blocks_l3():
    spec_code = "def merge(left, right):\n    return sorted(left + right)\n"
    spec = f"{_PROSE}\n{_PROSE}\n{_PROSE}\n\n```python\n{spec_code}```\n"
    report = leakage_report(spec, "unrelated reference body here entirely",
                            spec_code, 0.0, _CAPS)
    assert report.copy_containment == 1.0
    assert report.blocked
    assert any(r.startswith("L3") for r in report.reasons)


def test_executable_spec_blocks_l4():
    spec = f"{_PROSE}\n\n```python\nx = 1\n```\n"
    report = leakage_report(spec, "", "", 0.9, _CAPS)
    assert report.blocked
    assert any(r.startswith("L4") for r in report.reasons)


def test_l4_no_signal_is_flagged_never_clean_never_blocking():
    spec = f"{_PROSE}\n\n```python\nx = 1\n```\n"
    report = leakage_report(spec, "", "", None, _CAPS)
    assert not report.blocked            # L1-L3 carry the gate
    assert math.isnan(report.spec_only_correctness)
    assert any("L4 no signal" in r for r in report.reasons)


# --------------------------------------------------------------------------- #
# Whole-document leakage detection (regressions: fence-only L family)
# --------------------------------------------------------------------------- #

# Body of corpus/demo/b01/oracle.py (docstrings stripped) — the reference an
# adversarial spec would paste.
_ORACLE = (
    "def allowed(timestamps: list[int], limit: int, window: int)"
    " -> list[bool]:\n"
    "    counts: dict[int, int] = {}\n"
    "    verdicts: list[bool] = []\n"
    "    for t in timestamps:\n"
    "        bucket = t // window\n"
    "        used = counts.get(bucket, 0)\n"
    "        if used < limit:\n"
    "            counts[bucket] = used + 1\n"
    "            verdicts.append(True)\n"
    "        else:\n"
    "            verdicts.append(False)\n"
    "    return verdicts\n"
)


def test_unfenced_indented_oracle_paste_is_blocked():
    # Regression: fence-only detection gave code_frac 0.0 and containment 0.0
    # for the implementation pasted as indented prose — every gate passed.
    indented = "\n".join("    " + l for l in _ORACLE.splitlines())
    spec = f"# Spec\n\n{_PROSE}\n\nThe algorithm, for reference:\n\n{indented}\n"
    report = leakage_report(spec, _ORACLE, "", 0.0, _CAPS)
    assert report.blocked
    assert report.code_frac > _CAPS["code_frac"]
    assert report.reference_containment > _CAPS["reference"]
    assert any(r.startswith("L2") for r in report.reasons)


def test_fence_parity_desync_paste_is_blocked():
    # Regression: one stray bare ``` before the real block flipped the fence
    # toggle, the impl body landed "outside", and code_frac read 0.027.
    spec = (f"{_PROSE}\n{_PROSE}\n{_PROSE}\n\n"
            f"```\nnote\n```python\n{_ORACLE}```\n")
    report = leakage_report(spec, _ORACLE, "", 0.0, _CAPS)
    assert report.blocked
    assert report.reference_containment > _CAPS["reference"]
    assert any(r.startswith("L2") for r in report.reasons)


def test_identifier_renamed_copy_keeps_containment_above_half():
    # Regression: verbatim 5-gram containment dropped to 0.0 under a
    # systematic rename; the identifier-skeleton channel must survive it.
    renamed = _ORACLE
    for old, new in (("allowed", "check"), ("timestamps", "ts"),
                     ("limit", "cap"), ("window", "span"),
                     ("counts", "seen"), ("verdicts", "out"),
                     ("bucket", "slot"), ("used", "n"), ("t", "x")):
        renamed = re.sub(rf"\b{old}\b", new, renamed)
    assert renamed != _ORACLE
    assert ngram_containment(renamed, _ORACLE) > 0.5


def test_prose_only_spec_stays_unblocked_under_whole_document_detection():
    report = leakage_report(f"# Spec\n\n{_PROSE}\n\n{_PROSE}\n",
                            _ORACLE, "", 0.0, _CAPS)
    assert report.code_frac == 0.0
    assert not report.blocked


# --------------------------------------------------------------------------- #
# Round-5 regressions: line-prefix dressing, L2's denominator, L4's assembly
# --------------------------------------------------------------------------- #


def _dress(source: str, prefix: str, suffix: str = "") -> str:
    return "\n".join(prefix + line + suffix for line in source.splitlines())


def _dressed_spec(prefix: str, suffix: str = "") -> str:
    return (f"# Spec\n\n{_PROSE}\n\nThe algorithm, for reference:\n\n"
            f"{_dress(_ORACLE, prefix, suffix)}\n")


def test_blockquoted_oracle_paste_is_blocked():
    # Review repro verbatim: every classifier pattern is ``^``-anchored on
    # line.strip(), so a "> " blockquote detected 0/12 code lines — L1=L2=L3
    # = 0.0, code_tok = 0 (U1 conservation bypassed), and the working
    # implementation shipped inside the spec with every gate green.
    spec = _dressed_spec("> ")
    assert len(spec_code_lines(spec)) == len(_ORACLE.splitlines())
    report = leakage_report(spec, _ORACLE, "", 0.0, _CAPS)
    assert report.blocked
    assert report.code_frac > _CAPS["code_frac"]
    assert report.reference_containment > _CAPS["reference"]
    assert any(r.startswith("L2") for r in report.reasons)


def test_bullet_and_table_dressings_are_blocked_like_the_blockquote():
    for prefix, suffix in (("- ", ""), ("* ", ""), ("1. ", ""), ("| ", " |")):
        spec = _dressed_spec(prefix, suffix)
        report = leakage_report(spec, _ORACLE, "", 0.0, _CAPS)
        assert report.blocked, (prefix, report)
        assert report.reference_containment > _CAPS["reference"], prefix


def test_dressed_code_still_pays_the_u1_conservation_term():
    # code_tok feeds U1's spend index: a dressing that zeroed it made moving
    # implementation work into the spec free as well as invisible.
    for prefix in ("> ", "- ", "| "):
        assert code_token_count(_dressed_spec(prefix)) > 0, prefix


def test_dressed_prose_is_not_promoted_to_code():
    prose = "\n".join(f"> {line}" for line in _PROSE.split(". "))
    report = leakage_report(f"# Spec\n\n{prose}\n", _ORACLE, "", 0.0, _CAPS)
    assert report.code_frac == 0.0
    assert not report.blocked


def test_spec_code_source_carries_raw_and_dressed_forms():
    source = spec_code_source("> counts = {}\n")
    assert "> counts = {}" in source          # raw: L1 counts the marker
    assert "\ncounts = {}" in source          # dressed: containment sees code


def _payload_block(i: int) -> str:
    """One ordinary, NON-repeating indented JSON example — dilution filler."""
    return (f"    {{\n"
            f'      "tenant": "acme-{i}",\n'
            f'      "limit": {i * 7 + 3},\n'
            f'      "window_seconds": {i * 11 + 60},\n'
            f'      "observed_requests": {i * 13 + 5},\n'
            f'      "rejected_requests": {i * 3 + 1},\n'
            f'      "note": "sample capacity report number {i}"\n'
            f"    }}\n")


def _diluted_spec(blocks: int = 40, paragraphs: int = 160) -> str:
    return ("# Spec\n\n"
            + "\n\n".join(f"{_PROSE} Paragraph {i}." for i in range(paragraphs))
            + f"\n\nThe algorithm, verbatim:\n\n```python\n{_ORACLE}```\n"
            + "\n\nExample capacity payloads:\n\n"
            + "\n".join(_payload_block(i) for i in range(blocks)))


def test_reference_denominated_l2_survives_indented_json_dilution():
    # Review repro: L2 = matched / |spec_code| is AUTHOR-CONTROLLED. Padding
    # the spec with ordinary indented JSON examples (nothing removed, the
    # verbatim oracle still there) walked the old ratio under the 0.25 cap.
    # Reference-denominated presence cannot be moved by anything the author
    # adds: the denominator is the frozen oracle.
    spec = _diluted_spec()
    old_denominator = ngram_containment("\n".join(spec_code_lines(spec)),
                                        _ORACLE)
    assert old_denominator < _CAPS["reference"]      # the escape it bought
    report = leakage_report(spec, _ORACLE, "", 0.0, _CAPS)
    assert report.blocked
    assert report.reference_containment > _CAPS["reference"]
    # ONLY L2 fires: L1/L3/L4 are all clean, so the test cannot pass for a
    # neighbouring reason if someone touches the code-fraction detector.
    assert [r[:2] for r in report.reasons] == ["L2"]
    assert report.code_frac <= _CAPS["code_frac"]


def test_partial_paste_keeps_the_legacy_spec_denominated_channel():
    # Three lines lifted out of a long reference: reference-denominated
    # presence is tiny, so the legacy spec-denominated channel is what still
    # blocks. Both live in the max for exactly this case.
    excerpt = "\n".join(_ORACLE.splitlines()[4:8])
    long_reference = _ORACLE + "\n" + "\n".join(
        f"def helper_{i}(seq):\n    return [item for item in seq if item > {i}]"
        for i in range(30))
    spec = f"# Spec\n\n{_PROSE}\n\n```python\n{excerpt}\n```\n"
    report = leakage_report(spec, long_reference, "", 0.0, _CAPS)
    assert report.reference_containment > _CAPS["reference"]
    assert any(r.startswith("L2") for r in report.reasons)


def test_reference_docstring_prose_never_matches_honest_spec_prose():
    # The reference is docstring-stripped before n-gramming: the skeleton
    # channel collapses punctuation-free words to one placeholder, so an
    # oracle's prose docstring would otherwise match ordinary honest spec
    # prose (measured 0.092 across the honest fixture x oracle sweep).
    documented = ('"""The service accepts a request and validates it before '
                  'any work happens so malformed input is rejected early '
                  'with a clear error and every accepted request is '
                  'processed exactly once."""\n' + _ORACLE)
    report = leakage_report(f"# Spec\n\n{_PROSE}\n\n{_PROSE}\n",
                            documented, "", 0.0, _CAPS)
    assert report.reference_containment == 0.0
    assert not report.blocked


def test_spec_python_source_survives_a_non_python_block():
    # Review repro: L4 assembled EVERY detected line, so one indented JSON
    # example made the candidate a syntax error -> "no signal" -> the working
    # implementation next to it was never executed.
    spec = (f"# Spec\n\n{_PROSE}\n\nPayload example:\n\n{_payload_block(1)}\n"
            f"The algorithm:\n\n```python\n{_ORACLE}```\n")
    source = spec_python_source(spec)
    assert "def allowed(" in source
    ast.parse(source)                      # imports: the L4 control can run


def test_spec_python_source_dedresses_a_blockquoted_implementation():
    source = spec_python_source(_dressed_spec("> "))
    assert "def allowed(" in source
    ast.parse(source)


def test_spec_python_source_is_empty_when_nothing_parses():
    spec = f"# Spec\n\n{_PROSE}\n\n```python\ndef broken(:\n```\n"
    assert spec_python_source(spec).strip() == ""


_TRANSPORT_SAMPLE = (
    "    $ curl -X POST /v1/limits --data 'tenant=acme&limit=10'\n"
    "    HTTP/1.1 200 OK\n"
)


def test_spec_python_source_splits_a_run_at_its_blank_lines():
    # Detected runs break only on non-blank prose, so a non-Python block one
    # BLANK LINE above the paste is part of the SAME run: whole-set and
    # per-run assembly both fail and L4 goes quiet again — the round-4 hole
    # reopened by adjacency alone. The blank-line grain closes it.
    spec = (f"# Spec\n\n{_PROSE}\n\nTransport sample:\n\n"
            f"{_TRANSPORT_SAMPLE}\n"
            + "\n".join(f"    {line}" for line in _ORACLE.splitlines()) + "\n")
    source = spec_python_source(spec)
    assert "def allowed(" in source
    ast.parse(source)


def test_spec_python_source_prefers_the_whole_detected_set():
    # A signature and its body separated by a prose line still assemble: the
    # whole detected set is tried before per-run filtering.
    spec = ("def running_total(values):\n"
            "Explanatory sentence between the signature and the body.\n"
            "    total = 0\n"
            "    return total\n")
    source = spec_python_source(spec)
    assert "def running_total" in source and "return total" in source
    ast.parse(source)

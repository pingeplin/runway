"""Tests for the per-family default model resolution in ``analysis/assemble.py``.

``assemble.py`` lives under ``analysis/`` (a script, not part of the installed
package), so we load it by path. Only the pure ``_resolve_model`` helper is
exercised — no run cells, no extractor, no network.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_ASSEMBLE = Path(__file__).resolve().parents[1] / "analysis" / "assemble.py"


def _load_assemble():
    spec = importlib.util.spec_from_file_location("assemble_under_test", _ASSEMBLE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# Transcript helpers (synthetic stream-json lines)
# --------------------------------------------------------------------------- #


def _write_tool_use(file_path: str, content: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Write",
                 "input": {"file_path": file_path, "content": content}}
            ]
        },
    }


def _edit_tool_use(file_path: str, old: str, new: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Edit",
                 "input": {"file_path": file_path, "old_string": old, "new_string": new}}
            ]
        },
    }


def _write_transcript(path: Path, objs: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(o) for o in objs) + "\n", encoding="utf-8")
    return path


def test_default_models_are_the_two_pinned_families():
    asm = _load_assemble()
    # The two cross-family extractors the design pins (fix #1, >=2 families).
    assert asm._resolve_model("anthropic", "") == "claude-sonnet-4-6"
    assert asm._resolve_model("openai", "") == "gpt-5.4"


def test_explicit_model_overrides_the_default():
    asm = _load_assemble()
    assert asm._resolve_model("openai", "gpt-4o-mini") == "gpt-4o-mini"
    assert asm._resolve_model("anthropic", "claude-haiku-4-5") == "claude-haiku-4-5"


# --------------------------------------------------------------------------- #
# reconstruct_pre_evaluator_text — the merge-fidelity capture
# --------------------------------------------------------------------------- #


def test_pre_eval_ok_on_single_write_with_evaluator_edits(tmp_path):
    asm = _load_assemble()
    t = _write_transcript(tmp_path / "transcript.jsonl", [
        _write_tool_use("docs/designs/d.md", "GENERATOR OUTPUT"),
        _edit_tool_use("docs/designs/d.md", "GENERATOR OUTPUT", "EVALUATOR TRIMMED"),
    ])
    # Pre-evaluator = the generator's lone Write; the evaluator's Edit is the
    # expected transform (it lands in post, not pre).
    pre = asm.reconstruct_pre_evaluator(t)
    assert pre.status == "ok"
    assert pre.text == "GENERATOR OUTPUT"


def test_pre_eval_ambiguous_on_multiple_writes(tmp_path):
    asm = _load_assemble()
    t = _write_transcript(tmp_path / "transcript.jsonl", [
        _write_tool_use("docs/designs/d.md", "FIRST DRAFT"),
        _write_tool_use("docs/designs/d.md", "REWRITTEN"),  # 2nd Write -> untrustworthy
    ])
    # Fail-closed: a file written twice means the pre/post boundary is unknowable.
    pre = asm.reconstruct_pre_evaluator(t)
    assert pre.status == "ambiguous"
    assert pre.text == ""
    assert "docs/designs/d.md" in pre.detail  # names the offending file


def test_pre_eval_one_clean_one_twice_written_skips_whole_cell(tmp_path):
    asm = _load_assemble()
    # A clean single-Write spec PLUS an aux file written twice. We deliberately
    # fail closed on the WHOLE cell (not per-file): emitting a partial alignment
    # for just the clean file would read as a pass for the omitted ambiguous one.
    t = _write_transcript(tmp_path / "transcript.jsonl", [
        _write_tool_use("blueprint/specs/s.md", "clean spec"),
        _write_tool_use("docs/testing/conv.md", "draft 1"),
        _write_tool_use("docs/testing/conv.md", "draft 2"),
    ])
    pre = asm.reconstruct_pre_evaluator(t)
    assert pre.status == "ambiguous"
    assert "docs/testing/conv.md" in pre.detail
    assert "blueprint/specs/s.md" not in pre.detail  # the clean file is not the culprit


def test_pre_eval_ignores_non_artifact_writes(tmp_path):
    asm = _load_assemble()
    t = _write_transcript(tmp_path / "transcript.jsonl", [
        _write_tool_use("README.md", "not an artifact"),
        _write_tool_use("src/foo.py", "code, not prose"),
        _write_tool_use("blueprint/specs/s.md", "the spec"),
    ])
    pre = asm.reconstruct_pre_evaluator(t)
    assert pre.status == "ok"
    assert pre.text == "the spec"


def test_pre_eval_path_match_is_by_component_not_substring(tmp_path):
    asm = _load_assemble()
    # `tests/specs_helper.md` must NOT masquerade as a `specs/` artifact.
    assert asm._is_artifact_path("tests/specs_helper.md") is False
    assert asm._is_artifact_path("planservice/notes.md") is False
    assert asm._is_artifact_path("blueprint/specs/s.md") is True
    # Absolute paths (as stream-json emits) still match on components.
    assert asm._is_artifact_path("/home/u/workspace/blueprint/designs/d.md") is True
    t = _write_transcript(tmp_path / "transcript.jsonl", [
        _write_tool_use("tests/specs_helper.md", "decoy, not an artifact"),
    ])
    assert asm.reconstruct_pre_evaluator(t).status == "none"


def test_pre_eval_concatenates_multiple_artifacts_in_sorted_order(tmp_path):
    asm = _load_assemble()
    t = _write_transcript(tmp_path / "transcript.jsonl", [
        _write_tool_use("blueprint/specs/s.md", "SPEC"),
        _write_tool_use("blueprint/designs/d.md", "DESIGN"),
    ])
    # sorted by path: blueprint/designs/d.md before blueprint/specs/s.md
    pre = asm.reconstruct_pre_evaluator(t)
    assert pre.status == "ok"
    assert pre.text == "DESIGN\n\nSPEC"


def test_pre_eval_missing_transcript_is_none(tmp_path):
    asm = _load_assemble()
    pre = asm.reconstruct_pre_evaluator(tmp_path / "nope.jsonl")
    assert pre.status == "none"
    assert pre.text == ""


def test_pre_eval_tolerates_malformed_and_empty_lines(tmp_path):
    asm = _load_assemble()
    p = tmp_path / "transcript.jsonl"
    p.write_text(
        "\n"
        "not json at all {\n"
        + json.dumps(_write_tool_use("docs/designs/d.md", "OK")) + "\n"
        '{"type":"system","subtype":"init"}\n',
        encoding="utf-8",
    )
    pre = asm.reconstruct_pre_evaluator(p)
    assert pre.status == "ok"
    assert pre.text == "OK"


def test_pre_eval_none_when_only_edits_no_write(tmp_path):
    asm = _load_assemble()
    t = _write_transcript(tmp_path / "transcript.jsonl", [
        _write_tool_use("notes.txt", "x"),
        _edit_tool_use("blueprint/specs/s.md", "a", "b"),  # Edit, not Write
    ])
    # No artifact Write (e.g. text-editor `create`, or edits only) -> skip, not pass.
    assert asm.reconstruct_pre_evaluator(t).status == "none"


# --------------------------------------------------------------------------- #
# End-to-end: assemble emits merge_alignment from a transcript + fixtures
# --------------------------------------------------------------------------- #


def _pset(doc_id: str, ids: list[str]) -> dict:
    return {
        "document_id": doc_id,
        "propositions": [
            {"id": i, "text": i, "kind": "assertion", "tier": "must",
             "mention_sentences": [0]}
            for i in ids
        ],
    }


def test_assemble_emits_merge_alignment_from_transcript(tmp_path):
    asm = _load_assemble()
    # One cell: b01 / A1 / seed 1, with a post-evaluator artifact + a transcript
    # whose first Write is the pre-evaluator doc.
    cell = tmp_path / "results" / "b01" / "A1" / "seed-1"
    art = cell / "artifacts" / "blueprint" / "designs"
    art.mkdir(parents=True)
    (art / "d.md").write_text("post-evaluator body", encoding="utf-8")
    _write_transcript(cell / "transcript.jsonl", [
        _write_tool_use("blueprint/designs/d.md", "pre-evaluator body"),
        _edit_tool_use("blueprint/designs/d.md", "pre", "post"),
    ])

    post = _pset("b01:A1:1", ["p1"])
    pre = _pset("b01:A1:1:pre", ["s1", "s2"])
    fixtures = {
        "sets": {"b01:A1:1": post, "b01:A1:1:pre": pre},
        "alignments": {
            "b01:A1:1:pre|b01:A1:1": {
                "source": pre,
                "target": post,
                "links": [
                    {"source_id": "s1", "target_id": "p1", "relation": "preserved"},
                    {"source_id": "s2", "target_id": "p1", "relation": "merged_into"},
                ],
            }
        },
    }
    fx = tmp_path / "fixtures.json"
    fx.write_text(json.dumps(fixtures), encoding="utf-8")
    out = tmp_path / "results.json"

    rc = asm.main([
        "--results-root", str(tmp_path / "results"),
        "--corpus", str(tmp_path),  # unused by assemble, but required
        "--family", "fixture", "--fixtures", str(fx),
        "--out", str(out), "--baseline-arm", "A0",
    ])
    assert rc == 0

    data = json.loads(out.read_text(encoding="utf-8"))
    (record,) = data["records"]
    assert "merge_alignment" in record, record
    links = record["merge_alignment"]["links"]
    assert {l["source_id"] for l in links} == {"s1", "s2"}
    assert {l["relation"] for l in links} == {"preserved", "merged_into"}


def test_assemble_skips_merge_when_no_transcript(tmp_path):
    asm = _load_assemble()
    cell = tmp_path / "results" / "b01" / "A1" / "seed-1"
    art = cell / "artifacts" / "blueprint" / "designs"
    art.mkdir(parents=True)
    (art / "d.md").write_text("post body", encoding="utf-8")
    # No transcript.jsonl -> merge-fidelity must be skipped, not fabricated.

    fixtures = {"sets": {"b01:A1:1": _pset("b01:A1:1", ["p1"])}}
    fx = tmp_path / "fixtures.json"
    fx.write_text(json.dumps(fixtures), encoding="utf-8")
    out = tmp_path / "results.json"

    rc = asm.main([
        "--results-root", str(tmp_path / "results"),
        "--corpus", str(tmp_path),
        "--family", "fixture", "--fixtures", str(fx),
        "--out", str(out), "--baseline-arm", "A0",
    ])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    (record,) = data["records"]
    assert "merge_alignment" not in record


def _one_cell_tree(tmp_path, transcript_objs):
    """Build a single b01/A1/seed-1 cell with a post artifact + transcript."""
    cell = tmp_path / "results" / "b01" / "A1" / "seed-1"
    art = cell / "artifacts" / "blueprint" / "designs"
    art.mkdir(parents=True)
    (art / "d.md").write_text("post body", encoding="utf-8")
    _write_transcript(cell / "transcript.jsonl", transcript_objs)
    return cell


def test_assemble_skips_merge_on_ambiguous_transcript(tmp_path):
    asm = _load_assemble()
    # Two Writes to the same artifact -> ambiguous -> must NOT emit merge_alignment
    # (even though the fixtures could supply one).
    _one_cell_tree(tmp_path, [
        _write_tool_use("blueprint/designs/d.md", "draft one"),
        _write_tool_use("blueprint/designs/d.md", "draft two"),
    ])
    post, pre = _pset("b01:A1:1", ["p1"]), _pset("b01:A1:1:pre", ["s1"])
    fixtures = {
        "sets": {"b01:A1:1": post, "b01:A1:1:pre": pre},
        "alignments": {"b01:A1:1:pre|b01:A1:1": {
            "source": pre, "target": post,
            "links": [{"source_id": "s1", "target_id": None, "relation": "dropped"}],
        }},
    }
    fx = tmp_path / "fixtures.json"
    fx.write_text(json.dumps(fixtures), encoding="utf-8")
    out = tmp_path / "results.json"

    rc = asm.main([
        "--results-root", str(tmp_path / "results"), "--corpus", str(tmp_path),
        "--family", "fixture", "--fixtures", str(fx),
        "--out", str(out), "--baseline-arm", "A0",
    ])
    assert rc == 0
    (record,) = json.loads(out.read_text(encoding="utf-8"))["records"]
    assert "merge_alignment" not in record  # ambiguous -> skipped, never a false pass


def test_assemble_skips_cell_when_pre_set_uncanned_without_aborting(tmp_path):
    asm = _load_assemble()
    # Trustworthy "ok" transcript, but the fixtures omit the ":pre" set. The
    # per-cell extract must be caught (not crash the whole run).
    _one_cell_tree(tmp_path, [
        _write_tool_use("blueprint/designs/d.md", "the pre doc"),
    ])
    fixtures = {"sets": {"b01:A1:1": _pset("b01:A1:1", ["p1"])}}  # no ":pre"
    fx = tmp_path / "fixtures.json"
    fx.write_text(json.dumps(fixtures), encoding="utf-8")
    out = tmp_path / "results.json"

    rc = asm.main([
        "--results-root", str(tmp_path / "results"), "--corpus", str(tmp_path),
        "--family", "fixture", "--fixtures", str(fx),
        "--out", str(out), "--baseline-arm", "A0",
    ])
    assert rc == 0  # did not abort
    (record,) = json.loads(out.read_text(encoding="utf-8"))["records"]
    assert "merge_alignment" not in record  # skipped this cell, kept the rest

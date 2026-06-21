"""Tests for the thin CLI wiring.

The CLI owns no computation, so these tests assert wiring and exit codes, not
statistics: the example manifest's hash is reproduced end-to-end through
``main``; an unknown subcommand exits non-zero; each guardrail's block/no-block
boundary maps to the documented exit code; and a missing input fails with the
load-error code rather than a traceback. No network, no real LLM, no spaCy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval_overexplanation.cli import (
    EXIT_BLOCKED,
    EXIT_LOAD_ERROR,
    EXIT_OK,
    main,
)
from eval_overexplanation.manifest import load_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_MANIFEST = REPO_ROOT / "preregistration" / "manifest.example.json"


# --------------------------------------------------------------------------- #
# manifest-hash — the mandated end-to-end check
# --------------------------------------------------------------------------- #


def test_manifest_hash_matches_library(capsys: pytest.CaptureFixture[str]) -> None:
    # The CLI must print exactly what the library computes for the same file.
    expected = load_manifest(EXAMPLE_MANIFEST).content_hash()

    code = main(["manifest-hash", str(EXAMPLE_MANIFEST)])

    out = capsys.readouterr().out
    printed_hash = out.splitlines()[0].strip()
    assert code == EXIT_OK
    assert printed_hash == expected
    # A 64-char sha256 hexdigest.
    assert len(printed_hash) == 64
    assert all(c in "0123456789abcdef" for c in printed_hash)


def test_manifest_hash_missing_file_is_load_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["manifest-hash", str(tmp_path / "nope.json")])
    assert code == EXIT_LOAD_ERROR
    assert "error:" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Unknown / missing subcommand — argparse usage error (non-zero)
# --------------------------------------------------------------------------- #


def test_unknown_subcommand_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["does-not-exist"])
    assert exc.value.code != 0
    assert exc.value.code == 2  # argparse usage error


def test_no_subcommand_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0


# --------------------------------------------------------------------------- #
# Fixture builders for a results.json
# --------------------------------------------------------------------------- #


def _pset(doc_id: str, props: list[dict]) -> dict:
    return {"document_id": doc_id, "propositions": props}


def _prop(pid: str, mentions: list[int], tier: str = "should", kind: str = "claim") -> dict:
    return {
        "id": pid,
        "text": pid,
        "kind": kind,
        "tier": tier,
        "mention_sentences": mentions,
    }


def _write_results(tmp_path: Path, payload: dict) -> Path:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "results.json").write_text(json.dumps(payload), encoding="utf-8")
    return results_dir


# --------------------------------------------------------------------------- #
# restatement subcommand
# --------------------------------------------------------------------------- #


def test_restatement_prints_per_record_rate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {
        "records": [
            {
                "arm_id": "A0",
                "brief_id": "b01",
                "seed": 1,
                "word_count": 100,
                # 1 distinct, 2 mentions -> rate 0.5
                "propositions": _pset("d", [_prop("p", [0, 1])]),
            }
        ]
    }
    results_dir = _write_results(tmp_path, payload)
    code = main(["restatement", str(results_dir)])
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "A0" in out and "b01" in out
    assert "rate=0.5000" in out


# --------------------------------------------------------------------------- #
# guardrails block / no-block boundary
# --------------------------------------------------------------------------- #


def _substance_alignment(relation: str, tier: str) -> dict:
    source = _pset("a0", [_prop("s1", [0], tier=tier)])
    if relation == "dropped":
        target = _pset("a1", [])
        links = [{"source_id": "s1", "target_id": None, "relation": "dropped"}]
    else:
        target = _pset("a1", [_prop("t1", [0])])
        links = [{"source_id": "s1", "target_id": "t1", "relation": relation}]
    return {"source": source, "target": target, "links": links}


def test_guardrails_pass_when_must_preserved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {
        "records": [
            {
                "arm_id": "A1",
                "brief_id": "b01",
                "seed": 1,
                "propositions": _pset("a1", [_prop("t1", [0])]),
                "substance_alignment": _substance_alignment("preserved", "must"),
            }
        ]
    }
    results_dir = _write_results(tmp_path, payload)
    code = main(["guardrails", str(results_dir)])
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "substance" in out and "ok" in out


def test_guardrails_block_when_must_dropped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {
        "records": [
            {
                "arm_id": "A1",
                "brief_id": "b01",
                "seed": 1,
                "propositions": _pset("a1", [_prop("t1", [0])]),
                "substance_alignment": _substance_alignment("dropped", "must"),
            }
        ]
    }
    results_dir = _write_results(tmp_path, payload)
    code = main(["guardrails", str(results_dir)])
    out = capsys.readouterr().out
    assert code == EXIT_BLOCKED
    assert "BLOCK" in out


def test_guardrails_block_on_grammaticality_fragment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {
        "records": [
            {
                "arm_id": "A1",
                "brief_id": "b01",
                "seed": 1,
                "propositions": _pset("a1", [_prop("t1", [0])]),
                # Telegraphic fragment the default checker must flag.
                "sentences": ["Returns list."],
            }
        ]
    }
    results_dir = _write_results(tmp_path, payload)
    code = main(["guardrails", str(results_dir)])
    assert code == EXIT_BLOCKED
    assert "grammaticality" in capsys.readouterr().out


def test_guardrails_missing_results_is_load_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["guardrails", str(tmp_path / "absent")])
    assert code == EXIT_LOAD_ERROR
    assert "error:" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# stats subcommand (just exercise the wiring + exit code)
# --------------------------------------------------------------------------- #


def test_stats_runs_and_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Two briefs, baseline A0 vs treatment A1, treatment restates less.
    records = []
    for brief, base_mentions, treat_mentions in (
        ("b01", [0, 1, 2], [0]),
        ("b02", [0, 1], [0]),
    ):
        records.append(
            {
                "arm_id": "A0",
                "brief_id": brief,
                "seed": 1,
                "word_count": 200,
                "propositions": _pset(f"a0-{brief}", [_prop("p", base_mentions)]),
            }
        )
        records.append(
            {
                "arm_id": "A1",
                "brief_id": brief,
                "seed": 1,
                "word_count": 180,
                "propositions": _pset(f"a1-{brief}", [_prop("p", treat_mentions)]),
            }
        )
    results_dir = _write_results(tmp_path, {"records": records, "noise_floor": 0.0})
    code = main(["stats", str(results_dir)])
    out = capsys.readouterr().out
    # Treatment beat baseline (negative mean delta); exit code is whatever the
    # STOP gate decides — assert it is one of the two defined codes and that the
    # report was printed.
    assert code in (EXIT_OK, EXIT_BLOCKED)
    assert "A1" in out and "vs A0" in out
    assert "length_falsification" in out


# --------------------------------------------------------------------------- #
# decision subcommand — DO_NOT_SHIP exits non-zero, SHIP_TREATMENT exits 0
# --------------------------------------------------------------------------- #


def _tost(non_inferior: bool = True, certifiable: bool = True) -> dict:
    return {
        "non_inferior": non_inferior,
        "p_value": 0.01,
        "power": 0.9,
        "certifiable": certifiable,
    }


def _ship_treatment_inputs() -> dict:
    # All gates pass; A1 beats both A3_fair and A2_placebo; A4 does not capture
    # the effect alone -> the precedence ladder lands on SHIP_TREATMENT.
    return {
        "restatement_real": True,
        "substance_ok": True,
        "buildability": _tost(),
        "grammaticality": _tost(),
        "a3b_fails_grammaticality": True,
        "instrument_trusted": True,
        "beats_a3_fair": {"beats": True, "detail": "A1 beats the one-liner"},
        "beats_a2_placebo": {"beats": True, "detail": "A1 beats the placebo"},
        "a4_captures_effect": False,
    }


def _write_json(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_decision_do_not_ship_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Untrusted instrument -> precedence branch 1 -> DO_NOT_SHIP.
    payload = _ship_treatment_inputs()
    payload["instrument_trusted"] = False
    inputs = _write_json(tmp_path, "decision.json", payload)

    code = main(["decision", str(inputs)])

    out = capsys.readouterr().out
    assert code == EXIT_BLOCKED
    assert "do_not_ship" in out
    assert "verdict" in out


def test_decision_ship_treatment_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inputs = _write_json(tmp_path, "decision.json", _ship_treatment_inputs())

    code = main(["decision", str(inputs)])

    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "ship_treatment" in out


def test_decision_missing_file_is_load_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["decision", str(tmp_path / "nope.json")])
    assert code == EXIT_LOAD_ERROR
    assert "error:" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# sweep subcommand — prints stability + span
# --------------------------------------------------------------------------- #


def test_sweep_prints_stability(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Two thresholds, both with positive mean rates -> sign-stable.
    payload = {"0.5": [0.2, 0.3], "0.8": [0.25, 0.35]}
    sweep = _write_json(tmp_path, "sweep.json", payload)

    code = main(["sweep", str(sweep)])

    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "sign_stable" in out
    assert "span" in out
    assert "threshold=0.5000" in out

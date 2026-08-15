"""Smoke tests for the offline BLUEPRINT-BENCH demo (demo/run_benchmark_demo.py).

The contract: the clean run emits a real ``score.json`` whose verdict is
UNDERPOWERED (exit 1) — strata coverage derives from the manifest briefs and
the demo panel's buildable ``large_realistic`` stratum is n=1, structurally
underpowered by design (§0 N ceiling), so SHIP is unreachable at demo scale.
Every ``--break`` mode still blocks EARLIER in the precedence (rows 5-7)
with its own non-zero exit — including the unfenced-leakage vector, which
proves the whole-document detector gates what a fence-only detector would
wave through.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))

import run_benchmark_demo  # noqa: E402


def _run(tmp_path: Path, *argv: str) -> tuple[int, Path]:
    out = tmp_path / "bench"
    code = run_benchmark_demo.main([*argv, "--out", str(out)])
    return code, out / "score.json"


def test_clean_run_is_structurally_underpowered_exit_1(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Strata derive from the manifest: buildable large_realistic n=1 < 3
    # forces UNDERPOWERED — the demo panel can never SHIP, by design.
    code, score_path = _run(tmp_path)
    assert code == 1
    obj = json.loads(score_path.read_text())
    assert obj["schema"] == "blueprint-bench/1"
    assert obj["scorable"] is True
    assert obj["verdict"] == "underpowered_no_ship"
    assert obj["ceiling"] == "promising_scale_to_n18"
    assert obj["strata_coverage"]["U"]["large_realistic"] == 1
    assert any("large_realistic n=1 < 3" in r for r in obj["verdict_reasons"])
    # Every gate is green and the composite meets — power alone blocks.
    assert obj["arms"]["A1"]["gates_failed"] == []
    assert obj["arms"]["A1"]["composite"]["meets"] is True
    assert obj["arms"]["A1"]["composite"]["authorizes_ship"] is False


def test_break_leakage_unfenced_paste_blocks(tmp_path: Path,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    code, score_path = _run(tmp_path, "--break", "leakage")
    assert code == 1
    obj = json.loads(score_path.read_text())
    assert obj["verdict"] == "do_not_ship"
    arm = obj["arms"]["A1"]
    assert arm["leakage_voided"] is True
    assert "L1_code_fraction" in arm["gates_failed"]
    assert arm["dimensions"]["U"]["subscore"] == 0.0
    assert arm["dimensions"]["O"]["subscore"] == 0.0
    assert any("leakage" in r for r in obj["verdict_reasons"])


def test_break_workaround_blocks_on_o4(tmp_path: Path,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    code, score_path = _run(tmp_path, "--break", "workaround")
    assert code == 1
    obj = json.loads(score_path.read_text())
    assert "hard gate failed: O4_workaround_lint" in obj["verdict_reasons"]


def test_break_missing_result_blocks_on_u4(tmp_path: Path,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    code, score_path = _run(tmp_path, "--break", "missing-result")
    assert code == 1
    obj = json.loads(score_path.read_text())
    assert "hard gate failed: U4_completion" in obj["verdict_reasons"]
    cells = obj["arms"]["A1"]["cells"]["implement"]
    assert cells["missing"] == 1  # excluded AND counted, never imputed


def test_break_incomplete_is_not_scorable_exit_4(tmp_path: Path,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    code, score_path = _run(tmp_path, "--break", "incomplete")
    assert code == 4
    obj = json.loads(score_path.read_text())
    assert obj["scorable"] is False
    assert obj["reason"] == "incomplete_fraction_exceeded"
    assert obj["arms"] == {}  # a partial composite is never emitted

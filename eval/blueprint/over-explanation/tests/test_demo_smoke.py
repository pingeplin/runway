"""Smoke test for the end-to-end demo runner.

Runs ``demo/run_demo.py`` as a subprocess (it imports the installed package) and
asserts the whole pipeline composes to a verdict, and that the guardrail breaks
actually flip it. This is the integration backstop: every M1+M2 mechanism is
exercised together on the demo corpus, so a wiring regression fails here even if
the per-module unit tests still pass.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo" / "run_demo.py"


def _run(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(DEMO), *extra],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_clean_run_ships_treatment() -> None:
    proc = _run()
    assert proc.returncode == 0, proc.stderr
    assert "VERDICT: SHIP_TREATMENT" in proc.stdout
    # the non-blind caveat must always be emitted
    assert "NON-BLIND DEMO DATA" in proc.stdout


def test_each_break_blocks_the_ship() -> None:
    for mode in ("substance", "length", "grammaticality", "instrument"):
        proc = _run("--break", mode)
        assert proc.returncode == 0, proc.stderr
        assert "VERDICT: DO_NOT_SHIP" in proc.stdout, f"--break {mode} did not block: {proc.stdout[-400:]}"

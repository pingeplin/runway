from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class CorrectnessScore:
    score: float
    passed: int
    total: int
    failures: list[dict] = field(default_factory=list)
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ScorerError(Exception):
    pass


def _stage_oracle(task_dir: Path, run_dir: Path) -> Path:
    """Copy oracle/tests/ into a sibling of wt/ for invocation."""
    src = task_dir / "oracle" / "tests"
    if not src.is_dir():
        raise ScorerError(f"task missing oracle/tests/: {task_dir}")
    dst = run_dir / "oracle_tests"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def _starter_pythonpath_entries(wt: Path) -> list[Path]:
    """Honor the starter project's declared pytest pythonpath.

    Each task's starter/pyproject.toml is the source of truth for where its
    source root lives (e.g., src-layout tasks set pythonpath = ["src"]).
    The scorer respects that so oracle tests can import the agent's
    modules the same way the visible tests do.
    """
    pyproject = wt / "pyproject.toml"
    entries: list[Path] = [wt]
    if not pyproject.exists():
        return entries
    try:
        data = tomllib.loads(pyproject.read_text())
    except tomllib.TOMLDecodeError:
        return entries
    declared = (
        data.get("tool", {})
        .get("pytest", {})
        .get("ini_options", {})
        .get("pythonpath", [])
    )
    if isinstance(declared, str):
        declared = [declared]
    for entry in declared:
        resolved = (wt / entry).resolve()
        if resolved not in entries:
            entries.append(resolved)
    return entries


def _invoke_pytest(oracle_tests: Path, wt: Path, run_dir: Path) -> Path:
    """Run pytest against the staged oracle. Returns the JSON report path."""
    report_path = run_dir / "pytest_report.json"
    if report_path.exists():
        report_path.unlink()

    extra = [str(p) for p in _starter_pythonpath_entries(wt)]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(extra + [os.environ.get("PYTHONPATH", "")]).strip(os.pathsep),
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(oracle_tests),
        "--json-report",
        f"--json-report-file={report_path}",
        "-q",
        "--no-header",
        "--rootdir",
        str(run_dir),
    ]
    subprocess.run(cmd, env=env, capture_output=True, text=True)
    return report_path


def _parse_report(report_path: Path) -> CorrectnessScore:
    if not report_path.exists():
        return CorrectnessScore(
            score=0.0,
            passed=0,
            total=0,
            note="pytest produced no json report",
        )
    data = json.loads(report_path.read_text())
    summary = data.get("summary", {})
    passed = int(summary.get("passed", 0))
    failed = int(summary.get("failed", 0))
    errors = int(summary.get("error", 0))
    total = int(summary.get("total", passed + failed + errors))

    collector_errors: list[str] = []
    for col in data.get("collectors", []):
        if col.get("outcome") == "failed":
            longrepr = col.get("longrepr", "")
            collector_errors.append(longrepr[:1000])

    if total == 0:
        note = "no tests collected"
        if collector_errors:
            note += f"; collection errors: {collector_errors[0]}"
        return CorrectnessScore(
            score=0.0,
            passed=0,
            total=0,
            failures=[{"nodeid": "<collection>", "outcome": "error", "longrepr": e}
                      for e in collector_errors],
            note=note,
        )

    score = passed / total

    failures: list[dict] = []
    for test in data.get("tests", []):
        if test.get("outcome") in ("failed", "error"):
            failures.append({
                "nodeid": test.get("nodeid"),
                "outcome": test.get("outcome"),
                "longrepr": (test.get("call") or {}).get("longrepr", "")[:1000],
            })
    return CorrectnessScore(
        score=score,
        passed=passed,
        total=total,
        failures=failures,
    )


def score(task_dir: Path, wt: Path, run_dir: Path) -> CorrectnessScore:
    """Run the task's hidden oracle suite against the agent's working tree."""
    oracle_tests = _stage_oracle(task_dir, run_dir)
    report_path = _invoke_pytest(oracle_tests, wt, run_dir)
    return _parse_report(report_path)

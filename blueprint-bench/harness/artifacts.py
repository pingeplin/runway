from __future__ import annotations

import shutil
from pathlib import Path

from harness.sandbox import capture_diff, changed_paths


_BLUEPRINT_ARTIFACT_DIRS = ("specs", "plans")


def _filter_code_files(paths: list[str]) -> list[str]:
    """Drop blueprint artifact paths (specs/, plans/) from a path list.

    Used to distinguish "agent produced code" from "agent produced only a
    spec/plan and stopped." A cell with no code files touched is a clear
    workflow failure, not a 0/N correctness result.
    """
    non_code_prefixes = tuple(f"{d}/" for d in _BLUEPRINT_ARTIFACT_DIRS)
    return [p for p in paths if not p.startswith(non_code_prefixes)]


def collect(wt: Path, artifacts_dir: Path, baseline: str | None = None) -> dict[str, str | list[str]]:
    """Snapshot the agent's outputs into `artifacts_dir`.

    Captures the unified diff and copies the plugin-convention artifact dirs
    (specs/, plans/) if present. Returns a summary describing what was
    captured for inclusion in the per-run report. `baseline` is the starter
    commit SHA — pass Sandbox.starter_sha so /commit-driven HEAD advances
    don't mask the captured diff.

    `code_files_touched` lists paths the agent changed or added that aren't
    blueprint artifacts. Untracked files are included — an agent who wrote
    code but never ran /commit still counts as having produced code (pytest
    can still import it).
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    captured: dict[str, str | list[str]] = {}

    diff = capture_diff(wt, baseline=baseline)
    diff_path = artifacts_dir / "diff.patch"
    diff_path.write_text(diff)
    captured["diff_path"] = str(diff_path)
    captured["diff_bytes"] = str(len(diff.encode()))
    captured["code_files_touched"] = _filter_code_files(changed_paths(wt, baseline=baseline))

    copied_dirs: list[str] = []
    for name in _BLUEPRINT_ARTIFACT_DIRS:
        src = wt / name
        if src.is_dir():
            dst = artifacts_dir / name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            copied_dirs.append(name)
    captured["plugin_dirs"] = copied_dirs

    return captured

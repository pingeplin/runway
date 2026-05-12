from __future__ import annotations

import shutil
from pathlib import Path

from harness.sandbox import capture_diff


_BLUEPRINT_ARTIFACT_DIRS = ("specs", "plans")


def collect(wt: Path, artifacts_dir: Path, baseline: str | None = None) -> dict[str, str | list[str]]:
    """Snapshot the agent's outputs into `artifacts_dir`.

    Captures the unified diff and copies the plugin-convention artifact dirs
    (specs/, plans/) if present. Returns a summary describing what was
    captured for inclusion in the per-run report. `baseline` is the starter
    commit SHA — pass Sandbox.starter_sha so /commit-driven HEAD advances
    don't mask the captured diff.
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    captured: dict[str, str | list[str]] = {}

    diff = capture_diff(wt, baseline=baseline)
    diff_path = artifacts_dir / "diff.patch"
    diff_path.write_text(diff)
    captured["diff_path"] = str(diff_path)
    captured["diff_bytes"] = str(len(diff.encode()))

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

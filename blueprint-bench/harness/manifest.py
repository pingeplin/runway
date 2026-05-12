from __future__ import annotations

import datetime as dt
import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Manifest:
    run_id: str
    started_at: str
    plugin_sha: str
    plugin_version: str
    harness_sha: str
    args: dict = field(default_factory=dict)

    def write(self, dest: Path) -> None:
        dest.write_text(json.dumps(asdict(self), indent=2))


def _git_head(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _plugin_version(plugin_dir: Path) -> str:
    manifest = plugin_dir / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        return "unknown"
    try:
        data = json.loads(manifest.read_text())
        return str(data.get("version", "unknown"))
    except json.JSONDecodeError:
        return "unknown"


def build(
    run_id: str,
    plugin_dir: Path,
    harness_dir: Path,
    args: dict,
) -> Manifest:
    return Manifest(
        run_id=run_id,
        started_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        plugin_sha=_git_head(plugin_dir),
        plugin_version=_plugin_version(plugin_dir),
        harness_sha=_git_head(harness_dir),
        args=args,
    )

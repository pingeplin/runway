from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sandbox:
    """Per-run isolated working tree.

    `wt` is the agent's CWD during the invocation. Only the task's `starter/`
    contents land here — `oracle/` is never copied in. `run_dir` is the parent
    where the harness stages scorer inputs and artifacts as siblings of `wt`.
    `starter_sha` is the SHA of the baseline commit made at build time; diffs
    are computed against it so that agent-driven `/commit` calls don't erase
    the captured diff by advancing HEAD.
    """

    run_dir: Path
    wt: Path
    task_id: str
    starter_sha: str

    @property
    def oracle_tests_stage(self) -> Path:
        return self.run_dir / "oracle_tests"

    @property
    def artifacts_dir(self) -> Path:
        return self.run_dir / "artifacts"


def build(task_dir: Path, run_dir: Path) -> Sandbox:
    """Materialize a fresh working tree containing only `task_dir/starter/`.

    Initializes a git repo inside `wt` so blueprint's `/commit` step has a
    baseline diff to work against.
    """
    starter = task_dir / "starter"
    if not starter.is_dir():
        raise FileNotFoundError(f"task is missing starter/: {task_dir}")

    run_dir.mkdir(parents=True, exist_ok=True)
    wt = run_dir / "wt"
    if wt.exists():
        shutil.rmtree(wt)
    shutil.copytree(starter, wt)

    starter_sha = _git_init(wt)

    (run_dir / "artifacts").mkdir(exist_ok=True)
    return Sandbox(run_dir=run_dir, wt=wt, task_id=task_dir.name, starter_sha=starter_sha)


def _git_init(wt: Path) -> str:
    env_overrides = {
        "GIT_AUTHOR_NAME": "blueprint-bench",
        "GIT_AUTHOR_EMAIL": "bench@blueprint.local",
        "GIT_COMMITTER_NAME": "blueprint-bench",
        "GIT_COMMITTER_EMAIL": "bench@blueprint.local",
    }
    import os
    env = {**os.environ, **env_overrides}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=wt, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True, env=env)
    subprocess.run(
        ["git", "commit", "-q", "-m", "starter"],
        cwd=wt,
        check=True,
        env=env,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=wt,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()
    return sha


def capture_diff(wt: Path, baseline: str | None = None) -> str:
    """Return the unified diff of `wt` vs. its baseline starter commit.

    The baseline argument is the SHA of the starter commit stashed on the
    Sandbox at build time. We diff against it (not against HEAD) because the
    /tdd workflow ends with `/commit`, which advances HEAD inside wt/ —
    `git diff HEAD` would then see zero changes even though the agent
    rewrote source files.
    """
    if baseline is None:
        # Fall back to the root commit so older callers still see something
        # sensible. New callers should pass Sandbox.starter_sha explicitly.
        baseline = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            cwd=wt,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip().splitlines()[0]
    result = subprocess.run(
        ["git", "diff", baseline],
        cwd=wt,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout

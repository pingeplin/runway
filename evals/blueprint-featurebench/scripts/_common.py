"""Shared helpers for the blueprint x FeatureBench eval stages."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Any

EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = EVAL_ROOT / "results"
TASKS_PATH = RESULTS_DIR / "tasks.json"
RUNS_PATH = RESULTS_DIR / "runs.json"
SPECS_DIR = RESULTS_DIR / "specs"

# Arm B treatment: the spec is appended to the original statement, never
# substituted for it, and carries no precedence clause.
SPEC_SEPARATOR = "\n\n---\n\n## Implementation Spec\n\n"

STATUS_OK = "spec_ok"
STATUS_FAILED = "spec_failed"


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def mask_reference_solution(workspace, row):
    """Strip the reference implementation from an extracted /testbed.

    fb infer does not hand the agent /testbed as-is: it applies the dataset's
    `patch` (a mask that removes the feature) and deletes the FAIL_TO_PASS
    test files (featurebench/infer/runtime.py _initialize_level1). Any stage
    that shows the codebase to a model MUST reproduce this, or the model sees
    the oracle. Returns {"mask_applied": bool|None, "f2p_deleted": int,
    "mask_error": str?}; mask_applied is None when the row carries no patch.
    """
    import json as _json
    import subprocess as _sp

    info = {"mask_applied": None, "f2p_deleted": 0}
    mask = row.get("patch") or ""
    if mask.strip():
        mask_file = workspace.parent / f"{workspace.name}.mask.patch"
        mask_file.write_text(mask if mask.endswith("\n") else mask + "\n", encoding="utf-8")
        proc = _sp.run(
            ["git", "apply", "--whitespace=fix", str(mask_file)],
            cwd=workspace, capture_output=True, text=True,
        )
        mask_file.unlink(missing_ok=True)
        info["mask_applied"] = proc.returncode == 0
        if proc.returncode != 0:
            info["mask_error"] = (proc.stderr or proc.stdout or "").strip()[-300:]

    raw = row.get("FAIL_TO_PASS") or []
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except _json.JSONDecodeError:
            raw = [raw]
    if isinstance(raw, str):
        raw = [raw]
    for rel in sorted({str(t).split("::")[0] for t in raw if str(t).strip()}):
        target = workspace / rel
        if target.is_file():
            target.unlink()
            info["f2p_deleted"] += 1
    return info


def load_script_module(filename: str):
    """Import a sibling stage script whose name is not a valid identifier.

    Stage files are named `NN_thing.py`, so `import 02_make_dataset` is a
    syntax error. Later stages reuse earlier stages' helpers through this
    instead of duplicating them.
    """
    import importlib.util

    path = Path(__file__).resolve().parent / filename
    if not path.exists():
        die(f"stage script not found: {path}")
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        die(f"could not load stage script: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(path.stem, module)
    spec.loader.exec_module(module)
    return module


def add_config_arg(parser) -> None:
    parser.add_argument(
        "--config",
        default=None,
        help="Path to harness config.toml (default: config.toml next to the evals dir root)",
    )


def load_config(path: str | None) -> dict[str, Any]:
    cfg_path = Path(path).expanduser() if path else EVAL_ROOT / "config.toml"
    if not cfg_path.is_absolute():
        cfg_path = (Path.cwd() / cfg_path).resolve()
    if not cfg_path.exists():
        die(f"config not found: {cfg_path}\n       copy {EVAL_ROOT / 'config.example.toml'} to config.toml")
    with open(cfg_path, "rb") as f:
        return tomllib.load(f)


def resolve_path(value: str) -> Path:
    """Resolve a config path relative to the evals dir root."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else (EVAL_ROOT / p).resolve()


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    tmp.replace(path)


def read_tasks() -> dict[str, Any]:
    if not TASKS_PATH.exists():
        die(f"{TASKS_PATH} not found — run scripts/01_make_specs.py first")
    return read_json(TASKS_PATH)


def write_tasks(tasks: dict[str, Any]) -> None:
    write_json(TASKS_PATH, tasks)


def spec_ok_ids(tasks: dict[str, Any]) -> list[str]:
    return [t["id"] for t in tasks.get("tasks", []) if t.get("status") == STATUS_OK]


def read_runs() -> dict[str, Any]:
    return read_json(RUNS_PATH) if RUNS_PATH.exists() else {}


def update_run(arm: str, data: dict[str, Any]) -> dict[str, Any]:
    runs = read_runs()
    runs.setdefault(arm, {}).update(data)
    write_json(RUNS_PATH, runs)
    return runs


def load_split_rows(dataset: str, split: str, mock_dataset: str | None) -> list[dict[str, Any]]:
    """Load dataset rows, either from a JSONL fallback or from `datasets`.

    The JSONL path exists so the harness can be exercised offline (and by users
    behind a firewall that blocks HuggingFace).
    """
    if mock_dataset:
        rows = []
        with open(mock_dataset, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    try:
        from datasets import load_dataset
    except ImportError:
        die("the `datasets` library is required: pip install datasets (or pass --mock-dataset <jsonl>)")

    ds = load_dataset(dataset, split=split)
    return [dict(row) for row in ds]

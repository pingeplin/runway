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

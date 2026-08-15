#!/usr/bin/env python3
"""Stage 04 — score both arms with `fb eval` against the OFFICIAL dataset.

Predictions carry only instance_id / model_patch, so Arm B's rewritten
problem_statement cannot reach the scorer. `fb eval` writes its summary to
<predictions dir>/report.json and one report per instance under
<predictions dir>/eval_outputs/<instance_id>/attempt-<n>/report.json.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

from _common import (
    add_config_arg,
    die,
    load_config,
    read_runs,
    read_tasks,
    resolve_path,
    spec_ok_ids,
    update_run,
)


def build_cmd(predictions: Path, dataset: str, split: str, task_ids: list[str], fb_config: Path, n_concurrent: int) -> list[str]:
    return [
        "fb", "eval",
        "--config-path", str(fb_config),
        "--predictions-path", str(predictions),
        "--dataset", dataset,
        "--split", split,
        "--n-concurrent", str(n_concurrent),
        "--task-id", *task_ids,
    ]


def run_arm(arm: str, cfg: dict, fb_config: Path, task_ids: list[str], dry_run: bool) -> int:
    runs = read_runs()
    entry = runs.get(arm) or {}
    predictions = entry.get("output_jsonl")
    if not predictions:
        die(f"no output.jsonl recorded for arm {arm} in results/runs.json — run stage 03 first")
    predictions = Path(predictions)
    if not dry_run and not predictions.exists():
        die(f"predictions file missing: {predictions}")

    eval_cfg = cfg.get("eval", {})
    cmd = build_cmd(
        predictions,
        eval_cfg.get("dataset", ""),
        eval_cfg.get("split", "lite"),
        task_ids,
        fb_config,
        int(eval_cfg.get("n_concurrent", 4)),
    )

    if dry_run:
        print(f"[arm {arm}] {shlex.join(cmd)}")
        return 0

    print(f"[arm {arm}] {shlex.join(cmd)}", flush=True)
    proc = subprocess.run(cmd)
    report_path = predictions.parent / "report.json"

    update_run(arm, {
        "eval_cmd": cmd,
        "eval_returncode": proc.returncode,
        "report_json": str(report_path),
        "eval_outputs_dir": str(predictions.parent / "eval_outputs"),
    })

    if proc.returncode != 0:
        print(f"error: fb eval for arm {arm} exited {proc.returncode}")
        return proc.returncode
    if not report_path.exists():
        print(f"error: expected report at {report_path}")
        return 1
    print(f"[arm {arm}] report: {report_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_arg(parser)
    parser.add_argument("--arm", choices=["A", "B", "both"], default="both")
    parser.add_argument("--dry-run", action="store_true", help="Print the exact commands without running them")
    args = parser.parse_args()

    cfg = load_config(args.config)
    fb_config = resolve_path(str(cfg.get("infer", {}).get("fb_config_path", "fb_config.toml")))
    if not args.dry_run and not fb_config.exists():
        die(f"fb config not found: {fb_config}")

    task_ids = sorted(spec_ok_ids(read_tasks()))
    if not task_ids:
        die("no spec_ok tasks — run stage 01 first")

    arms = ["A", "B"] if args.arm == "both" else [args.arm]
    for arm in arms:
        rc = run_arm(arm, cfg, fb_config, task_ids, args.dry_run)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

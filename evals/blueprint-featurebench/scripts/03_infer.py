#!/usr/bin/env python3
"""Stage 03 — run `fb infer` once per arm over the same task ids.

Arm A reads the official dataset; Arm B reads the locally rewritten copy from
stage 02. Agent, model, task-id list and fb config are identical — the only
difference between the arms is the problem_statement text.

`fb infer` writes to <output-dir>/<YYYY-MM-DD__HH-MM-SS>/output.jsonl, so the
run directory is discovered after the process exits and recorded in
results/runs.json.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

from _common import (
    RESULTS_DIR,
    add_config_arg,
    die,
    load_config,
    read_tasks,
    resolve_path,
    spec_ok_ids,
    update_run,
)

ARM_B_DATASET = RESULTS_DIR / "dataset_arm_b"


def build_cmd(dataset: str, split: str, task_ids: list[str], out_dir: Path, cfg: dict) -> list[str]:
    infer_cfg = cfg.get("infer", {})
    return [
        "fb", "infer",
        "--config-path", str(cfg["_fb_config_path"]),
        "--agent", "claude_code",
        "--model", str(infer_cfg.get("model", "")),
        "--dataset", dataset,
        "--split", split,
        "--output-dir", str(out_dir),
        "--n-concurrent", str(int(infer_cfg.get("n_concurrent", 1))),
        "--timeout", str(int(infer_cfg.get("timeout_seconds", 3600))),
        "--task-id", *task_ids,
    ]


def newest_output_jsonl(out_dir: Path) -> Path | None:
    candidates = sorted(out_dir.glob("*/output.jsonl"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def run_arm(arm: str, cfg: dict, task_ids: list[str], dry_run: bool) -> int:
    eval_cfg = cfg.get("eval", {})
    split = eval_cfg.get("split", "lite")
    if arm == "A":
        dataset = eval_cfg.get("dataset", "")
    else:
        if not (ARM_B_DATASET / "README.md").exists():
            die(f"Arm B dataset missing at {ARM_B_DATASET} — run stage 02 first")
        dataset = str(ARM_B_DATASET)

    out_dir = RESULTS_DIR / f"infer_arm_{arm.lower()}"
    cmd = build_cmd(dataset, split, task_ids, out_dir, cfg)

    if dry_run:
        print(f"[arm {arm}] {shlex.join(cmd)}")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[arm {arm}] {shlex.join(cmd)}", flush=True)
    proc = subprocess.run(cmd)
    output_jsonl = newest_output_jsonl(out_dir)

    update_run(arm, {
        "arm": arm,
        "dataset": dataset,
        "split": split,
        "task_ids": task_ids,
        "infer_cmd": cmd,
        "infer_returncode": proc.returncode,
        "output_jsonl": str(output_jsonl) if output_jsonl else None,
    })

    if proc.returncode != 0:
        print(f"error: fb infer for arm {arm} exited {proc.returncode}")
        return proc.returncode
    if output_jsonl is None:
        print(f"error: no output.jsonl found under {out_dir}")
        return 1
    print(f"[arm {arm}] predictions: {output_jsonl}")
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
        die(f"fb config not found: {fb_config} (copy fb_config.example.toml)")
    cfg["_fb_config_path"] = fb_config

    task_ids = spec_ok_ids(read_tasks())
    if not task_ids:
        die("no spec_ok tasks — run stage 01 (and check results/specs/*.meta.json)")
    task_ids.sort()

    arms = ["A", "B"] if args.arm == "both" else [args.arm]
    for arm in arms:
        rc = run_arm(arm, cfg, task_ids, args.dry_run)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stage 01b — rebuild stage-01 workspaces without re-running `/spec`.

Stage 01 short-circuits on a cached spec (`01_make_specs.py` run_one: meta
exists + ok + the .md is there -> skip), and the short-circuit happens BEFORE
`process_task`, so a cached run never extracts a testbed. Stage 06 needs those
workspaces: it copies one per task as the referee's scratch tree.

This stage does exactly what `process_task` does minus the `claude -p` call —
`extract_testbed` then `mask_reference_solution` — so a panel whose specs are
restored from an archived report can reach stage 06 for $0 of model spend.

    uv run --with datasets python3 scripts/01b_rebuild_workspaces.py \
        --task-ids-file panel.txt

Refuses to write a workspace whose mask did not apply: an unmasked tree carries
the reference implementation and the deleted FAIL_TO_PASS tests in its git
history, which is the leak this panel exists to have fixed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    RESULTS_DIR,
    add_config_arg,
    die,
    load_config,
    load_script_module,
    load_split_rows,
    mask_reference_solution,
    write_json,
)

WORKSPACES_DIR = RESULTS_DIR / "workspaces"


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    add_config_arg(parser)
    parser.add_argument("--task-ids-file", required=True)
    parser.add_argument("--mock-testbed", default=None)
    parser.add_argument("--mock-dataset", default=None)
    parser.add_argument("--force", action="store_true", help="Rebuild workspaces that already exist")
    args = parser.parse_args()

    cfg = load_config(args.config)
    eval_cfg = cfg.get("eval", {})
    stage01 = load_script_module("01_make_specs.py")

    wanted = [
        line.strip()
        for line in Path(args.task_ids_file).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not wanted:
        die(f"no task ids in {args.task_ids_file}")

    rows = load_split_rows(
        eval_cfg.get("dataset", "LiberCoders/FeatureBench"),
        eval_cfg.get("split", "fast"),
        args.mock_dataset,
    )
    by_id = {r["instance_id"]: r for r in rows}
    missing = [t for t in wanted if t not in by_id]
    if missing:
        die(f"task ids not in split: {', '.join(missing)}")

    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, dict] = {}
    failed: list[str] = []

    for idx, task_id in enumerate(wanted, 1):
        row = by_id[task_id]
        dest = WORKSPACES_DIR / task_id

        if dest.exists() and not args.force:
            log(f"[{idx}/{len(wanted)}] {task_id}: workspace exists, skipping")
            continue
        if dest.exists():
            shutil.rmtree(dest)

        log(f"[{idx}/{len(wanted)}] {task_id}: extracting testbed")
        try:
            stage01.extract_testbed(row.get("image_name", ""), dest, args.mock_testbed)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()[-400:]
            log(f"[{idx}/{len(wanted)}] {task_id}: FAILED extraction — {stderr}")
            report[task_id] = {"ok": False, "error": f"extraction failed: {stderr}"}
            failed.append(task_id)
            continue

        info = mask_reference_solution(dest, row)
        ok = bool(info.get("mask_applied")) and bool(info.get("git_reinit"))
        report[task_id] = {"ok": ok, **info}

        if not ok:
            # An unmasked or history-carrying tree is an oracle leak, not a
            # degraded cell. Remove it so no later stage can pick it up.
            shutil.rmtree(dest, ignore_errors=True)
            log(
                f"[{idx}/{len(wanted)}] {task_id}: FAILED mask "
                f"(mask_applied={info.get('mask_applied')} "
                f"git_reinit={info.get('git_reinit')}) — workspace removed"
            )
            failed.append(task_id)
            continue

        log(
            f"[{idx}/{len(wanted)}] {task_id}: ok "
            f"(f2p_deleted={info.get('f2p_deleted')}, git_reinit={info.get('git_reinit')})"
        )

    write_json(RESULTS_DIR / "workspaces_rebuild.json", report)
    if failed:
        log(f"stage 01b: {len(failed)} task(s) FAILED — {', '.join(failed)}")
        return 1
    log(f"stage 01b: {len(wanted)} workspace(s) ready under {WORKSPACES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

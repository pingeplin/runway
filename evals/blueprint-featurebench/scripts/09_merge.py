#!/usr/bin/env python3
"""Stage 09 — merge per-batch results into one panel.

The scale run is executed one container image at a time (disk cannot hold
more than a couple of FeatureBench images), so each batch overwrites
`results/tasks.json` and `results/runs.json`. `run_batch.sh` archives both
under `results/batches/<batch>/` before the next batch clobbers them; this
stage stitches those archives back into a single panel.

Outputs (default `results/merged/`) are shaped so the *unmodified* report
stages consume them:

  tasks.json          -> 05 --tasks
  report_<ARM>.json   -> 05 --report-a/--report-b, 05b --report-b/-c/-c0
                         (per-instance keyed: 05's `looks_per_instance` path)
  output_<ARM>.jsonl  -> predictions referenced by merged runs.json
  runs.json           -> 07 --runs (all mutation cells already cached)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from _common import (
    RESULTS_DIR,
    STATUS_OK,
    die,
    read_json,
    write_json,
)


def log(msg: str) -> None:
    print(msg, flush=True)

BATCHES_DIR = RESULTS_DIR / "batches"
MERGED_DIR = RESULTS_DIR / "merged"


def looks_per_instance(payload: Any) -> bool:
    return isinstance(payload, dict) and any(
        isinstance(v, dict) and "resolved" in v for v in payload.values()
    )


def load_arm_results(report_path: Path) -> dict[str, dict[str, Any]]:
    """{instance_id: {resolved, pass_rate}} from an fb eval report.

    Mirrors 05_report.load_arm_results: the top-level report.json is keyed by
    attempt, not instance, so fall back to the per-instance siblings.
    """
    if not report_path.exists():
        log(f"  warn: report missing, skipping: {report_path}")
        return {}
    try:
        payload = read_json(report_path)
    except (OSError, json.JSONDecodeError) as exc:
        log(f"  warn: unreadable report {report_path}: {exc}")
        return {}

    if looks_per_instance(payload):
        return {
            iid: {
                "resolved": bool(entry.get("resolved", False)),
                "pass_rate": float(entry.get("pass_rate", 0.0) or 0.0),
            }
            for iid, entry in payload.items()
            if isinstance(entry, dict)
        }

    eval_outputs = report_path.parent / "eval_outputs"
    if not eval_outputs.is_dir():
        log(f"  warn: aggregate report with no eval_outputs: {report_path}")
        return {}

    results: dict[str, dict[str, Any]] = {}
    for per_instance in sorted(eval_outputs.glob("*/attempt-*/report.json")):
        try:
            data = read_json(per_instance)
        except (OSError, json.JSONDecodeError):
            continue
        for iid, entry in (data or {}).items():
            if not isinstance(entry, dict):
                continue
            record = {
                "resolved": bool(entry.get("resolved", False)),
                "pass_rate": float(entry.get("pass_rate", 0.0) or 0.0),
            }
            prior = results.get(iid)
            if prior is None or (record["resolved"] and not prior["resolved"]):
                results[iid] = record
    return results


def read_predictions(jsonl: Path) -> dict[str, str]:
    preds: dict[str, str] = {}
    if not jsonl.exists():
        log(f"  warn: predictions missing: {jsonl}")
        return preds
    with jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            iid = row.get("instance_id")
            if iid:
                preds[iid] = row.get("model_patch") or ""
    return preds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batches", default=None, help=f"Batch archive dir (default {BATCHES_DIR})")
    parser.add_argument("--out", default=None, help=f"Merged output dir (default {MERGED_DIR})")
    parser.add_argument("--batch", action="append", default=None,
                        help="Restrict to this batch name (repeatable)")
    args = parser.parse_args()

    batches_dir = Path(args.batches).resolve() if args.batches else BATCHES_DIR
    out_dir = Path(args.out).resolve() if args.out else MERGED_DIR
    if not batches_dir.is_dir():
        die(f"no batch archive dir: {batches_dir} — run scripts/run_batch.sh first")

    names = sorted(p.name for p in batches_dir.iterdir() if p.is_dir())
    if args.batch:
        wanted = set(args.batch)
        missing = wanted - set(names)
        if missing:
            die(f"batch(es) not found in {batches_dir}: {', '.join(sorted(missing))}")
        names = [n for n in names if n in wanted]
    if not names:
        die(f"no batches under {batches_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)

    merged_tasks: list[dict[str, Any]] = []
    seen_tasks: set[str] = set()
    dataset = split = ""
    # arm -> {instance_id: record}
    arm_results: dict[str, dict[str, dict[str, Any]]] = {}
    arm_preds: dict[str, dict[str, str]] = {}
    arm_meta: dict[str, dict[str, Any]] = {}

    for name in names:
        bdir = batches_dir / name
        tasks_path, runs_path = bdir / "tasks.json", bdir / "runs.json"
        if not tasks_path.exists() or not runs_path.exists():
            log(f"batch {name}: missing tasks.json or runs.json, skipping")
            continue
        log(f"batch {name}:")

        tasks = read_json(tasks_path)
        dataset = dataset or tasks.get("dataset", "")
        split = split or tasks.get("split", "")
        n_ok = 0
        for t in tasks.get("tasks", []):
            tid = t.get("id")
            if not tid or tid in seen_tasks:
                continue
            seen_tasks.add(tid)
            merged_tasks.append(t)
            n_ok += 1 if t.get("status") == STATUS_OK else 0
        log(f"  tasks: {len(tasks.get('tasks', []))} ({n_ok} {STATUS_OK})")

        runs = read_json(runs_path)
        for arm, entry in runs.items():
            if not isinstance(entry, dict):
                continue
            report_json = entry.get("report_json")
            if report_json:
                got = load_arm_results(Path(report_json))
                arm_results.setdefault(arm, {}).update(got)
                log(f"  arm {arm}: {len(got)} scored instance(s)")
            jsonl = entry.get("output_jsonl")
            if jsonl:
                arm_preds.setdefault(arm, {}).update(read_predictions(Path(jsonl)))
            meta = arm_meta.setdefault(arm, {"arm": arm, "dataset": entry.get("dataset", ""),
                                             "split": entry.get("split", ""), "task_ids": [],
                                             "source_run_dirs": [], "eval_outputs_dirs": []})
            meta["task_ids"] = sorted(set(meta["task_ids"]) | set(entry.get("task_ids") or []))
            # The merged jsonl has no sibling run_outputs/ or eval_outputs/, so
            # keep pointers to the real per-batch run directories. Stage 10
            # reads the agent transcripts from them; stage 08 needs eval outputs.
            if jsonl:
                meta["source_run_dirs"].append(str(Path(jsonl).parent))
            eo = entry.get("eval_outputs_dir")
            if eo:
                meta["eval_outputs_dirs"].append(eo)

    if not merged_tasks:
        die("no tasks merged — check the batch archives")

    merged_tasks.sort(key=lambda t: t.get("id", ""))
    write_json(out_dir / "tasks.json",
               {"dataset": dataset, "split": split, "tasks": merged_tasks})

    merged_runs: dict[str, Any] = {}
    for arm in sorted(set(arm_results) | set(arm_preds)):
        report_path = out_dir / f"report_{arm}.json"
        write_json(report_path, arm_results.get(arm, {}))

        preds = arm_preds.get(arm, {})
        jsonl_path = out_dir / f"output_{arm}.jsonl"
        with jsonl_path.open("w", encoding="utf-8") as fh:
            for iid in sorted(preds):
                fh.write(json.dumps({"instance_id": iid, "model_patch": preds[iid]}) + "\n")

        entry = dict(arm_meta.get(arm, {"arm": arm}))
        entry.update({
            "output_jsonl": str(jsonl_path),
            "report_json": str(report_path),
            "merged_from": names,
        })
        # Single-batch panels can still drive stage 08, which wants one dir.
        eo_dirs = entry.get("eval_outputs_dirs") or []
        if len(eo_dirs) == 1:
            entry["eval_outputs_dir"] = eo_dirs[0]
        merged_runs[arm] = entry
        resolved = sum(1 for r in arm_results.get(arm, {}).values() if r.get("resolved"))
        log(f"arm {arm}: {len(arm_results.get(arm, {}))} scored, {resolved} resolved, "
            f"{len(preds)} prediction(s)")

    write_json(out_dir / "runs.json", merged_runs)

    n_ok_total = sum(1 for t in merged_tasks if t.get("status") == STATUS_OK)
    log(f"\nstage 09 ok: {len(names)} batch(es) -> {out_dir}")
    log(f"  {len(merged_tasks)} task(s), {n_ok_total} {STATUS_OK}, arms: {', '.join(sorted(merged_runs))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

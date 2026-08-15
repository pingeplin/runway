#!/usr/bin/env python3
"""Stage 01 — produce a blueprint spec per pilot task, headlessly.

For each task: extract its codebase from the task's own docker image
(`docker create` + `docker cp :/testbed`), run `claude -p` with the blueprint
plugin in that workspace, and save the resulting spec plus cost/duration
metadata. A task whose spec stage fails is recorded and excluded from both
arms — the paired design needs both cells.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from _common import (
    EVAL_ROOT,
    RESULTS_DIR,
    SPECS_DIR,
    STATUS_FAILED,
    STATUS_OK,
    add_config_arg,
    die,
    load_config,
    load_split_rows,
    read_json,
    write_json,
    write_tasks,
)

PROMPT_TEMPLATE = EVAL_ROOT / "prompts" / "spec_headless.md"
WORKSPACES_DIR = RESULTS_DIR / "workspaces"
SPEC_PATH_RE = re.compile(r"^\s*SPEC_PATH:\s*(.+?)\s*$", re.MULTILINE)


def log(msg: str) -> None:
    print(msg, flush=True)


def extract_testbed(image: str, workspace: Path, mock_testbed: str | None) -> None:
    """Materialise the task's /testbed into `workspace` (which must not exist)."""
    workspace.parent.mkdir(parents=True, exist_ok=True)
    if mock_testbed:
        shutil.copytree(mock_testbed, workspace)
        return

    cid = subprocess.run(
        ["docker", "create", image],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    try:
        # docker cp with a non-existent DEST copies the *contents* of /testbed
        # into DEST, so the workspace root is the repo root (already a git repo).
        subprocess.run(
            ["docker", "cp", f"{cid}:/testbed", str(workspace)],
            capture_output=True, text=True, check=True,
        )
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True, text=True)


def newest_spec_file(workspace: Path) -> Path | None:
    specs = sorted(
        (workspace / ".blueprint" / "specs").glob("**/*.md"),
        key=lambda p: p.stat().st_mtime,
    )
    return specs[-1] if specs else None


def locate_spec(workspace: Path, result_text: str) -> tuple[Path | None, str]:
    """Find the produced spec: SPEC_PATH marker first, newest .md as fallback."""
    matches = SPEC_PATH_RE.findall(result_text or "")
    if matches:
        raw = matches[-1].strip().strip("`").strip()
        candidate = Path(raw)
        candidate = candidate if candidate.is_absolute() else workspace / candidate
        if candidate.is_file():
            return candidate, "marker"
    fallback = newest_spec_file(workspace)
    if fallback is not None:
        return fallback, "fallback_newest"
    return None, "not_found"


def run_claude(
    claude_cmd: str,
    prompt: str,
    workspace: Path,
    model: str,
    claude_args: list[str],
    timeout_s: int,
) -> tuple[dict[str, Any], str | None]:
    """Run one headless claude pass. Returns (parsed_payload, error)."""
    argv = [claude_cmd, "-p", prompt, "--output-format", "json", *claude_args, "--model", model]
    try:
        proc = subprocess.run(
            argv, cwd=workspace, capture_output=True, text=True, timeout=timeout_s
        )
    except subprocess.TimeoutExpired:
        return {}, f"claude timed out after {timeout_s}s"
    except FileNotFoundError:
        return {}, f"claude command not found: {claude_cmd}"

    payload: dict[str, Any] = {"returncode": proc.returncode}
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        return payload, f"claude stdout was not JSON (rc={proc.returncode}): {tail}"

    # stream-json style output can arrive as a list of events; take the last
    # object that carries a result field.
    if isinstance(parsed, list):
        parsed = next((e for e in reversed(parsed) if isinstance(e, dict) and "result" in e), {})
    if not isinstance(parsed, dict):
        return payload, "claude JSON payload had an unexpected shape"

    payload.update(parsed)
    if proc.returncode != 0:
        return payload, f"claude exited {proc.returncode}"
    return payload, None


def process_task(
    row: dict[str, Any],
    args: argparse.Namespace,
    spec_cfg: dict[str, Any],
    template: str,
) -> dict[str, Any]:
    """Run the spec stage for one task and write its meta. Returns the meta."""
    task_id = row["instance_id"]
    workspace = WORKSPACES_DIR / task_id
    meta: dict[str, Any] = {"instance_id": task_id, "image_name": row.get("image_name", "")}

    if workspace.exists():
        shutil.rmtree(workspace)
    try:
        extract_testbed(row.get("image_name", ""), workspace, args.mock_testbed)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()[-500:]
        meta.update(ok=False, error=f"testbed extraction failed: {stderr}")
        return meta

    prompt = template.replace("{problem_statement}", row.get("problem_statement", ""))
    started = time.time()
    payload, error = run_claude(
        claude_cmd=args.claude_cmd,
        prompt=prompt,
        workspace=workspace,
        model=spec_cfg.get("model", "claude-sonnet-4-5"),
        claude_args=list(spec_cfg.get("claude_args", [])),
        timeout_s=int(spec_cfg.get("timeout_seconds", 900)),
    )
    wall_seconds = round(time.time() - started, 2)

    meta.update(
        cost_usd=payload.get("total_cost_usd"),
        duration_ms=payload.get("duration_ms"),
        duration_api_ms=payload.get("duration_api_ms"),
        wall_seconds=wall_seconds,
        num_turns=payload.get("num_turns"),
        usage=payload.get("usage"),
        returncode=payload.get("returncode"),
    )
    if error:
        meta.update(ok=False, error=error)
        return meta

    spec_file, how = locate_spec(workspace, payload.get("result") or "")
    if spec_file is None:
        meta.update(ok=False, error="no spec file produced under .blueprint/specs/")
        return meta

    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    dest = SPECS_DIR / f"{task_id}.md"
    shutil.copyfile(spec_file, dest)
    meta.update(
        ok=True,
        error=None,
        spec_located_by=how,
        spec_source=str(spec_file.relative_to(workspace)),
        spec_path=str(dest.relative_to(EVAL_ROOT)),
        spec_chars=dest.stat().st_size,
    )
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_arg(parser)
    parser.add_argument("--limit", type=int, default=None, help="Override [eval].limit")
    parser.add_argument("--task-ids-file", default=None, help="Newline-separated instance_ids to use instead of the first N")
    parser.add_argument("--force", action="store_true", help="Redo tasks whose spec already succeeded")
    parser.add_argument("--parallel", type=int, default=1, help="Concurrent spec workers (claude -p sessions)")
    parser.add_argument("--claude-cmd", default="claude", help="Path to the claude binary (for smoke tests)")
    parser.add_argument("--mock-testbed", default=None, help="Copy this dir instead of docker cp (for smoke tests)")
    parser.add_argument("--mock-dataset", default=None, help="Read rows from this JSONL instead of HuggingFace")
    args = parser.parse_args()

    cfg = load_config(args.config)
    eval_cfg = cfg.get("eval", {})
    spec_cfg = cfg.get("spec", {})
    split = eval_cfg.get("split", "lite")

    if not PROMPT_TEMPLATE.exists():
        die(f"prompt template missing: {PROMPT_TEMPLATE}")
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")

    rows = load_split_rows(eval_cfg.get("dataset", ""), split, args.mock_dataset)
    if not rows:
        die("dataset split loaded zero rows")
    rows.sort(key=lambda r: r["instance_id"])

    if args.task_ids_file:
        wanted = [
            line.strip()
            for line in Path(args.task_ids_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        by_id = {r["instance_id"]: r for r in rows}
        missing = [i for i in wanted if i not in by_id]
        if missing:
            die(f"task ids not present in split '{split}': {', '.join(missing)}")
        rows = [by_id[i] for i in wanted]
    else:
        limit = args.limit if args.limit is not None else int(eval_cfg.get("limit", 0))
        if limit:
            rows = rows[:limit]

    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    tasks = {
        "dataset": eval_cfg.get("dataset", ""),
        "split": split,
        "tasks": [
            {"id": r["instance_id"], "image_name": r.get("image_name", ""), "status": "pending"}
            for r in rows
        ],
    }
    write_tasks(tasks)

    log(f"stage 01: {len(rows)} task(s) from {tasks['dataset']}:{split}")
    state_lock = threading.Lock()
    n_ok = 0

    def run_one(idx: int, row: dict[str, Any]) -> bool:
        task_id = row["instance_id"]
        meta_path = SPECS_DIR / f"{task_id}.meta.json"

        if not args.force and meta_path.exists():
            try:
                prior = read_json(meta_path)
            except (OSError, json.JSONDecodeError):
                prior = {}
            if prior.get("ok") and (SPECS_DIR / f"{task_id}.md").exists():
                with state_lock:
                    tasks["tasks"][idx - 1]["status"] = STATUS_OK
                    write_tasks(tasks)
                log(f"[{idx}/{len(rows)}] {task_id}: cached spec, skipping")
                return True

        log(f"[{idx}/{len(rows)}] {task_id}: extracting testbed + running /spec")
        meta = process_task(row, args, spec_cfg, template)
        with state_lock:
            write_json(meta_path, meta)
            tasks["tasks"][idx - 1]["status"] = STATUS_OK if meta.get("ok") else STATUS_FAILED
            write_tasks(tasks)

        if meta.get("ok"):
            cost = meta.get("cost_usd")
            cost_s = f"${cost:.4f}" if isinstance(cost, (int, float)) else "cost n/a"
            log(f"[{idx}/{len(rows)}] {task_id}: ok ({cost_s}, {meta['wall_seconds']}s)")
            return True
        log(f"[{idx}/{len(rows)}] {task_id}: FAILED — {meta.get('error')}")
        return False

    if args.parallel > 1:
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            n_ok = sum(pool.map(run_one, range(1, len(rows) + 1), rows))
    else:
        n_ok = sum(run_one(idx, row) for idx, row in enumerate(rows, 1))

    log(f"stage 01 done: {n_ok}/{len(rows)} specs ok -> {RESULTS_DIR / 'tasks.json'}")
    if n_ok == 0:
        print("error: no specs produced; Arm B cannot run", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

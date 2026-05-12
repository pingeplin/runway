from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from harness import artifacts, manifest, modes, probes, sandbox
from scorers import correctness, efficiency, mutation, refactor


# Opus is deliberately excluded. The pilot tasks are sized for small-to-medium
# models; a model that one-shots them isn't telling us anything about the /tdd
# workflow. The signal we want is the delta between full and naked mode on
# models that benefit from external scaffolding — that's where smaller models
# live.
DEFAULT_MODELS = "claude-sonnet-4-6,claude-haiku-4-5"


# Reasons a cell did not produce a scoreable result. `None` means the cell
# ran end-to-end and the scores in the row are the real signal. Centralized
# so producers and downstream consumers (summary stats, dashboards) agree on
# the spelling.
FailureMode = Literal[
    "pre_probe_offenders",
    "no_code_written",
    "harness_exception",
]
FM_PRE_PROBE_OFFENDERS: FailureMode = "pre_probe_offenders"
FM_NO_CODE_WRITTEN: FailureMode = "no_code_written"
FM_HARNESS_EXCEPTION: FailureMode = "harness_exception"


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_default_plugin_path() -> Path:
    return _resolve_repo_root() / "plugins" / "blueprint"


def _resolve_default_tasks_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "tasks"


def _resolve_default_results_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "results"


def _discover_tasks(tasks_arg: Path) -> list[Path]:
    """Return one or more task directories from the user's --tasks argument.

    If the path looks like a single task (contains description.md) it is
    returned alone; otherwise its immediate subdirectories that contain a
    description.md are enumerated.
    """
    if (tasks_arg / "description.md").exists():
        return [tasks_arg]
    return sorted(p for p in tasks_arg.iterdir() if (p / "description.md").exists())


def _model_slug(model: str) -> str:
    """Compact filename-safe identifier — strip the `claude-` prefix."""
    return model.removeprefix("claude-")


def _cell_id(task_name: str, mode: str, model: str, seed: int) -> str:
    return f"{task_name}__{mode}__{_model_slug(model)}__seed{seed}"


def _empty_scores() -> dict:
    return {
        "correctness": {"score": None, "passed": None, "total": None},
        "mutation": {"score": None},
        "refactor": {"score": None},
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="blueprint-bench")
    p.add_argument(
        "--tasks",
        type=Path,
        default=_resolve_default_tasks_dir(),
        help="Directory of tasks, or a single task directory.",
    )
    p.add_argument(
        "--modes",
        default="naked",
        help="Comma-separated list of modes: full | naked.",
    )
    p.add_argument(
        "--models",
        default=DEFAULT_MODELS,
        help=(
            "Comma-separated `claude -p --model` ids. Default: sonnet+haiku. "
            "Opus is deliberately excluded — pilot tasks are sized for "
            "small/medium models."
        ),
    )
    p.add_argument("--seeds", type=int, default=1)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--timeout-full", type=int, default=1800)
    p.add_argument("--timeout-naked", type=int, default=900)
    p.add_argument(
        "--plugin-path",
        type=Path,
        default=_resolve_default_plugin_path(),
    )
    p.add_argument(
        "--output",
        type=Path,
        default=_resolve_default_results_dir(),
    )
    return p.parse_args(argv)


def _run_id() -> str:
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{uuid.uuid4().hex[:8]}"


def _timeout_for(mode: str, args: argparse.Namespace) -> int:
    return args.timeout_full if mode == "full" else args.timeout_naked


def _execute_cell(
    task_dir: Path,
    mode: str,
    seed: int,
    model: str,
    run_root: Path,
    timeout: int,
) -> dict:
    cell_id = _cell_id(task_dir.name, mode, model, seed)
    run_dir = run_root / "runs" / cell_id
    run_dir.mkdir(parents=True, exist_ok=True)

    description = (task_dir / "description.md").read_text()
    leak_paths = probes.load_leak_paths(task_dir)

    sb = sandbox.build(task_dir, run_dir)
    pre = probes.run_probes(sb.wt, transcript_path=None, leak_paths=leak_paths, stage="pre")
    if not pre.pre_clean:
        probes.write_probe_report(pre, run_dir / "probes.json")
        return {
            "task": task_dir.name,
            "mode": mode,
            "model": model,
            "seed": seed,
            "compromised": True,
            "failure_mode": FM_PRE_PROBE_OFFENDERS,
            "reason": FM_PRE_PROBE_OFFENDERS,
            "score": None,
            "runtime_s": 0.0,
            "cell_id": cell_id,
        }

    mode_result = modes.run(
        mode=mode,
        description=description,
        wt=sb.wt,
        artifacts_dir=sb.artifacts_dir,
        timeout=timeout,
        model=model,
    )

    captured = artifacts.collect(sb.wt, sb.artifacts_dir, baseline=sb.starter_sha)
    code_files_touched = captured.get("code_files_touched") or []

    post = probes.run_probes(
        sb.wt,
        transcript_path=mode_result.transcript_path,
        leak_paths=leak_paths,
        stage="post",
    )
    probes.write_probe_report(post, run_dir / "probes.json")

    def _skipped(reason: str) -> dict:
        return {"score": None, "note": reason}

    failure_mode: FailureMode | None = None
    if post.compromised:
        score_dict = _skipped("scoring skipped: run compromised")
        mutation_dict = _skipped("scoring skipped: run compromised")
        refactor_dict = _skipped("scoring skipped: run compromised")
    elif not code_files_touched:
        # The agent produced specs/plans but never wrote production code.
        # Distinguish this from "wrote code that failed all oracle tests" —
        # the former is a workflow failure (orchestrator stalled, asked a
        # question the headless caller can't answer), the latter is a real
        # 0/N correctness result. Skip the oracle suite entirely; pytest
        # would just report an import error and we'd lose the signal.
        failure_mode = FM_NO_CODE_WRITTEN
        score_dict = _skipped("skipped: agent produced no production code")
        mutation_dict = _skipped("skipped: agent produced no production code")
        refactor_dict = _skipped("skipped: agent produced no production code")
    else:
        score = correctness.score(task_dir, sb.wt, run_dir)
        score_dict = score.to_dict()
        # Mutation and refactor both depend on a working oracle baseline.
        # If the agent's code failed correctness their signal is noise.
        if score.total > 0 and score.score > 0:
            mutation_dict = mutation.score(sb.wt).to_dict()
            refactor_dict = refactor.score(task_dir, sb.wt, run_dir).to_dict()
        else:
            mutation_dict = _skipped("skipped: correctness baseline failed")
            refactor_dict = _skipped("skipped: correctness baseline failed")
    (run_dir / "score.json").write_text(json.dumps(score_dict, indent=2))
    (run_dir / "mutation.json").write_text(json.dumps(mutation_dict, indent=2))
    (run_dir / "refactor.json").write_text(json.dumps(refactor_dict, indent=2))

    row = {
        "task": task_dir.name,
        "mode": mode,
        "model": model,
        "seed": seed,
        "compromised": post.compromised,
        "failure_mode": failure_mode,
        "scores": {
            "correctness": {
                "score": score_dict.get("score"),
                "passed": score_dict.get("passed"),
                "total": score_dict.get("total"),
            },
            "mutation": {"score": mutation_dict.get("score")},
            "refactor": {"score": refactor_dict.get("score")},
        },
        "runtime_s": mode_result.runtime_s,
        "timed_out": mode_result.timed_out,
        "returncode": mode_result.returncode,
        "usage": modes.usage_to_dict(mode_result.usage),
        "cell_id": cell_id,
        "artifacts": captured,
    }
    (run_dir / "result.json").write_text(json.dumps(row, indent=2))
    return row


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    tasks = _discover_tasks(args.tasks)
    if not tasks:
        print(f"no tasks found under {args.tasks}", file=sys.stderr)
        return 2

    mode_list = [m.strip() for m in args.modes.split(",") if m.strip()]
    if not mode_list:
        print("no modes requested", file=sys.stderr)
        return 2

    model_list = [m.strip() for m in args.models.split(",") if m.strip()]
    if not model_list:
        print("no models requested", file=sys.stderr)
        return 2

    run_root = args.output / _run_id()
    run_root.mkdir(parents=True, exist_ok=True)

    repo_root = _resolve_repo_root()
    mf = manifest.build(
        run_id=run_root.name,
        plugin_dir=args.plugin_path,
        harness_dir=repo_root,
        args={
            "tasks": str(args.tasks),
            "modes": mode_list,
            "models": model_list,
            "seeds": args.seeds,
            "workers": args.workers,
            "timeout_full": args.timeout_full,
            "timeout_naked": args.timeout_naked,
        },
    )
    mf.write(run_root / "manifest.json")

    cells = [
        (task, mode, seed, model)
        for task in tasks
        for mode in mode_list
        for model in model_list
        for seed in range(args.seeds)
    ]
    print(
        f"[runner] {len(cells)} cells: {len(tasks)} tasks × {len(mode_list)} modes × "
        f"{len(model_list)} models × {args.seeds} seeds",
        file=sys.stderr,
    )

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                _execute_cell,
                task,
                mode,
                seed,
                model,
                run_root,
                _timeout_for(mode, args),
            ): (task, mode, seed, model)
            for task, mode, seed, model in cells
        }
        completed = 0
        for fut in as_completed(futures):
            task, mode, seed, model = futures[fut]
            try:
                row = fut.result()
            except Exception as exc:
                row = {
                    "task": task.name,
                    "mode": mode,
                    "model": model,
                    "seed": seed,
                    "compromised": False,
                    "failure_mode": FM_HARNESS_EXCEPTION,
                    "scores": _empty_scores(),
                    "runtime_s": 0.0,
                    "error": repr(exc),
                    "cell_id": _cell_id(task.name, mode, model, seed),
                }
            rows.append(row)
            completed += 1
            scores = row.get("scores") or {}
            corr = (scores.get("correctness") or {}).get("score")
            mut = (scores.get("mutation") or {}).get("score")
            ref = (scores.get("refactor") or {}).get("score")
            usage = row.get("usage") or {}
            cost = usage.get("cost_usd")
            cost_str = f"${cost:.3f}" if cost is not None else "$?"
            err_str = " ERROR" if usage.get("is_error") else ""
            mut_str = f" mut={mut:.2f}" if isinstance(mut, (int, float)) else ""
            ref_str = f" ref={ref:.2f}" if isinstance(ref, (int, float)) else ""
            failure_mode = row.get("failure_mode")
            fail_str = f" failure={failure_mode}" if failure_mode else ""
            print(
                f"[{completed}/{len(cells)}] {row['cell_id']} score={corr}"
                f"{mut_str}{ref_str} "
                f"compromised={row.get('compromised')}{fail_str} "
                f"runtime={row.get('runtime_s', 0):.1f}s "
                f"cost={cost_str}{err_str}",
                file=sys.stderr,
            )

    total_cost = sum(
        ((r.get("usage") or {}).get("cost_usd") or 0.0)
        for r in rows
    )
    summary = {
        "manifest": asdict(mf),
        "total_cost_usd": round(total_cost, 4),
        "efficiency_by_mode": efficiency.compute(rows),
        "rows": sorted(rows, key=lambda r: r["cell_id"]),
    }
    (run_root / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nresults: {run_root} (total cost ${total_cost:.3f})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

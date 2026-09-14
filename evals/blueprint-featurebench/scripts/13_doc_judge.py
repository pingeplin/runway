#!/usr/bin/env python3
"""Stage 13 — LLM-judged spec-quality metrics (report-only).

Two prompts under prompts/judge_*.md, each a listing task whose final line
is one JSON object:

- **fence** — symbols the spec forbids the agent to touch; intersected here
  with the stage-12 oracle (mask-removed symbols) to give `fenced∩oracle`.
- **testability** — per-scenario class (behavioral / vague /
  implementation_coupled / untestable) plus the two contract checks.

The judge is never the plugin's fix-loop `spec-evaluator`; it edits nothing,
and it is run blind: `claude -p` with all tools disabled, in an empty
temporary cwd, so the verdict is a function of the spec text alone.
`--repeats N` runs each (spec, metric) N times so judge self-agreement is
reported next to the number — a count the judge cannot reproduce is not a
number to build on.

Cells cache under results/doc_judge/<label>/<task>.<metric>.r<k>.json,
fingerprinted by the spec's and the prompt template's sha256; a cell whose
fingerprint no longer matches is re-judged.
"""

from __future__ import annotations

import argparse
import hashlib
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from _common import EVAL_ROOT, RESULTS_DIR, SPECS_DIR, add_config_arg, die, load_config, load_script_module, read_json, write_json

PROMPTS_DIR = EVAL_ROOT / "prompts"
OUT_DIR = RESULTS_DIR / "doc_judge"
OUT_MD = RESULTS_DIR / "doc_judge_report.md"
METRICS = ("fence", "testability")
BLIND_ARGS = ["--tools", ""]

dq = load_script_module("12_doc_quality.py")
tx = load_script_module("08_taxonomy.py")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cell_path(out_dir: Path, label: str, task_id: str, metric: str, rep: int) -> Path:
    return out_dir / label / f"{task_id}.{metric}.r{rep}.json"


def cell_is_fresh(path: Path, spec_sha: str, prompt_sha: str) -> bool:
    if not path.exists():
        return False
    meta = read_json(path)
    return bool(meta.get("ok")) and meta.get("spec_sha256") == spec_sha and meta.get("prompt_sha256") == prompt_sha


def judge_cell(spec_text: str, template: str, cfg: dict[str, Any], claude_cmd: str) -> dict[str, Any]:
    prompt = template.replace("{spec}", spec_text)
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="fb-judge-") as blind_cwd:
        payload, error = tx.run_claude(claude_cmd, prompt, cfg["model"], cfg["claude_args"], cfg["timeout_seconds"], cwd=Path(blind_cwd))
    meta: dict[str, Any] = {
        "model": cfg["model"],
        "claude_args": cfg["claude_args"],
        "spec_sha256": sha256(spec_text),
        "prompt_sha256": sha256(template),
        "cost_usd": payload.get("total_cost_usd"),
        "wall_seconds": round(time.time() - started, 2),
        "usage": payload.get("usage"),
        "ok": error is None,
        "error": error,
        "result": None,
    }
    if error:
        return meta
    obj, parse_error = tx.parse_classification(payload.get("result") or "")
    if parse_error:
        meta.update(ok=False, error=parse_error, raw_tail=(payload.get("result") or "")[-800:])
        return meta
    meta["result"] = obj
    return meta


def bare_symbol(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().split("(")[0].split(".")[-1].strip() or None


def as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    return bool(value)


def summarize_fence(result: dict[str, Any], oracle_symbols: set[str]) -> dict[str, Any]:
    items = [i for i in result.get("fenced") or [] if isinstance(i, dict) and bare_symbol(i.get("symbol"))]
    hard = {bare_symbol(i["symbol"]) for i in items if i.get("strength") == "hard"}
    soft = {bare_symbol(i["symbol"]) for i in items if i.get("strength") != "hard"}
    return {"n_fenced": len(items), "hard_oracle": sorted(hard & oracle_symbols), "soft_oracle": sorted(soft & oracle_symbols)}


def summarize_testability(result: dict[str, Any], _: set[str]) -> dict[str, Any]:
    scen = [s for s in result.get("scenarios") or [] if isinstance(s, dict)]
    n = len(scen)
    return {
        "n_scenarios": n,
        "behavioral_share": round(sum(1 for s in scen if s.get("class") == "behavioral") / n, 3) if n else None,
        "vague": sum(1 for s in scen if s.get("class") == "vague"),
        "implementation_coupled": sum(1 for s in scen if s.get("class") == "implementation_coupled"),
        "untestable": sum(1 for s in scen if s.get("class") == "untestable"),
        "has_dod": as_bool(result.get("has_definition_of_done")),
        "has_agent_instruction": as_bool(result.get("has_implementing_agent_instruction")),
    }


SUMMARIZERS = {"fence": summarize_fence, "testability": summarize_testability}
fmt, mean = dq.fmt, dq.mean


def spread(vals: list[float]) -> str:
    return f" ±{max(vals) - min(vals):g}" if len(vals) > 1 and max(vals) != min(vals) else ""


def render(cells: dict[str, dict[str, dict[str, list[dict[str, Any]]]]], rates: dict[str, dict[str, float]]) -> str:
    """cells[label][task][metric] = [summary per repeat]."""
    n_reps = max((len(v) for tasks in cells.values() for m in tasks.values() for v in m.values()), default=0)
    lines = ["# Doc quality — LLM-judged spec metrics (stage 13)", ""]
    lines.append(f"Judge: report-only, tools disabled, prompts under `prompts/judge_*.md`, up to {n_reps} repeat(s) per cell. Values are means over repeats; ± is max−min across repeats (judge self-agreement).")
    lines.append("")
    hdr = "| label | task | fenced (hard∩oracle) | scenarios | behavioral share | DoD / agent instr | B pass_rate |"
    lines += [hdr, "|" + "---|" * (hdr.count("|") - 1)]

    def col(rows: list[dict[str, Any]], key: str) -> tuple[float | None, str]:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return mean(vals), (fmt(mean(vals)) + spread(vals))

    flat_rows: list[dict[str, Any]] = []
    for label, tasks in cells.items():
        for task_id, metrics in tasks.items():
            f, t = metrics.get("fence", []), metrics.get("testability", [])
            hard_sets = [set(r["hard_oracle"]) for r in f]
            hard_counts = [float(len(s)) for s in hard_sets]
            flat = {
                "label": label, "task_id": task_id,
                "hard_oracle_n": mean(hard_counts),
                "behavioral_share": col(t, "behavioral_share")[0],
                "pass_rate": rates.get(label, {}).get(task_id),
            }
            flat_rows.append(flat)
            hard_union = sorted(set().union(*hard_sets)) if hard_sets else []
            lines.append("| " + " | ".join([
                label, f"`{dq.short_id(task_id)}`",
                f"{fmt(flat['hard_oracle_n'])}{spread(hard_counts)} {hard_union or ''}".strip(),
                col(t, "n_scenarios")[1], col(t, "behavioral_share")[1],
                ("/".join("y" if all(r.get(k) for r in t) else "n" for k in ("has_dod", "has_agent_instruction")) if t else "—"),
                fmt(flat["pass_rate"]),
            ]) + " |")

    lines += ["", "## Per-label means", ""]
    hdr = "| label | n | hard fenced∩oracle | behavioral share | B pass_rate |"
    lines += [hdr, "|" + "---|" * (hdr.count("|") - 1)]
    for label in cells:
        rows = [r for r in flat_rows if r["label"] == label]
        lines.append("| " + " | ".join([
            label, str(len(rows)),
            fmt(mean(r["hard_oracle_n"] for r in rows)),
            fmt(mean(r["behavioral_share"] for r in rows)), fmt(mean(r["pass_rate"] for r in rows)),
        ]) + " |")

    joined = [r for r in flat_rows if r["pass_rate"] is not None]
    if joined:
        n_tasks, n_labels = len({r["task_id"] for r in joined}), len({r["label"] for r in joined})
        lines += ["", f"## Direction against B pass_rate ({n_tasks} tasks × {n_labels} labels)", ""]
        keys: dict[str, dq.Direction] = {
            "hard_oracle_n": (lambda r: r["hard_oracle_n"], -1),
            "behavioral_share": (lambda r: r["behavioral_share"], 1),
        }
        lines += dq.render_direction(joined, keys)[3:]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_config_arg(parser)
    parser.add_argument("--corpus", action="append", default=[], help="label=specs_dir[:report.md]; repeatable. Default: results/specs")
    parser.add_argument("--dataset-jsonl", default=None, help="Arm B dataset JSONL carrying `patch` (for fenced∩oracle)")
    parser.add_argument("--metrics", default=",".join(METRICS), help=f"comma list from {METRICS}")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--claude-cmd", default="claude")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--out-md", default=str(OUT_MD))
    args = parser.parse_args()

    jcfg = load_config(args.config).get("doc_judge", {})
    cfg = {
        "model": jcfg.get("model", "claude-opus-5"),
        "timeout_seconds": int(jcfg.get("timeout_seconds", 1800)),
        "claude_args": list(jcfg.get("claude_args", BLIND_ARGS)),
    }
    metrics = [m for m in args.metrics.split(",") if m]
    if any(m not in METRICS for m in metrics):
        die(f"--metrics must be from {METRICS}")
    templates = {m: (PROMPTS_DIR / f"judge_{m}.md").read_text(encoding="utf-8") for m in metrics}

    jsonl = Path(args.dataset_jsonl) if args.dataset_jsonl else dq.default_dataset_jsonl()
    if not jsonl or not jsonl.exists():
        die("dataset JSONL not found — run stage 02 or pass --dataset-jsonl")
    oracles = dq.load_oracles(jsonl)
    corpus = dq.parse_corpus(args.corpus) or {"results": (SPECS_DIR, None)}
    out_dir = Path(args.out_dir)

    jobs: list[tuple[str, str, str, int, str, Path]] = []
    for label, (specs_dir, _) in corpus.items():
        for spec_path in sorted(specs_dir.glob("*.md")):
            tid = spec_path.stem
            if tid.endswith(".ledger") or tid not in oracles:
                continue
            spec_text = spec_path.read_text(encoding="utf-8")
            for metric in metrics:
                for rep in range(1, args.repeats + 1):
                    target = cell_path(out_dir, label, tid, metric, rep)
                    if not args.force and cell_is_fresh(target, sha256(spec_text), sha256(templates[metric])):
                        continue
                    jobs.append((label, tid, metric, rep, spec_text, target))

    print(f"{len(jobs)} judge call(s) pending, model={cfg['model']}, claude_args={cfg['claude_args']}, repeats={args.repeats}", flush=True)
    if args.dry_run:
        for j in jobs:
            print("  ", j[0], dq.short_id(j[1]), j[2], f"r{j[3]}")
        return 0

    def run(job):
        label, tid, metric, rep, spec_text, target = job
        meta = judge_cell(spec_text, templates[metric], cfg, args.claude_cmd)
        meta.update(label=label, instance_id=tid, metric=metric, repeat=rep)
        write_json(target, meta)
        return job, meta

    spent = 0.0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for fut in as_completed([pool.submit(run, j) for j in jobs]):
            job, meta = fut.result()
            spent += meta.get("cost_usd") or 0.0
            print(f"  {'ok ' if meta['ok'] else 'ERR'} {job[0]} {dq.short_id(job[1])} {job[2]} r{job[3]} ${meta.get('cost_usd') or 0:.2f} {meta.get('error') or ''}", flush=True)
    print(f"judge spend this run: ${spent:.2f}")

    cells: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}
    rates: dict[str, dict[str, float]] = {}
    for label, (specs_dir, report) in corpus.items():
        if report and report.exists():
            rates[label] = dq.pass_rates_from_report(report)
        for path in sorted((out_dir / label).glob("*.json")) if (out_dir / label).is_dir() else []:
            meta = read_json(path)
            tid, metric = meta.get("instance_id"), meta.get("metric")
            if not meta.get("ok") or metric not in metrics or tid not in oracles:
                continue
            summary = SUMMARIZERS[metric](meta["result"], oracles[tid].all_symbols)
            cells.setdefault(label, {}).setdefault(tid, {}).setdefault(metric, []).append(summary)

    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(render(cells, rates), encoding="utf-8")
    print(f"wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

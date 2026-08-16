#!/usr/bin/env python3
"""Stage 05 — paired report: per-task table, McNemar, spec cost.

`fb eval`'s top-level report.json is an aggregate keyed by attempt, not by
instance, so per-task outcomes are read from the sibling
eval_outputs/<instance_id>/attempt-*/report.json files. A file that is already
keyed by instance_id is accepted directly.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from _common import (
    RESULTS_DIR,
    SPECS_DIR,
    add_config_arg,
    die,
    load_config,
    read_json,
    read_runs,
    read_tasks,
    spec_ok_ids,
)

OUT_PATH = RESULTS_DIR / "report.md"

CAVEATS = """## Caveats

- **Single seed.** One inference pass per arm per task. Agent runs are
  stochastic; a rerun will move these numbers.
- **Small N.** With FeatureBench-level resolve rates the discordant-pair count
  is expected to be single-digit, so the McNemar p-value is **directional
  evidence only** — it is not a verdict, and it is not corrected for anything.
- **End-to-end correctness only.** FeatureBench scores hidden fail-to-pass
  tests, so this table says nothing about the quality of the tests the agent
  itself wrote. That is measured separately by the mutation overlay
  (`mutation_report.md`); design-argument quality is measured by neither.
- **Cost is one-sided.** The spec-stage cost above is spent by Arm B and not by
  Arm A. It is not the whole picture: the implementing agent's own in-container
  token cost is reported separately in `cost_report.md` (stage 10), which is
  where the all-in A-vs-B comparison lives.
- **Model contamination** (the model may know these repos) dilutes both arms
  equally under pairing: it biases levels, not the A/B delta.
"""


def looks_per_instance(payload: Any) -> bool:
    return isinstance(payload, dict) and any(
        isinstance(v, dict) and "resolved" in v for v in payload.values()
    )


def load_arm_results(report_path: Path) -> dict[str, dict[str, Any]]:
    """Return {instance_id: {"resolved": bool, "pass_rate": float}}."""
    if not report_path.exists():
        die(f"report not found: {report_path}")
    payload = read_json(report_path)

    if looks_per_instance(payload):
        return {
            iid: {
                "resolved": bool(entry.get("resolved", False)),
                "pass_rate": float(entry.get("pass_rate", 0.0) or 0.0),
            }
            for iid, entry in payload.items()
            if isinstance(entry, dict)
        }

    # Aggregate shape ({"attempt_1": {...}}): fall back to the per-instance files.
    eval_outputs = report_path.parent / "eval_outputs"
    if not eval_outputs.is_dir():
        die(f"{report_path} is an aggregate report and {eval_outputs} does not exist")

    results: dict[str, dict[str, Any]] = {}
    for per_instance in sorted(eval_outputs.glob("*/attempt-*/report.json")):
        try:
            data = read_json(per_instance)
        except (OSError, json.JSONDecodeError):
            continue
        for iid, entry in (data or {}).items():
            if not isinstance(entry, dict):
                continue
            # Keep the best attempt if several exist.
            prior = results.get(iid)
            record = {
                "resolved": bool(entry.get("resolved", False)),
                "pass_rate": float(entry.get("pass_rate", 0.0) or 0.0),
            }
            if prior is None or (record["resolved"] and not prior["resolved"]):
                results[iid] = record
    if not results:
        die(f"no per-instance reports found under {eval_outputs}")
    return results


def mcnemar_exact_p(b: int, c: int) -> float:
    """Two-sided exact McNemar: binomial(n=b+c, p=0.5) tail at min(b, c)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def load_spec_meta(task_id: str) -> dict[str, Any]:
    path = SPECS_DIR / f"{task_id}.meta.json"
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


def fmt_bool(value: bool | None) -> str:
    if value is None:
        return "—"
    return "yes" if value else "no"


def fmt_num(value: Any, spec: str) -> str:
    return format(value, spec) if isinstance(value, (int, float)) else "—"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_arg(parser)
    parser.add_argument("--report-a", default=None, help="Override Arm A report.json path")
    parser.add_argument("--report-b", default=None, help="Override Arm B report.json path")
    parser.add_argument("--tasks", default=None, help="Override results/tasks.json path")
    parser.add_argument("--out", default=None, help="Override results/report.md path")
    args = parser.parse_args()

    cfg = load_config(args.config)
    runs = read_runs()

    def pick(arm: str, override: str | None) -> Path:
        if override:
            return Path(override).resolve()
        recorded = (runs.get(arm) or {}).get("report_json")
        if not recorded:
            die(f"no report recorded for arm {arm} — run stage 04 or pass --report-{arm.lower()}")
        return Path(recorded)

    report_a_path, report_b_path = pick("A", args.report_a), pick("B", args.report_b)
    arm_a = load_arm_results(report_a_path)
    arm_b = load_arm_results(report_b_path)

    tasks = read_json(Path(args.tasks)) if args.tasks else read_tasks()
    task_ids = sorted(spec_ok_ids(tasks)) or sorted(set(arm_a) | set(arm_b))

    rows = []
    b_count = c_count = 0  # b: A-only resolved, c: B-only resolved
    a_resolved = b_resolved = 0
    sum_a_rate = sum_b_rate = 0.0
    total_cost = 0.0
    total_seconds = 0.0
    for task_id in task_ids:
        ra = arm_a.get(task_id)
        rb = arm_b.get(task_id)
        res_a = ra["resolved"] if ra else None
        res_b = rb["resolved"] if rb else None
        rate_a = ra["pass_rate"] if ra else None
        rate_b = rb["pass_rate"] if rb else None

        if res_a and not res_b:
            b_count += 1
        elif res_b and not res_a:
            c_count += 1
        a_resolved += 1 if res_a else 0
        b_resolved += 1 if res_b else 0
        sum_a_rate += rate_a or 0.0
        sum_b_rate += rate_b or 0.0

        meta = load_spec_meta(task_id)
        cost = meta.get("cost_usd")
        seconds = meta.get("wall_seconds")
        if isinstance(cost, (int, float)):
            total_cost += cost
        if isinstance(seconds, (int, float)):
            total_seconds += seconds

        rows.append(
            f"| `{task_id}` | {fmt_bool(res_a)} | {fmt_bool(res_b)} | "
            f"{fmt_num(rate_a, '.2f')} | {fmt_num(rate_b, '.2f')} | "
            f"{fmt_num(cost, '.4f')} | {fmt_num(seconds, '.0f')} |"
        )

    n = len(task_ids)
    p_value = mcnemar_exact_p(b_count, c_count)
    eval_cfg = cfg.get("eval", {})

    lines: list[str] = []
    lines.append("# Blueprint spec ablation on FeatureBench\n")
    lines.append(
        f"Panel: `{eval_cfg.get('dataset', '')}` split `{eval_cfg.get('split', '')}`, "
        f"{n} paired task(s).  \n"
        f"Arm A = original problem statement. Arm B = original + blueprint spec.  \n"
        f"Implementing agent: `claude_code` / `{cfg.get('infer', {}).get('model', '')}` "
        f"(identical in both arms). Spec model: `{cfg.get('spec', {}).get('model', '')}`.\n"
    )
    lines.append(f"Reports: A `{report_a_path}` · B `{report_b_path}`\n")

    lines.append("## Per-task paired results\n")
    lines.append("| task id | A resolved | B resolved | A pass_rate | B pass_rate | spec cost USD | spec seconds |")
    lines.append("|---|---|---|---|---|---|---|")
    lines.extend(rows)
    lines.append(
        f"| **totals ({n})** | **{a_resolved}** | **{b_resolved}** | "
        f"**{(sum_a_rate / n if n else 0):.2f}** | **{(sum_b_rate / n if n else 0):.2f}** | "
        f"**{total_cost:.4f}** | **{total_seconds:.0f}** |\n"
    )

    lines.append("## Paired comparison\n")
    lines.append(f"- Resolved: A **{a_resolved}/{n}**, B **{b_resolved}/{n}** (delta **{b_resolved - a_resolved:+d}**)")
    lines.append(f"- Discordant pairs: b (A-only resolved) = **{b_count}**, c (B-only resolved) = **{c_count}**")
    lines.append(f"- Exact McNemar (two-sided binomial on {b_count + c_count} discordant pairs): **p = {p_value:.4f}**")
    lines.append(f"- Spec-stage cost: **${total_cost:.4f}** total over {n} task(s), {total_seconds:.0f}s wall\n")

    lines.append(CAVEATS)

    out_path = Path(args.out).resolve() if args.out else OUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"stage 05 ok: {out_path}")
    print(f"  A resolved {a_resolved}/{n} · B resolved {b_resolved}/{n} · b={b_count} c={c_count} p={p_value:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

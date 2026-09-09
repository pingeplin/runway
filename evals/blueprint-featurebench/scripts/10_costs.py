#!/usr/bin/env python3
"""Stage 10 — the cost ledger the pilot never had.

The pilot could only report the spec stage's spend, so `report.md` carried the
caveat "the implementing agent's own token cost is not included in either arm".
It is recoverable: `fb infer` preserves the in-container agent's stream-json at
`run_outputs/<id>/attempt-*/claude_code_stream_output.jsonl`, whose terminal
`result` event carries `total_cost_usd`, `num_turns` and `duration_ms`.

This stage joins that against the host-side stages that already record cost
(01 specs, 06 verdicts) to answer the question a README reader actually asks:
**what does the spec arm cost per extra task resolved?**

The same `result` events (and the `.meta.json` sidecars) also carry a `usage`
payload with input/cache-write/cache-read/output token counts, so token
totals are reported alongside cost from the identical source.

  uv run --with datasets python3 scripts/10_costs.py --out results/cost_report.md

Reads runs.json (use --runs results/merged/runs.json for the whole panel).
Arms whose stream files are absent are reported as unmeasured rather than $0 —
a missing number must never read as a free arm.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from _common import (
    RESULTS_DIR,
    SPECS_DIR,
    die,
    read_json,
    read_runs,
)

VERDICTS_DIR = RESULTS_DIR / "verdicts"
REPORT_PATH = RESULTS_DIR / "cost_report.md"

TOKEN_KEYS = ("input", "cache_write", "cache_read", "output")


def log(msg: str) -> None:
    print(msg, flush=True)


def extract_tokens(usage: Any) -> dict[str, int] | None:
    """{input, cache_write, cache_read, output} from a `usage` payload.

    None when `usage` is absent — an unmeasured task, never a free one.
    """
    if not isinstance(usage, dict):
        return None
    return {
        "input": int(usage.get("input_tokens") or 0),
        "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "output": int(usage.get("output_tokens") or 0),
    }


def add_tokens(a: dict[str, int] | None, b: dict[str, int] | None) -> dict[str, int] | None:
    """Key-wise sum; either side unmeasured poisons the sum to unmeasured."""
    if a is None or b is None:
        return None
    return {k: a[k] + b[k] for k in TOKEN_KEYS}


def sum_tokens(records: list[dict[str, int] | None]) -> dict[str, int] | None:
    total: dict[str, int] | None = {k: 0 for k in TOKEN_KEYS}
    for r in records:
        total = add_tokens(total, r)
        if total is None:
            return None
    return total


def tokens_total(tokens: dict[str, int] | None) -> int | None:
    return sum(tokens.values()) if tokens is not None else None


def stream_cost(path: Path) -> dict[str, Any] | None:
    """Terminal `result` event of a Claude Code stream-json transcript."""
    last = None
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "result":
                    last = ev
    except OSError:
        return None
    if last is None:
        return None
    return {
        "cost_usd": float(last.get("total_cost_usd") or 0.0),
        "turns": last.get("num_turns"),
        "seconds": (last.get("duration_ms") or 0) / 1000.0,
        "subtype": last.get("subtype"),
        "tokens": extract_tokens(last.get("usage")),
    }


def infer_costs(run_entry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{instance_id: cost record} for one arm's inference round."""
    # A merged panel's jsonl has no sibling run_outputs/, so 09_merge records
    # the real per-batch run directories. Fall back to the jsonl's own parent
    # for an unmerged single-batch run.
    dirs = [Path(d) for d in (run_entry.get("source_run_dirs") or [])]
    if not dirs:
        jsonl = run_entry.get("output_jsonl")
        if not jsonl:
            return {}
        dirs = [Path(jsonl).parent]
    out: dict[str, dict[str, Any]] = {}
    for run_dir in dirs:
        pattern = "run_outputs/*/attempt-*/claude_code_stream_output.jsonl"
        for p in sorted(run_dir.glob(pattern)):
            # <run_dir>/run_outputs/<instance_id>/attempt-N/<file>
            tid = p.parts[len(run_dir.parts) + 1]
            rec = stream_cost(p)
            if rec is None:
                continue
            prior = out.get(tid)
            # Several attempts: charge them all, the spend is real.
            if prior:
                prior["cost_usd"] += rec["cost_usd"]
                prior["seconds"] += rec["seconds"]
                prior["tokens"] = add_tokens(prior["tokens"], rec["tokens"])
            else:
                out[tid] = rec
    return out


def count_resolved(report_path: Path) -> int:
    """Resolved count from an fb eval report.

    The top-level report.json is keyed by attempt, not instance, so a direct
    `.resolved` scan silently returns 0. Fall back to the per-instance
    siblings the same way 05_report does.
    """
    if not report_path.exists():
        return 0
    try:
        payload = read_json(report_path)
    except (OSError, json.JSONDecodeError):
        return 0

    if isinstance(payload, dict) and any(
        isinstance(v, dict) and "resolved" in v for v in payload.values()
    ):
        return sum(1 for v in payload.values()
                   if isinstance(v, dict) and v.get("resolved"))

    resolved: dict[str, bool] = {}
    for per_instance in sorted((report_path.parent / "eval_outputs").glob("*/attempt-*/report.json")):
        try:
            data = read_json(per_instance)
        except (OSError, json.JSONDecodeError):
            continue
        for iid, entry in (data or {}).items():
            if isinstance(entry, dict):
                resolved[iid] = resolved.get(iid, False) or bool(entry.get("resolved"))
    return sum(1 for v in resolved.values() if v)


def host_stage_costs(directory: Path, panel: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """{instance_id: cost} from stage 01 / 06 *.meta.json sidecars.

    `panel` restricts to the tasks actually being reported. These directories
    accumulate across runs, so an earlier run's specs/verdicts would otherwise
    be billed to this panel — inflating the very number a reader uses to judge
    whether the spec stage is worth it.
    """
    out: dict[str, dict[str, Any]] = {}
    if not directory.is_dir():
        return out
    for meta in sorted(directory.glob("*.meta.json")):
        tid = meta.name[: -len(".meta.json")]
        if panel is not None and tid not in panel:
            continue
        try:
            data = read_json(meta)
        except (OSError, json.JSONDecodeError):
            continue
        cost = data.get("cost_usd")
        if isinstance(cost, (int, float)):
            out[tid] = {"cost_usd": float(cost),
                        "seconds": float(data.get("wall_seconds") or 0.0),
                        "tokens": extract_tokens(data.get("usage"))}
    return out


def fmt_usd(v: Any) -> str:
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "—"


def fmt_tokens(v: Any) -> str:
    return f"{round(v):,}" if isinstance(v, (int, float)) else "—"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", default=None, help="Path to runs.json (default results/runs.json)")
    parser.add_argument("--out", default=None, help="Path for the markdown report")
    parser.add_argument("--task-ids-file", default=None,
                        help="Restrict host-stage costs to these ids (default: union of runs.json task_ids)")
    args = parser.parse_args()

    runs = read_json(Path(args.runs)) if args.runs else read_runs()
    if not runs:
        die("no runs.json — run stage 03/04 (or 09_merge) first")

    # The panel = every task any arm actually ran.
    panel: set[str] = set()
    for entry in runs.values():
        if isinstance(entry, dict):
            panel |= set(entry.get("task_ids") or [])
    if args.task_ids_file:
        panel = {l.strip() for l in Path(args.task_ids_file).read_text().splitlines() if l.strip()}
    spec = host_stage_costs(SPECS_DIR, panel or None)
    verdict = host_stage_costs(VERDICTS_DIR, panel or None)

    per_arm: dict[str, dict[str, Any]] = {}
    for arm in sorted(runs):
        entry = runs[arm]
        if not isinstance(entry, dict):
            continue
        costs = infer_costs(entry)
        report_json = entry.get("report_json")
        resolved = count_resolved(Path(report_json)) if report_json else 0
        infer_tokens = sum_tokens([c["tokens"] for c in costs.values()])
        per_arm[arm] = {
            "infer": costs,
            "infer_total": sum(c["cost_usd"] for c in costs.values()),
            "infer_tokens": infer_tokens,
            "n_measured": len(costs),
            "n_tasks": len(entry.get("task_ids") or []) or len(costs),
            "resolved": resolved,
        }

    # Host-side stages are spent by the arms that consume them.
    spec_total = sum(v["cost_usd"] for v in spec.values())
    verdict_total = sum(v["cost_usd"] for v in verdict.values())
    spec_tokens = sum_tokens([v["tokens"] for v in spec.values()])
    verdict_tokens = sum_tokens([v["tokens"] for v in verdict.values()])

    lines: list[str] = ["# Cost ledger\n"]
    lines.append(
        "In-container inference cost is read from each task's Claude Code "
        "stream-json (`total_cost_usd` on the terminal `result` event); host "
        "stages from their `.meta.json` sidecars. Token counts (input, cache "
        "write, cache read, output) come from the same `usage` payload in "
        "each source. Arms with no stream file are reported as unmeasured, "
        "never as $0 or 0 tokens.\n"
    )

    lines.append("## Per-arm inference\n")
    lines.append("| arm | tasks measured | infer cost | mean/task | resolved | cost/resolved |")
    lines.append("|---|---|---|---|---|---|")
    for arm, d in per_arm.items():
        n = d["n_measured"]
        mean = d["infer_total"] / n if n else None
        per_res = d["infer_total"] / d["resolved"] if d["resolved"] else None
        measured = f"{n}/{d['n_tasks']}" if d["n_tasks"] else str(n)
        lines.append(
            f"| {arm} | {measured} | {fmt_usd(d['infer_total'])} | {fmt_usd(mean)} | "
            f"{d['resolved']} | {fmt_usd(per_res)} |"
        )
    lines.append("")

    lines.append("## Per-arm tokens\n")
    lines.append("| arm | input | cache write | cache read | output | total | mean total/task | total/resolved |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for arm, d in per_arm.items():
        tok = d["infer_tokens"]
        n = d["n_measured"]
        total = tokens_total(tok)
        mean = total / n if (total is not None and n) else None
        per_res = total / d["resolved"] if (total is not None and d["resolved"]) else None
        if tok is None:
            row_vals = ("—", "—", "—", "—")
        else:
            row_vals = tuple(fmt_tokens(tok[k]) for k in TOKEN_KEYS)
        lines.append(
            f"| {arm} | {row_vals[0]} | {row_vals[1]} | {row_vals[2]} | {row_vals[3]} | "
            f"{fmt_tokens(total)} | {fmt_tokens(mean)} | {fmt_tokens(per_res)} |"
        )
    lines.append("")

    lines.append("## Host-side stages\n")
    lines.append("| stage | tasks | cost | mean/task | input | cache write | cache read | output | total tokens |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for label, data, total, tok in [
        ("01 specs (Arm B/C input)", spec, spec_total, spec_tokens),
        ("06 verdicts (Arm C input)", verdict, verdict_total, verdict_tokens),
    ]:
        n = len(data)
        tok_cells = tuple(fmt_tokens(tok[k]) for k in TOKEN_KEYS) if tok is not None else ("—",) * 4
        lines.append(f"| {label} | {n} | {fmt_usd(total)} | "
                     f"{fmt_usd(total / n if n else None)} | "
                     f"{tok_cells[0]} | {tok_cells[1]} | {tok_cells[2]} | {tok_cells[3]} | "
                     f"{fmt_tokens(tokens_total(tok))} |")
    lines.append("")

    # The headline: what the treatment costs over the control, end to end.
    a = per_arm.get("A", {})
    b = per_arm.get("B", {})
    if a.get("n_measured") and b.get("n_measured"):
        a_total = a["infer_total"]
        b_total = b["infer_total"] + spec_total
        delta_resolved = b.get("resolved", 0) - a.get("resolved", 0)
        a_tok_total = tokens_total(a["infer_tokens"])
        b_tok = add_tokens(b["infer_tokens"], spec_tokens)
        b_tok_total = tokens_total(b_tok)
        lines.append("## Arm A vs Arm B, all-in\n")
        lines.append(f"- Arm A (inference only): **{fmt_usd(a_total)}**, "
                     f"**{fmt_tokens(a_tok_total)} tokens**")
        lines.append(f"- Arm B (inference + spec stage): **{fmt_usd(b_total)}** "
                     f"= {fmt_usd(b['infer_total'])} infer + {fmt_usd(spec_total)} spec, "
                     f"**{fmt_tokens(b_tok_total)} tokens** "
                     f"= {fmt_tokens(tokens_total(b['infer_tokens']))} infer + "
                     f"{fmt_tokens(tokens_total(spec_tokens))} spec")
        lines.append(f"- Spec overhead: **{fmt_usd(b_total - a_total)}** "
                     f"({((b_total / a_total - 1) * 100):+.0f}%)")
        if a_tok_total is not None and b_tok_total is not None and a_tok_total:
            lines.append(f"- Token overhead: **{fmt_tokens(b_tok_total - a_tok_total)}** "
                         f"({((b_tok_total / a_tok_total - 1) * 100):+.0f}%)")
        else:
            lines.append("- Token overhead: **—** (unmeasured tokens on one arm)")
        if delta_resolved > 0:
            lines.append(f"- Extra tasks resolved by B: **{delta_resolved}** → "
                         f"**{fmt_usd((b_total - a_total) / delta_resolved)}** per extra resolve")
            if a_tok_total is not None and b_tok_total is not None:
                lines.append(f"- Tokens per extra resolve: "
                             f"**{fmt_tokens((b_tok_total - a_tok_total) / delta_resolved)}**")
        else:
            lines.append(f"- Extra tasks resolved by B: **{delta_resolved}** — "
                         "cost per extra resolve is undefined; the spec arm's return "
                         "at this N is in test quality (see the mutation report), "
                         "not in resolved count.")
        lines.append("")

    total_all = sum(d["infer_total"] for d in per_arm.values()) + spec_total + verdict_total
    lines.append(f"**Panel total (measured): {fmt_usd(total_all)}**\n")

    out_path = Path(args.out).expanduser() if args.out else REPORT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    log(f"stage 10 ok: {out_path}")
    for arm, d in per_arm.items():
        n = d["n_measured"]
        tok_total = tokens_total(d["infer_tokens"])
        log(f"  arm {arm}: {fmt_usd(d['infer_total'])} over {n} task(s)"
            + (f", mean {fmt_usd(d['infer_total']/n)}" if n else "")
            + f", {fmt_tokens(tok_total)} tokens")
    log(f"  specs {fmt_usd(spec_total)} · verdicts {fmt_usd(verdict_total)} "
        f"· panel {fmt_usd(total_all)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

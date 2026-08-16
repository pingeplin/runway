#!/usr/bin/env python3
"""Stage 05b — Arm C report: does the `/verify` referee beat a bare second pass?

Three arms over the same task ids:

  B   original + spec (stage 03)
  C   B's patch + the headless referee verdict, re-implemented from scratch
  C0  B's patch + a generic "review it yourself" instruction — the control that
      isolates the referee's contribution from the mere second-iteration effect

Reads the same `fb eval` outputs as stage 05 and reuses its report loader and
exact-McNemar helper, so the two reports cannot drift apart.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from _common import (
    RESULTS_DIR,
    add_config_arg,
    die,
    load_config,
    load_script_module,
    read_json,
    read_runs,
)

VERDICTS_DIR = RESULTS_DIR / "verdicts"
OUT_PATH = RESULTS_DIR / "report_c.md"

ARMS = ("B", "C", "C0")

CAVEATS = """## Caveats

- **C0 is the attribution control.** C − B mixes "the referee helped" with
  "a second pass helps". Only **C − C0** isolates the referee's contribution;
  read C − C0 first and C − B second.
- **The referee ran blind to the test suite.** The verify round happens on the
  host, where the task's dependencies are not installed, so the referee scored
  scenario coverage, anti-vacuity, desiderata and implementation quality
  statically. A verdict that a green/red suite would have changed is invisible.
- **Round 2 restarts from the pristine repo.** Both C and C0 re-implement from
  scratch with the previous patch quoted in the prompt; neither continues an
  existing working tree, so this measures feedback quality, not patch repair.
- **Oracle masking is applied upstream.** Stage 01 writes its spec against a
  tree that has been masked exactly as `fb infer` masks it — the dataset's
  mask patch applied and the FAIL_TO_PASS test files deleted
  (`_common.mask_reference_solution`; a task whose mask fails to apply is
  hard-failed, and each spec's `.meta.json` records `mask_applied` /
  `f2p_deleted`). The verify round reproduces the same masking, so the referee
  saw what the implementing agent saw. An earlier, pre-masking run of this
  harness did leak the reference solution into the spec stage and its results
  were discarded.
- **Single seed, small N.** Discordant-pair counts are expected to be
  single-digit; the McNemar p-values are directional evidence only.
- **Cost is one-sided.** Arm C additionally pays the verify-round cost shown
  below, on top of Arm B's spec cost and both arms' inference cost.
- **Residual prompt confound.** C and C0 statements differ only in the feedback
  section, but C0's closing instruction still says "addressing the verdict",
  which for C0 refers to its own self-review.
"""


def load_verdict_meta(task_id: str) -> dict[str, Any]:
    path = VERDICTS_DIR / f"{task_id}.meta.json"
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_arg(parser)
    parser.add_argument("--report-b", default=None, help="Override Arm B report.json path")
    parser.add_argument("--report-c", default=None, help="Override Arm C report.json path")
    parser.add_argument("--report-c0", default=None, help="Override Arm C0 report.json path")
    parser.add_argument("--task-ids-file", default=None,
                        help="Newline-separated ids (default: runs.json C.task_ids)")
    parser.add_argument("--out", default=None, help="Override results/report_c.md path")
    args = parser.parse_args()

    stage05 = load_script_module("05_report.py")
    cfg = load_config(args.config)
    runs = read_runs()

    overrides = {"B": args.report_b, "C": args.report_c, "C0": args.report_c0}
    paths: dict[str, Path] = {}
    results: dict[str, dict[str, dict[str, Any]]] = {}
    for arm in ARMS:
        override = overrides[arm]
        if override:
            paths[arm] = Path(override).resolve()
        else:
            recorded = (runs.get(arm) or {}).get("report_json")
            if not recorded:
                die(f"no report recorded for arm {arm} — score it first "
                    f"(stage 04 for B, 06 --stage eval for C/C0) or pass --report-{arm.lower()}")
            paths[arm] = Path(recorded)
        results[arm] = stage05.load_arm_results(paths[arm])

    if args.task_ids_file:
        task_ids = [
            line.strip()
            for line in Path(args.task_ids_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        task_ids = list((runs.get("C") or {}).get("task_ids") or [])
    if not task_ids:
        task_ids = sorted(set(results["C"]) & set(results["C0"]))
    if not task_ids:
        die("no task ids to report on")
    task_ids = sorted(task_ids)

    resolved: dict[str, int] = {arm: 0 for arm in ARMS}
    rate_sum: dict[str, float] = {arm: 0.0 for arm in ARMS}
    total_cost = total_seconds = 0.0
    rows: list[str] = []

    def cell(arm: str, task_id: str, key: str) -> Any:
        entry = results[arm].get(task_id)
        return entry[key] if entry else None

    for task_id in task_ids:
        res = {arm: cell(arm, task_id, "resolved") for arm in ARMS}
        rate = {arm: cell(arm, task_id, "pass_rate") for arm in ARMS}
        for arm in ARMS:
            resolved[arm] += 1 if res[arm] else 0
            rate_sum[arm] += rate[arm] or 0.0

        meta = load_verdict_meta(task_id)
        cost, seconds = meta.get("cost_usd"), meta.get("wall_seconds")
        if isinstance(cost, (int, float)):
            total_cost += cost
        if isinstance(seconds, (int, float)):
            total_seconds += seconds

        rows.append(
            f"| `{task_id}` | "
            + " | ".join(stage05.fmt_bool(res[arm]) for arm in ARMS)
            + " | "
            + " | ".join(stage05.fmt_num(rate[arm], ".2f") for arm in ARMS)
            + f" | {stage05.fmt_num(cost, '.4f')} | {stage05.fmt_num(seconds, '.0f')} |"
        )

    n = len(task_ids)

    def discordant(left: str, right: str) -> tuple[int, int, float]:
        """b = left-only resolved, c = right-only resolved, plus the exact p."""
        b = c = 0
        for task_id in task_ids:
            rl, rr = cell(left, task_id, "resolved"), cell(right, task_id, "resolved")
            if rl and not rr:
                b += 1
            elif rr and not rl:
                c += 1
        return b, c, stage05.mcnemar_exact_p(b, c)

    eval_cfg = cfg.get("eval", {})
    lines: list[str] = []
    lines.append("# Blueprint /verify referee loop on FeatureBench (Arm C)\n")
    lines.append(
        f"Panel: `{eval_cfg.get('dataset', '')}` split `{eval_cfg.get('split', '')}`, "
        f"{n} paired task(s).  \n"
        "Arm B = original + spec (round 1). Arm C = round 2 with the `/verify` referee "
        "verdict. Arm C0 = round 2 with a generic self-review instruction (control).  \n"
        f"Implementing agent: `claude_code` / `{cfg.get('infer', {}).get('model', '')}` in all "
        f"three arms. Referee model: `{cfg.get('verify', {}).get('model', '')}`.\n"
    )
    lines.append("Reports: " + " · ".join(f"{arm} `{paths[arm]}`" for arm in ARMS) + "\n")

    lines.append("## Per-task results\n")
    lines.append("| task id | B resolved | C resolved | C0 resolved | B pass_rate | "
                 "C pass_rate | C0 pass_rate | verdict cost USD | verdict seconds |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    lines.extend(rows)
    lines.append(
        f"| **totals ({n})** | "
        + " | ".join(f"**{resolved[arm]}**" for arm in ARMS)
        + " | "
        + " | ".join(f"**{(rate_sum[arm] / n if n else 0):.2f}**" for arm in ARMS)
        + f" | **{total_cost:.4f}** | **{total_seconds:.0f}** |\n"
    )

    lines.append("## Paired comparisons\n")
    lines.append(
        "- Resolved: B **{b}/{n}**, C **{c}/{n}**, C0 **{c0}/{n}**".format(
            b=resolved["B"], c=resolved["C"], c0=resolved["C0"], n=n
        )
    )
    for left, right, label in (
        ("C", "C0", "referee vs bare second pass (the attribution test)"),
        ("C", "B", "referee loop vs spec-only round 1"),
        ("C0", "B", "bare second pass vs spec-only round 1"),
    ):
        b, c, p = discordant(left, right)
        lines.append(
            f"- **{left} − {right}** ({label}): delta **{resolved[left] - resolved[right]:+d}**, "
            f"discordant b({left}-only)=**{b}** c({right}-only)=**{c}**, exact McNemar "
            f"**p = {p:.4f}**"
        )
    lines.append(
        f"- Verify-round cost: **${total_cost:.4f}** over {n} task(s), {total_seconds:.0f}s wall\n"
    )

    lines.append(CAVEATS)

    out_path = Path(args.out).resolve() if args.out else OUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"stage 05b ok: {out_path}")
    b, c, p = discordant("C", "C0")
    print(f"  B {resolved['B']}/{n} · C {resolved['C']}/{n} · C0 {resolved['C0']}/{n} "
          f"· C-vs-C0 b={b} c={c} p={p:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

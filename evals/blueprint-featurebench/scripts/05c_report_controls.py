#!/usr/bin/env python3
"""Stage 05c — control-arm report: does Arm B beat the cheaper explanations?

Four arms over the same task ids:

  A       original problem statement                      (stage 03)
  A_hint  original + one breadth sentence                 (stage 14)
  A_plan  original + a generic brief, blueprint disabled  (stage 14)
  B       original + blueprint spec                       (stages 01-03)

B − A_plan separates blueprint's methodology from "any upfront document";
B − A_hint separates it from the one mechanism the 4.0 specs were seen to
carry. Reuses stage 05's loader and exact McNemar so the reports cannot drift.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from _common import (
    BRIEFS_DIR,
    RESULTS_DIR,
    SPECS_DIR,
    add_config_arg,
    die,
    load_config,
    load_script_module,
    read_json,
    read_runs,
    read_tasks,
    spec_ok_ids,
)

OUT_PATH = RESULTS_DIR / "report_controls.md"

ARMS = ("A", "A_hint", "A_plan", "B")
DOC_DIRS = {"A_plan": BRIEFS_DIR, "B": SPECS_DIR}
COMPARISONS = (
    ("B", "A_plan", "blueprint spec vs a generic brief (the attribution test)"),
    ("B", "A_hint", "blueprint spec vs one breadth sentence"),
    ("A_plan", "A", "generic brief vs nothing"),
    ("A_hint", "A", "breadth sentence vs nothing"),
    ("B", "A", "blueprint spec vs nothing"),
)
# Per-task pass-rate moves smaller than this count as ties.
TIE = 0.05

CAVEATS = """## Caveats

- **Small N, one repository, one seed per arm.** Per-task outcomes swing hard
  with document wording (the same `vo` task scored 0.95 / 0.00 / 1.00 under
  three spec variants), so every delta here is directional evidence only.
- **A_plan's cost is reported, not matched.** The brief writer spends what it
  spends; read its document cost next to B's before reading its pass rate.
- **A_hint encodes a mechanism found by reading 4.0's specs.** It is a ceiling
  test of that mechanism, not a product a user would have written blind.
- **The benchmark rewards breadth.** FeatureBench strips whole features, so
  any document that widens scope is favoured; a task shape that penalises
  over-reach would grade all three treatments differently.
- **Self-run evaluation of our own plugin.**
"""


def parse_report_overrides(items: list[str]) -> dict[str, Path]:
    overrides: dict[str, Path] = {}
    for item in items:
        arm, sep, path = item.partition("=")
        if not sep or arm not in ARMS:
            die(f"--report expects ARM=PATH with ARM in {', '.join(ARMS)}: {item}")
        overrides[arm] = Path(path).resolve()
    return overrides


def load_doc_meta(arm: str, task_id: str) -> dict[str, Any]:
    directory = DOC_DIRS.get(arm)
    path = directory / f"{task_id}.meta.json" if directory else None
    if path is None or not path.exists():
        return {}
    try:
        return read_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_arg(parser)
    parser.add_argument("--report", action="append", default=[], metavar="ARM=PATH",
                        help="Override an arm's fb eval report.json (repeatable)")
    parser.add_argument("--task-ids-file", default=None,
                        help="Newline-separated ids (default: tasks.json spec_ok ids)")
    parser.add_argument("--out", default=None, help="Override results/report_controls.md path")
    args = parser.parse_args()

    stage05 = load_script_module("05_report.py")
    cfg = load_config(args.config)
    runs = read_runs()
    overrides = parse_report_overrides(args.report)

    paths: dict[str, Path] = {}
    for arm in ARMS:
        recorded = (runs.get(arm) or {}).get("report_json")
        if arm in overrides:
            paths[arm] = overrides[arm]
        elif recorded:
            paths[arm] = Path(recorded)
    arms = [arm for arm in ARMS if arm in paths]
    omitted = [arm for arm in ARMS if arm not in paths]
    if len(arms) < 2:
        die(f"need at least two scored arms, have {arms or 'none'} — run stage 04 / 14 --stage eval")
    results = {arm: stage05.load_arm_results(paths[arm]) for arm in arms}

    if args.task_ids_file:
        task_ids = [l.strip() for l in Path(args.task_ids_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        task_ids = spec_ok_ids(read_tasks())
    task_ids = sorted(task_ids)
    if not task_ids:
        die("no task ids to report on")
    n = len(task_ids)

    def rate(arm: str, task_id: str) -> float | None:
        entry = results[arm].get(task_id)
        return entry["pass_rate"] if entry else None

    def resolved(arm: str, task_id: str) -> bool | None:
        entry = results[arm].get(task_id)
        return entry["resolved"] if entry else None

    def cell(arm: str, task_id: str) -> str:
        value = rate(arm, task_id)
        return stage05.fmt_num(value, ".2f") + (" ✓" if resolved(arm, task_id) else "")

    doc_arms = [arm for arm in arms if arm in DOC_DIRS]
    lines: list[str] = ["# Blueprint spec vs control arms on FeatureBench\n"]
    eval_cfg = cfg.get("eval", {})
    lines.append(
        f"Panel: `{eval_cfg.get('dataset', '')}` split `{eval_cfg.get('split', '')}`, {n} task(s).  \n"
        "A = original statement. A_hint = + one breadth sentence. "
        "A_plan = + a generic brief (blueprint disabled). B = + blueprint spec.  \n"
        f"Implementing agent: `claude_code` / `{cfg.get('infer', {}).get('model', '')}` in every arm.\n"
    )
    lines.append("Reports: " + " · ".join(f"{arm} `{paths[arm]}`" for arm in arms) + "\n")
    if omitted:
        lines.append(f"Not scored, omitted: {', '.join(omitted)}.\n")

    lines.append("## Per-task pass rate (✓ = resolved)\n")
    header = ["task id", *arms, *(f"{arm} doc USD" for arm in doc_arms)]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for task_id in task_ids:
        costs = [stage05.fmt_num(load_doc_meta(arm, task_id).get("cost_usd"), ".2f") for arm in doc_arms]
        lines.append(f"| `{task_id}` | " + " | ".join([*(cell(arm, task_id) for arm in arms), *costs]) + " |")
    lines.append("")

    lines.append("## Per arm\n")
    lines.append("| arm | resolved | mean pass rate | doc cost / task | doc wall / task |")
    lines.append("|---|---|---|---|---|")
    means: dict[str, float] = {}
    for arm in arms:
        means[arm] = sum(rate(arm, t) or 0.0 for t in task_ids) / n
        n_resolved = sum(1 for t in task_ids if resolved(arm, t))
        metas = [load_doc_meta(arm, t) for t in task_ids] if arm in DOC_DIRS else []
        cost = mean([m["cost_usd"] for m in metas if isinstance(m.get("cost_usd"), (int, float))])
        wall = mean([m["wall_seconds"] for m in metas if isinstance(m.get("wall_seconds"), (int, float))])
        cost_s = f"${cost:.2f}" if cost is not None else "—"
        wall_s = f"{wall / 60:.0f} min" if wall is not None else "—"
        lines.append(f"| {arm} | {n_resolved}/{n} | {means[arm]:.2f} | {cost_s} | {wall_s} |")
    lines.append("")

    lines.append("## Paired comparisons\n")
    for left, right, label in COMPARISONS:
        if left not in results or right not in results:
            continue
        up = down = tied = 0
        b = c = 0
        for task_id in task_ids:
            rl, rr = rate(left, task_id), rate(right, task_id)
            if rl is not None and rr is not None:
                delta = rl - rr
                if abs(delta) < TIE:
                    tied += 1
                elif delta > 0:
                    up += 1
                else:
                    down += 1
            sl, sr = resolved(left, task_id), resolved(right, task_id)
            if sl and not sr:
                b += 1
            elif sr and not sl:
                c += 1
        lines.append(
            f"- **{left} − {right}** ({label}): mean pass rate **{means[left] - means[right]:+.2f}**, "
            f"per task {up} up / {down} down / {tied} tied (|Δ| < {TIE}), "
            f"discordant resolved b({left}-only)=**{b}** c({right}-only)=**{c}**, "
            f"exact McNemar **p = {stage05.mcnemar_exact_p(b, c):.4f}**"
        )
    lines.append("")
    lines.append(CAVEATS)

    out_path = Path(args.out).resolve() if args.out else OUT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"stage 05c ok: {out_path}")
    print("  " + " · ".join(f"{arm} {means[arm]:.2f}" for arm in arms))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

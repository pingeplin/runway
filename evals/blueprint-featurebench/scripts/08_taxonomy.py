#!/usr/bin/env python3
"""Stage 08 — failure taxonomy: classify WHY each failing (task, arm) cell
failed, using a host-side `claude -p` rater.

Real layout discovered under results/infer_arm_{a,b}/<timestamp>/eval_outputs/
(2026-08-15 pilot, astropy + metaflow tasks) is:

    eval_outputs/<instance_id>/attempt-1/
        report.json                    # {instance_id: {resolved, pass_rate,
                                        #  patch_successfully_applied,
                                        #  tests_status: {FAIL_TO_PASS, PASS_TO_PASS}}}
        patch.diff                     # duplicate of output.jsonl's model_patch
        run_instance.log               # container-orchestration log; mostly
                                        # docker/setup noise, and it only embeds
                                        # a *truncated* copy of test_output.txt
        test_output.txt                # full pytest output for the FAIL_TO_PASS
                                        # run — this is the log that directly
                                        # produced `pass_rate`/`resolved`
        test_output_p2p_<name>.txt     # one pytest output per PASS_TO_PASS
                                        # (regression) test module

We use `test_output.txt` as the primary failing-test log: it is the direct,
untruncated pytest transcript for the tests that determine the score, unlike
run_instance.log (orchestration noise) or the per-module P2P files (usually
irrelevant — P2P tests exist to catch regressions, not to explain a F2P
failure). The one case where test_output.txt alone is misleading is when the
agent passes every FAIL_TO_PASS test but still gets resolved=false because it
broke a PASS_TO_PASS (regression) test — there test_output.txt looks clean,
so we fall back to whichever test_output_p2p_*.txt file(s) show pytest
failures (see `pick_test_log`).

Original problem_statement comes from Arm A's own output.jsonl
(`task_metadata.problem_statement`), never from the HuggingFace dataset — Arm
A always ran against the *official* dataset, so its task_metadata carries the
untouched statement, and reading it avoids any network dependency here.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from _common import (
    EVAL_ROOT,
    RESULTS_DIR,
    SPECS_DIR,
    SPEC_SEPARATOR,
    add_config_arg,
    die,
    load_config,
    read_json,
    read_runs,
    write_json,
)

PROMPT_TEMPLATE = EVAL_ROOT / "prompts" / "taxonomy.md"
TAXONOMY_DIR = RESULTS_DIR / "taxonomy"
TAXONOMY_REPORT_PATH = RESULTS_DIR / "taxonomy_report.md"

# Truncation budgets (~chars). The problem statement and patch are truncated
# from the *head* (file list / opening hunks / opening ask are the
# informative part); the test log is truncated from the *tail* (the pytest
# failure summary lives at the end of the run).
PROBLEM_STATEMENT_MAX_CHARS = 6000
MODEL_PATCH_MAX_CHARS = 6000
TEST_LOG_MAX_CHARS = 4000

ALLOWED_CLASSES = {"spec_wrong", "impl_wrong", "env_or_flaky", "unclear"}
ALLOWED_CONTRIB = {"helped", "neutral", "harmed"}

CAVEATS = """## Caveats

- **Single-rater LLM.** One `claude -p` classification pass per cell, no
  cross-check, no human adjudication. Treat every row as directional
  evidence, not a verdict.
- **Blind to ground truth.** The rater sees the same task-side evidence a
  human triager would (statement, spec, patch, test log) but never the
  reference patch or reference tests — its `spec_wrong`/`impl_wrong` call is
  an inference, not a fact.
- **Truncated bundles.** Problem statement and patch are truncated to
  ~6k chars (head), the test log to ~4k chars (tail). A failure whose
  evidence lives outside those windows will read as `unclear`.
"""


def log(msg: str) -> None:
    print(msg, flush=True)


def truncate_head(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [truncated, {len(text)} chars total]"


def truncate_tail(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"[... truncated, {len(text)} chars total, showing tail] ...\n" + text[-max_chars:]


def load_predictions(output_jsonl: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not output_jsonl.exists():
        return rows
    with open(output_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            iid = row.get("instance_id")
            if iid:
                rows[iid] = row
    return rows


def load_instance_report(eval_outputs_dir: Path, instance_id: str) -> dict[str, Any] | None:
    path = eval_outputs_dir / instance_id / "attempt-1" / "report.json"
    if not path.exists():
        return None
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    entry = data.get(instance_id) if isinstance(data, dict) else None
    return entry if isinstance(entry, dict) else None


def pick_test_log(attempt_dir: Path, report_entry: dict[str, Any] | None) -> tuple[str, str]:
    """Return (tail_text, source_description). See module docstring for the
    selection rule: FAIL_TO_PASS log by default, PASS_TO_PASS regression logs
    when F2P is all-green but the cell is still unresolved.
    """
    ts = (report_entry or {}).get("tests_status") or {}
    f2p_failures = (ts.get("FAIL_TO_PASS") or {}).get("failure") or []
    primary = attempt_dir / "test_output.txt"

    if not f2p_failures and (report_entry or {}).get("resolved") is False:
        p2p_files = sorted(attempt_dir.glob("test_output_p2p_*.txt"))
        chunks = []
        for pf in p2p_files:
            text = pf.read_text(encoding="utf-8", errors="replace")
            if "FAILED" in text or "ERROR" in text or " failed" in text.lower():
                chunks.append(f"--- {pf.name} ---\n{text}")
        if chunks:
            combined = "\n\n".join(chunks)
            return (
                truncate_tail(combined, TEST_LOG_MAX_CHARS),
                "test_output_p2p_*.txt — FAIL_TO_PASS all green but resolved=false, "
                "so the break is in a PASS_TO_PASS regression",
            )

    if primary.exists():
        return (
            truncate_tail(primary.read_text(encoding="utf-8", errors="replace"), TEST_LOG_MAX_CHARS),
            "test_output.txt (FAIL_TO_PASS pytest output)",
        )
    return "(no test log files found under this attempt dir)", "none"


def format_outcome_header(report_entry: dict[str, Any] | None) -> str:
    if not report_entry:
        return "(no per-instance report.json available for this cell)"
    ts = report_entry.get("tests_status") or {}
    f2p = ts.get("FAIL_TO_PASS") or {}
    p2p = ts.get("PASS_TO_PASS") or {}
    return "\n".join([
        f"resolved: {report_entry.get('resolved')}",
        f"pass_rate (FAIL_TO_PASS): {report_entry.get('pass_rate')}",
        f"patch_is_None: {report_entry.get('patch_is_None')}, "
        f"patch_successfully_applied: {report_entry.get('patch_successfully_applied')}",
        f"FAIL_TO_PASS failing: {f2p.get('failure') or []}",
        f"PASS_TO_PASS failing (regressions): {p2p.get('failure') or []}",
    ])


def original_problem_statement(task_id: str, canonical: dict[str, str], arm: str, own_row: dict[str, Any]) -> str:
    if task_id in canonical:
        return canonical[task_id]
    # Fallback (Arm A predictions unavailable): strip the appended spec back
    # off this cell's own mutated statement, if it looks mutated.
    raw = ((own_row.get("task_metadata") or {}).get("problem_statement")) or ""
    if arm != "A" and SPEC_SEPARATOR in raw:
        return raw.split(SPEC_SEPARATOR, 1)[0]
    return raw


def build_bundle(
    arm: str,
    task_id: str,
    canonical_ps: dict[str, str],
    predictions_by_arm: dict[str, dict[str, dict[str, Any]]],
    eval_outputs_dirs: dict[str, Path],
) -> dict[str, Any]:
    own_row = predictions_by_arm.get(arm, {}).get(task_id, {})
    ps = original_problem_statement(task_id, canonical_ps, arm, own_row)

    spec_text = ""
    if arm != "A":
        spec_path = SPECS_DIR / f"{task_id}.md"
        if spec_path.exists():
            spec_text = spec_path.read_text(encoding="utf-8", errors="replace")

    model_patch = own_row.get("model_patch") or ""
    attempt_dir = eval_outputs_dirs[arm] / task_id / "attempt-1"
    report_entry = load_instance_report(eval_outputs_dirs[arm], task_id)
    test_log_tail, test_log_source = pick_test_log(attempt_dir, report_entry)

    return {
        "problem_statement": truncate_head(ps, PROBLEM_STATEMENT_MAX_CHARS),
        "spec_text": spec_text,
        "model_patch": truncate_head(model_patch, MODEL_PATCH_MAX_CHARS),
        "test_log_tail": test_log_tail,
        "test_log_source": test_log_source,
        "outcome_header": format_outcome_header(report_entry),
        "raw_sizes": {
            "problem_statement_chars": len(ps),
            "spec_chars": len(spec_text),
            "model_patch_chars": len(model_patch),
        },
    }


def render_prompt(template: str, task_id: str, arm: str, bundle: dict[str, Any]) -> str:
    if arm == "A":
        spec_section = "(Arm A — control condition; the agent saw only the original problem statement above, no spec.)\n"
    elif bundle["spec_text"]:
        spec_section = bundle["spec_text"]
    else:
        spec_section = "(no spec file found under results/specs/ for this task — spec influence is unknown.)\n"

    text = template
    text = text.replace("{task_id}", task_id)
    text = text.replace("{arm}", arm)
    text = text.replace("{outcome_header}", bundle["outcome_header"])
    text = text.replace("{problem_statement}", bundle["problem_statement"])
    text = text.replace("{spec_section}", spec_section)
    text = text.replace("{model_patch}", bundle["model_patch"])
    text = text.replace("{test_log_source}", bundle["test_log_source"])
    text = text.replace("{test_log_tail}", bundle["test_log_tail"])
    return text


def run_claude(
    claude_cmd: str,
    prompt: str,
    model: str,
    claude_args: list[str],
    timeout_s: int,
    cwd: Path,
) -> tuple[dict[str, Any], str | None]:
    """Copied from 01_make_specs.py's run_claude: same argv shape, same
    JSON/cost/timeout handling. No workspace is needed here (the rater
    classifies from the bundle in the prompt, not from a checked-out repo),
    so cwd is just EVAL_ROOT.
    """
    argv = [claude_cmd, "-p", prompt, "--output-format", "json", *claude_args, "--model", model]
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
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

    if isinstance(parsed, list):
        parsed = next((e for e in reversed(parsed) if isinstance(e, dict) and "result" in e), {})
    if not isinstance(parsed, dict):
        return payload, "claude JSON payload had an unexpected shape"

    payload.update(parsed)
    if proc.returncode != 0:
        return payload, f"claude exited {proc.returncode}"
    return payload, None


def parse_classification(result_text: str) -> tuple[dict[str, Any], str | None]:
    """Defensive parse: the model was told the final line must be a JSON
    object. Scan lines from the end (not a greedy `{.*}` regex — that spans
    the first '{' to the last '}' across the whole reply and breaks the
    moment there is any brace in the prose above it) and take the first line
    that parses as a JSON object.
    """
    lines = [l.strip() for l in (result_text or "").splitlines() if l.strip()]
    if not lines:
        return {}, "empty result text"
    for line in reversed(lines):
        candidate = line.strip("`").strip() if line.startswith("```") or line.endswith("```") else line
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj, None
    return {}, "no JSON object found on any line of result text"


def process_cell(
    arm: str,
    task_id: str,
    bundle: dict[str, Any],
    template: str,
    claude_cmd: str,
    model: str,
    claude_args: list[str],
    timeout_s: int,
) -> dict[str, Any]:
    prompt = render_prompt(template, task_id, arm, bundle)
    started = time.time()
    payload, error = run_claude(claude_cmd, prompt, model, claude_args, timeout_s, cwd=EVAL_ROOT)
    wall_seconds = round(time.time() - started, 2)

    meta: dict[str, Any] = {
        "instance_id": task_id,
        "arm": arm,
        "model": model,
        "cost_usd": payload.get("total_cost_usd"),
        "duration_ms": payload.get("duration_ms"),
        "wall_seconds": wall_seconds,
        "num_turns": payload.get("num_turns"),
        "usage": payload.get("usage"),
        "returncode": payload.get("returncode"),
        "bundle_sizes": bundle["raw_sizes"],
    }
    if error:
        meta.update(ok=False, error=error, classification=None, spec_contribution=None, rationale=None)
        return meta

    obj, parse_error = parse_classification(payload.get("result") or "")
    if parse_error:
        # Recorded as-is; per the resumability contract this cell is skipped
        # on future runs unless --force is passed, same as any other cell.
        meta.update(
            ok=False,
            error=f"parse_error: {parse_error}",
            classification="unclear",
            spec_contribution=None,
            rationale=(payload.get("result") or "")[:500],
        )
        return meta

    cls = obj.get("class")
    if cls not in ALLOWED_CLASSES:
        meta.update(
            ok=False,
            error=f"invalid class field: {cls!r}",
            classification="unclear",
            spec_contribution=None,
            rationale=str(obj.get("rationale") or ""),
        )
        return meta

    contrib = obj.get("spec_contribution")
    if arm == "A" or contrib not in ALLOWED_CONTRIB:
        contrib = None

    meta.update(ok=True, error=None, classification=cls, spec_contribution=contrib, rationale=str(obj.get("rationale") or ""))
    return meta


def discover_failing_cells(runs: dict[str, Any], arm_filter: list[str] | None, task_filter: list[str] | None) -> list[tuple[str, str]]:
    """(arm, task_id) pairs with an eval report and resolved == False.

    A task/arm with no per-instance report at all is logged and skipped
    (consistent with 05_report.py rendering '—' rather than counting it as
    unresolved).
    """
    arms = arm_filter if arm_filter else sorted(runs.keys())
    cells: list[tuple[str, str]] = []
    for arm in arms:
        entry = runs.get(arm)
        if not entry:
            log(f"warning: arm {arm} not present in runs.json, skipping")
            continue
        eval_outputs_dir = entry.get("eval_outputs_dir")
        if not eval_outputs_dir:
            die(f"arm {arm} has no eval_outputs_dir recorded in runs.json — run stage 04 first")
        eval_outputs_dir = Path(eval_outputs_dir)
        task_ids = entry.get("task_ids") or []
        if not task_ids:
            die(f"arm {arm} has no task_ids recorded in runs.json")
        for tid in task_ids:
            if task_filter and tid not in task_filter:
                continue
            report_entry = load_instance_report(eval_outputs_dir, tid)
            if report_entry is None:
                log(f"note: no per-instance report for {tid} (arm {arm}), skipping")
                continue
            if bool(report_entry.get("resolved", False)):
                continue
            cells.append((arm, tid))
    cells.sort(key=lambda c: (c[1], c[0]))
    return cells


def escape_md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def build_taxonomy_report(out_path: Path = TAXONOMY_REPORT_PATH) -> None:
    """Rebuilt from a full scan of results/taxonomy/*/*.json each run, so it
    always reflects every cell analyzed so far, not just the current
    selection.
    """
    records: list[tuple[str, str, dict[str, Any]]] = []
    if TAXONOMY_DIR.is_dir():
        for arm_dir in sorted(TAXONOMY_DIR.iterdir()):
            if not arm_dir.is_dir():
                continue
            for f in sorted(arm_dir.glob("*.json")):
                try:
                    data = read_json(f)
                except (OSError, json.JSONDecodeError):
                    continue
                records.append((f.stem, arm_dir.name, data))
    records.sort(key=lambda r: (r[0], r[1]))

    totals: dict[str, int] = {c: 0 for c in ALLOWED_CLASSES}
    rows = []
    for task_id, arm, data in records:
        cls = data.get("classification") or "unclear"
        totals[cls] = totals.get(cls, 0) + 1
        contrib = data.get("spec_contribution") or "—"
        rationale = escape_md_cell(data.get("rationale") or "")
        if len(rationale) > 160:
            rationale = rationale[:157] + "..."
        flag = "" if data.get("ok") else " ⚠"
        rows.append(f"| `{task_id}` | {arm} | {cls}{flag} | {contrib} | {rationale or '—'} |")

    lines: list[str] = []
    lines.append("# Failure taxonomy\n")
    lines.append(
        "Per-cell classification of WHY a (task, arm) combination failed: "
        "`spec_wrong` (blueprint's spec misled the agent — Arm B/treatment "
        "only), `impl_wrong` (agent failed despite a correct brief), "
        "`env_or_flaky` (harness/test environment), `unclear`.\n"
    )
    lines.append("## Per-cell classifications\n")
    lines.append("| task id | arm | class | spec_contribution | rationale |")
    lines.append("|---|---|---|---|---|")
    lines.extend(rows if rows else ["| — | — | — | — | (no cells analyzed yet) |"])
    lines.append("")
    lines.append("## Totals\n")
    lines.append("| class | count |")
    lines.append("|---|---|")
    for cls in sorted(ALLOWED_CLASSES):
        lines.append(f"| {cls} | {totals.get(cls, 0)} |")
    lines.append(f"| **total cells** | **{len(records)}** |\n")
    lines.append(CAVEATS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_arg(parser)
    parser.add_argument("--task-id", action="append", default=None, help="Restrict to this task id (repeatable)")
    parser.add_argument("--arm", action="append", default=None, help="Restrict to this arm (repeatable)")
    parser.add_argument("--force", action="store_true", help="Redo cells that already have a taxonomy json")
    parser.add_argument("--dry-run", action="store_true", help="List selected cells + bundle sizes, call no claude")
    parser.add_argument("--claude-cmd", default="claude", help="Path to the claude binary (for smoke tests)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    taxonomy_cfg = cfg.get("taxonomy", {})
    model = taxonomy_cfg.get("model", "claude-sonnet-4-5")
    timeout_s = int(taxonomy_cfg.get("timeout_seconds", 300))
    claude_args = list(taxonomy_cfg.get("claude_args", []))

    if not PROMPT_TEMPLATE.exists():
        die(f"prompt template missing: {PROMPT_TEMPLATE}")
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")

    runs = read_runs()
    if not runs:
        die(f"{RESULTS_DIR / 'runs.json'} not found or empty — run stages 03/04 first")

    cells = discover_failing_cells(runs, args.arm, args.task_id)
    if not cells:
        log("stage 08: no failing (task, arm) cells found — nothing to classify")
        build_taxonomy_report()
        return 0

    predictions_by_arm: dict[str, dict[str, dict[str, Any]]] = {}
    eval_outputs_dirs: dict[str, Path] = {}
    for arm, entry in runs.items():
        output_jsonl = entry.get("output_jsonl")
        if not output_jsonl:
            continue
        predictions_by_arm[arm] = load_predictions(Path(output_jsonl))
        eod = entry.get("eval_outputs_dir")
        if eod:
            eval_outputs_dirs[arm] = Path(eod)

    canonical_ps: dict[str, str] = {}
    for tid, row in predictions_by_arm.get("A", {}).items():
        ps = (row.get("task_metadata") or {}).get("problem_statement")
        if ps:
            canonical_ps[tid] = ps

    log(f"stage 08: {len(cells)} failing cell(s) selected")

    if args.dry_run:
        for arm, tid in cells:
            bundle = build_bundle(arm, tid, canonical_ps, predictions_by_arm, eval_outputs_dirs)
            out_path = TAXONOMY_DIR / arm / f"{tid}.json"
            skip = " (existing json, would skip)" if out_path.exists() and not args.force else ""
            sizes = bundle["raw_sizes"]
            log(
                f"  {tid} [{arm}] ps={sizes['problem_statement_chars']}c "
                f"spec={sizes['spec_chars']}c patch={sizes['model_patch_chars']}c "
                f"test_log_src={bundle['test_log_source']!r}{skip}"
            )
        return 0

    n_ok = 0
    for arm, tid in cells:
        out_path = TAXONOMY_DIR / arm / f"{tid}.json"
        if out_path.exists() and not args.force:
            log(f"  {tid} [{arm}]: cached, skipping")
            try:
                if read_json(out_path).get("ok"):
                    n_ok += 1
            except (OSError, json.JSONDecodeError):
                pass
            continue
        if arm not in predictions_by_arm or arm not in eval_outputs_dirs:
            log(f"  {tid} [{arm}]: FAILED — arm missing output_jsonl/eval_outputs_dir in runs.json")
            continue

        bundle = build_bundle(arm, tid, canonical_ps, predictions_by_arm, eval_outputs_dirs)
        meta = process_cell(arm, tid, bundle, template, args.claude_cmd, model, claude_args, timeout_s)
        write_json(out_path, meta)
        if meta.get("ok"):
            n_ok += 1
            cost = meta.get("cost_usd")
            cost_s = f"${cost:.4f}" if isinstance(cost, (int, float)) else "cost n/a"
            log(f"  {tid} [{arm}]: {meta['classification']} / {meta['spec_contribution']} ({cost_s})")
        else:
            log(f"  {tid} [{arm}]: FAILED — {meta.get('error')}")

    build_taxonomy_report()
    log(f"stage 08 done: {n_ok}/{len(cells)} cells ok -> {TAXONOMY_REPORT_PATH}")
    return 0 if n_ok == len(cells) else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
# Run the control-arm panel on one resident image: A and B again, plus the
# stage-14 controls A_plan and A_hint — same day, same pinned in-container
# Claude Code — then write the report archive.
#
#   bash scripts/run_controls.sh <spec-archive-dir> <report-dir>
#   bash scripts/run_controls.sh reports/2609_clean_paired_astropy_n5/v4 reports/2609_control_arms_astropy_n5
#
# B reuses the archive's tasks.json + specs/ instead of paying for stage 01
# again. Inference is the expensive, non-idempotent step; resume a dead run
# past what already finished with START_AT:
#   10 seed · 20 briefs · 30 datasets · 41 infer A · 42 infer B
#   43 infer A_plan · 44 infer A_hint · 50 eval · 60 reports
set -euo pipefail

ARCHIVE="${1:?usage: run_controls.sh <spec-archive-dir> <report-dir>}"
REPORT="${2:?usage: run_controls.sh <spec-archive-dir> <report-dir>}"

cd "$(dirname "$0")/.."
PY="uv run --with datasets python3"
BRIEF_PARALLEL="${BRIEF_PARALLEL:-3}"
START_AT="${START_AT:-00}"
LOGDIR="results/logs/controls"
mkdir -p "$LOGDIR" "$REPORT"

step() { echo; echo "=== [controls] $* @ $(date '+%H:%M:%S') ==="; }
run_stage() { ! [ "$1" \< "$START_AT" ]; }

if ! grep -Eq '^CLAUDE_CODE_VERSION = "[^"]+"' fb_config.toml; then
  echo "error: pin CLAUDE_CODE_VERSION in fb_config.toml — fb installs @latest otherwise," \
       "so arms run on different days run different agents" >&2
  exit 1
fi

if run_stage 10; then
  step "10 seed panel + B specs from $ARCHIVE"
  mkdir -p results/specs
  cp "$ARCHIVE/tasks.json" results/tasks.json
  cp "$ARCHIVE"/specs/*.md "$ARCHIVE"/specs/*.meta.json results/specs/
fi
$PY -c 'import json; print("\n".join(t["id"] for t in json.load(open("results/tasks.json"))["tasks"] if t["status"] == "spec_ok"))' \
  > "$REPORT/panel_task_ids.txt"

if run_stage 20; then
  step "20 A_plan briefs (blueprint disabled)"
  $PY scripts/14_control_arms.py --stage brief --parallel "$BRIEF_PARALLEL" 2>&1 | tee "$LOGDIR/20_briefs.log"
fi

if run_stage 30; then
  step "30 datasets B, A_plan, A_hint + dry-run of all four infer commands"
  $PY scripts/02_make_dataset.py 2>&1 | tee "$LOGDIR/30_dataset_b.log"
  $PY scripts/14_control_arms.py --stage dataset 2>&1 | tee "$LOGDIR/30_dataset_controls.log"
  $PY scripts/03_infer.py --dry-run 2>&1 | tee "$LOGDIR/30_dryrun.log"
  $PY scripts/14_control_arms.py --stage infer --dry-run 2>&1 | tee -a "$LOGDIR/30_dryrun.log"
fi

if run_stage 41; then
  step "41 infer A"
  $PY scripts/03_infer.py --arm A 2>&1 | tee "$LOGDIR/41_infer_a.log"
fi
if run_stage 42; then
  step "42 infer B"
  $PY scripts/03_infer.py --arm B 2>&1 | tee "$LOGDIR/42_infer_b.log"
fi
if run_stage 43; then
  step "43 infer A_plan"
  $PY scripts/14_control_arms.py --stage infer --arm A_plan 2>&1 | tee "$LOGDIR/43_infer_a_plan.log"
fi
if run_stage 44; then
  step "44 infer A_hint"
  $PY scripts/14_control_arms.py --stage infer --arm A_hint 2>&1 | tee "$LOGDIR/44_infer_a_hint.log"
fi

if run_stage 50; then
  step "50 eval all four arms against the official dataset"
  $PY scripts/04_eval.py --arm both 2>&1 | tee "$LOGDIR/50_eval_ab.log"
  $PY scripts/14_control_arms.py --stage eval 2>&1 | tee "$LOGDIR/50_eval_controls.log"
fi

if run_stage 60; then
  step "60 reports -> $REPORT"
  $PY scripts/05_report.py --out "$REPORT/report_ab.md" 2>&1 | tee "$LOGDIR/60_report_ab.log"
  $PY scripts/05c_report_controls.py --out "$REPORT/report.md" 2>&1 | tee "$LOGDIR/60_report.log"
  $PY scripts/10_costs.py --task-ids-file "$REPORT/panel_task_ids.txt" --out "$REPORT/cost_report.md" \
    2>&1 | tee "$LOGDIR/60_costs.log"
  mkdir -p "$REPORT/briefs"
  cp results/briefs/*.md results/briefs/*.meta.json "$REPORT/briefs/"
  cp results/tasks.json results/runs.json "$REPORT/"
fi

step "done"

#!/usr/bin/env bash
# Stitch every finished batch into one panel and archive it outside results/.
#
#   bash scripts/11_finalize.sh <report-name> [panel-ids-file]
#     e.g. bash scripts/11_finalize.sh 2608_scale_astropy_n5 samples/batch_astropy.txt
#
# panel-ids-file is the published panel: it bounds the C/C0 report and the
# cost ledger, so leftover cells or meta sidecars from an earlier run are
# never billed or scored against this panel.
#
# results/ is gitignored in full, so the deliverable is copied into
# reports/<report-name>/ — that directory IS the published artifact.
# Safe to re-run: 07/08/10 reuse cached per-cell JSONs and call no model.
set -euo pipefail

NAME="${1:?usage: 11_finalize.sh <report-name> [panel-ids-file]}"
PANEL_IDS="${2:-samples/scale_n25.txt}"

cd "$(dirname "$0")/.."
PY="uv run --with datasets python3"
MERGED="results/merged"
OUT="reports/${NAME}"

step() { echo; echo "=== $* @ $(date '+%H:%M:%S') ==="; }

step "09 merge batches"
$PY scripts/09_merge.py

step "05 paired A/B report (whole panel)"
$PY scripts/05_report.py \
  --tasks "$MERGED/tasks.json" \
  --report-a "$MERGED/report_A.json" \
  --report-b "$MERGED/report_B.json" \
  --out "$MERGED/report.md"

step "05b C vs C0 report (whole panel)"
if [ -f "$MERGED/report_C.json" ] && [ -f "$MERGED/report_C0.json" ]; then
  $PY scripts/05b_report_c.py \
    --report-b "$MERGED/report_B.json" \
    --report-c "$MERGED/report_C.json" \
    --report-c0 "$MERGED/report_C0.json" \
    --task-ids-file "$PANEL_IDS" \
    --out "$MERGED/report_c.md"
else
  echo "warn: no C/C0 reports merged — skipping 05b"
fi

step "07 mutation report (cached cells, no model calls)"
$PY scripts/07_mutation.py --arm both --runs "$MERGED/runs.json" \
  --out "$MERGED/mutation_report.md"

step "10 cost ledger (whole panel)"
$PY scripts/10_costs.py --runs "$MERGED/runs.json" --task-ids-file "$PANEL_IDS" \
  --out "$MERGED/cost_report.md"

step "08 taxonomy report (cached cells)"
# 08 has no --runs override, so point the canonical file at the merged panel.
cp -f results/runs.json "results/runs.batch-last.json" 2>/dev/null || true
cp -f "$MERGED/runs.json" results/runs.json
cp -f "$MERGED/tasks.json" results/tasks.json
$PY scripts/08_taxonomy.py || echo "warn: taxonomy pass incomplete"
cp -f results/taxonomy_report.md "$MERGED/taxonomy_report.md" 2>/dev/null || true

step "archive to $OUT"
mkdir -p "$OUT/batches"
for f in report.md report_c.md mutation_report.md taxonomy_report.md cost_report.md \
         tasks.json runs.json; do
  [ -f "$MERGED/$f" ] && cp -f "$MERGED/$f" "$OUT/$f"
done
cp -f "$PANEL_IDS" "$OUT/panel_task_ids.txt"
for b in results/logs/*/; do
  [ -d "$b" ] || continue
  bn="$(basename "$b")"
  mkdir -p "$OUT/batches/$bn"
  cp -f "$b"/*.md "$OUT/batches/$bn/" 2>/dev/null || true
  cp -f "$b"/*.log "$OUT/batches/$bn/" 2>/dev/null || true
done

step "done"
ls -la "$OUT"

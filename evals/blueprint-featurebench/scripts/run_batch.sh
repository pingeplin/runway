#!/usr/bin/env bash
# Run one image-batch of the scale panel end to end.
#
# The panel spans 5 container images at ~18GB each; the podman VM is capped at
# 93GB, so images are processed one repo at a time and purged in between.
# Every stage below writes to results/{tasks,runs}.json, which the NEXT batch
# overwrites — so the batch is archived to results/batches/<name>/ at the end
# and stitched back together by scripts/09_merge.py.
#
#   bash scripts/run_batch.sh <batch-name> <image-name>
#
# Resumable: stages 01/06/07/08 skip cells that already succeeded, so a killed
# batch can be re-run with the same arguments. Pass FORCE=1 to redo stage 01.
set -euo pipefail

BATCH="${1:?usage: run_batch.sh <batch-name> <image-name>}"
IMAGE="${2:?usage: run_batch.sh <batch-name> <image-name>}"

cd "$(dirname "$0")/.."
EVAL_ROOT="$(pwd)"
IDS="samples/batch_${BATCH}.txt"
LOGDIR="results/logs/${BATCH}"
ARCHIVE="results/batches/${BATCH}"
PY="uv run --with datasets python3"
SPEC_PARALLEL="${SPEC_PARALLEL:-3}"
VERIFY_PARALLEL="${VERIFY_PARALLEL:-3}"

[ -f "$IDS" ] || { echo "error: no id file $IDS" >&2; exit 1; }
mkdir -p "$LOGDIR" "$ARCHIVE"

step() { echo; echo "=== [$BATCH] $* @ $(date '+%H:%M:%S') ==="; }

# Resume support. Stage 03 (inference) is the expensive, NON-idempotent stage:
# re-running it spends the whole arm again. So a batch that dies late must be
# resumed past it, never restarted.
#   START_AT=06 bash scripts/run_batch.sh astropy <image>
START_AT="${START_AT:-00}"
run_stage() { [ "$1" \< "$START_AT" ] && return 1 || return 0; }
skip_note() { echo "--- [$BATCH] skipping stage $1 (START_AT=$START_AT)"; }

step "batch of $(wc -l < "$IDS" | tr -d ' ') task(s), image $IMAGE"

step "pull image (no-op if prefetched)"
docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull "$IMAGE"

if run_stage 01; then
step "01 specs"
$PY scripts/01_make_specs.py --task-ids-file "$IDS" --parallel "$SPEC_PARALLEL" \
  ${FORCE:+--force} 2>&1 | tee "$LOGDIR/01_specs.log"
else skip_note 01; fi

step "gate: every task must have a spec"
# Stage 01 exits 0 on partial failure, but stage 02 silently drops non-spec_ok
# tasks from BOTH arms — so a soft failure here shrinks the panel and is only
# discovered at merge time, after the image is gone. Fail now, while it isn't.
$PY - "$IDS" <<'PYGATE' 2>&1 | tee "$LOGDIR/01_gate.log"
import json, pathlib, sys
wanted = [l.strip() for l in open(sys.argv[1]) if l.strip()]
tasks = json.load(open("results/tasks.json"))["tasks"]
# On a START_AT resume, stage 01 is skipped and tasks.json is whatever the last
# batch wrote. If that is a DIFFERENT batch, every check below passes vacuously
# and the run silently scores the wrong panel.
present = {t["id"] for t in tasks}
if not set(wanted) <= present:
    print(f"tasks.json holds a different panel ({len(present)} ids) than {sys.argv[1]} "
          f"({len(wanted)} ids) — re-run stage 01 for this batch")
    raise SystemExit(1)
ok = {t["id"] for t in tasks if t.get("status") == "spec_ok"}
missing = [i for i in wanted if i not in ok]
print(f"spec_ok {len(ok)}/{len(wanted)}")
if missing:
    print("MISSING SPECS:")
    for i in missing:
        meta = pathlib.Path(f"results/specs/{i}.meta.json")
        err = ""
        if meta.exists():
            try: err = (json.load(open(meta)).get("error") or "")[:200]
            except Exception: pass
        print(f"  {i}: {err or 'no meta.json'}")
    raise SystemExit(1)
PYGATE

if run_stage 02; then
step "02 arm B dataset"
$PY scripts/02_make_dataset.py 2>&1 | tee "$LOGDIR/02_dataset.log"
else skip_note 02; fi

if run_stage 03; then
step "03 infer arms A+B"
$PY scripts/03_infer.py 2>&1 | tee "$LOGDIR/03_infer.log"
else skip_note 03; fi

if run_stage 04; then
step "04 eval arms A+B"
$PY scripts/04_eval.py 2>&1 | tee "$LOGDIR/04_eval.log"
else skip_note 04; fi

if run_stage 05; then
step "05 per-batch A/B report"
$PY scripts/05_report.py --out "$LOGDIR/report.md" 2>&1 | tee "$LOGDIR/05_report.log"
else skip_note 05; fi

step "06 arm C + C0 (verify loop)"
$PY scripts/06_arm_c.py --stage all --arm both-c --parallel "$VERIFY_PARALLEL" \
  2>&1 | tee "$LOGDIR/06_arm_c.log"

step "05b per-batch C report"
$PY scripts/05b_report_c.py --out "$LOGDIR/report_c.md" 2>&1 | tee "$LOGDIR/05b_report_c.log"

step "07 mutation overlay (all arms)"
$PY scripts/07_mutation.py --arm both --out "$LOGDIR/mutation_report.md" \
  2>&1 | tee "$LOGDIR/07_mutation.log"

step "10 cost ledger (must run before the image purge)"
$PY scripts/10_costs.py --out "$LOGDIR/cost_report.md" 2>&1 | tee "$LOGDIR/10_costs.log"

step "08 failure taxonomy"
$PY scripts/08_taxonomy.py 2>&1 | tee "$LOGDIR/08_taxonomy.log"
cp -f results/taxonomy_report.md "$LOGDIR/taxonomy_report.md" 2>/dev/null || true

step "archive batch state"
cp -f results/tasks.json "$ARCHIVE/tasks.json"
cp -f results/runs.json  "$ARCHIVE/runs.json"
echo "$IMAGE" > "$ARCHIVE/image.txt"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$ARCHIVE/finished_at.txt"

step "purge image + workspaces, reclaim host space"
rm -rf results/workspaces results/workspaces_c
docker rmi "$IMAGE" >/dev/null 2>&1 || echo "warn: could not remove $IMAGE"
docker container prune -f >/dev/null 2>&1 || true
podman machine ssh podman-machine-apple "sudo fstrim -av" 2>/dev/null | tail -1 || true

step "done"
df -h /System/Volumes/Data | tail -1
podman machine ssh podman-machine-apple "df -h / | tail -1" 2>/dev/null || true

#!/usr/bin/env bash
# Paired rerun driver: B_4.1 (archived v4 specs) vs B_new (branch plugin specs).
# Phase 1 runs B_4.1 inference (podman VM) alongside B_new spec writing (host).
# Phase 2 infers B_new only after B_4.1 has left the VM (n_concurrent 1).
# Stage 03 is not idempotent: resume with START_AT=bnew_infer, never from the top.
set -uo pipefail
SP="$(cd "$(dirname "$0")" && pwd)"
PY="uv run --with datasets python3"
LOG="$SP/logs"
START_AT="${START_AT:-phase1}"
mkdir -p "$LOG"
say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG/driver.log"; }

if [ "$START_AT" = phase1 ]; then
  say "phase 1: b41 infer+eval ‖ bnew specs"
  ( cd "$SP/b41" \
    && $PY scripts/03_infer.py --arm B > "$LOG/b41_03_infer.log" 2>&1 \
    && $PY scripts/04_eval.py --arm B > "$LOG/b41_04_eval.log" 2>&1 ) &
  P_B41=$!
  ( cd "$SP/bnew" \
    && $PY scripts/01_make_specs.py --task-ids-file samples/panel.txt --parallel 2 > "$LOG/bnew_01_specs.log" 2>&1 ) &
  P_SPEC=$!
  wait $P_SPEC; say "bnew specs exit $?"
  wait $P_B41; B41_RC=$?; say "b41 infer+eval exit $B41_RC"
  [ "$B41_RC" = 0 ] || { say "STOP: b41 failed"; exit 1; }
fi

cd "$SP/bnew"
if [ "$START_AT" = phase1 ] || [ "$START_AT" = gate ]; then
  $PY - samples/panel.txt <<'PYGATE' 2>&1 | tee -a "$LOG/driver.log"
import json, sys
wanted = [l.strip() for l in open(sys.argv[1]) if l.strip()]
ok = {t["id"] for t in json.load(open("results/tasks.json"))["tasks"] if t.get("status") == "spec_ok"}
missing = [i for i in wanted if i not in ok]
print(f"gate: spec_ok {len(wanted) - len(missing)}/{len(wanted)}")
raise SystemExit(1 if missing else 0)
PYGATE
  [ "${PIPESTATUS[0]}" = 0 ] || { say "STOP: bnew spec gate failed"; exit 1; }
  $PY scripts/02_make_dataset.py > "$LOG/bnew_02_dataset.log" 2>&1 || { say "STOP: bnew dataset"; exit 1; }
fi

say "phase 2: bnew infer"
$PY scripts/03_infer.py --arm B > "$LOG/bnew_03_infer.log" 2>&1 || { say "STOP: bnew infer"; exit 1; }
say "bnew eval"
$PY scripts/04_eval.py --arm B > "$LOG/bnew_04_eval.log" 2>&1 || { say "STOP: bnew eval"; exit 1; }

for arm in b41 bnew; do
  ( cd "$SP/$arm" && $PY scripts/10_costs.py --out "$LOG/${arm}_cost_report.md" > "$LOG/${arm}_10_costs.log" 2>&1 ) || say "warn: $arm costs"
done
say "DONE"

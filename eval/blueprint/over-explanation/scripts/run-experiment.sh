#!/usr/bin/env bash
#
# run-experiment.sh — drive a FULL over-explanation panel (all arms x briefs x
# seeds) end to end, the bash/cron fallback path (eval-methodology.md §5). The
# primary path is the Workflow script in orchestration/run-experiment.workflow.js;
# this script is the manual equivalent for when you'd rather drive it from a shell
# or a cron loop.
#
# Pipeline:
#   1. (precondition) scripts/setup-worktrees.sh has created a worktree + a
#      ~/.claude-<ARM_ID> config dir per arm, each authed (§2).
#   2. for each arm x brief x seed: scripts/run-arm.sh produces the artifact cell.
#   3. analysis/assemble.py runs the cross-family extractor over the cells and
#      writes results.json.
#   4. overexpl restatement|guardrails|stats reads results.json and prints the
#      metrics + guardrail/STOP gates (non-zero exit on a block/STOP).
#
# The instrument-trust gate (overexpl instrument) and the final decision
# (overexpl decision) are run separately — the gate must pass BEFORE you read any
# arm number, and the decision consumes assembled per-arm comparisons.
#
# Usage:
#   scripts/run-experiment.sh <MANIFEST.json> <CORPUS_ROOT> [RESULTS_ROOT]
#
# Environment:
#   FAMILY     extractor family for assembly: openai|anthropic  (default: openai)
#   MODEL      extractor model id; empty -> per-family default
#              (anthropic: claude-sonnet-4-6, openai: gpt-5.4)
#   BASE_URL   OpenAI-compatible base url (optional)

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ $# -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat >&2 <<'USAGE'
Usage: run-experiment.sh <MANIFEST.json> <CORPUS_ROOT> [RESULTS_ROOT]
  MANIFEST.json  pre-registration manifest listing arms / briefs / seeds
  CORPUS_ROOT    dir holding one subdir per brief id (e.g. corpus/demo)
  RESULTS_ROOT   where cells + results.json are written (default: ./results)
USAGE
  exit 2
fi

MANIFEST="$1"
CORPUS_ROOT="$2"
RESULTS_ROOT="${3:-${ROOT}/results}"
FAMILY="${FAMILY:-openai}"
MODEL="${MODEL:-}"   # empty -> assemble.py picks the per-family default

[[ -f "$MANIFEST" ]] || { echo "error: manifest not found: $MANIFEST" >&2; exit 1; }
[[ -d "$CORPUS_ROOT" ]] || { echo "error: corpus root not found: $CORPUS_ROOT" >&2; exit 1; }

# Pull arms / briefs / seeds out of the manifest with the package's own loader so
# the panel matches the pre-registration exactly.
read_manifest() {
  uv run python - "$MANIFEST" <<'PY'
import sys
from pathlib import Path
from eval_overexplanation.manifest import load_manifest
reg = load_manifest(Path(sys.argv[1]))
problems = reg.validate()
if problems:
    sys.stderr.write("manifest validation problems:\n  " + "\n  ".join(problems) + "\n")
print("ARMS=" + " ".join(a.id for a in reg.arms))
print("BRIEFS=" + " ".join(b.id for b in reg.briefs))
print("SEEDS=" + " ".join(str(s) for s in reg.seeds))
PY
}

eval "$(read_manifest)"
echo "==> arms:   $ARMS"
echo "==> briefs: $BRIEFS"
echo "==> seeds:  $SEEDS"
echo "==> results root: $RESULTS_ROOT"
echo

# 2. Generate every cell. Continue on per-cell failure (a stuck/rate-limited arm
# shouldn't abort the whole panel); tally outcomes.
ok=0; fail=0
for arm in $ARMS; do
  for brief in $BRIEFS; do
    brief_dir="${CORPUS_ROOT}/${brief}"
    [[ -d "$brief_dir" ]] || { echo "skip: no brief dir $brief_dir" >&2; continue; }
    for seed in $SEEDS; do
      echo "---- ${arm} / ${brief} / seed-${seed} ----"
      if RESULTS_ROOT="$RESULTS_ROOT" scripts/run-arm.sh "$arm" "$brief_dir" "$seed"; then
        ok=$((ok + 1))
      else
        echo "warn: cell ${arm}/${brief}/seed-${seed} failed (rc=$?)" >&2
        fail=$((fail + 1))
      fi
    done
  done
done
echo
echo "==> generation complete: ${ok} ok, ${fail} failed"

# 3. Assemble results.json via the cross-family extractor. Omit --model when
# empty so assemble.py applies the per-family default (sonnet 4.6 / gpt-5.4).
echo "==> assembling results.json with the ${FAMILY} extractor (${MODEL:-default})"
uv run python analysis/assemble.py \
  --results-root "$RESULTS_ROOT" --corpus "$CORPUS_ROOT" \
  --family "$FAMILY" ${MODEL:+--model "$MODEL"} ${BASE_URL:+--base-url "$BASE_URL"} \
  --out "${RESULTS_ROOT}/results.json"

# 4. Analysis gates (non-zero exit propagates a block / STOP to the caller).
echo
echo "==> restatement"; uv run overexpl restatement "$RESULTS_ROOT" || true
echo
echo "==> guardrails";  uv run overexpl guardrails  "$RESULTS_ROOT" || gr=$?
echo
echo "==> stats";       uv run overexpl stats       "$RESULTS_ROOT" || st=$?

echo
echo "==> done. Next: run 'overexpl instrument <docs> <decoys>' (must pass before"
echo "    reading numbers) and 'overexpl decision <inputs>' for the final verdict."
echo "    Reminder: a NON-BLIND demo corpus certifies nothing — see corpus/demo/PROVENANCE.md."
exit "${gr:-${st:-0}}"

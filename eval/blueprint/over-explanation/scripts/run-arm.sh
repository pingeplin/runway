#!/usr/bin/env bash
#
# run-arm.sh — drive a single eval arm (one pinned plugin version) through the
# Claude Code CLI against one brief, and capture the produced design doc / spec.
#
# Implements eval-methodology.md §5 ("Orchestration: driving a single arm"):
#   - select the arm's isolated $CLAUDE_CONFIG_DIR (scaffolded by
#     setup-worktrees.sh) so the pinned plugin version is the one loaded
#   - run `claude` headless against an identical brief (§3: both arms read the
#     SAME brief; output differences come from the plugin, not the prompt)
#   - apply the §5 auto-approval gate defaults non-interactively
#   - capture the resulting blueprint/ artifacts (design doc + spec) into a
#     per-(arm,brief,seed) results dir
#
# Determinism note: the seed is recorded into the results dir and passed to the
# agent in the prompt. LLM sampling is still variance-prone (§7 "N=1 per cell"),
# so the seed labels the cell rather than guaranteeing reproducibility.

set -euo pipefail

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
  cat <<'USAGE'
Usage: run-arm.sh <ARM_ID> <BRIEF_DIR> <SEED>

Drive one eval arm against one brief (eval-methodology.md §5).

Arguments:
  ARM_ID      any manifest arm id (A0, A1, A3_fair, ...); selects ~/.claude-<ARM_ID>
  BRIEF_DIR   path to a corpus brief dir (must contain brief.md + brief.json)
  SEED        integer seed; labels this cell and is woven into the prompt

Environment overrides (optional):
  CLAUDE_BIN          claude executable                  (default: claude)
  RESULTS_ROOT        where cells are written            (default: ./results)
  ARM_WORKROOT        live workspace root, OUTSIDE this repo
                                            (default: $TMPDIR/bench-arm)
  WORKFLOW_CMD        slash command the agent runs        (default: /blueprint)
  CLAUDE_CONFIG_DIR   override the per-arm config dir (escape hatch; §2 shortcut
                      of reusing the default ~/.claude for one arm)
  TIMEOUT_SECS        hard wall-clock cap for the CLI run (default: 1800)
  BENCH_MANIFEST      manifest whose bench.leak_patterns drive the post-run
                      C0 transcript scan (default: the package's frozen
                      deadend.LEAK_PATTERNS)

Examples:
  scripts/run-arm.sh A0 corpus/example-brief 0
  scripts/run-arm.sh A1 corpus/example-brief 0
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 3 ]]; then
  echo "error: expected exactly 3 arguments (ARM_ID, BRIEF_DIR, SEED)" >&2
  echo >&2
  usage >&2
  exit 2
fi

ARM_ID="$1"
BRIEF_DIR="$2"
SEED="$3"

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
RESULTS_ROOT="${RESULTS_ROOT:-$(pwd)/results}"
ARM_WORKROOT="${ARM_WORKROOT:-${TMPDIR:-/tmp}/bench-arm}"
WORKFLOW_CMD="${WORKFLOW_CMD:-/blueprint}"
TIMEOUT_SECS="${TIMEOUT_SECS:-1800}"
BENCH_MANIFEST="${BENCH_MANIFEST:-}"

# python3 is load-bearing here: the workroot realpath check, the brief-id
# read, AND the post-run C0 leak scan (the transcript scan is what the
# C0_generate_isolation gate consumes — without it a cell would carry no
# leak signal and the gate would have nothing to fail on). Fail closed.
if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required (workroot realpath, brief id, C0 leak scan)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Validate inputs.
# ---------------------------------------------------------------------------
# Any non-empty arm id from the manifest is accepted (Milestone 2 runs up to 8
# arms: A0, A0_prime, A1, A2_placebo, A3_fair, A3b_dumb, A4_evaluator_only,
# A5_full). The arm must have a matching ~/.claude-<ARM_ID> config dir, which the
# config-dir existence check below enforces.
if [[ -z "$ARM_ID" || "$ARM_ID" == -* ]]; then
  echo "error: ARM_ID must be a non-empty arm id (e.g. A0, A1, A3_fair)" >&2
  exit 2
fi

if [[ ! -d "$BRIEF_DIR" ]]; then
  echo "error: brief dir not found: $BRIEF_DIR" >&2
  exit 1
fi
# §3: the brief is the single identical input both arms read.
BRIEF_MD="${BRIEF_DIR}/brief.md"
BRIEF_JSON="${BRIEF_DIR}/brief.json"
if [[ ! -f "$BRIEF_MD" ]]; then
  echo "error: missing brief.md in $BRIEF_DIR" >&2
  exit 1
fi
if [[ ! "$SEED" =~ ^-?[0-9]+$ ]]; then
  echo "error: SEED must be an integer (got '$SEED')" >&2
  exit 1
fi

# Derive a stable brief id (prefer brief.json's id; fall back to dir name).
BRIEF_ID="$(basename "$BRIEF_DIR")"
if [[ -f "$BRIEF_JSON" ]]; then
  BRIEF_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$BRIEF_JSON" 2>/dev/null || echo "$BRIEF_ID")"
fi

# ---------------------------------------------------------------------------
# §2: select the arm's isolated config dir so the correct pinned plugin loads.
# Honour an explicit CLAUDE_CONFIG_DIR override (the §2 "unset to reuse default
# ~/.claude" shortcut for one arm); otherwise use ~/.claude-<ARM_ID>.
# ---------------------------------------------------------------------------
if [[ -n "${CLAUDE_CONFIG_DIR:-}" ]]; then
  ARM_CONFIG_DIR="$CLAUDE_CONFIG_DIR"
  echo "==> using caller-provided CLAUDE_CONFIG_DIR: $ARM_CONFIG_DIR"
else
  ARM_CONFIG_DIR="${HOME}/.claude-${ARM_ID}"
fi
if [[ ! -d "$ARM_CONFIG_DIR" ]]; then
  echo "error: config dir $ARM_CONFIG_DIR does not exist." >&2
  echo "       Run scripts/setup-worktrees.sh first (eval-methodology.md §2)." >&2
  exit 1
fi
export CLAUDE_CONFIG_DIR="$ARM_CONFIG_DIR"

if ! command -v "$CLAUDE_BIN" >/dev/null 2>&1; then
  echo "error: '$CLAUDE_BIN' not on PATH. Set CLAUDE_BIN or install Claude Code." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Per-(arm,brief,seed) results cell (§4: artifacts are scored per cell).
# A clean, git-tracked workspace per cell keeps the agent's blueprint/ output
# isolated and lets the §6 git-audit step read a clean log.
#
# ISOLATION (BLUEPRINT-BENCH §1 C0, the U0 analogue for the GENERATE cell).
# What is actually enforced, stated exactly:
#   (a) the live workspace's cwd sits OUTSIDE the repo tree (an inside-repo
#       workroot is refused below), which removes RELATIVE-path access to
#       corpus/<b>/oracle.py and the gold/cases assets — but the agent can
#       still Read/Grep absolute repo paths, so cwd placement alone is NOT a
#       filesystem restriction and never claimed as one;
#   (b) a POST-HOC transcript scan (deadend.count_leaks over every tool_use
#       block, bench.leak_patterns) records leak_hits into cell.json — the
#       C0_generate_isolation gate then requires 0 hits across all generate
#       cells, so any absolute-path touch of a frozen asset fails the run.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
WORKROOT_REAL="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$ARM_WORKROOT")"
if [[ -n "$REPO_ROOT" && ( "$WORKROOT_REAL" == "$REPO_ROOT" || "$WORKROOT_REAL" == "$REPO_ROOT"/* ) ]]; then
  echo "error: ARM_WORKROOT ($WORKROOT_REAL) is inside the repo tree ($REPO_ROOT)." >&2
  echo "       The generate workspace must live outside the repo so the spec author" >&2
  echo "       cannot reach corpus oracle/gold assets by relative path; absolute-path" >&2
  echo "       touches are caught by the post-run C0 transcript scan." >&2
  exit 1
fi

CELL_DIR="${RESULTS_ROOT}/${BRIEF_ID}/${ARM_ID}/seed-${SEED}"
WORKSPACE="${ARM_WORKROOT}/${BRIEF_ID}/${ARM_ID}/seed-${SEED}/workspace"
rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE" "$CELL_DIR"

echo "==> arm:        $ARM_ID"
echo "==> brief:      $BRIEF_ID ($BRIEF_DIR)"
echo "==> seed:       $SEED"
echo "==> config dir: $CLAUDE_CONFIG_DIR"
echo "==> cell dir:   $CELL_DIR"
echo

# Stage the brief into the workspace identically for both arms (§3), and init a
# fresh git repo so §6's git audit (commit count, failing-test checkpoints) has
# a clean baseline.
cp "$BRIEF_MD" "${WORKSPACE}/brief.md"
[[ -f "$BRIEF_JSON" ]] && cp "$BRIEF_JSON" "${WORKSPACE}/brief.json"
if [[ ! -d "${WORKSPACE}/.git" ]]; then
  git -C "$WORKSPACE" init -q
  git -C "$WORKSPACE" add -A
  git -C "$WORKSPACE" -c user.name="eval-arm" -c user.email="eval@local" \
      commit -q -m "chore: stage brief for ${ARM_ID}/${BRIEF_ID}/seed-${SEED}" || true
fi

# Record the cell's provenance for the scoring pass. "workspace_outside_repo"
# records that the isolation check above held for this cell (it is only ever
# written true: an inside-repo workroot exits before this line).
cat >"${CELL_DIR}/cell.json" <<JSON
{
  "arm": "${ARM_ID}",
  "brief_id": "${BRIEF_ID}",
  "seed": ${SEED},
  "config_dir": "${CLAUDE_CONFIG_DIR}",
  "workflow_cmd": "${WORKFLOW_CMD}",
  "workspace": "${WORKSPACE}",
  "workspace_outside_repo": true,
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON

# ---------------------------------------------------------------------------
# §5 auto-approval gate defaults.
# We run `claude` headless (`-p` / --print). In headless mode the standard
# blueprint gates (spec/plan/commit approve, language menu -> Python, refactor
# direction -> skip, trust-folder -> Enter) are pre-resolved by:
#   - --permission-mode acceptEdits  : auto-accept file edits (gate: "Approve")
#   - --dangerously-skip-permissions : optionally skip tool prompts in the
#       sandboxed eval workspace (off by default; opt in with SKIP_PERMS=1)
# and by stating the §5 gate defaults explicitly in the prompt so any chat-style
# "approve, or revise?" gate is answered "approve" by the agent itself.
# ---------------------------------------------------------------------------
PERM_FLAGS=(--permission-mode acceptEdits)
if [[ "${SKIP_PERMS:-0}" == "1" ]]; then
  # Use only inside the throwaway eval workspace; never on a real repo.
  PERM_FLAGS=(--dangerously-skip-permissions)
fi

# The prompt encodes §5's gate defaults so the headless run is fully unattended.
PROMPT="$(cat <<EOF
Run the ${WORKFLOW_CMD} workflow to design and spec the task described in
./brief.md. This is an unattended evaluation run (seed=${SEED}); apply these
gate defaults without asking:
  - spec gate, plan gate, commit gate -> APPROVE
  - language selection -> Python
  - refactor-direction menu -> skip
  - trust-folder prompt -> accept
Write the design doc and spec under blueprint/ as the workflow normally does.
Do not ask clarifying questions; proceed end to end.
EOF
)"

echo "==> §5 launching headless claude (timeout ${TIMEOUT_SECS}s)"
echo

# Portable timeout: prefer GNU `timeout`/`gtimeout` if present, else run direct.
TIMEOUT_BIN=""
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_BIN="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_BIN="gtimeout"
fi

TRANSCRIPT="${CELL_DIR}/transcript.jsonl"
set +e
(
  cd "$WORKSPACE"
  if [[ -n "$TIMEOUT_BIN" ]]; then
    "$TIMEOUT_BIN" "${TIMEOUT_SECS}" \
      "$CLAUDE_BIN" -p "$PROMPT" \
        "${PERM_FLAGS[@]}" \
        --output-format stream-json --verbose
  else
    echo "warning: no timeout binary found; running without a wall-clock cap" >&2
    "$CLAUDE_BIN" -p "$PROMPT" \
      "${PERM_FLAGS[@]}" \
      --output-format stream-json --verbose
  fi
) >"$TRANSCRIPT" 2>"${CELL_DIR}/run.log"
RUN_RC=$?
set -e

if [[ $RUN_RC -eq 124 ]]; then
  echo "warning: claude run hit the ${TIMEOUT_SECS}s timeout (§5 failure mode: stuck/rate-limited)" >&2
elif [[ $RUN_RC -ne 0 ]]; then
  echo "warning: claude exited non-zero (rc=$RUN_RC); see ${CELL_DIR}/run.log" >&2
fi

# ---------------------------------------------------------------------------
# §4: capture the produced design doc / spec for scoring.
# Blueprint writes under blueprint/ (3.6+) or specs/+docs/designs/ (pre-3.6);
# collect whichever exist so the harness is version-agnostic across A0/A1.
# The artifacts/ snapshot is the POST-evaluator document. The PRE-evaluator
# snapshot (for merge-fidelity, change ②) is recovered downstream by
# analysis/assemble.py from transcript.jsonl below — the generator's lone Write
# to each artifact, before the evaluator Edits it. That recovery is fail-closed:
# if an artifact was written more than once (boundary unknowable) the cell's
# merge-fidelity is skipped, never guessed. No separate capture step needed here.
# ---------------------------------------------------------------------------
ARTIFACTS_DIR="${CELL_DIR}/artifacts"
mkdir -p "$ARTIFACTS_DIR"

copied_any=0
for sub in blueprint/specs blueprint/plans blueprint/designs specs plans docs/designs docs/testing; do
  src="${WORKSPACE}/${sub}"
  if [[ -d "$src" ]]; then
    dest="${ARTIFACTS_DIR}/${sub}"
    mkdir -p "$(dirname "$dest")"
    cp -R "$src" "$dest"
    echo "    captured ${sub}"
    copied_any=1
  fi
done

# Also snapshot the git log for the §6 process-discipline audit, and the
# workspace itself (sans .git) so the cell stays self-contained even though
# the LIVE workspace ran outside the repo tree.
git -C "$WORKSPACE" log --oneline --stat >"${CELL_DIR}/git-log.txt" 2>/dev/null || true
rm -rf "${CELL_DIR}/workspace"
cp -R "$WORKSPACE" "${CELL_DIR}/workspace"
rm -rf "${CELL_DIR}/workspace/.git"

if [[ "$copied_any" -eq 0 ]]; then
  echo "warning: no design/spec artifacts found under known paths." >&2
  echo "         Inspect ${WORKSPACE} and ${CELL_DIR}/transcript.jsonl by hand." >&2
fi

# ---------------------------------------------------------------------------
# §1 C0: post-hoc leak scan over the generate transcript, then stamp the cell.
# deadend.count_leaks (bench.leak_patterns when BENCH_MANIFEST is given, else
# the package's frozen LEAK_PATTERNS) runs over EVERY tool_use block; the hits
# and leak_scanned:true land in cell.json so the score packer can populate
# GateValues.c0_leak_hits (gate: 0 hits across 100% of generate cells). One
# stage-specific exemption: bare "brief.md"/"brief.json" fragments are the
# cell's own STAGED INPUT (the generate agent must read the brief), so those
# exact FRAGMENTS are dropped. The exemption is order-independent because
# count_leaks records EVERY distinct matched fragment per tool_use — a Bash
# command touching both brief.md and corpus/<b>/oracle.py yields separate
# hits for "brief.md", "corpus" and "oracle.py", so dropping the brief.*
# fragments still leaves the oracle-side hits standing: a tool_use is exempt
# only when NO non-exempt fragment matched it. A scan that cannot run
# records leak_scanned:false — no signal, never a pass — and this script
# then EXITS NON-ZERO below (an unscanned cell must never look green).
# ---------------------------------------------------------------------------
PYTHONPATH="${SCRIPT_DIR}/../src${PYTHONPATH:+:$PYTHONPATH}" \
python3 - "$CELL_DIR/cell.json" "$RUN_RC" "$TRANSCRIPT" "$BENCH_MANIFEST" <<'PY' || true
import datetime, json, sys
path, rc, transcript, manifest = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
d = json.load(open(path))
d["finished_at"] = datetime.datetime.now(datetime.timezone.utc).strftime(
    "%Y-%m-%dT%H:%M:%SZ")
d["return_code"] = rc
STAGED_INPUT_FRAGMENTS = {"brief.md", "brief.json"}
try:
    from eval_overexplanation.deadend import LEAK_PATTERNS, count_leaks, iter_tool_uses
    patterns = LEAK_PATTERNS
    if manifest:
        bench = json.load(open(manifest)).get("bench") or {}
        patterns = tuple(bench.get("leak_patterns") or LEAK_PATTERNS)
    with open(transcript, encoding="utf-8") as fh:
        raw_hits = count_leaks(iter_tool_uses(fh), patterns)
    hits = [h for h in raw_hits
            if h.split(": ", 1)[-1] not in STAGED_INPUT_FRAGMENTS]
    d["leak_scanned"] = True
    d["leak_hits"] = len(hits)
    d["leak_hit_details"] = list(hits)
except Exception as exc:  # fail-closed: unscanned is recorded, never a pass
    d["leak_scanned"] = False
    d["leak_scan_error"] = f"{type(exc).__name__}: {exc}"
json.dump(d, open(path, "w"), indent=2, sort_keys=True)
PY

# Fail closed on a scan that never ran: leak_scanned:false is NO SIGNAL for
# the C0 gate, so the cell must read as failed to the orchestrator — never
# as a green cell that merely forgot its scan.
if [[ ! -f "$CELL_DIR/cell.json" ]] || \
   ! python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get("leak_scanned") else 1)' "$CELL_DIR/cell.json" 2>/dev/null; then
  echo "error: C0 leak scan did not run (leak_scanned:false) — no signal is never a pass; see ${CELL_DIR}/cell.json" >&2
  exit 1
fi
if ! python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get("leak_hits", 1) == 0 else 1)' "$CELL_DIR/cell.json" 2>/dev/null; then
  echo "warning: C0 leak scan found hits; see ${CELL_DIR}/cell.json (the C0_generate_isolation gate will fail)" >&2
fi

echo
echo "==> cell complete: $CELL_DIR"
echo "    artifacts:  $ARTIFACTS_DIR"
echo "    transcript: $TRANSCRIPT"
echo "    git log:    ${CELL_DIR}/git-log.txt"

# Propagate the CLI's exit status so an orchestrator (§5) can detect failures.
exit "$RUN_RC"

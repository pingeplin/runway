#!/usr/bin/env bash
#
# run-implementer.sh — drive the ONE fixed, pinned implementer over an arm's
# captured spec, producing a downstream "implement" cell (BLUEPRINT-BENCH v1
# §0/§1-U/§3). Modeled on run-arm.sh: same cell layout, same stream-json
# capture, same portable-timeout and fail-closed rc conventions.
#
# Contract highlights (BENCHMARK.md §3 "scripts/run-implementer.sh"):
#   - input:   results/<BRIEF_ID>/<ARM_ID>/seed-<SEED>/artifacts/**/*spec*.md —
#              EXACTLY one match; 0 or >=2 => exit 1, cell status="missing"
#   - prompt:  render(PREAMBLE_TEMPLATE, module, entrypoint) + "\n\n" + spec
#              text, NOTHING else. module/entrypoint are read from brief.json
#              by this harness (the §0 interface pin) — the implementer never
#              sees brief.json, so leak_hits stays 0.
#   - stage:   the SPEC ONLY into a fresh git workspace OUTSIDE the repo tree.
#              brief.md, brief.json, gold_propositions.json, cases*.json,
#              oracle.py, mutations.json are never staged and never reachable
#              (§1 U0: isolation is reachability, not a listing check).
#   - config:  one FIXED CLAUDE_CONFIG_DIR (~/.claude-implementer) for ALL
#              arms; must exist or exit 1. No per-arm plugin, no arm identity.
#   - retry:   subtype "error_during_execution" => up to MAX_RETRIES with
#              exponential backoff, retried:true. rc 124 => timeout, no retry.
#   - record:  impl-cell.json (arm, brief_id, seed, implementer_model,
#              prompt_sha, preamble_template_sha, module, entrypoint,
#              spec_path, spec_sha, workspace, started_at, finished_at,
#              return_code, retried, status) + transcript.jsonl + run.log +
#              workspace snapshot + git-log.txt in the cell dir.
#   - exit:    propagates the CLI rc so the orchestrator can count failures.
#              Usage/arg errors exit 2 (§2 exit-code table); environment /
#              input-state failures exit 1 (the cell reads as missing, which
#              the fail-closed chain counts into incomplete_fraction).

set -euo pipefail

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
  cat <<'USAGE'
Usage: run-implementer.sh <ARM_ID> <BRIEF> <SEED>

Drive the pinned implementer over one arm's captured spec (BENCHMARK.md §3).

Arguments:
  ARM_ID      a u_arms manifest arm id (A0, A1, A2_placebo, A3_fair, A3b_dumb);
              selects results/<brief>/<ARM_ID>/seed-<SEED> as the spec source
  BRIEF       a buildable corpus brief: either a brief id resolved under
              CORPUS_ROOT, or a path to a brief dir containing brief.json
              (brief.json must carry module + entrypoint — the interface pin)
  SEED        integer seed; labels this cell and selects the generate cell

Environment:
  IMPLEMENTER_MODEL   REQUIRED pinned model id passed to `claude --model`
  CLAUDE_BIN          claude executable                  (default: claude)
  RESULTS_ROOT        generate-cell root                 (default: ./results)
  IMPL_ROOT           implement-cell root                (default: ./impl)
  CORPUS_ROOT         brief-id resolution root           (default: ./corpus)
  IMPL_WORKROOT       workspace root, OUTSIDE this repo  (default: $TMPDIR/bench-impl)
  CLAUDE_CONFIG_DIR   fixed implementer config dir       (default: ~/.claude-implementer)
  TIMEOUT_SECS        hard wall-clock cap per attempt    (default: 1800)
  MAX_RETRIES         retries on error_during_execution  (default: 2)
  RETRY_BACKOFF_SECS  backoff base, doubles per retry    (default: 10)
  PREAMBLE_TEMPLATE_FILE  override the frozen preamble template (must contain
                          exactly the {module} and {entrypoint} placeholders)
  SKIP_PERMS=1        use --dangerously-skip-permissions in the throwaway
                      workspace instead of --permission-mode acceptEdits

Examples:
  IMPLEMENTER_MODEL=claude-sonnet-4-6 scripts/run-implementer.sh A0 b01 0
  IMPLEMENTER_MODEL=claude-sonnet-4-6 scripts/run-implementer.sh A1 corpus/b02 1
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 3 ]]; then
  echo "error: expected exactly 3 arguments (ARM_ID, BRIEF, SEED)" >&2
  echo >&2
  usage >&2
  exit 2
fi

ARM_ID="$1"
BRIEF_ARG="$2"
SEED="$3"

# ---------------------------------------------------------------------------
# Argument validation — usage errors exit 2 (§2 exit-code table).
# ---------------------------------------------------------------------------
if [[ -z "$ARM_ID" || "$ARM_ID" == -* ]]; then
  echo "error: ARM_ID must be a non-empty arm id (e.g. A0, A1, A3_fair)" >&2
  exit 2
fi
if [[ -z "$BRIEF_ARG" || "$BRIEF_ARG" == -* ]]; then
  echo "error: BRIEF must be a brief id or a brief dir path" >&2
  exit 2
fi
if [[ ! "$SEED" =~ ^-?[0-9]+$ ]]; then
  echo "error: SEED must be an integer (got '$SEED')" >&2
  exit 2
fi
if [[ -z "${IMPLEMENTER_MODEL:-}" ]]; then
  echo "error: IMPLEMENTER_MODEL is required (the FIXED pinned implementer, §3)" >&2
  exit 2
fi

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
RESULTS_ROOT="${RESULTS_ROOT:-$(pwd)/results}"
IMPL_ROOT="${IMPL_ROOT:-$(pwd)/impl}"
CORPUS_ROOT="${CORPUS_ROOT:-$(pwd)/corpus}"
IMPL_WORKROOT="${IMPL_WORKROOT:-${TMPDIR:-/tmp}/bench-impl}"
TIMEOUT_SECS="${TIMEOUT_SECS:-1800}"
MAX_RETRIES="${MAX_RETRIES:-2}"
RETRY_BACKOFF_SECS="${RETRY_BACKOFF_SECS:-10}"

# python3 is load-bearing here (JSON fields, sha256, and the fail-closed
# status derivation through usage.parse_usage); fail closed without it.
if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required (brief.json fields, sha256, transcript parse)" >&2
  exit 1
fi

sha256_stdin() {
  python3 -c 'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
}

# ---------------------------------------------------------------------------
# Resolve the brief. Accept a dir path (run-arm.sh convention) or a bare id
# resolved under CORPUS_ROOT (BENCHMARK.md §3 usage). The harness — never the
# implementer — reads brief.json for the §0 interface pin.
# ---------------------------------------------------------------------------
if [[ -d "$BRIEF_ARG" && -f "$BRIEF_ARG/brief.json" ]]; then
  BRIEF_DIR="$BRIEF_ARG"
else
  BRIEF_DIR="${CORPUS_ROOT}/${BRIEF_ARG}"
fi
BRIEF_JSON="${BRIEF_DIR}/brief.json"
if [[ ! -f "$BRIEF_JSON" ]]; then
  echo "error: brief.json not found: $BRIEF_JSON" >&2
  exit 1
fi

read -r BRIEF_ID MODULE ENTRYPOINT BUILDABLE < <(python3 - "$BRIEF_JSON" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(d.get("id", "") or "-", d.get("module", "") or "-",
      d.get("entrypoint", "") or "-", str(bool(d.get("buildable", False))).lower())
PY
)
[[ "$BRIEF_ID" == "-" ]] && BRIEF_ID="$(basename "$BRIEF_DIR")"

if [[ "$BUILDABLE" != "true" ]]; then
  echo "error: brief '$BRIEF_ID' is not buildable; U/O cells cover buildable briefs only" >&2
  exit 1
fi
# §0 interface pin: without module+entrypoint in the prompt, run_oracle scores
# every arm 0.0 and O1 voids the run. Fail closed here instead.
if [[ "$MODULE" == "-" || "$ENTRYPOINT" == "-" ]]; then
  echo "error: brief.json for '$BRIEF_ID' lacks module/entrypoint (interface pin, §0)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Locate the arm's captured spec: exactly one artifacts/**/*spec*.md.
# 0 or >=2 => exit 1 and record the cell as missing (fail-closed: the scorer
# counts it into incomplete_fraction; it is never imputed).
# ---------------------------------------------------------------------------
GEN_CELL_DIR="${RESULTS_ROOT}/${BRIEF_ID}/${ARM_ID}/seed-${SEED}"
CELL_DIR="${IMPL_ROOT}/${BRIEF_ID}/${ARM_ID}/seed-${SEED}"
mkdir -p "$CELL_DIR"

record_missing() {
  local detail="$1"
  python3 - "$CELL_DIR/impl-cell.json" "$ARM_ID" "$BRIEF_ID" "$SEED" "$detail" <<'PY'
import datetime, json, sys
path, arm, brief_id, seed, detail = sys.argv[1:6]
json.dump(
    {"arm": arm, "brief_id": brief_id, "seed": int(seed), "status": "missing",
     "detail": detail,
     "started_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
    open(path, "w"), indent=2, sort_keys=True)
PY
}

SPEC_MATCHES=()
if [[ -d "${GEN_CELL_DIR}/artifacts" ]]; then
  while IFS= read -r -d '' f; do
    SPEC_MATCHES+=("$f")
  done < <(find "${GEN_CELL_DIR}/artifacts" -type f -name '*spec*.md' -print0 | sort -z)
fi
if [[ ${#SPEC_MATCHES[@]} -ne 1 ]]; then
  echo "error: expected exactly 1 spec artifact under ${GEN_CELL_DIR}/artifacts (found ${#SPEC_MATCHES[@]})" >&2
  record_missing "spec artifact count ${#SPEC_MATCHES[@]} != 1"
  exit 1
fi
SPEC_PATH="${SPEC_MATCHES[0]}"

# ---------------------------------------------------------------------------
# Workspace: $IMPL_WORKROOT/<brief>/<arm>/seed-<seed>/workspace, OUTSIDE the
# repo tree (U0: reachability). Refuse a workroot inside this repo.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
WORKROOT_REAL="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$IMPL_WORKROOT")"
if [[ -n "$REPO_ROOT" && ( "$WORKROOT_REAL" == "$REPO_ROOT" || "$WORKROOT_REAL" == "$REPO_ROOT"/* ) ]]; then
  echo "error: IMPL_WORKROOT ($WORKROOT_REAL) is inside the repo tree ($REPO_ROOT)." >&2
  echo "       U0 isolation is reachability: the workspace must live outside the repo." >&2
  exit 1
fi
WORKSPACE="${IMPL_WORKROOT}/${BRIEF_ID}/${ARM_ID}/seed-${SEED}/workspace"

# ---------------------------------------------------------------------------
# One FIXED pinned implementer config for ALL arms (plugins disabled there).
# Same convention as run-arm.sh: honour an explicit override, else the default.
# ---------------------------------------------------------------------------
IMPL_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-${HOME}/.claude-implementer}"
if [[ ! -d "$IMPL_CONFIG_DIR" ]]; then
  echo "error: implementer config dir $IMPL_CONFIG_DIR does not exist." >&2
  echo "       Create the FIXED pinned-implementer config first (BENCHMARK.md §3)." >&2
  exit 1
fi
export CLAUDE_CONFIG_DIR="$IMPL_CONFIG_DIR"

if ! command -v "$CLAUDE_BIN" >/dev/null 2>&1; then
  echo "error: '$CLAUDE_BIN' not on PATH. Set CLAUDE_BIN or install Claude Code." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Prompt: render(PREAMBLE_TEMPLATE, module, entrypoint) + "\n\n" + spec text.
# The template is frozen (manifest bench.preamble_template); it substitutes
# exactly two values and carries no brief text, no arm identity, no hint about
# the experiment. prompt_sha/preamble_template_sha feed the U0 gate.
# ---------------------------------------------------------------------------
PREAMBLE_TEMPLATE='You are implementing a small Python project from the specification below.

Deliverables, all inside the current working directory:
  1. A Python module `{module}.py` at the top level, defining a callable
     `{entrypoint}` that satisfies the specification.
  2. A pytest test suite under `tests/`.

Rules:
  - Work only inside the current working directory.
  - Do not ask clarifying questions; proceed end to end.
  - Commit your work with git as you go.

Specification:'
if [[ -n "${PREAMBLE_TEMPLATE_FILE:-}" ]]; then
  if [[ ! -f "$PREAMBLE_TEMPLATE_FILE" ]]; then
    echo "error: PREAMBLE_TEMPLATE_FILE not found: $PREAMBLE_TEMPLATE_FILE" >&2
    exit 1
  fi
  PREAMBLE_TEMPLATE="$(cat "$PREAMBLE_TEMPLATE_FILE")"
fi
if [[ "$PREAMBLE_TEMPLATE" != *"{module}"* || "$PREAMBLE_TEMPLATE" != *"{entrypoint}"* ]]; then
  echo "error: preamble template must contain both {module} and {entrypoint} placeholders" >&2
  exit 1
fi

PREAMBLE="${PREAMBLE_TEMPLATE//\{module\}/$MODULE}"
PREAMBLE="${PREAMBLE//\{entrypoint\}/$ENTRYPOINT}"
# FROZEN normalization (BENCHMARK.md §1 U0): $(cat) strips ALL trailing
# newlines from the spec text; the joiner is exactly one "\n\n"; printf '%s'
# hashes the exact prompt string with no newline appended. spec_sha, by
# contrast, hashes the raw file bytes untouched. A verifier re-derives
# prompt_sha from (template, module, entrypoint, spec file) with these rules.
SPEC_TEXT="$(cat "$SPEC_PATH")"
PROMPT="${PREAMBLE}"$'\n\n'"${SPEC_TEXT}"

PROMPT_SHA="$(printf '%s' "$PROMPT" | sha256_stdin)"
TEMPLATE_SHA="$(printf '%s' "$PREAMBLE_TEMPLATE" | sha256_stdin)"
SPEC_SHA="$(sha256_stdin <"$SPEC_PATH")"

echo "==> arm:        $ARM_ID"
echo "==> brief:      $BRIEF_ID ($BRIEF_DIR)"
echo "==> seed:       $SEED"
echo "==> model:      $IMPLEMENTER_MODEL"
echo "==> config dir: $CLAUDE_CONFIG_DIR"
echo "==> spec:       $SPEC_PATH"
echo "==> workspace:  $WORKSPACE"
echo "==> cell dir:   $CELL_DIR"
echo

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------------------
# §5-analogue auto-approval: acceptEdits by default; SKIP_PERMS=1 opts into
# --dangerously-skip-permissions inside the throwaway workspace only.
# ---------------------------------------------------------------------------
PERM_FLAGS=(--permission-mode acceptEdits)
if [[ "${SKIP_PERMS:-0}" == "1" ]]; then
  PERM_FLAGS=(--dangerously-skip-permissions)
fi

# Portable timeout: prefer GNU timeout/gtimeout if present, else run direct.
TIMEOUT_BIN=""
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_BIN="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_BIN="gtimeout"
fi

TRANSCRIPT="${CELL_DIR}/transcript.jsonl"
RUN_LOG="${CELL_DIR}/run.log"

stage_workspace() {
  # Fresh workspace per attempt: the SPEC ONLY (never brief.md — the §1 U0
  # leakage rule), then git init + initial commit as the audit baseline.
  rm -rf "$WORKSPACE"
  mkdir -p "$WORKSPACE"
  cp "$SPEC_PATH" "${WORKSPACE}/SPEC.md"
  git -C "$WORKSPACE" init -q
  git -C "$WORKSPACE" add -A
  git -C "$WORKSPACE" -c user.name="eval-implementer" -c user.email="eval@local" \
      commit -q -m "chore: stage spec for ${ARM_ID}/${BRIEF_ID}/seed-${SEED}" || true
}

last_result_subtype() {
  # Last {"type":"result"} event wins; malformed lines are skipped (usage.py's
  # fail-closed convention). Prints "" when no result event exists.
  python3 - "$TRANSCRIPT" <<'PY' || true
import json, sys
subtype = ""
try:
    with open(sys.argv[1]) as fh:
        for line in fh:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("type") == "result":
                subtype = event.get("subtype") or ""
except OSError:
    pass
print(subtype)
PY
}

ATTEMPT=0
RETRIED=false
RUN_RC=0
SUBTYPE=""
while :; do
  stage_workspace
  echo "==> launching headless claude (attempt $((ATTEMPT + 1)), timeout ${TIMEOUT_SECS}s)"
  set +e
  (
    cd "$WORKSPACE"
    if [[ -n "$TIMEOUT_BIN" ]]; then
      "$TIMEOUT_BIN" "${TIMEOUT_SECS}" \
        "$CLAUDE_BIN" -p "$PROMPT" \
          --model "$IMPLEMENTER_MODEL" \
          "${PERM_FLAGS[@]}" \
          --output-format stream-json --verbose
    else
      echo "warning: no timeout binary found; running without a wall-clock cap" >&2
      "$CLAUDE_BIN" -p "$PROMPT" \
        --model "$IMPLEMENTER_MODEL" \
        "${PERM_FLAGS[@]}" \
        --output-format stream-json --verbose
    fi
  ) >"$TRANSCRIPT" 2>>"$RUN_LOG"
  RUN_RC=$?
  set -e

  if [[ $RUN_RC -eq 124 ]]; then
    # Timeout: no retry (§3 retry row).
    echo "warning: implementer hit the ${TIMEOUT_SECS}s timeout (status=timeout)" >&2
    break
  fi
  SUBTYPE="$(last_result_subtype)"
  if [[ "$SUBTYPE" == "error_during_execution" && $ATTEMPT -lt $MAX_RETRIES ]]; then
    ATTEMPT=$((ATTEMPT + 1))
    RETRIED=true
    BACKOFF=$((RETRY_BACKOFF_SECS * (2 ** (ATTEMPT - 1))))
    echo "warning: error_during_execution; retry $ATTEMPT/$MAX_RETRIES after ${BACKOFF}s" >&2
    sleep "$BACKOFF"
    continue
  fi
  break
done

# Status is derived by usage.parse_usage ITSELF — the same parser the scorer
# runs — never re-implemented here. A shell re-derivation was strictly more
# permissive (a result event with truncated scored fields read as "ok" while
# the scorer read "missing"), letting the script exit 0 on a cell the
# fail-closed chain would exclude. parse_usage is stdlib-only, so plain
# python3 (already a hard dependency) with PYTHONPATH at the package src is
# enough. Any parse failure fails closed to "missing".
STATUS="$(PYTHONPATH="${SCRIPT_DIR}/../src${PYTHONPATH:+:$PYTHONPATH}" \
  python3 - "$TRANSCRIPT" "$RUN_RC" <<'PY' || true
import sys
from eval_overexplanation.usage import parse_usage
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        print(parse_usage(fh, return_code=int(sys.argv[2])).status)
except OSError:
    print("missing")
PY
)"
if [[ -z "$STATUS" ]]; then
  STATUS="missing"   # the parser itself failed: fail closed, never "ok"
fi
if [[ "$STATUS" == "missing" ]]; then
  echo "warning: no usable result event in $TRANSCRIPT (status=missing)" >&2
fi

# ---------------------------------------------------------------------------
# Capture: workspace snapshot (sans .git — git-log.txt is the audit record),
# git log, and the impl-cell.json provenance record.
# ---------------------------------------------------------------------------
git -C "$WORKSPACE" log --oneline --stat >"${CELL_DIR}/git-log.txt" 2>/dev/null || true
rm -rf "${CELL_DIR}/workspace"
cp -R "$WORKSPACE" "${CELL_DIR}/workspace"
rm -rf "${CELL_DIR}/workspace/.git"

python3 - "$CELL_DIR/impl-cell.json" \
  "$ARM_ID" "$BRIEF_ID" "$SEED" "$IMPLEMENTER_MODEL" \
  "$PROMPT_SHA" "$TEMPLATE_SHA" "$MODULE" "$ENTRYPOINT" \
  "$SPEC_PATH" "$SPEC_SHA" "$WORKSPACE" "$STARTED_AT" \
  "$RUN_RC" "$RETRIED" "$STATUS" <<'PY'
import datetime, json, sys
(path, arm, brief_id, seed, model, prompt_sha, template_sha, module,
 entrypoint, spec_path, spec_sha, workspace, started_at, rc, retried,
 status) = sys.argv[1:17]
json.dump(
    {
        "arm": arm,
        "brief_id": brief_id,
        "seed": int(seed),
        "implementer_model": model,
        "prompt_sha": prompt_sha,
        "preamble_template_sha": template_sha,
        "module": module,
        "entrypoint": entrypoint,
        "spec_path": spec_path,
        "spec_sha": spec_sha,
        "workspace": workspace,
        "started_at": started_at,
        "finished_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "return_code": int(rc),
        "retried": retried == "true",
        "status": status,
    },
    open(path, "w"), indent=2, sort_keys=True)
PY

echo
echo "==> implement cell complete: $CELL_DIR (status=$STATUS)"
echo "    transcript: $TRANSCRIPT"
echo "    workspace:  ${CELL_DIR}/workspace"
echo "    git log:    ${CELL_DIR}/git-log.txt"

# Fail-closed exit: ANY non-ok status exits non-zero, even when the CLI itself
# returned 0. A cell whose transcript carries no result event (status=missing)
# with rc 0 is exactly the fabricated-cheap-cell case the fail-closed chain
# exists to prevent — the orchestrator must count it, so it must see a failure.
if [[ "$STATUS" != "ok" ]]; then
  echo "error: cell status=$STATUS (fail-closed: non-ok cells exit non-zero)" >&2
  if [[ $RUN_RC -ne 0 ]]; then
    exit "$RUN_RC"   # propagate the CLI's own rc (e.g. 124 timeout)
  fi
  exit 1
fi

# Propagate the CLI's exit status so the orchestrator can count failures.
exit "$RUN_RC"

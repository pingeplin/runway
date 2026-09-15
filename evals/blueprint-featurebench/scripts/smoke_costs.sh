#!/usr/bin/env bash
# Offline smoke test for stage 10 (cost ledger + token reporting).
# Needs python3.11+, no docker/network/fb/claude.
set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
TMP="$(mktemp -d)"
[ -n "${KEEP_TMP:-}" ] && echo "tmp: $TMP" || trap 'rm -rf "$TMP"' EXIT

pass() { printf '  ok  %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1" >&2; exit 1; }

# Work on a throwaway copy of the tree so this never touches real results/.
FIX="$TMP/harness"
mkdir -p "$FIX"
cp -R "$SCRIPTS/.." "$FIX/evals"
EV="$FIX/evals"
rm -rf "$EV/results"
mkdir -p "$EV/results/specs" "$EV/results/verdicts"

# ------------------------------------------------------------ fixture data
# Arm A: task1 (single attempt, usage present), task2 (no usage — unmeasured,
# cost still recorded). Arm A's per-arm token total must poison to "—".
# Arm B: task1 (two attempts, both with usage — summed). Arm B's token total
# must reflect the sum across attempts, not just the last one.
RUN_A="$TMP/infer_arm_a/2026-09-10__00-00-00"
RUN_B="$TMP/infer_arm_b/2026-09-10__00-00-00"

mk_stream() {
  # $1 = path, $2 = cost, $3 = usage json fragment (or "null")
  local path="$1" cost="$2" usage="$3"
  mkdir -p "$(dirname "$path")"
  if [ "$usage" = "null" ]; then
    printf '{"type":"result","subtype":"success","total_cost_usd":%s,"duration_ms":1000,"num_turns":3}\n' \
      "$cost" > "$path"
  else
    printf '{"type":"result","subtype":"success","total_cost_usd":%s,"duration_ms":1000,"num_turns":3,"usage":%s}\n' \
      "$cost" "$usage" > "$path"
  fi
}

USAGE_A1='{"input_tokens":50,"cache_creation_input_tokens":5,"cache_read_input_tokens":2,"output_tokens":8}'
USAGE_B1='{"input_tokens":100,"cache_creation_input_tokens":50,"cache_read_input_tokens":20,"output_tokens":30}'
USAGE_B2='{"input_tokens":200,"cache_creation_input_tokens":10,"cache_read_input_tokens":5,"output_tokens":15}'

mk_stream "$RUN_A/run_outputs/task1.lv1/attempt-1/claude_code_stream_output.jsonl" 1.00 "$USAGE_A1"
mk_stream "$RUN_A/run_outputs/task2.lv1/attempt-1/claude_code_stream_output.jsonl" 2.00 null
mk_stream "$RUN_B/run_outputs/task1.lv1/attempt-1/claude_code_stream_output.jsonl" 1.00 "$USAGE_B1"
mk_stream "$RUN_B/run_outputs/task1.lv1/attempt-2/claude_code_stream_output.jsonl" 0.50 "$USAGE_B2"

# Control arm A_plan: task1 only, its brief billed from results/briefs/.
RUN_P="$TMP/infer_arm_a_plan/2026-09-10__00-00-00"
mk_stream "$RUN_P/run_outputs/task1.lv1/attempt-1/claude_code_stream_output.jsonl" 0.75 "$USAGE_A1"

cat > "$EV/results/runs.json" <<JSON
{
  "A": {"arm": "A", "task_ids": ["task1.lv1", "task2.lv1"],
        "source_run_dirs": ["$RUN_A"],
        "report_json": "$EV/results/report_a.json"},
  "B": {"arm": "B", "task_ids": ["task1.lv1"],
        "source_run_dirs": ["$RUN_B"],
        "report_json": "$EV/results/report_b.json"},
  "A_plan": {"arm": "A_plan", "task_ids": ["task1.lv1"],
        "source_run_dirs": ["$RUN_P"],
        "report_json": "$EV/results/report_p.json"}
}
JSON
cat > "$EV/results/report_p.json" <<'JSON'
{"task1.lv1": {"resolved": false}}
JSON
mkdir -p "$EV/results/briefs"
cat > "$EV/results/briefs/task1.lv1.meta.json" <<'JSON'
{"cost_usd": 0.40, "wall_seconds": 20,
 "usage": {"input_tokens": 7, "cache_creation_input_tokens": 0,
           "cache_read_input_tokens": 0, "output_tokens": 3}}
JSON

# report.json in the top-level {iid: {"resolved": bool}} shape.
cat > "$EV/results/report_a.json" <<'JSON'
{"task1.lv1": {"resolved": true}, "task2.lv1": {"resolved": false}}
JSON
cat > "$EV/results/report_b.json" <<'JSON'
{"task1.lv1": {"resolved": true}}
JSON

# Host stage sidecar (01 specs) for task1, feeding Arm B's spec cost.
cat > "$EV/results/specs/task1.lv1.meta.json" <<'JSON'
{"cost_usd": 0.25, "wall_seconds": 30,
 "usage": {"input_tokens": 40, "cache_creation_input_tokens": 0,
           "cache_read_input_tokens": 0, "output_tokens": 10}}
JSON

printf '\n== pure-function check: attempt summing in infer_costs()\n'
$PY - "$EV" "$RUN_A" "$RUN_B" <<'PY' || exit 1
import importlib.util, pathlib, sys
ev, run_a, run_b = (pathlib.Path(p) for p in sys.argv[1:4])
spec = importlib.util.spec_from_file_location("r10", ev / "scripts/10_costs.py")
sys.path.insert(0, str(ev / "scripts"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

costs = m.infer_costs({"source_run_dirs": [str(run_b)]})
tok = costs["task1.lv1"]["tokens"]
assert tok == {"input": 300, "cache_write": 60, "cache_read": 25, "output": 45}, tok
assert abs(costs["task1.lv1"]["cost_usd"] - 1.5) < 1e-9, costs["task1.lv1"]["cost_usd"]

costs_a = m.infer_costs({"source_run_dirs": [str(run_a)]})
assert costs_a["task2.lv1"]["tokens"] is None, costs_a["task2.lv1"]["tokens"]
PY
pass "infer_costs() sums tokens across attempts (not just the last one)"

printf '\n== 10 costs (token reporting)\n'
OUT="$($PY "$EV/scripts/10_costs.py" --runs "$EV/results/runs.json" \
  --out "$EV/results/cost_report.md")" || fail "10 exited non-zero"
echo "$OUT" | sed 's/^/    /'

echo "$OUT" | grep -q 'tokens' || fail "console log missing token totals"

MD="$EV/results/cost_report.md"
[ -f "$MD" ] || fail "cost_report.md not written"

$PY - "$MD" <<'PY' || exit 1
import sys
md = open(sys.argv[1]).read()
lines = md.splitlines()

# USD totals: A = 1.00 + 2.00 = 3.00; B = 1.00 + 0.50 = 1.50.
assert "$3.00" in md, "arm A USD total wrong:\n" + md
assert "$1.50" in md, "arm B USD total wrong:\n" + md

assert "Per-arm tokens" in md, "tokens table missing"

# Arm A: task2 has no usage, so the whole arm's token total is unmeasured.
a_token_row = "| A | — | — | — | — | — | — | — |"
assert a_token_row in lines, f"expected exact row {a_token_row!r} not found:\n{md}"

# Arm B: attempts summed -> input 300, cache_write 60, cache_read 25,
# output 45, total 430; n_measured=1, resolved=1 -> mean/total-per-resolved both 430.
b_token_row = "| B | 300 | 60 | 25 | 45 | 430 | 430 | 430 |"
assert b_token_row in lines, f"expected exact row {b_token_row!r} not found:\n{md}"

# Cost row for A still shows a real dollar figure, proving cost and token
# measurement are tracked independently (A's tokens are unmeasured, its cost is not).
a_cost_row = next(l for l in lines if l.startswith("| A |") and "$" in l)
assert "$3.00" in a_cost_row, f"arm A cost row should still be measured:\n{a_cost_row}"

assert "Host-side stages" in md
assert "40" in md and "10" in md, "host stage token columns missing"

assert "`usage`" in md, "intro should mention usage payload"

# Briefs are a host stage of their own, billed to A_plan only.
assert any(l.startswith("| 14 briefs (Arm A_plan input) | 1 | $0.40 |") for l in lines), md
# All-in = inference + the arm's own host stage; A has none.
for row in ("| A | 2 | $3.00 | $0.00 | $3.00 | $1.50 | 1 |",
            "| B | 1 | $1.50 | $0.25 | $1.75 | $1.75 | 1 |",
            "| A_plan | 1 | $0.75 | $0.40 | $1.15 | $1.15 | 0 |"):
    assert row in lines, f"expected all-in row {row!r} not found:\n{md}"
# 3.00 + 1.50 + 0.75 infer + 0.25 spec + 0.40 brief
assert "**Panel total (measured): $5.90**" in md, md
PY
pass "USD totals correct; task2 missing usage renders arm A tokens as — (never 0)"
pass "arm B token row exactly matches summed attempts"
pass "briefs billed as their own host stage; all-in per arm adds only the arm's own host stage"

printf '\nsmoke costs PASSED\n'

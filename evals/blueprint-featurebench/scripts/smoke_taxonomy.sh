#!/usr/bin/env bash
# Offline smoke test for stage 08 (failure taxonomy). Needs python3.11+;
# needs neither docker, nor network, nor a real `claude`, nor `fb`.
#
# Covers: bundle assembly (original problem_statement from Arm A, spec from
# results/specs/, model_patch, F2P test log), the FAIL_TO_PASS-all-green ->
# PASS_TO_PASS-regression log fallback, per-cell json + aggregated
# taxonomy_report.md, a malformed-response -> parse_error cell, and
# resumability (a cached cell — including a parse_error one — is never
# re-run without --force).
set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPTS/.." && pwd)"
PY="${PYTHON:-python3}"
TMP="$(mktemp -d)"
[ -n "${KEEP_TMP:-}" ] && echo "tmp: $TMP" || trap 'rm -rf "$TMP"' EXIT

pass() { printf '  ok  %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1" >&2; exit 1; }

# Build the fixture tree by hand (not `cp -R` of the whole repo — results/
# holds real, large pilot artifacts we must never touch or copy).
EV="$TMP/harness"
mkdir -p "$EV/scripts" "$EV/prompts" "$EV/results"
cp "$SCRIPTS/_common.py" "$SCRIPTS/08_taxonomy.py" "$EV/scripts/"
cp "$ROOT/prompts/taxonomy.md" "$EV/prompts/"

cat > "$EV/config.toml" <<'TOML'
[eval]
dataset = "LiberCoders/FeatureBench"
split = "lite"
limit = 0
n_concurrent = 2

[taxonomy]
model = "mock-taxonomy-model"
timeout_seconds = 60
claude_args = ["--permission-mode", "bypassPermissions"]
TOML

# ---------------------------------------------------------------- fixtures
SPEC_SEP=$'\n\n---\n\n## Implementation Spec\n\n'

mkdir -p "$EV/results/specs"
printf '# Spec for t1\n\nAcceptance: widget() returns 42.\n' > "$EV/results/specs/acme__t1.lv1.md"
printf '# Spec for t2\n\nAcceptance: no regressions in mod.py.\n' > "$EV/results/specs/acme__t2.lv1.md"
printf '# Spec for t3\n\nAcceptance: parses malformed input.\n' > "$EV/results/specs/acme__t3.lv1.md"

$PY - "$EV" "$SPEC_SEP" <<'PY'
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])
sep = sys.argv[2]

tasks = ["acme__t1.lv1", "acme__t2.lv1", "acme__t3.lv1"]
originals = {
    "acme__t1.lv1": "Original statement for t1: implement widget().",
    "acme__t2.lv1": "Original statement for t2: fix mod.py without breaking callers.",
    "acme__t3.lv1": "Original statement for t3: handle malformed input.",
}
patches_a = {t: f"diff --git a/{t}.py b/{t}.py\n+arm a patch for {t}\n" for t in tasks}
patches_b = {t: f"diff --git a/{t}.py b/{t}.py\n+arm b patch for {t}\n" for t in tasks}
specs = {
    "acme__t1.lv1": (ev / "results/specs/acme__t1.lv1.md").read_text(),
    "acme__t2.lv1": (ev / "results/specs/acme__t2.lv1.md").read_text(),
    "acme__t3.lv1": (ev / "results/specs/acme__t3.lv1.md").read_text(),
}

def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

rows_a = [
    {
        "instance_id": t, "n_attempt": 1, "model_patch": patches_a[t],
        "task_metadata": {"instance_id": t, "problem_statement": originals[t]},
    }
    for t in tasks
]
write_jsonl(ev / "results/infer_arm_a/output.jsonl", rows_a)

rows_b = [
    {
        "instance_id": t, "n_attempt": 1, "model_patch": patches_b[t],
        "task_metadata": {"instance_id": t, "problem_statement": originals[t] + sep + specs[t]},
    }
    for t in tasks
]
write_jsonl(ev / "results/infer_arm_b/output.jsonl", rows_b)

def write_report(path, iid, resolved, pass_rate, f2p_fail, p2p_fail):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({iid: {
        "n_attempt": 1, "patch_is_None": False, "patch_exists": True,
        "patch_successfully_applied": True,
        "resolved": resolved, "pass_rate": pass_rate,
        "tests_status": {
            "FAIL_TO_PASS": {"success": [], "failure": f2p_fail},
            "PASS_TO_PASS": {"success": [], "failure": p2p_fail},
        },
    }}, indent=2))

# Arm A: only t1 has a report at all (t2/t3 test the "no report -> skip" path).
d = ev / "results/infer_arm_a/eval_outputs/acme__t1.lv1/attempt-1"
d.mkdir(parents=True, exist_ok=True)
write_report(d / "report.json", "acme__t1.lv1", False, 0.0, ["tests/test_1.py::test_widget"], [])
(d / "test_output.txt").write_text(
    "===== test session starts =====\n"
    "tests/test_1.py::test_widget FAILED\n"
    "E   AssertionError: widget() returned None\n"
    "===== 1 failed in 0.02s =====\n"
)

# Arm B / t1: ordinary F2P failure — the primary test_output.txt path.
d = ev / "results/infer_arm_b/eval_outputs/acme__t1.lv1/attempt-1"
d.mkdir(parents=True, exist_ok=True)
write_report(d / "report.json", "acme__t1.lv1", False, 0.0, ["tests/test_1.py::test_widget"], [])
(d / "test_output.txt").write_text(
    "===== test session starts =====\n"
    "tests/test_1.py::test_widget FAILED\n"
    "E   AssertionError: widget() returned None (arm B)\n"
    "===== 1 failed in 0.02s =====\n"
)

# Arm B / t2: F2P all green (pass_rate 1.0, no F2P failures) but resolved is
# still False because a PASS_TO_PASS regression broke — this must make
# pick_test_log() fall back to the failing test_output_p2p_*.txt file
# instead of the clean test_output.txt.
d = ev / "results/infer_arm_b/eval_outputs/acme__t2.lv1/attempt-1"
d.mkdir(parents=True, exist_ok=True)
write_report(d / "report.json", "acme__t2.lv1", False, 1.0, [], ["mod.py::test_caller"])
(d / "test_output.txt").write_text(
    "===== test session starts =====\ntests/test_2.py::test_fix PASSED\n===== 1 passed in 0.01s =====\n"
)
(d / "test_output_p2p_mod.txt").write_text(
    "===== test session starts =====\n"
    "mod.py::test_caller FAILED\n"
    "E   TypeError: caller() missing 1 required positional argument\n"
    "===== 1 failed in 0.03s =====\n"
)

# Arm B / t3: F2P failure present (so primary log path), content unused by
# the mock claude below — this cell exercises the malformed-response ->
# parse_error path instead.
d = ev / "results/infer_arm_b/eval_outputs/acme__t3.lv1/attempt-1"
d.mkdir(parents=True, exist_ok=True)
write_report(d / "report.json", "acme__t3.lv1", False, 0.0, ["tests/test_3.py::test_parse"], [])
(d / "test_output.txt").write_text(
    "===== test session starts =====\ntests/test_3.py::test_parse FAILED\n===== 1 failed in 0.02s =====\n"
)

runs = {
    "A": {
        "arm": "A", "task_ids": tasks,
        "output_jsonl": str(ev / "results/infer_arm_a/output.jsonl"),
        "eval_outputs_dir": str(ev / "results/infer_arm_a/eval_outputs"),
    },
    "B": {
        "arm": "B", "task_ids": tasks,
        "output_jsonl": str(ev / "results/infer_arm_b/output.jsonl"),
        "eval_outputs_dir": str(ev / "results/infer_arm_b/eval_outputs"),
    },
}
(ev / "results/runs.json").write_text(json.dumps(runs, indent=2))
PY

# Mock claude: same argv shape as the real one. Branches on which task id
# appears in the rendered prompt. t3 returns a reply with NO final-line JSON
# object at all, to exercise the parse_error path (no retry is implemented,
# per the design notes — a malformed reply is recorded as parse_error).
CLAUDE="$TMP/fake-claude"
cat > "$CLAUDE" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
prompt=""
next_is_prompt=0
model=""
next_is_model=0
for arg in "$@"; do
  if [ "$next_is_prompt" = 1 ]; then prompt="$arg"; next_is_prompt=0; fi
  if [ "$next_is_model" = 1 ]; then model="$arg"; next_is_model=0; fi
  if [ "$arg" = "-p" ]; then next_is_prompt=1; fi
  if [ "$arg" = "--model" ]; then next_is_model=1; fi
done
[ -n "$prompt" ] || { echo "mock claude: no -p prompt" >&2; exit 3; }
[ "$model" = "mock-taxonomy-model" ] || { echo "mock claude: unexpected model $model" >&2; exit 5; }
case "$prompt" in
  *'{problem_statement}'*|*'{model_patch}'*|*'{task_id}'*|*'{test_log_tail}'*) \
    echo "mock claude: a template placeholder was not substituted" >&2; exit 4;;
esac
case "$prompt" in
  *'`acme__t3.lv1`'*)
    echo '{"type":"result","subtype":"success","is_error":false,"result":"I cannot decide, sorry, no final JSON line here.","total_cost_usd":0.02,"duration_ms":400,"num_turns":2,"usage":{"input_tokens":10,"output_tokens":5}}'
    ;;
  *'`acme__t2.lv1`'*)
    echo '{"type":"result","subtype":"success","is_error":false,"result":"Reasoning about the regression...\n{\"class\": \"impl_wrong\", \"spec_contribution\": \"harmed\", \"rationale\": \"F2P passed but the patch broke a PASS_TO_PASS caller test.\"}","total_cost_usd":0.03,"duration_ms":800,"num_turns":3,"usage":{"input_tokens":20,"output_tokens":10}}'
    ;;
  *)
    echo '{"type":"result","subtype":"success","is_error":false,"result":"Reasoning...\n{\"class\": \"spec_wrong\", \"spec_contribution\": \"harmed\", \"rationale\": \"The spec narrowed the ask and the agent followed it exactly.\"}","total_cost_usd":0.05,"duration_ms":1200,"num_turns":4,"usage":{"input_tokens":30,"output_tokens":15}}'
    ;;
esac
SH
chmod +x "$CLAUDE"

printf '\n== 08 taxonomy --dry-run\n'
OUT_DRY="$($PY "$EV/scripts/08_taxonomy.py" --config "$EV/config.toml" --claude-cmd "$CLAUDE" --dry-run)" \
  || fail "--dry-run exited non-zero"
echo "$OUT_DRY" | sed 's/^/    /'
echo "$OUT_DRY" | grep -q "4 failing cell(s) selected" || fail "dry-run should select 4 cells (A/t1, B/t1, B/t2, B/t3)"
echo "$OUT_DRY" | grep -q "acme__t2.lv1 \[B\].*test_output_p2p" || fail "t2/B should select the P2P regression log, not test_output.txt"
[ -d "$EV/results/taxonomy" ] && fail "--dry-run must not write any taxonomy json"
pass "--dry-run lists exactly the 4 failing cells and picks the P2P fallback log for t2/B"

printf '\n== 08 taxonomy (real run against mock claude)\n'
$PY "$EV/scripts/08_taxonomy.py" --config "$EV/config.toml" --claude-cmd "$CLAUDE" >/dev/null \
  && fail "run should exit 1 (one cell — t3/B — is a parse_error)"
pass "exit code reflects the parse_error cell (1/4 not ok)"

$PY - "$EV" <<'PY' || exit 1
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])

a1 = json.loads((ev / "results/taxonomy/A/acme__t1.lv1.json").read_text())
assert a1["ok"] is True, a1
assert a1["classification"] in {"spec_wrong", "impl_wrong", "env_or_flaky", "unclear"}, a1
assert a1["spec_contribution"] is None, a1  # Arm A must never carry a spec_contribution
assert a1["model"] == "mock-taxonomy-model", a1

b1 = json.loads((ev / "results/taxonomy/B/acme__t1.lv1.json").read_text())
assert b1["ok"] is True and b1["classification"] == "spec_wrong", b1
assert b1["spec_contribution"] == "harmed", b1

b2 = json.loads((ev / "results/taxonomy/B/acme__t2.lv1.json").read_text())
assert b2["ok"] is True and b2["classification"] == "impl_wrong", b2
assert "PASS_TO_PASS" in b2["rationale"] or "caller" in b2["rationale"], b2

b3 = json.loads((ev / "results/taxonomy/B/acme__t3.lv1.json").read_text())
assert b3["ok"] is False, b3
assert b3["error"].startswith("parse_error:"), b3
assert b3["classification"] == "unclear", b3
assert b3["spec_contribution"] is None, b3

# Arm A never got a report for t2/t3, so no cells (and no files) exist for them.
assert not (ev / "results/taxonomy/A/acme__t2.lv1.json").exists()
assert not (ev / "results/taxonomy/A/acme__t3.lv1.json").exists()
PY
pass "per-cell json: A/t1 spec_contribution=null, B/t1 spec_wrong, B/t2 impl_wrong (P2P evidence), B/t3 parse_error"

$PY - "$EV" <<'PY' || exit 1
import pathlib, sys
md = (pathlib.Path(sys.argv[1]) / "results/taxonomy_report.md").read_text()
assert "`acme__t1.lv1` | A |" in md, md
assert "`acme__t1.lv1` | B |" in md, md
assert "`acme__t2.lv1` | B |" in md, md
assert "`acme__t3.lv1` | B |" in md, md
assert "acme__t2.lv1` | A |" not in md, md
assert "| **total cells** | **4** |" in md, md
assert "Single-rater LLM" in md, md
PY
pass "taxonomy_report.md: 4-row table + totals + single-rater caveat"

printf '\n== resumability: cached cells (incl. parse_error) are never re-run without --force\n'
B3_BEFORE="$(cat "$EV/results/taxonomy/B/acme__t3.lv1.json")"
BROKEN="$TMP/broken-claude"
printf '#!/usr/bin/env bash\necho "should never be invoked" >&2\nexit 9\n' > "$BROKEN"
chmod +x "$BROKEN"
RESUME_LOG="$TMP/resume_out.log"
set +e
$PY "$EV/scripts/08_taxonomy.py" --config "$EV/config.toml" --claude-cmd "$BROKEN" >"$RESUME_LOG" 2>&1
rc=$?
set -e
OUT_RESUME="$(cat "$RESUME_LOG")"
[ "$rc" -eq 1 ] || fail "resumed run should still report the cached t3 parse_error as not-ok, got rc=$rc"
echo "$OUT_RESUME" | grep -q "cached, skipping" || fail "expected cached-skip log lines"
echo "$OUT_RESUME" | grep -q "should never be invoked" && fail "broken claude was invoked despite cached json"
B3_AFTER="$(cat "$EV/results/taxonomy/B/acme__t3.lv1.json")"
[ "$B3_BEFORE" = "$B3_AFTER" ] || fail "cached parse_error cell must be left untouched without --force"
pass "second run skips every cached cell (including the parse_error one) and calls claude zero times"

printf '\n== --force + --task-id/--arm filters retry a single cell\n'
FIXED="$TMP/fixed-claude"
cat > "$FIXED" <<'SH'
#!/usr/bin/env bash
echo '{"type":"result","subtype":"success","is_error":false,"result":"{\"class\": \"env_or_flaky\", \"spec_contribution\": \"neutral\", \"rationale\": \"Retried and now the rater can decide.\"}","total_cost_usd":0.01,"duration_ms":300,"num_turns":1,"usage":{"input_tokens":5,"output_tokens":5}}'
SH
chmod +x "$FIXED"
$PY "$EV/scripts/08_taxonomy.py" --config "$EV/config.toml" --claude-cmd "$FIXED" \
  --force --task-id acme__t3.lv1 --arm B >/dev/null || fail "forced single-cell retry exited non-zero"
$PY - "$EV" <<'PY' || exit 1
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])
b3 = json.loads((ev / "results/taxonomy/B/acme__t3.lv1.json").read_text())
assert b3["ok"] is True and b3["classification"] == "env_or_flaky", b3
# Untouched by the forced, filtered rerun.
b1 = json.loads((ev / "results/taxonomy/B/acme__t1.lv1.json").read_text())
assert b1["classification"] == "spec_wrong", b1
PY
pass "--force --task-id --arm retries exactly the selected cell, leaves the rest cached"

printf '\nsmoke test PASSED\n'

#!/usr/bin/env bash
# Offline smoke test for stage 14 (control arms) and stage 05c (their report).
# Needs python3.11+ and `datasets`; needs neither docker, nor network, nor a
# real `claude`, nor `fb`.
set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
TMP="$(mktemp -d)"
[ -n "${KEEP_TMP:-}" ] && echo "tmp: $TMP" || trap 'rm -rf "$TMP"' EXIT

pass() { printf '  ok  %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1" >&2; exit 1; }

FIX="$TMP/harness"
mkdir -p "$FIX"
cp -R "$SCRIPTS/.." "$FIX/evals"
EV="$FIX/evals"
rm -rf "$EV/results"
mkdir -p "$EV/results/specs"

cat > "$EV/config.toml" <<'TOML'
[eval]
dataset = "LiberCoders/FeatureBench"
split = "lite"
n_concurrent = 2

[spec]
model = "claude-sonnet-5"
timeout_seconds = 120
claude_args = ["--permission-mode", "bypassPermissions"]

[brief]
timeout_seconds = 60
max_budget_usd = 30

[infer]
model = "claude-sonnet-5"
fb_config_path = "fb_config.toml"
n_concurrent = 1
timeout_seconds = 1800
TOML
cp "$EV/fb_config.example.toml" "$EV/fb_config.toml"

# ---------------------------------------------------------------- fixtures
DS="$TMP/split.jsonl"
$PY - "$DS" "$EV" <<'PY'
import json, pathlib, sys
rows, tasks = [], []
for i in range(1, 5):
    iid = f"acme__widget-{i}.lv1"
    rows.append({
        "instance_id": iid,
        "problem_statement": f"Original statement for task {i}.",
        "image_name": f"librecoders/featurebench:acme_widget_{i}",
        "patch": (
            "diff --git a/src/widget.py b/src/widget.py\n"
            "--- a/src/widget.py\n"
            "+++ b/src/widget.py\n"
            "@@ -1,2 +1 @@\n"
            " def widget(): pass\n"
            "-REFERENCE_SOLUTION = True\n"
        ),
        "FAIL_TO_PASS": [f"tests/test_{i}.py::test_feature"],
        "repo_settings": "{}",
    })
    tasks.append({"id": iid, "image_name": "img", "status": "spec_ok"})
with open(sys.argv[1], "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
ev = pathlib.Path(sys.argv[2])
(ev / "results/tasks.json").write_text(json.dumps(
    {"dataset": "LiberCoders/FeatureBench", "split": "lite", "tasks": tasks}, indent=2))
for t in tasks:
    (ev / "results/specs" / f"{t['id']}.md").write_text(f"# Mock spec for {t['id']}\n")
    (ev / "results/specs" / f"{t['id']}.meta.json").write_text(json.dumps(
        {"ok": True, "cost_usd": 2.0, "wall_seconds": 600}))
PY

TESTBED="$TMP/testbed"
mkdir -p "$TESTBED/src" "$TESTBED/tests"
printf 'def widget(): pass\nREFERENCE_SOLUTION = True\n' > "$TESTBED/src/widget.py"
for i in 1 2 3 4; do echo "def test_feature(): pass" > "$TESTBED/tests/test_$i.py"; done
git -C "$TESTBED" init -q && git -C "$TESTBED" add -A && \
  git -C "$TESTBED" -c user.email=smoke@test -c user.name=smoke commit -qm testbed

# Mock claude. FAKE_MODE: ok (default) | leak (init lists blueprint) |
# noinit (single stage-01-style JSON, no init event).
cat > "$TMP/fake_claude.py" <<'PY'
import json, os, pathlib, sys

argv = sys.argv[1:]
if os.environ.get("FAKE_ARGV_LOG"):
    with open(os.environ["FAKE_ARGV_LOG"], "a") as f:
        f.write(json.dumps({"cwd": os.getcwd(), "argv": argv}) + "\n")
if "{problem_statement}" in argv[argv.index("-p") + 1]:
    sys.exit(4)
mode = os.environ.get("FAKE_MODE", "ok")
name = pathlib.Path.cwd().name

brief = pathlib.Path(".handoff/brief.md")
brief.parent.mkdir(parents=True, exist_ok=True)
brief.write_text(f"# Brief for {name}\n\nRestore helper() in src/widget.py.\n")
marker = "(no marker)" if "widget-3." in name else "BRIEF_PATH: .handoff/brief.md"
result = {"type": "result", "subtype": "success", "is_error": False,
          "result": f"Wrote the brief.\n\n{marker}", "total_cost_usd": 0.5,
          "duration_ms": 1000, "duration_api_ms": 900, "num_turns": 4,
          "usage": {"input_tokens": 10, "output_tokens": 5}}
if mode == "noinit":
    print(json.dumps(result))
    sys.exit(0)
if argv[argv.index("--output-format") + 1] != "stream-json" or "--verbose" not in argv:
    sys.exit(5)

plugins = [{"name": "code-review", "path": "/plugins/code-review"}]
skills = ["code-review:code-review"]
agents = ["general-purpose"]
if mode == "leak":
    plugins.append({"name": "blueprint", "path": "/plugins/blueprint"})
    skills.append("blueprint:spec")
    agents.append("blueprint:spec-evaluator")
print(json.dumps({"type": "system", "subtype": "init", "claude_code_version": "9.9.9",
                  "plugins": plugins, "skills": skills, "slash_commands": skills, "agents": agents}))
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "working"}]}}))
print(json.dumps(result))
PY
CLAUDE="$TMP/fake-claude"
printf '#!/usr/bin/env bash\nexec python3 %q "$@"\n' "$TMP/fake_claude.py" > "$CLAUDE"
chmod +x "$CLAUDE"

S14=("$PY" "$EV/scripts/14_control_arms.py" --config "$EV/config.toml" --mock-dataset "$DS")

printf '\n== 14 brief (mock claude + mock testbed)\n'
FAKE_ARGV_LOG="$TMP/argv.jsonl" "${S14[@]}" --stage brief --mock-testbed "$TESTBED" \
  --claude-cmd "$CLAUDE" --keep-workspaces --parallel 2 >/dev/null || fail "14 brief exited non-zero"

$PY - "$EV" "$TMP/argv.jsonl" <<'PY' || exit 1
import json, pathlib, subprocess, sys
ev, argv_log = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
for i in range(1, 5):
    tid = f"acme__widget-{i}.lv1"
    meta = json.loads((ev / "results/briefs" / f"{tid}.meta.json").read_text())
    assert meta["ok"] is True and meta["cost_usd"] == 0.5, meta
    assert meta["plugins_loaded"] == ["code-review"] and meta["blueprint_leaks"] == [], meta
    assert meta["claude_code_version"] == "9.9.9", meta
    assert meta["mask_applied"] is True and meta["f2p_deleted"] == 1 and meta["git_reinit"] is True, meta
    assert meta["brief_located_by"] == ("fixed_path" if i == 3 else "marker"), meta
    assert f"Brief for {tid}" in (ev / "results/briefs" / f"{tid}.md").read_text()
    ws = ev / "results/workspaces_brief" / tid
    assert "REFERENCE_SOLUTION" not in (ws / "src/widget.py").read_text(), "oracle survived masking"
    assert not (ws / "tests" / f"test_{i}.py").exists(), "F2P test file not deleted"
    count = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=ws, capture_output=True, text=True)
    assert count.stdout.strip() == "1", count.stdout
    head = subprocess.run(["git", "show", "HEAD:src/widget.py"], cwd=ws, capture_output=True, text=True)
    assert "REFERENCE_SOLUTION" not in head.stdout, "oracle recoverable via git show HEAD"

calls = [json.loads(l) for l in argv_log.read_text().splitlines()]
assert len(calls) == 4, calls
for call in calls:
    argv = call["argv"]
    settings = json.loads(argv[argv.index("--settings") + 1])
    assert settings == {"enabledPlugins": {"blueprint@runway": False}}, settings
    assert argv[argv.index("--max-budget-usd") + 1] == "30", argv
    assert argv[argv.index("--permission-mode") + 1] == "bypassPermissions", "[spec] claude_args not inherited"
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5", argv
    assert "/workspaces_brief/acme__widget-" in call["cwd"], call["cwd"]
PY
pass "briefs + metas written; blueprint disabled in argv and proven absent; oracle masked, history re-initialised; marker and fixed-path fallback"

BROKEN="$TMP/broken-claude"
printf '#!/usr/bin/env bash\nexit 9\n' > "$BROKEN"; chmod +x "$BROKEN"
"${S14[@]}" --stage brief --mock-testbed "$TESTBED" --claude-cmd "$BROKEN" >/dev/null \
  || fail "14 brief resume run failed"
pass "brief stage is resumable (cached briefs skipped)"

"${S14[@]}" --stage brief --mock-testbed "$TESTBED" --claude-cmd "$CLAUDE" --force >/dev/null \
  || fail "14 brief --force exited non-zero"
[ -z "$(ls -A "$EV/results/workspaces_brief" 2>/dev/null)" ] || fail "workspaces kept without --keep-workspaces"
pass "workspaces removed after a successful brief by default"

set +e
FAKE_MODE=leak "${S14[@]}" --stage brief --mock-testbed "$TESTBED" --claude-cmd "$CLAUDE" --force >/dev/null 2>&1
rc_leak=$?
GATE="$("${S14[@]}" --stage dataset --arm A_plan 2>&1)"
rc_gate=$?
set -e
[ "$rc_leak" -eq 1 ] || fail "a session that loads blueprint must fail the brief stage, got rc=$rc_leak"
[ "$rc_gate" -ne 0 ] || fail "A_plan dataset must refuse tasks without a usable brief"
echo "$GATE" | grep -q "no usable brief" || fail "gate message missing: $GATE"
$PY - "$EV" <<'PY' || exit 1
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])
meta = json.loads((ev / "results/briefs/acme__widget-1.lv1.meta.json").read_text())
assert meta["ok"] is False and "blueprint reachable" in meta["error"], meta
assert meta["blueprint_leaks"] == ["blueprint", "blueprint:spec", "blueprint:spec-evaluator"], meta
PY
"${S14[@]}" --stage dataset --arm A_hint >/dev/null || fail "A_hint must not depend on briefs"
pass "blueprint in the init event fails the task; A_plan dataset gated, A_hint unaffected"

set +e
FAKE_MODE=noinit "${S14[@]}" --stage brief --mock-testbed "$TESTBED" --claude-cmd "$CLAUDE" --force >/dev/null 2>&1
rc_noinit=$?
set -e
[ "$rc_noinit" -eq 1 ] || fail "a session without an init event must fail, got rc=$rc_noinit"
$PY - "$EV" <<'PY' || exit 1
import json, pathlib, sys
meta = json.loads((pathlib.Path(sys.argv[1]) / "results/briefs/acme__widget-2.lv1.meta.json").read_text())
assert meta["ok"] is False and "cannot prove blueprint was disabled" in meta["error"], meta
PY
pass "no init event = no proof = failed task"

"${S14[@]}" --stage brief --mock-testbed "$TESTBED" --claude-cmd "$CLAUDE" --force >/dev/null \
  || fail "14 brief restore run failed"

printf '\n== 14 dataset (local HF dataset round-trip)\n'
"${S14[@]}" --stage dataset >/dev/null || fail "14 dataset exited non-zero (round-trip asserts live inside)"
$PY - "$EV" <<'PY' || exit 1
import pathlib, sys
from datasets import load_dataset
ev = pathlib.Path(sys.argv[1])
sep = "\n\n---\n\n## Implementation Spec\n\n"
hint = (ev / "prompts/breadth_hint.md").read_text().strip()
plan = load_dataset(str(ev / "results/dataset_arm_a_plan"), split="lite")
hints = load_dataset(str(ev / "results/dataset_arm_a_hint"), split="lite")
assert len(plan) == 4 and len(hints) == 4, (len(plan), len(hints))
for row_p, row_h in zip(plan, hints):
    tid = row_p["instance_id"]
    i = tid.split("-")[1].split(".")[0]
    original = f"Original statement for task {i}."
    brief = (ev / "results/briefs" / f"{tid}.md").read_text().strip()
    assert row_p["problem_statement"] == original + sep + brief, row_p["problem_statement"]
    assert row_h["problem_statement"] == original + sep + hint, row_h["problem_statement"]
    assert row_p["FAIL_TO_PASS"] == [f"tests/test_{i}.py::test_feature"]
    for col in ("image_name", "patch", "FAIL_TO_PASS", "repo_settings"):
        assert col in plan.column_names and col in hints.column_names, col
assert "Arm A_plan dataset" in (ev / "results/dataset_arm_a_plan/README.md").read_text()
PY
pass "A_plan = original + separator + brief; A_hint = original + separator + hint; columns preserved"

BRIEF1="$EV/results/briefs/acme__widget-1.lv1.md"
cp "$BRIEF1" "$TMP/brief1.bak"
$PY -c "import sys; open(sys.argv[1], 'w').write('x' * 120000)" "$BRIEF1"
set +e
BUDGET="$("${S14[@]}" --stage dataset --arm A_plan 2>&1)"
rc_budget=$?
set -e
cp "$TMP/brief1.bak" "$BRIEF1"
[ "$rc_budget" -ne 0 ] && echo "$BUDGET" | grep -q "argv budget" || fail "oversized statement must be refused: $BUDGET"
pass "a statement over the argv budget is refused, never truncated"

printf '\n== 03 + 14 infer --dry-run (four arms)\n'
$PY "$EV/scripts/02_make_dataset.py" --config "$EV/config.toml" --mock-dataset "$DS" >/dev/null \
  || fail "02 exited non-zero"
OUT_AB="$($PY "$EV/scripts/03_infer.py" --config "$EV/config.toml" --dry-run)" || fail "03 --dry-run failed"
OUT_CTRL="$("${S14[@]}" --stage infer --dry-run)" || fail "14 infer --dry-run failed"
printf '%s\n%s\n' "$OUT_AB" "$OUT_CTRL" | sed 's/^/    /'
$PY - "$OUT_AB" "$OUT_CTRL" <<'PY' || exit 1
import shlex, sys
cmds = {}
for line in "\n".join(sys.argv[1:]).splitlines():
    if line.startswith("[arm "):
        arm, cmd = line[len("[arm "):].split("] ", 1)
        cmds[arm] = shlex.split(cmd)
assert sorted(cmds) == ["A", "A_hint", "A_plan", "B"], cmds
def strip(c):
    out, skip = [], False
    for t in c:
        if skip:
            skip = False
            continue
        if t in ("--dataset", "--output-dir"):
            skip = True
            continue
        out.append(t)
    return out
assert all(strip(c) == strip(cmds["A"]) for c in cmds.values()), {a: strip(c) for a, c in cmds.items()}
for arm, suffix in (("A_plan", "a_plan"), ("A_hint", "a_hint")):
    c = cmds[arm]
    assert c[c.index("--dataset") + 1].endswith(f"results/dataset_arm_{suffix}"), c
    assert c[c.index("--output-dir") + 1].endswith(f"results/infer_arm_{suffix}"), c
PY
pass "A, B, A_plan, A_hint infer commands differ only in --dataset/--output-dir"

printf '\n== 14 eval --dry-run\n'
$PY - "$EV" <<'PY'
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])
runs = {}
for arm in ("A_plan", "A_hint"):
    d = ev / f"results/infer_arm_{arm.lower()}/2026-09-16__10-00-00"
    d.mkdir(parents=True, exist_ok=True)
    (d / "output.jsonl").write_text("")
    runs[arm] = {"arm": arm, "output_jsonl": str(d / "output.jsonl")}
(ev / "results/runs.json").write_text(json.dumps(runs, indent=2))
PY
OUT_EVAL="$("${S14[@]}" --stage eval --dry-run)" || fail "14 eval --dry-run failed"
$PY - "$OUT_EVAL" <<'PY' || exit 1
import shlex, sys
lines = [l for l in sys.argv[1].splitlines() if l.startswith("[arm ")]
assert len(lines) == 2, lines
for line in lines:
    cmd = shlex.split(line.split("] ", 1)[1])
    assert cmd[:2] == ["fb", "eval"], cmd
    assert cmd[cmd.index("--dataset") + 1] == "LiberCoders/FeatureBench", cmd
    assert cmd[cmd.index("--task-id") + 1:] == [f"acme__widget-{i}.lv1" for i in range(1, 5)], cmd
PY
pass "control arms are scored against the official dataset"

printf '\n== 05c report\n'
$PY - "$EV" <<'PY'
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])
# (pass rates, resolved) per arm, tasks 1..4
cells = {
    "A":      ([0.0, 0.4, 1.0, 0.2], [False, False, True, False]),
    "A_hint": ([0.8, 0.4, 1.0, 0.2], [False, False, True, False]),
    "A_plan": ([1.0, 0.6, 1.0, 0.0], [True, False, True, False]),
    "B":      ([1.0, 1.0, 1.0, 0.2], [True, True, True, False]),
}
for arm, (rates, resolved) in cells.items():
    report = {f"acme__widget-{i}.lv1": {"resolved": resolved[i - 1], "pass_rate": rates[i - 1]} for i in range(1, 5)}
    (ev / f"results/eval_{arm}.json").write_text(json.dumps(report))
PY
R="$EV/results"
$PY "$EV/scripts/05c_report_controls.py" --config "$EV/config.toml" \
  --report "A=$R/eval_A.json" --report "A_hint=$R/eval_A_hint.json" \
  --report "A_plan=$R/eval_A_plan.json" --report "B=$R/eval_B.json" \
  --out "$R/report_controls.md" | sed 's/^/    /' || fail "05c exited non-zero"
$PY - "$R/report_controls.md" <<'PY' || exit 1
import sys
md = open(sys.argv[1]).read()
lines = md.splitlines()
assert "| `acme__widget-2.lv1` | 0.40 | 0.40 | 0.60 | 1.00 ✓ | 0.50 | 2.00 |" in lines, md
assert "| A | 1/4 | 0.40 | — | — |" in lines, md
assert "| B | 3/4 | 0.80 | $2.00 | 10 min |" in lines, md
assert any(l.startswith("| A_plan | 2/4 | 0.65 | $0.50 |") for l in lines), md
def comparison(prefix):
    return next(l for l in lines if l.startswith(f"- **{prefix}**"))
bp = comparison("B − A_plan")
assert "mean pass rate **+0.15**" in bp and "2 up / 0 down / 2 tied" in bp, bp
assert "b(B-only)=**1** c(A_plan-only)=**0**" in bp and "p = 1.0000" in bp, bp
ba = comparison("B − A")
assert "**+0.40**" in ba and "b(B-only)=**2** c(A-only)=**0**" in ba and "p = 0.5000" in ba, ba
pa = comparison("A_plan − A")
assert "**+0.25**" in pa and "2 up / 1 down / 1 tied" in pa, pa
ha = comparison("A_hint − A")
assert "**+0.20**" in ha and "1 up / 0 down / 3 tied" in ha, ha
PY
pass "per-task cells, per-arm totals, doc cost, up/down/tied and McNemar per pair"

$PY "$EV/scripts/05c_report_controls.py" --config "$EV/config.toml" \
  --report "A=$R/eval_A.json" --report "B=$R/eval_B.json" --out "$R/report_ab_only.md" >/dev/null \
  || fail "05c with two arms exited non-zero"
$PY - "$R/report_ab_only.md" <<'PY' || exit 1
import sys
md = open(sys.argv[1]).read()
assert "Not scored, omitted: A_hint, A_plan." in md, md
assert "- **B − A**" in md and "- **B − A_plan**" not in md, md
PY
pass "unscored arms are named as omitted and their comparisons skipped"

printf '\nsmoke controls PASSED\n'

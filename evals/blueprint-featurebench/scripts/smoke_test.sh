#!/usr/bin/env bash
# Offline smoke test for the harness. Needs python3.11+ and `datasets`;
# needs neither docker, nor network, nor a real `claude`, nor `fb`.
#
# Covers: 02's local-dataset round-trip, 01 end-to-end with a mock claude and
# a mock testbed, 03/04 --dry-run command shapes, and 05's paired table +
# exact McNemar over a fixture with all four discordance cells.
set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
TMP="$(mktemp -d)"
[ -n "${KEEP_TMP:-}" ] && echo "tmp: $TMP" || trap 'rm -rf "$TMP"' EXIT

pass() { printf '  ok  %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1" >&2; exit 1; }

# The harness roots itself at scripts/.. so the fixture run must not clobber a
# real results/ dir: work on a throwaway copy of the tree.
FIX="$TMP/harness"
mkdir -p "$FIX"
cp -R "$SCRIPTS/.." "$FIX/evals"
EV="$FIX/evals"
rm -rf "$EV/results"
mkdir -p "$EV/results"

cat > "$EV/config.toml" <<'TOML'
[eval]
dataset = "LiberCoders/FeatureBench"
split = "lite"
limit = 4
n_concurrent = 2

[spec]
model = "claude-sonnet-5"
timeout_seconds = 120
claude_args = ["--permission-mode", "bypassPermissions"]

[infer]
model = "claude-sonnet-5"
fb_config_path = "fb_config.toml"
n_concurrent = 1
timeout_seconds = 1800
TOML
cp "$EV/fb_config.example.toml" "$EV/fb_config.toml"

# ---------------------------------------------------------------- fixtures
# instance_id must end in .lv1/.lv2: FeatureBench's DatasetLoader derives the
# level from that suffix and raises otherwise.
DS="$TMP/split.jsonl"
$PY - "$DS" <<'PY'
import json, sys
rows = []
for i in range(1, 5):
    rows.append({
        "instance_id": f"acme__widget-{i}.lv1",
        "problem_statement": f"Original statement for task {i}.",
        "image_name": f"librecoders/featurebench:acme_widget_{i}",
        # Realistic mask patch: fb infer applies it to strip the reference
        # solution before the agent (or /spec) sees the tree. Removes the
        # oracle line that the fixture testbed plants in src/widget.py.
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
with open(sys.argv[1], "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
PY

TESTBED="$TMP/testbed"
mkdir -p "$TESTBED/src" "$TESTBED/tests"
printf 'def widget(): pass\nREFERENCE_SOLUTION = True\n' > "$TESTBED/src/widget.py"
echo "# acme widget" > "$TESTBED/README.md"
# F2P test files that stage 01 must delete before /spec sees the tree.
for i in 1 2 3 4; do echo "def test_feature(): pass" > "$TESTBED/tests/test_$i.py"; done
git -C "$TESTBED" init -q && git -C "$TESTBED" add -A && \
  git -C "$TESTBED" -c user.email=smoke@test -c user.name=smoke commit -qm testbed

# Mock claude: same argv shape as the real one, emits --output-format json and
# actually writes a spec under .blueprint/specs/ in cwd.
CLAUDE="$TMP/fake-claude"
cat > "$CLAUDE" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
prompt=""
next_is_prompt=0
for arg in "$@"; do
  if [ "$next_is_prompt" = 1 ]; then prompt="$arg"; next_is_prompt=0; fi
  if [ "$arg" = "-p" ]; then next_is_prompt=1; fi
done
[ -n "$prompt" ] || { echo "mock claude: no -p prompt" >&2; exit 3; }
case "$prompt" in
  *"{problem_statement}"*) echo "mock claude: placeholder was not substituted" >&2; exit 4;;
esac
mkdir -p .blueprint/specs
spec=".blueprint/specs/2608.0001_mock_feature.md"
printf '# Mock spec\n\nAcceptance scenario: widget() returns 42.\n' > "$spec"
cat <<JSON
{"type":"result","subtype":"success","is_error":false,
 "result":"Wrote the spec.\n\nSPEC_PATH: $spec",
 "total_cost_usd":0.1234,"duration_ms":4200,"duration_api_ms":3900,"num_turns":6,
 "usage":{"input_tokens":1000,"output_tokens":250}}
JSON
SH
chmod +x "$CLAUDE"

printf '\n== 01 make_specs (mock claude + mock testbed + jsonl dataset)\n'
$PY "$EV/scripts/01_make_specs.py" \
  --config "$EV/config.toml" \
  --mock-dataset "$DS" \
  --mock-testbed "$TESTBED" \
  --claude-cmd "$CLAUDE" >/dev/null || fail "01 exited non-zero"

$PY - "$EV" <<'PY' || exit 1
import json, sys, pathlib
ev = pathlib.Path(sys.argv[1])
tasks = json.loads((ev / "results/tasks.json").read_text())
assert len(tasks["tasks"]) == 4, tasks
assert all(t["status"] == "spec_ok" for t in tasks["tasks"]), tasks
ids = [t["id"] for t in tasks["tasks"]]
assert ids == sorted(ids), "tasks must be sorted by instance_id"
for tid in ids:
    md = ev / "results/specs" / f"{tid}.md"
    meta = json.loads((ev / "results/specs" / f"{tid}.meta.json").read_text())
    assert md.exists() and "Mock spec" in md.read_text(), md
    assert meta["ok"] is True and meta["cost_usd"] == 0.1234, meta
    assert meta["spec_located_by"] == "marker", meta
    assert meta["duration_ms"] == 4200 and meta["usage"]["input_tokens"] == 1000, meta
    assert meta["mask_applied"] is True and meta["f2p_deleted"] == 1, meta
    ws = ev / "results/workspaces" / tid
    assert "REFERENCE_SOLUTION" not in (ws / "src/widget.py").read_text(), \
        "oracle survived masking"
    i = tid.split("-")[1].split(".")[0]
    assert not (ws / "tests" / f"test_{i}.py").exists(), "F2P test file not deleted"
PY
pass "tasks.json / specs / metas written; oracle masked, F2P tests deleted"

# Resume path: a second run must not re-invoke claude.
BROKEN="$TMP/broken-claude"
printf '#!/usr/bin/env bash\nexit 9\n' > "$BROKEN"; chmod +x "$BROKEN"
$PY "$EV/scripts/01_make_specs.py" --config "$EV/config.toml" --mock-dataset "$DS" \
  --mock-testbed "$TESTBED" --claude-cmd "$BROKEN" >/dev/null || fail "01 resume run failed"
pass "01 is resumable (cached specs skipped)"

# Failure path: a claude that produces no spec must mark the task spec_failed
# without aborting the panel.
NOSPEC="$TMP/nospec-claude"
cat > "$NOSPEC" <<'SH'
#!/usr/bin/env bash
echo '{"result":"I have some questions first.","total_cost_usd":0.01,"duration_ms":100}'
SH
chmod +x "$NOSPEC"
# All four tasks fail here, so 01 must exit 1 ("no specs produced") while still
# having recorded every per-task failure rather than aborting on the first one.
set +e
$PY "$EV/scripts/01_make_specs.py" --config "$EV/config.toml" --mock-dataset "$DS" \
  --mock-testbed "$TESTBED" --claude-cmd "$NOSPEC" --force >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "01 with zero usable specs should exit 1, got $rc"
$PY - "$EV" <<'PY' || exit 1
import json, sys, pathlib
ev = pathlib.Path(sys.argv[1])
tasks = json.loads((ev / "results/tasks.json").read_text())
assert all(t["status"] == "spec_failed" for t in tasks["tasks"]), tasks
PY
pass "spec failures recorded as spec_failed, panel not aborted"

# Restore the good state for downstream stages.
$PY "$EV/scripts/01_make_specs.py" --config "$EV/config.toml" --mock-dataset "$DS" \
  --mock-testbed "$TESTBED" --claude-cmd "$CLAUDE" --force >/dev/null || fail "01 restore run failed"

printf '\n== 02 make_dataset (local HF dataset round-trip)\n'
# Mark one task failed so the filter is actually exercised.
$PY - "$EV" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]) / "results/tasks.json"
tasks = json.loads(p.read_text())
tasks["tasks"][-1]["status"] = "spec_failed"
p.write_text(json.dumps(tasks, indent=2))
PY
$PY "$EV/scripts/02_make_dataset.py" --config "$EV/config.toml" --mock-dataset "$DS" \
  || fail "02 exited non-zero (round-trip assertions live inside 02)"

$PY - "$EV" <<'PY' || exit 1
import sys, pathlib
from datasets import load_dataset
ev = pathlib.Path(sys.argv[1])
out = ev / "results/dataset_arm_b"
ds = load_dataset(str(out), split="lite")
assert len(ds) == 3, f"expected 3 spec_ok rows, got {len(ds)}"
row = ds[0]
assert row["instance_id"] == "acme__widget-1.lv1", row["instance_id"]
ps = row["problem_statement"]
assert ps.startswith("Original statement for task 1."), ps[:80]
assert "\n\n---\n\n## Implementation Spec\n\n" in ps
assert "Acceptance scenario: widget() returns 42." in ps
# Every other column must survive verbatim.
for col in ("image_name", "patch", "FAIL_TO_PASS", "repo_settings"):
    assert col in ds.column_names, col
assert row["FAIL_TO_PASS"] == ["tests/test_1.py::test_feature"]
assert "acme__widget-4.lv1" not in set(ds["instance_id"]), "spec_failed task leaked into Arm B"
PY
pass "load_dataset(dir, split='lite') round-trips; spec appended; columns preserved"

printf '\n== 03 infer --dry-run\n'
OUT03="$($PY "$EV/scripts/03_infer.py" --config "$EV/config.toml" --dry-run)" || fail "03 --dry-run exited non-zero"
echo "$OUT03" | sed 's/^/    /'
$PY - <<PY || exit 1
import shlex, sys
lines = [l for l in """$OUT03""".splitlines() if l.strip()]
assert len(lines) == 2, lines
cmds = {}
for line in lines:
    arm = line.split("]")[0].strip("[arm ").strip()
    cmds[arm] = shlex.split(line.split("] ", 1)[1])
for arm, cmd in cmds.items():
    assert cmd[:2] == ["fb", "infer"], cmd
    assert "--agent" in cmd and cmd[cmd.index("--agent") + 1] == "claude_code"
    assert cmd[cmd.index("--split") + 1] == "lite"
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5"
    ids = cmd[cmd.index("--task-id") + 1:]
    assert ids == ["acme__widget-1.lv1", "acme__widget-2.lv1", "acme__widget-3.lv1"], ids
a, b = cmds["A"], cmds["B"]
assert a[a.index("--dataset") + 1] == "LiberCoders/FeatureBench"
assert b[b.index("--dataset") + 1].endswith("results/dataset_arm_b"), b
# The two arms may differ only in --dataset and --output-dir.
def strip(c):
    out, skip = [], False
    for i, t in enumerate(c):
        if skip: skip = False; continue
        if t in ("--dataset", "--output-dir"): skip = True; continue
        out.append(t)
    return out
assert strip(a) == strip(b), (strip(a), strip(b))
PY
pass "03 emits two fb infer commands differing only in --dataset/--output-dir"

printf '\n== 04 eval --dry-run\n'
$PY - "$EV" <<'PY'
import json, sys, pathlib
ev = pathlib.Path(sys.argv[1])
runs = {}
for arm in ("A", "B"):
    d = ev / f"results/infer_arm_{arm.lower()}/2026-08-15__10-00-00"
    d.mkdir(parents=True, exist_ok=True)
    (d / "output.jsonl").write_text("")
    runs[arm] = {"arm": arm, "output_jsonl": str(d / "output.jsonl")}
(ev / "results/runs.json").write_text(json.dumps(runs, indent=2))
PY
OUT04="$($PY "$EV/scripts/04_eval.py" --config "$EV/config.toml" --dry-run)" || fail "04 --dry-run exited non-zero"
echo "$OUT04" | sed 's/^/    /'
$PY - <<PY || exit 1
import shlex
lines = [l for l in """$OUT04""".splitlines() if l.strip()]
assert len(lines) == 2, lines
for line in lines:
    cmd = shlex.split(line.split("] ", 1)[1])
    assert cmd[:2] == ["fb", "eval"], cmd
    # Both arms are scored against the OFFICIAL dataset.
    assert cmd[cmd.index("--dataset") + 1] == "LiberCoders/FeatureBench", cmd
    assert cmd[cmd.index("--split") + 1] == "lite"
    assert cmd[cmd.index("--predictions-path") + 1].endswith("output.jsonl")
    assert cmd[cmd.index("--task-id") + 1:] == [
        "acme__widget-1.lv1", "acme__widget-2.lv1", "acme__widget-3.lv1"]
PY
pass "04 scores both arms against the official dataset"

printf '\n== 05 report (McNemar)\n'
# Pure-function check first: hand-computed exact two-sided binomial p-values.
$PY - "$EV" <<'PY' || exit 1
import sys, pathlib, importlib.util
spec = importlib.util.spec_from_file_location(
    "r05", pathlib.Path(sys.argv[1]) / "scripts/05_report.py")
sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / "scripts"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
# b=1,c=1: n=2, k=1, tail=(C(2,0)+C(2,1))/4 = 3/4, p=min(1, 1.5)=1.0
assert m.mcnemar_exact_p(1, 1) == 1.0
# b=3,c=0: n=3, k=0, tail=C(3,0)/8 = 1/8, p=2*0.125=0.25
assert abs(m.mcnemar_exact_p(3, 0) - 0.25) < 1e-12
# b=5,c=0: n=5, k=0, tail=1/32, p=1/16=0.0625
assert abs(m.mcnemar_exact_p(5, 0) - 0.0625) < 1e-12
assert m.mcnemar_exact_p(0, 0) == 1.0
PY
pass "mcnemar_exact_p matches hand-computed values (1,1)->1.0 (3,0)->0.25 (5,0)->0.0625"

# Four tasks covering every discordance cell: both / A-only / B-only / neither.
$PY - "$EV" <<'PY'
import json, sys, pathlib
ev = pathlib.Path(sys.argv[1])
tasks = {"dataset": "LiberCoders/FeatureBench", "split": "lite", "tasks": [
    {"id": f"acme__widget-{i}.lv1", "image_name": "img", "status": "spec_ok"}
    for i in range(1, 5)]}
(ev / "results/tasks_fixture.json").write_text(json.dumps(tasks, indent=2))

# (A resolved, B resolved, A rate, B rate)
cells = {
    "acme__widget-1.lv1": (True,  True,  1.0, 1.0),   # concordant resolved
    "acme__widget-2.lv1": (True,  False, 1.0, 0.5),   # b: A-only
    "acme__widget-3.lv1": (False, True,  0.25, 1.0),  # c: B-only
    "acme__widget-4.lv1": (False, False, 0.0, 0.0),   # concordant unresolved
}
for arm, idx in (("A", 0), ("B", 1)):
    run = ev / f"results/eval_arm_{arm.lower()}"
    (run).mkdir(parents=True, exist_ok=True)
    resolved = sum(1 for v in cells.values() if v[idx])
    # Aggregate shape actually emitted by fb eval.
    (run / "report.json").write_text(json.dumps({"attempt_1": {
        "n_attempt": 1, "total_instances": 4, "completed_instances": 4,
        "resolved_instances": resolved, "resolved_rate": round(resolved / 4, 4),
        "pass_rate": 0.5, "resolved_ids": [], "submitted_ids": []}}, indent=4))
    for iid, vals in cells.items():
        d = run / "eval_outputs" / iid / "attempt-1"
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.json").write_text(json.dumps({iid: {
            "n_attempt": 1, "patch_is_None": False, "patch_exists": True,
            "patch_successfully_applied": True,
            "resolved": vals[idx], "pass_rate": vals[2 + idx],
            "tests_status": {"FAIL_TO_PASS": {"success": [], "failure": []},
                             "PASS_TO_PASS": {"success": [], "failure": []}}}}, indent=4))
PY

OUT05="$($PY "$EV/scripts/05_report.py" --config "$EV/config.toml" \
  --tasks "$EV/results/tasks_fixture.json" \
  --report-a "$EV/results/eval_arm_a/report.json" \
  --report-b "$EV/results/eval_arm_b/report.json" \
  --out "$EV/results/report.md")" || fail "05 exited non-zero"
echo "$OUT05" | sed 's/^/    /'

$PY - "$EV" <<'PY' || exit 1
import sys, pathlib
md = (pathlib.Path(sys.argv[1]) / "results/report.md").read_text()
# b=1 (task 2), c=1 (task 3)  ->  n=2, p = min(1, 2*(1+2)/4) = 1.0
assert "b (A-only resolved) = **1**" in md, md
assert "c (B-only resolved) = **1**" in md, md
assert "p = 1.0000" in md, md
assert "A **2/4**, B **2/4**" in md, md
assert "(delta **+0**)" in md, md
# Spec cost carried next to the outcome: 4 tasks x $0.1234.
assert "$0.4936" in md, md
assert "| **totals (4)** | **2** | **2** |" in md, md
for i in (1, 2, 3, 4):
    assert f"`acme__widget-{i}.lv1`" in md
assert "Single seed" in md and "Small N" in md
PY
pass "report.md: paired table, totals, b/c counts, exact p, spec cost, caveats"

printf '\nsmoke test PASSED\n'

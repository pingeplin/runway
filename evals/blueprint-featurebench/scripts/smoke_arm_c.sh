#!/usr/bin/env bash
# Offline smoke test for Arm C (scripts/06_arm_c.py + 05b_report_c.py).
# Needs python3.11+ and `datasets`; needs neither docker, nor network, nor a
# real `claude`, nor a real `fb`.
#
#   uv run --python 3.12 --with datasets bash scripts/smoke_arm_c.sh
#
# Covers: the verify round end-to-end against a mock claude and a real git
# workspace (so `git apply` of the Arm B patch is genuinely exercised), the
# C / C0 round-2 dataset build (asserting the two differ ONLY in the feedback
# section), the fb infer --dry-run command shape, recording into runs.json via
# a mock `fb`, and 05b's three-way paired report.
set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
TMP="$(mktemp -d)"
[ -n "${KEEP_TMP:-}" ] && echo "tmp: $TMP" || trap 'rm -rf "$TMP"' EXIT

pass() { printf '  ok  %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1" >&2; exit 1; }

# The harness roots itself at scripts/.., so work on a throwaway copy of the
# tree — the real results/ dir must never be touched.
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
limit = 3
n_concurrent = 2

[spec]
model = "claude-sonnet-4-5"
timeout_seconds = 120
claude_args = ["--permission-mode", "bypassPermissions"]

[verify]
model = "claude-opus-4-1"
timeout_seconds = 240

[infer]
model = "claude-sonnet-4-5"
fb_config_path = "fb_config.toml"
n_concurrent = 1
timeout_seconds = 1800
TOML
cp "$EV/fb_config.example.toml" "$EV/fb_config.toml"

IDS=(acme__widget-1.lv1 acme__widget-2.lv1 acme__widget-3.lv1)

# ---------------------------------------------------------------- fixtures
#
# `patch` is FeatureBench's MASK patch: `fb infer` applies it (and deletes the
# FAIL_TO_PASS files) before the agent runs, so 06 must reproduce that state or
# the Arm B patch will not apply.
DS="$TMP/split.jsonl"
$PY - "$DS" <<'PY'
import json, sys
mask = (
    "diff --git a/src/widget.py b/src/widget.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/src/widget.py\n"
    "+++ b/src/widget.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def widget():\n"
    "-    return 42\n"
    "+    raise NotImplementedError\n"
)
with open(sys.argv[1], "w") as f:
    for i in (1, 2, 3):
        f.write(json.dumps({
            "instance_id": f"acme__widget-{i}.lv1",
            "problem_statement": f"Original statement for task {i}.",
            "image_name": f"librecoders/featurebench:acme_widget_{i}",
            "patch": mask,
            "FAIL_TO_PASS": [f"tests/test_{i}.py::test_feature"],
            "repo_settings": "{}",
        }) + "\n")
PY

# tasks.json + specs, as stage 01 would have left them.
$PY - "$EV" <<'PY'
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])
ids = [f"acme__widget-{i}.lv1" for i in (1, 2, 3)]
(ev / "results/specs").mkdir(parents=True, exist_ok=True)
for tid in ids:
    (ev / "results/specs" / f"{tid}.md").write_text(
        f"# Spec for {tid}\n\nAcceptance scenario: widget() returns 42.\n")
    (ev / "results/specs" / f"{tid}.meta.json").write_text(json.dumps(
        {"instance_id": tid, "ok": True, "cost_usd": 0.1234, "wall_seconds": 12.0}))
(ev / "results/tasks.json").write_text(json.dumps({
    "dataset": "LiberCoders/FeatureBench", "split": "lite",
    "tasks": [{"id": t, "image_name": "img", "status": "spec_ok"} for t in ids]}, indent=2))
PY

# Stage-01 workspaces: real git repos with a committed file plus the leftover
# .blueprint/specs that 06 must purge.
WS="$TMP/workspaces"
i=0
for id in "${IDS[@]}"; do
  i=$((i + 1))
  d="$WS/$id"
  mkdir -p "$d/src" "$d/tests" "$d/.blueprint/specs"
  printf 'def widget():\n    return 42\n' > "$d/src/widget.py"
  printf 'def test_feature():\n    assert widget() == 42\n' > "$d/tests/test_$i.py"
  echo "# acme widget" > "$d/README.md"
  echo "# stale stage-01 spec" > "$d/.blueprint/specs/stale.md"
  git -C "$d" init -q
  git -C "$d" add -A
  git -C "$d" -c user.email=smoke@example.com -c user.name=smoke commit -qm init
done

# Arm B predictions. Task 1/2 carry a real new-file diff (applies against any
# tree); task 3's patch is empty and must be skipped with a log.
ARMB="$TMP/arm_b_output.jsonl"
$PY - "$ARMB" <<'PY'
import json, sys
patch = (
    "diff --git a/src/feature.py b/src/feature.py\n"
    "new file mode 100644\n"
    "index 0000000..1111111\n"
    "--- /dev/null\n"
    "+++ b/src/feature.py\n"
    "@@ -0,0 +1,2 @@\n"
    "+def feature():\n"
    "+    return 42\n"
)
rows = [
    {"instance_id": "acme__widget-1.lv1", "model_patch": patch.rstrip("\n")},  # no trailing \n
    {"instance_id": "acme__widget-2.lv1", "model_patch": patch},
    {"instance_id": "acme__widget-3.lv1", "model_patch": ""},
]
with open(sys.argv[1], "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
PY

# Mock claude for the verify round: asserts the workspace state the referee is
# supposed to see, then writes a verdict and emits the VERDICT_PATH marker.
CLAUDE="$TMP/fake-claude"
cat > "$CLAUDE" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
prompt=""; next=0; model=""
for arg in "$@"; do
  if [ "$next" = 1 ]; then prompt="$arg"; next=0; continue; fi
  if [ "$next" = 2 ]; then model="$arg"; next=0; continue; fi
  [ "$arg" = "-p" ] && next=1
  [ "$arg" = "--model" ] && next=2
done
[ -n "$prompt" ] || { echo "mock claude: no -p prompt" >&2; exit 3; }
case "$prompt" in
  *"{problem_statement}"*) echo "mock claude: placeholder not substituted" >&2; exit 4;;
esac
[ "$model" = "claude-opus-4-1" ] || { echo "mock claude: wrong model '$model'" >&2; exit 5; }
# The workspace must look like what the implementing agent saw: mask patch
# applied, F2P test file gone, Arm B patch on top, exactly one spec.
[ -f src/feature.py ] || { echo "mock claude: arm B patch not applied" >&2; exit 6; }
[ -f .blueprint/specs/spec.md ] || { echo "mock claude: spec missing" >&2; exit 7; }
[ ! -f .blueprint/specs/stale.md ] || { echo "mock claude: stale spec not purged" >&2; exit 8; }
grep -q NotImplementedError src/widget.py || { echo "mock claude: mask patch not applied" >&2; exit 9; }
[ -z "$(ls -A tests 2>/dev/null)" ] || { echo "mock claude: F2P test not deleted" >&2; exit 10; }
mkdir -p .blueprint/verdicts
v=".blueprint/verdicts/verdict.md"
printf '# Verdict\n\nScenario 1 is covered but VACUOUS: %s\n' "$(basename "$PWD")" > "$v"
cat <<JSON
{"type":"result","subtype":"success","is_error":false,
 "result":"Refereed.\n\nVERDICT_PATH: $v",
 "total_cost_usd":0.2468,"duration_ms":8400,"duration_api_ms":8000,"num_turns":9,
 "usage":{"input_tokens":5000,"output_tokens":900}}
JSON
SH
chmod +x "$CLAUDE"

# Mock fb: handles `infer` (writes a timestamped output.jsonl) and `eval`
# (writes report.json + per-instance eval_outputs).
BIN="$TMP/bin"; mkdir -p "$BIN"
cat > "$BIN/fb" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
sub="$1"; shift
out=""; preds=""; ids=(); collecting=0
while [ $# -gt 0 ]; do
  case "$1" in
    --output-dir) out="$2"; collecting=0; shift 2;;
    --predictions-path) preds="$2"; collecting=0; shift 2;;
    --task-id) collecting=1; shift;;
    --*) collecting=0; shift;;
    *) if [ "$collecting" = 1 ]; then ids+=("$1"); fi; shift;;
  esac
done
if [ "$sub" = "infer" ]; then
  d="$out/2026-08-15__12-00-00"; mkdir -p "$d"
  : > "$d/output.jsonl"
  for id in "${ids[@]}"; do
    printf '{"instance_id":"%s","model_patch":"diff --git a/z b/z\\n"}\n' "$id" >> "$d/output.jsonl"
  done
  echo "mock fb infer -> $d/output.jsonl"
else
  d="$(dirname "$preds")"
  printf '{"attempt_1": {"n_attempt": 1, "total_instances": %d}}\n' "${#ids[@]}" > "$d/report.json"
  echo "mock fb eval -> $d/report.json"
fi
SH
chmod +x "$BIN/fb"
export PATH="$BIN:$PATH"

# ------------------------------------------------------- 06 verify round
printf '\n== 06 verify round (mock claude, real git apply)\n'
$PY "$EV/scripts/06_arm_c.py" --config "$EV/config.toml" --stage verify \
  --mock-dataset "$DS" --arm-b-output "$ARMB" --workspace-src "$WS" \
  --claude-cmd "$CLAUDE" --parallel 2 --keep-workspaces > "$TMP/verify.log" 2>&1 \
  || { sed 's/^/    /' "$TMP/verify.log" >&2; fail "06 verify exited non-zero"; }
sed 's/^/    /' "$TMP/verify.log"

grep -q "skip acme__widget-3.lv1: Arm B prediction missing or empty" "$TMP/verify.log" \
  || fail "task with an empty Arm B patch was not skipped with a log"
pass "task with a missing/empty Arm B prediction is skipped with a log"

$PY - "$EV" <<'PY' || exit 1
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])
vd = ev / "results/verdicts"
for tid in ("acme__widget-1.lv1", "acme__widget-2.lv1"):
    md = vd / f"{tid}.md"
    meta = json.loads((vd / f"{tid}.meta.json").read_text())
    assert md.exists() and "VACUOUS" in md.read_text(), md
    assert meta["ok"] is True and meta["error"] is None, meta
    assert meta["patch_applied"] is True, meta
    assert meta["mask_applied"] is True and meta["f2p_deleted"] == 1, meta
    assert meta["verdict_located_by"] == "marker", meta
    assert meta["cost_usd"] == 0.2468 and meta["duration_ms"] == 8400, meta
    assert meta["usage"]["input_tokens"] == 5000 and meta["num_turns"] == 9, meta
    assert isinstance(meta["wall_seconds"], (int, float)), meta
    assert meta["verdict_chars"] > 0 and meta["patch_chars"] > 0, meta
assert not (vd / "acme__widget-3.lv1.meta.json").exists(), "skipped task got a verdict"
# The scratch copy must be separate from the pristine stage-01 workspace.
assert (ev / "results/workspaces_c/acme__widget-1.lv1/src/feature.py").exists()
PY
pass "verdicts/<id>.md + .meta.json (cost, duration, patch_applied) written"

# The pristine stage-01 workspaces must be untouched.
for id in acme__widget-1.lv1 acme__widget-2.lv1; do
  [ ! -e "$WS/$id/src/feature.py" ] || fail "06 dirtied the stage-01 workspace $id"
  grep -q "return 42" "$WS/$id/src/widget.py" || fail "06 masked the stage-01 workspace $id"
  [ -f "$WS/$id/.blueprint/specs/stale.md" ] || fail "06 purged the stage-01 workspace $id"
  [ -z "$(git -C "$WS/$id" status --porcelain)" ] || fail "stage-01 workspace $id is dirty"
done
pass "stage-01 workspaces left pristine (patch applied in results/workspaces_c/)"

# Resume path: a second run must not re-invoke claude.
BROKEN="$TMP/broken-claude"; printf '#!/usr/bin/env bash\nexit 9\n' > "$BROKEN"; chmod +x "$BROKEN"
$PY "$EV/scripts/06_arm_c.py" --config "$EV/config.toml" --stage verify \
  --mock-dataset "$DS" --arm-b-output "$ARMB" --workspace-src "$WS" \
  --claude-cmd "$BROKEN" > "$TMP/resume.log" 2>&1 \
  || { sed 's/^/    /' "$TMP/resume.log" >&2; fail "06 verify resume run failed"; }
grep -q "cached verdict" "$TMP/resume.log" || fail "06 verify is not resumable"
pass "verify round is resumable (cached verdicts skipped)"

# Failure path: a claude that writes no verdict must not abort the panel.
NOVERDICT="$TMP/noverdict-claude"
cat > "$NOVERDICT" <<'SH'
#!/usr/bin/env bash
echo '{"result":"I have questions.","total_cost_usd":0.01,"duration_ms":100}'
SH
chmod +x "$NOVERDICT"
set +e
$PY "$EV/scripts/06_arm_c.py" --config "$EV/config.toml" --stage verify \
  --mock-dataset "$DS" --arm-b-output "$ARMB" --workspace-src "$WS" \
  --claude-cmd "$NOVERDICT" --force > "$TMP/verify_fail.log" 2>&1
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "06 verify with zero verdicts should exit 1, got $rc"
grep -q "acme__widget-2.lv1: FAILED" "$TMP/verify_fail.log" \
  || fail "per-task verify failure not recorded for every task"
pass "verify failures recorded per task, panel not aborted"

# A failed verify must not leave a stale verdict .md that re-enters C/C0.
$PY - "$EV" <<'PY' || exit 1
import json, pathlib, sys
vd = pathlib.Path(sys.argv[1]) / "results/verdicts"
tid = "acme__widget-1.lv1"
assert (vd / f"{tid}.md").exists(), "fixture: previous verdict should still be on disk"
assert json.loads((vd / f"{tid}.meta.json").read_text())["ok"] is False
sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / "scripts"))
from _common import load_script_module
assert load_script_module("06_arm_c.py").verdict_ok(tid) is False, \
    "a stale verdict .md with a failed meta must not count as eligible"
PY
pass "stale verdict file with a failed meta is not eligible for C/C0"

# Restore the good state (default: the scratch workspace is cleaned up).
$PY "$EV/scripts/06_arm_c.py" --config "$EV/config.toml" --stage verify \
  --mock-dataset "$DS" --arm-b-output "$ARMB" --workspace-src "$WS" \
  --claude-cmd "$CLAUDE" --force >/dev/null || fail "06 verify restore run failed"
[ ! -d "$EV/results/workspaces_c/acme__widget-1.lv1" ] \
  || fail "scratch workspace not cleaned up after a successful verdict"
pass "scratch workspace removed after a successful verdict (--keep-workspaces opts out)"

# ------------------------------------------------------- 06 dataset build
printf '\n== 06 dataset build (C and C0)\n'
$PY "$EV/scripts/06_arm_c.py" --config "$EV/config.toml" --stage dataset \
  --mock-dataset "$DS" --arm-b-output "$ARMB" --workspace-src "$WS" \
  || fail "06 dataset exited non-zero (round-trip assertions live inside)"

$PY - "$EV" <<'PY' || exit 1
import pathlib, sys
from datasets import load_dataset
ev = pathlib.Path(sys.argv[1])
loaded = {}
for arm in ("c", "c0"):
    ds = load_dataset(str(ev / f"results/dataset_arm_{arm}"), split="lite")
    assert len(ds) == 2, f"arm {arm}: expected 2 rows, got {len(ds)}"
    assert set(ds["instance_id"]) == {"acme__widget-1.lv1", "acme__widget-2.lv1"}
    for col in ("image_name", "patch", "FAIL_TO_PASS", "repo_settings"):
        assert col in ds.column_names, (arm, col)
    loaded[arm] = {r["instance_id"]: r for r in ds}

tid = "acme__widget-1.lv1"
c, c0 = loaded["c"][tid]["problem_statement"], loaded["c0"][tid]["problem_statement"]

for ps in (c, c0):
    assert ps.startswith("Original statement for task 1."), ps[:80]
    assert "\n\n---\n\n## Implementation Spec\n\n" in ps
    assert "Acceptance scenario: widget() returns 42." in ps
    assert "## Previous attempt" in ps and "```diff" in ps
    assert "+def feature():" in ps, "arm B patch not embedded"
    assert "## Instruction" in ps
    assert "Start from the pristine repository" in ps

assert "## Referee verdict" in c and "VACUOUS" in c, "arm C carries no verdict"
assert "## Self-review" in c0 and "VACUOUS" not in c0, "arm C0 leaked referee content"
assert "Review the previous attempt critically yourself" in c0

# Structural check: C and C0 must differ in EXACTLY ONE contiguous region —
# the feedback block between the diff fence and the instruction.
head = "\n## Instruction\n"
pre_c, pre_c0 = c.split("## Referee verdict")[0], c0.split("## Self-review")[0]
assert pre_c == pre_c0, "prefix (statement + spec + previous attempt) diverged"
assert c[c.index(head):] == c0[c0.index(head):], "instruction tail diverged"

# Other columns must be byte-identical across the two arms.
for arm_tid in loaded["c"]:
    a, b = loaded["c"][arm_tid], loaded["c0"][arm_tid]
    for col in a:
        if col != "problem_statement":
            assert a[col] == b[col], (arm_tid, col)
PY
pass "C/C0 datasets round-trip; differ only in the feedback section"

# ------------------------------------------------------- 06 infer --dry-run
printf '\n== 06 infer --dry-run\n'
OUT06="$($PY "$EV/scripts/06_arm_c.py" --config "$EV/config.toml" --stage infer --dry-run \
  --arm-b-output "$ARMB")" || fail "06 infer --dry-run exited non-zero"
echo "$OUT06" | sed 's/^/    /'
$PY - <<PY || exit 1
import shlex
lines = [l for l in """$OUT06""".splitlines() if l.strip().startswith("[arm ")]
assert len(lines) == 2, lines
cmds = {}
for line in lines:
    arm = line.split("]")[0].strip("[arm ").strip()
    cmds[arm] = shlex.split(line.split("] ", 1)[1])
assert set(cmds) == {"C", "C0"}, cmds
for arm, cmd in cmds.items():
    assert cmd[:2] == ["fb", "infer"], cmd
    assert cmd[cmd.index("--agent") + 1] == "claude_code"
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-4-5"
    assert cmd[cmd.index("--split") + 1] == "lite"
    assert cmd[cmd.index("--dataset") + 1].endswith(f"results/dataset_arm_{arm.lower()}"), cmd
    assert cmd[cmd.index("--output-dir") + 1].endswith(f"results/infer_arm_{arm.lower()}"), cmd
    assert cmd[cmd.index("--task-id") + 1:] == ["acme__widget-1.lv1", "acme__widget-2.lv1"], cmd
def strip(c):
    out, skip = [], False
    for t in c:
        if skip: skip = False; continue
        if t in ("--dataset", "--output-dir"): skip = True; continue
        out.append(t)
    return out
assert strip(cmds["C"]) == strip(cmds["C0"]), "C and C0 differ beyond --dataset/--output-dir"
PY
pass "06 emits two fb infer commands differing only in --dataset/--output-dir"

# ------------------------------------------------ 06 infer + eval (mock fb)
printf '\n== 06 infer + eval (mock fb) -> runs.json\n'
$PY "$EV/scripts/06_arm_c.py" --config "$EV/config.toml" --stage infer \
  --arm-b-output "$ARMB" >/dev/null || fail "06 infer (mock fb) exited non-zero"
$PY "$EV/scripts/06_arm_c.py" --config "$EV/config.toml" --stage eval \
  --arm-b-output "$ARMB" >/dev/null || fail "06 eval (mock fb) exited non-zero"

$PY - "$EV" <<'PY' || exit 1
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])
runs = json.loads((ev / "results/runs.json").read_text())
assert set(runs) == {"C", "C0"}, list(runs)
for arm in ("C", "C0"):
    e = runs[arm]
    assert e["arm"] == arm and e["split"] == "lite", e
    assert e["task_ids"] == ["acme__widget-1.lv1", "acme__widget-2.lv1"], e
    assert e["infer_returncode"] == 0 and e["eval_returncode"] == 0, e
    assert e["output_jsonl"].endswith("output.jsonl") and pathlib.Path(e["output_jsonl"]).exists()
    assert e["report_json"].endswith("report.json") and pathlib.Path(e["report_json"]).exists()
    assert e["dataset"].endswith(f"dataset_arm_{arm.lower()}"), e
assert runs["C"]["task_ids"] == runs["C0"]["task_ids"], "C and C0 must share one id list"
PY
pass "runs.json records C and C0 (infer cmd, predictions, report, shared id list)"

# ------------------------------------------------------------- 05b report
printf '\n== 05b report (B vs C vs C0)\n'
# Per-instance eval fixtures: C beats both B and C0 on task 1; all tie on 2.
$PY - "$EV" <<'PY'
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])
runs = json.loads((ev / "results/runs.json").read_text())
cells = {  # (resolved, pass_rate) per arm
    "B":  {"acme__widget-1.lv1": (False, 0.25), "acme__widget-2.lv1": (True, 1.0)},
    "C":  {"acme__widget-1.lv1": (True, 1.0),   "acme__widget-2.lv1": (True, 1.0)},
    "C0": {"acme__widget-1.lv1": (False, 0.50), "acme__widget-2.lv1": (True, 1.0)},
}
for arm, per in cells.items():
    if arm == "B":
        root = ev / "results/infer_arm_b/2026-08-15__12-00-00"
        root.mkdir(parents=True, exist_ok=True)
        (root / "report.json").write_text(json.dumps({"attempt_1": {"n_attempt": 1}}))
        runs.setdefault("B", {})["report_json"] = str(root / "report.json")
    else:
        root = pathlib.Path(runs[arm]["report_json"]).parent
    for iid, (resolved, rate) in per.items():
        d = root / "eval_outputs" / iid / "attempt-1"
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.json").write_text(json.dumps(
            {iid: {"resolved": resolved, "pass_rate": rate}}, indent=2))
(ev / "results/runs.json").write_text(json.dumps(runs, indent=2))
PY

OUT05B="$($PY "$EV/scripts/05b_report_c.py" --config "$EV/config.toml")" \
  || fail "05b exited non-zero"
echo "$OUT05B" | sed 's/^/    /'

$PY - "$EV" <<'PY' || exit 1
import pathlib, sys
md = (pathlib.Path(sys.argv[1]) / "results/report_c.md").read_text()
assert "B **1/2**, C **2/2**, C0 **1/2**" in md, md
# C vs C0: b=1 (C-only), c=0 -> n=1, p = 2 * (1/2) = 1.0
assert "**C − C0**" in md and "discordant b(C-only)=**1** c(C0-only)=**0**" in md, md
assert "**C − B**" in md and "**C0 − B**" in md, md
assert "p = 1.0000" in md, md
assert "delta **+1**" in md, md
# Verify-round cost carried next to the outcome: 2 tasks x $0.2468.
assert "$0.4936" in md, md
assert "| **totals (2)** | **1** | **2** | **1** |" in md, md
for i in (1, 2):
    assert f"`acme__widget-{i}.lv1`" in md
assert "C0 is the attribution control" in md and "blind to the test suite" in md
PY
pass "report_c.md: three-way table, C/C0 attribution comparison, verdict cost, caveats"

printf '\nArm C smoke test PASSED\n'

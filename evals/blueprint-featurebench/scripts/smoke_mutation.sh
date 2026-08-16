#!/usr/bin/env bash
# Fully offline smoke test for stage 07 (the mutation-score overlay).
# Needs python3.12 + pytest + `datasets`; needs neither docker, nor network,
# nor a real `claude`, nor `fb`.
#
#   uv run --python 3.12 --with datasets --with pytest bash scripts/smoke_mutation.sh
#
# Covers: the real container-state reconstruction (restore /testbed, apply the
# mask patch, delete FAIL_TO_PASS, re-init git, apply model_patch) against a
# mock docker whose "container" is a host temp dir; kill/survive accounting with
# one non-applicable proposal; the baseline_red path; the no_agent_tests path;
# cell resumability; --dry-run; and the generated report.
set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
TMP="$(mktemp -d)"
[ -n "${KEEP_TMP:-}" ] && echo "tmp: $TMP" || trap 'rm -rf "$TMP"' EXIT

pass() { printf '  ok  %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1" >&2; exit 1; }

command -v git >/dev/null || fail "git is required"
command -v pytest >/dev/null || fail "pytest is required (run under: uv run --with pytest)"

# The harness roots itself at scripts/.., so work on a throwaway copy of the
# tree — a fixture run must never clobber a real results/ dir.
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
limit = 0

[mutation]
model = "claude-sonnet-5"
timeout_seconds = 120
claude_args = ["--permission-mode", "bypassPermissions"]
n_mutations = 3
test_timeout_seconds = 120
TOML

# ------------------------------------------------------------------- unit bits
printf '\n== classification helpers\n'
$PY - "$EV" <<'PY' || exit 1
import sys, pathlib, importlib.util
scripts = pathlib.Path(sys.argv[1]) / "scripts"
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location("m07", scripts / "07_mutation.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

assert m.is_test_path("tests/test_x.py")
assert m.is_test_path("pkg/test/helpers_test.py")
assert m.is_test_path("astropy/visualization/tests/test_basic_rgb.py")
assert m.is_test_path("test_grade_agent.py")
assert not m.is_test_path("pkg/latest_thing.py")
assert not m.is_test_path("IMPLEMENTATION_SUMMARY.md")
assert not m.is_test_path("tests/fixture.txt")

tests, sources = m.classify(
    ["IMPLEMENTATION_SUMMARY.md", "pkg/core.py", "pkg/tests/test_core.py", "README.md"])
assert tests == ["pkg/tests/test_core.py"], tests
assert sources == ["pkg/core.py"], sources   # .md noise never reaches the mutator

patch = (
    "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x\n+y\n"
    "diff --git a/gone.py b/gone.py\ndeleted file mode 100644\n--- a/gone.py\n+++ /dev/null\n"
    "diff --git a/tests/test_a.py b/tests/test_a.py\nnew file mode 100644\n--- /dev/null\n+++ b/tests/test_a.py\n@@ -0,0 +1 @@\n+z\n"
)
assert m.patch_files(patch) == ["a.py", "tests/test_a.py"], m.patch_files(patch)
assert "gone.py" not in m.source_diff(patch, ["a.py"])
assert m.source_diff(patch, ["a.py"]).startswith("diff --git a/a.py")

assert m.extract_json_array('prose\n```json\n[{"file": "a"}]\n```\ntrailing') == [{"file": "a"}]
good, bad = m.sanitize_mutations(
    [{"file": "a.py", "find": "x", "replace": "y"},
     {"file": "tests/test_a.py", "find": "x", "replace": "y"},
     {"file": "a.py", "find": "x", "replace": "x"}],
    ["a.py"])
assert len(good) == 1 and len(bad) == 2, (good, bad)
assert {b["skip_reason"] for b in bad} == {
    "file is not a mutable source file of this patch", "no-op mutation"}

# FeatureBench's runner choice, minus the pytest-timeout flag.
assert m.test_command({"repo_settings": '{"test_cmd": "pytest -q"}'}) == "pytest -q"
assert m.test_command({"repo_settings": '{"test_cmd": "pytest -q", "use_uv": true}'}) == "uv run pytest -q"
assert m.test_command({"repo": "pydantic/pydantic", "repo_settings": '{"test_cmd": "nope"}'}) \
    == "pytest -rA -v --color=no"
assert "--timeout" not in m.test_command({"repo_settings": '{"timeout_one": 10}'})
PY
pass "is_test_path / classify / patch parsing / mutation sanitising / test_command"

# ------------------------------------------------------------------- fixtures
printf '\n== fixtures (fake image, mask patch, per-arm model patches)\n'
$PY - "$TMP" <<'PY'
import itertools, json, pathlib, subprocess, sys

tmp = pathlib.Path(sys.argv[1])
img = tmp / "image"

CALC_FULL = '''def area(w, h):
    return w * h


def grade(score):
    if score >= 90:
        return "A"
    if score >= 60:
        return "P"
    return "F"
'''

CALC_MASKED = '''def area(w, h):
    return w * h
'''

CALC_BROKEN = '''def area(w, h):
    return w * h


def grade(score):
    return "F"
'''

F2P_TEST = '''from calc import grade


def test_hidden_oracle():
    assert grade(95) == "A"
'''

AGENT_TEST_WEAK = '''from calc import grade


def test_a_boundary():
    assert grade(90) == "A"
    assert grade(89) == "P"
'''

AGENT_TEST_STRONG = '''from calc import grade


def test_all_boundaries():
    assert grade(90) == "A"
    assert grade(89) == "P"
    assert grade(60) == "P"
    assert grade(59) == "F"
'''

MY_REPO = {"calc.py": CALC_FULL, "conftest.py": "", "test_grade.py": F2P_TEST}
# State the agent actually saw: mask applied, FAIL_TO_PASS file deleted.
BASE = {"calc.py": CALC_MASKED, "conftest.py": ""}


def git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo, capture_output=True, text=True, check=True)


def write(root, files):
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


counter = itertools.count()


def make_patch(before, after):
    d = tmp / f"scratch{next(counter)}"
    d.mkdir(parents=True)
    write(d, before)
    git(d, "init", "-q")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "base", "--allow-empty")
    for p in d.rglob("*"):
        if ".git" in p.parts or not p.is_file():
            continue
        p.unlink()
    write(d, after)
    git(d, "add", "-A")
    return git(d, "diff", "--cached", "HEAD").stdout


mask_patch = make_patch(MY_REPO, {**MY_REPO, "calc.py": CALC_MASKED})
patch_measured = make_patch(BASE, {**BASE, "calc.py": CALC_FULL, "test_grade_agent.py": AGENT_TEST_WEAK})
patch_red = make_patch(BASE, {**BASE, "calc.py": CALC_BROKEN, "test_grade_agent.py": AGENT_TEST_WEAK})
patch_notests = make_patch(BASE, {**BASE, "calc.py": CALC_FULL})
# Arm B's agent test deliberately lands on the deleted FAIL_TO_PASS path.
patch_strong = make_patch(BASE, {**BASE, "calc.py": CALC_FULL, "test_grade.py": AGENT_TEST_STRONG})

# Fake image filesystem: /testbed is a git repo (as FeatureBench images ship it)
# and /root/my_repo holds the pristine tree the runtime restores from.
(img / "testbed").mkdir(parents=True)
git(img / "testbed", "init", "-q")
write(img / "root" / "my_repo", MY_REPO)

repo_settings = json.dumps({"test_cmd": "pytest -rA --tb=short --color=no -p no:cacheprovider"})
rows = []
for i in (1, 2, 3):
    rows.append({
        "instance_id": f"acme__widget-{i}.lv1",
        "problem_statement": "Add a grade() helper.",
        "image_name": "mock/featurebench:acme_widget",
        "repo": "acme/widget",
        "patch": mask_patch,
        "FAIL_TO_PASS": ["test_grade.py"],
        "repo_settings": repo_settings,
    })
with open(tmp / "split.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")

arm_a = {
    "acme__widget-1.lv1": patch_measured,   # 2 applicable mutations, 1 killed
    "acme__widget-2.lv1": patch_red,        # agent tests fail on agent code
    "acme__widget-3.lv1": patch_notests,    # source only, no agent tests
}
arm_b = {"acme__widget-1.lv1": patch_strong}   # same source, thorough tests
for name, preds in (("output_a.jsonl", arm_a), ("output_b.jsonl", arm_b)):
    with open(tmp / name, "w") as f:
        for iid, patch in preds.items():
            f.write(json.dumps({"instance_id": iid, "model_patch": patch}) + "\n")
print("fixtures written")
PY

# runs.json uses non-default arm keys to prove --arm resolves against the file.
$PY - "$EV" "$TMP" <<'PY'
import json, pathlib, sys
ev, tmp = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
runs = {
    "A": {"arm": "A", "split": "lite", "output_jsonl": str(tmp / "output_a.jsonl")},
    "B": {"arm": "B", "split": "lite", "output_jsonl": str(tmp / "output_b.jsonl")},
}
(ev / "results/runs.json").write_text(json.dumps(runs, indent=2))
PY
pass "fake image, mask patch, 4 model patches, runs.json"

# ---------------------------------------------------------------- mock docker
# "Containers" are host temp dirs holding a testbed/ and a root/my_repo/. Every
# exec runs the REAL command after rewriting container-absolute paths and
# stripping the conda prelude, so the state reconstruction is genuinely tested.
MOCK_STATE="$TMP/containers"
mkdir -p "$MOCK_STATE"
DOCKER="$TMP/fake-docker"
cat > "$DOCKER" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
sub="$1"; shift
case "$sub" in
  run)
    cid="c$$-$RANDOM"
    mkdir -p "$MOCK_STATE/$cid"
    cp -R "$MOCK_IMAGE_DIR/." "$MOCK_STATE/$cid/"
    mkdir -p "$MOCK_STATE/$cid/tmp"
    echo "$cid"
    ;;
  exec)
    cid="$1"; script="$4"   # <cid> bash -c <script>
    root="$MOCK_STATE/$cid"
    [ -d "$root" ] || { echo "no such container: $cid" >&2; exit 1; }
    script="$(python3 -c '
import sys
root, s = sys.argv[1], sys.argv[2]
s = s.replace("source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed && ", "")
s = s.replace("/root/my_repo", root + "/root/my_repo")
s = s.replace("/testbed", root + "/testbed")
s = s.replace("/tmp/fb_", root + "/tmp/fb_")
sys.stdout.write(s)
' "$root" "$script")"
    set +e
    bash -c "$script"
    exit $?
    ;;
  cp)
    src="$1"; dst="$2"
    cid="${dst%%:*}"; path="${dst#*:}"
    root="$MOCK_STATE/$cid"
    target="$root${path}"
    mkdir -p "$(dirname "$target")"
    cp "$src" "$target"
    ;;
  rm) : ;;   # -f <cid>: keep the dir so the smoke test can inspect it
  *) echo "mock docker: unsupported subcommand $sub" >&2; exit 2 ;;
esac
SH
chmod +x "$DOCKER"
export MOCK_STATE MOCK_IMAGE_DIR="$TMP/image"

# ---------------------------------------------------------------- mock claude
CLAUDE="$TMP/fake-claude"
cat > "$CLAUDE" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
prompt=""; next_is_prompt=0
for arg in "$@"; do
  if [ "$next_is_prompt" = 1 ]; then prompt="$arg"; next_is_prompt=0; fi
  if [ "$arg" = "-p" ]; then next_is_prompt=1; fi
done
[ -n "$prompt" ] || { echo "mock claude: no -p prompt" >&2; exit 3; }
case "$prompt" in
  *"{source_diff}"*|*"{source_files}"*|*"{n_mutations}"*|*"{instance_id}"*)
    echo "mock claude: placeholder was not substituted" >&2; exit 4;;
esac
case "$prompt" in
  *"calc.py"*) ;;
  *) echo "mock claude: source file list missing from prompt" >&2; exit 5;;
esac
case "$prompt" in
  *"def test_"*) echo "mock claude: test hunks leaked into the mutation prompt" >&2; exit 6;;
esac
echo "$prompt" > "$MOCK_STATE/../last_mutation_prompt.txt"
cat <<'JSON'
{"type":"result","subtype":"success","is_error":false,
 "result":"Here are the mutations.\n\n```json\n[{\"file\":\"calc.py\",\"find\":\"    if score >= 90:\",\"replace\":\"    if score >= 91:\",\"rationale\":\"flip the A boundary\"},{\"file\":\"calc.py\",\"find\":\"    if score >= 60:\",\"replace\":\"    if score >= 61:\",\"rationale\":\"flip the pass boundary\"},{\"file\":\"calc.py\",\"find\":\"    return 12345\",\"replace\":\"    return 54321\",\"rationale\":\"not present anywhere\"}]\n```\n",
 "total_cost_usd":0.0321,"duration_ms":2100,"num_turns":2}
JSON
SH
chmod +x "$CLAUDE"

# -------------------------------------------------------------------- dry run
printf '\n== 07 --dry-run\n'
OUT="$($PY "$EV/scripts/07_mutation.py" --config "$EV/config.toml" --arm both \
  --mock-dataset "$TMP/split.jsonl" --dry-run --docker-cmd "$DOCKER" --claude-cmd "$CLAUDE")" \
  || fail "07 --dry-run exited non-zero"
echo "$OUT" | sed 's/^/    /'
echo "$OUT" | grep -q "arm A: 3 cell(s)" || fail "dry-run did not list arm A cells"
echo "$OUT" | grep -q "arm B: 1 cell(s)" || fail "dry-run did not list arm B cells"
echo "$OUT" | grep -q "sources=\['calc.py'\]" || fail "dry-run did not classify source files"
[ -f "$EV/results/mutation_report.md" ] && fail "dry-run must not write a report"
[ -d "$EV/results/mutation" ] && fail "dry-run must not write cell JSON"
pass "--dry-run lists cells for every runs.json arm and writes nothing"

# -------------------------------------------------------------------- real run
printf '\n== 07 full run (mock docker + mock claude)\n'
$PY "$EV/scripts/07_mutation.py" --config "$EV/config.toml" --arm both \
  --mock-dataset "$TMP/split.jsonl" --docker-cmd "$DOCKER" --claude-cmd "$CLAUDE" \
  | sed 's/^/    /' || fail "07 exited non-zero"

$PY - "$EV" <<'PY' || exit 1
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])


def cell(arm, i):
    return json.loads((ev / f"results/mutation/{arm}/acme__widget-{i}.lv1.json").read_text())


# --- measured cell: 3 proposals, 1 non-applicable, 1 killed of 2 applicable
c = cell("A", 1)
assert c["status"] == "measured", c
assert c["agent_test_files"] == ["test_grade_agent.py"], c["agent_test_files"]
assert c["source_files"] == ["calc.py"], c["source_files"]
assert c["baseline"]["rc"] == 0, c["baseline"]
assert c["n_proposed"] == 3, c
assert c["n_applicable"] == 2, c
assert c["n_killed"] == 1, c
assert c["kill_rate"] == 0.5, c
assert c["claude"]["cost_usd"] == 0.0321, c["claude"]
assert c["agent_tests_on_f2p_path"] == [], c
by_find = {m["find"]: m for m in c["mutations"]}
assert by_find["    if score >= 90:"]["killed"] is True
assert by_find["    if score >= 60:"]["killed"] is False
skipped = by_find["    return 12345"]
assert skipped["applicable"] is False and "absent" in skipped["skip_reason"], skipped
assert c["mask_patch_warning"] is None, c["mask_patch_warning"]

# --- baseline_red: agent tests fail against the agent's own code
c = cell("A", 2)
assert c["status"] == "baseline_red", c
assert c["baseline"]["rc"] == 1, c["baseline"]
assert c["mutations"] == [] and c["kill_rate"] is None, c
assert c["claude"] is None, "claude must not be paid for a red baseline"

# --- no_agent_tests: source-only patch, resolved without a container
c = cell("A", 3)
assert c["status"] == "no_agent_tests", c
assert c["agent_test_files"] == [] and c["source_files"] == ["calc.py"], c
assert c["baseline"] is None and c["claude"] is None, c

# --- arm B: same source, thorough tests kill both mutations
c = cell("B", 1)
assert c["status"] == "measured", c
assert c["n_applicable"] == 2 and c["n_killed"] == 2 and c["kill_rate"] == 1.0, c
# the agent's test file landed on the deleted oracle path — flagged, not excluded
assert c["agent_test_files"] == ["test_grade.py"], c
assert c["agent_tests_on_f2p_path"] == ["test_grade.py"], c
print("cell assertions ok")
PY
pass "kill/survive accounting, non-applicable drop, baseline_red, no_agent_tests"

$PY - "$EV" <<'PY' || exit 1
import pathlib, sys
md = (pathlib.Path(sys.argv[1]) / "results/mutation_report.md").read_text()
for i in (1, 2, 3):
    assert f"`acme__widget-{i}.lv1`" in md, md
assert "| `acme__widget-1.lv1` | 0.50 (1/2) | 1.00 (2/2) |" in md, md
assert "| `acme__widget-2.lv1` | — (baseline_red) | — |" in md, md
assert "| `acme__widget-3.lv1` | — (no_agent_tests) | — |" in md, md
# Arm A: 3 cells, 1 measured @0.50, 1 no_agent_tests, 1 baseline_red.
# measured-only mean = 0.50; with no_agent_tests scored 0.0 = 0.25.
assert "| **A** | 3 | 1 | 1 | 1 | 0 | 0 | **0.5000** | **0.2500** |" in md, md
assert "| **B** | 1 | 1 | 0 | 0 | 0 | 0 | **1.0000** | **1.0000** |" in md, md
assert "## Agent tests on a fail-to-pass path" in md, md
assert "- arm **B** · `acme__widget-1.lv1` — `test_grade.py`" in md, md
assert "## Caveats" in md and "Small N" in md
assert "LLM-chosen mutations" in md and "Agent-tests-only scope" in md
PY
pass "mutation_report.md: per-task rates, both denominators, arm census, caveats"

# ------------------------------------------------------------------ resumable
printf '\n== 07 resume (cached cells)\n'
BROKEN="$TMP/broken"
printf '#!/usr/bin/env bash\nexit 9\n' > "$BROKEN"; chmod +x "$BROKEN"
$PY "$EV/scripts/07_mutation.py" --config "$EV/config.toml" --arm both \
  --mock-dataset "$TMP/split.jsonl" --docker-cmd "$BROKEN" --claude-cmd "$BROKEN" >/dev/null \
  || fail "07 resume run failed"
$PY - "$EV" <<'PY' || exit 1
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])
c = json.loads((ev / "results/mutation/A/acme__widget-1.lv1.json").read_text())
assert c["status"] == "measured" and c["kill_rate"] == 0.5, c
PY
pass "cached cells are reused (broken docker/claude never invoked)"

# --------------------------------------------------------------- single arm
printf '\n== 07 --arm A --task-id (single cell, --force)\n'
$PY "$EV/scripts/07_mutation.py" --config "$EV/config.toml" --arm A \
  --task-id acme__widget-1.lv1 --force --mock-dataset "$TMP/split.jsonl" \
  --docker-cmd "$DOCKER" --claude-cmd "$CLAUDE" \
  --out "$EV/results/mutation_report_one.md" | sed 's/^/    /' || fail "07 single-cell run failed"
$PY - "$EV" <<'PY' || exit 1
import pathlib, sys
md = (pathlib.Path(sys.argv[1]) / "results/mutation_report_one.md").read_text()
assert "| task | arm A |" in md, md
assert "acme__widget-2" not in md and "acme__widget-3" not in md, md
PY
pass "--arm/--task-id narrow the panel; unknown arm keys are rejected"

set +e
ERR="$($PY "$EV/scripts/07_mutation.py" --config "$EV/config.toml" --arm Z \
  --mock-dataset "$TMP/split.jsonl" --docker-cmd "$DOCKER" --claude-cmd "$CLAUDE" 2>&1)"
rc=$?
set -e
[ "$rc" -eq 1 ] || fail "unknown arm should exit 1, got $rc"
echo "$ERR" | grep -q "not present in runs.json" || fail "unknown arm error message: $ERR"
pass "unknown --arm exits 1 with a message naming the available arms"

printf '\nsmoke test PASSED\n'

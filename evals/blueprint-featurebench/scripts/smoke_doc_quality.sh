#!/usr/bin/env bash
# Offline smoke test for stages 12 (deterministic doc quality) and 13 (LLM
# judge, with a mock `claude`). Needs python3.11+ and git; needs neither
# docker, nor network, nor a real `claude`, nor `fb`.
#
# Covers: oracle extraction from a mask patch; symbol recall counted only in
# code context; effective recall minus fenced symbols; the fence heuristic
# (an "Out of scope" heading fences, a "Companion gaps" heading with an
# in-scope line does not, a code-block comment never does); grounding
# against a re-masked workspace (hallucinated path counted, test paths and
# oracle symbols not counted); corpus mode joined to a report.md whose A
# column is "—"; direction table; stage 13 blind args, cell caching, stale
# fingerprint re-judging, and summary tables via a mock judge.
set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPTS/.." && pwd)"
PY="${PYTHON:-python3}"
TMP="$(mktemp -d)"
[ -n "${KEEP_TMP:-}" ] && echo "tmp: $TMP" || trap 'rm -rf "$TMP"' EXIT

pass() { printf '  ok  %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1" >&2; exit 1; }

EV="$TMP/harness"
mkdir -p "$EV/scripts" "$EV/prompts" "$EV/results/dataset_arm_b/data" "$EV/specs_x" "$EV/specs_y"
cp "$SCRIPTS/_common.py" "$SCRIPTS/08_taxonomy.py" "$SCRIPTS/12_doc_quality.py" "$SCRIPTS/13_doc_judge.py" "$EV/scripts/"
cp "$ROOT/prompts/taxonomy.md" "$ROOT"/prompts/judge_*.md "$EV/prompts/"

cat > "$EV/config.toml" <<'TOML'
[eval]
dataset = "LiberCoders/FeatureBench"
split = "lite"
limit = 0
n_concurrent = 1

[spec]
model = "mock"
claude_args = ["--permission-mode", "must-not-leak-into-judge"]

[doc_judge]
model = "mock-judge"
timeout_seconds = 30
TOML

# ---------------------------------------------------------------- pristine testbed
TB="$TMP/testbed"
mkdir -p "$TB/pkg/tests"
cat > "$TB/pkg/mod.py" <<'PY'
def kept():
    return 1


def alpha(x):
    return x + 1


class Beta:
    def gamma(self):
        return 2
PY
printf 'def test_alpha():\n    assert alpha(1) == 2\n' > "$TB/pkg/tests/test_mod.py"
git -C "$TB" init -q && git -C "$TB" add -A && git -C "$TB" -c user.email=s@s -c user.name=s commit -qm base

# The mask: strip alpha, Beta and gamma, leave kept().
cat > "$TB/pkg/mod.py" <<'PY'
def kept():
    return 1
PY
MASK="$(git -C "$TB" diff)"
git -C "$TB" checkout -q -- pkg/mod.py

$PY - "$EV" "$MASK" <<'PY'
import json, pathlib, sys
ev, mask = pathlib.Path(sys.argv[1]), sys.argv[2]
row = {"instance_id": "acme__t1.lv1", "patch": mask, "FAIL_TO_PASS": ["pkg/tests/test_mod.py::test_alpha"], "problem_statement": "restore"}
(ev / "results/dataset_arm_b/data/lite.jsonl").write_text(json.dumps(row) + "\n")
PY

# ---------------------------------------------------------------- specs
# X: names `alpha` in code context, `gamma` only under a fence, Beta only in
# prose (must not count) → recall 2/3, effective 1/3. Hallucinates
# pkg/ghost.py; names test paths (not counted) and `kept` (grounded).
cat > "$EV/specs_x/acme__t1.lv1.md" <<'MD'
# Spec X

Restore `alpha` in `pkg/mod.py`. Reuse `kept`. The Beta class is context.
Write tests in `pkg/tests/test_new.py` and `tests/test_top.py`. See `pkg/ghost.py`.

## Out of scope

- `gamma` is pre-existing breakage; do not attempt to fix it.

## Acceptance Scenarios

- S1 Given 1 When alpha Then 2
MD
# Y: names everything; a "Companion gaps" heading with an in-scope line and a
# code-block comment must not fence anything.
cat > "$EV/specs_y/acme__t1.lv1.md" <<'MD'
# Spec Y

Restore `alpha`, `Beta` and `Beta.gamma` in `pkg/mod.py`.

## Companion gaps found during review

- **In scope, added during review** — `gamma` must be restored too.

```python
# do not modify `alpha` here — illustrative only
def alpha(x): ...
```
MD
printf '# Spec ledger — must be ignored\n' > "$EV/specs_y/acme__t1.lv1.ledger.md"

for L in x y; do
  R=$([ "$L" = x ] && echo 0.40 || echo 0.90)
  printf '| task id | A resolved | B resolved | A pass_rate | B pass_rate | spec cost USD | spec seconds |\n|---|---|---|---|---|---|---|\n| `acme__t1.lv1` | — | no | — | %s | 1.0 | 10 |\n| **totals (1)** | **0** | **0** | **—** | **%s** | **1.0** | **10** |\n' "$R" "$R" > "$EV/report_$L.md"
done

# ---------------------------------------------------------------- stage 12
( cd "$EV" && $PY scripts/12_doc_quality.py --pristine-testbed "$TB" \
    --corpus "x=$EV/specs_x:$EV/report_x.md" --corpus "y=$EV/specs_y:$EV/report_y.md" >/dev/null )

$PY - "$EV" <<'PY' || fail "stage 12 assertions"
import json, pathlib, sys
ev = pathlib.Path(sys.argv[1])
g = json.loads((ev / "results/doc_quality.json").read_text())["groups"]
x, y = g["x"][0], g["y"][0]
assert x["n_oracle_symbols"] == 3, x["n_oracle_symbols"]
assert x["symbol_recall"] == round(2/3, 3), x["symbol_recall"]
assert x["effective_recall"] == round(1/3, 3), x["effective_recall"]
assert x["missed_symbols"] == ["Beta"], x["missed_symbols"]
assert x["fenced_oracle_symbols"] == ["gamma"], x["fenced_oracle_symbols"]
assert y["symbol_recall"] == 1.0 and y["effective_recall"] == 1.0, (y["symbol_recall"], y["effective_recall"])
assert y["fenced_oracle_symbols"] == [], y["fenced_oracle_symbols"]
assert x["file_recall"] == 1.0 and y["file_recall"] == 1.0
assert x["ungrounded"] == ["pkg/ghost.py"], x["ungrounded"]
assert x["pass_rate"] == 0.40 and y["pass_rate"] == 0.90
md = (ev / "results/doc_quality_report.md").read_text()
assert "1 tasks × 2 labels" in md and "within-task agreement" in md and "| x | 1 |" in md and "ledger" not in md
PY
pass "stage 12: oracle, recall in code context, effective recall, fence heuristic, grounding, corpus join"

# ---------------------------------------------------------------- stage 13 (mock claude)
MOCK="$TMP/claude"
cat > "$MOCK" <<'PY'
#!/usr/bin/env python3
"""Mock `claude -p`: pick a canned JSON result by which judge prompt it got.
Records argv and cwd so the smoke can assert the judge ran blind."""
import json, os, pathlib, sys
pathlib.Path(os.environ["MOCK_LOG"]).open("a").write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\n")
prompt = sys.argv[2]
if "**listing** task" in prompt:
    res = {"fenced": [{"symbol": "Beta.gamma()", "strength": "hard", "quote": "do not attempt"}, {"symbol": None}]}
else:
    res = {"scenarios": [{"id": "S1", "class": "behavioral", "why": ""}, {"id": "S2", "class": "vague", "why": "v"}],
           "has_definition_of_done": "no", "has_implementing_agent_instruction": True}
print(json.dumps({"result": "some prose first\n" + json.dumps(res), "total_cost_usd": 0.01, "duration_ms": 5, "usage": {}}))
PY
chmod +x "$MOCK"
export MOCK_LOG="$TMP/mock_calls.jsonl"

( cd "$EV" && $PY scripts/13_doc_judge.py --claude-cmd "$MOCK" --repeats 2 --workers 2 \
    --corpus "x=$EV/specs_x:$EV/report_x.md" --corpus "y=$EV/specs_y:$EV/report_y.md" >"$TMP/j1.log" )
grep -q "8 judge call(s) pending" "$TMP/j1.log" || fail "stage 13: expected 8 pending calls (2 labels × 2 metrics × 2 repeats)"
[ "$(ls "$EV"/results/doc_judge/x/*.json | wc -l | tr -d ' ')" = 4 ] || fail "stage 13: 4 cached cells for label x"
pass "stage 13: 8 mock judge calls, cells cached"

$PY - "$TMP/mock_calls.jsonl" "$EV" <<'PY' || fail "stage 13: judge must run blind"
import json, sys
calls = [json.loads(l) for l in open(sys.argv[1])]
assert len(calls) == 8
for c in calls:
    assert "--tools" in c["argv"] and c["argv"][c["argv"].index("--tools") + 1] == "", c["argv"]
    assert "must-not-leak-into-judge" not in c["argv"], c["argv"]
    assert not c["cwd"].startswith(sys.argv[2]), c["cwd"]
PY
pass "stage 13: tools disabled, [spec] args not inherited, empty cwd"

$PY - "$EV" <<'PY' || fail "stage 13 report assertions"
import pathlib, sys
md = (pathlib.Path(sys.argv[1]) / "results/doc_judge_report.md").read_text()
row = next(l for l in md.splitlines() if l.startswith("| x | `acme__t1.lv1`"))
cells = [c.strip() for c in row.strip("|").split("|")]
assert cells[2].startswith("1.00 ['gamma']"), cells[2]        # Class.method() → gamma, None entry dropped
assert cells[3] == "2.00" and cells[4] == "0.50", cells[3:5]  # scenarios, behavioral share
assert cells[5] == "n/y", cells[5]                            # "no" string → False
assert cells[6] == "0.40", cells[6]                           # joined pass_rate
assert "within-task agreement" in md
PY
pass "stage 13: report row (fence∩oracle, testability, pass_rate join)"

( cd "$EV" && $PY scripts/13_doc_judge.py --claude-cmd "$MOCK" --repeats 2 \
    --corpus "x=$EV/specs_x:$EV/report_x.md" --corpus "y=$EV/specs_y:$EV/report_y.md" >"$TMP/j2.log" )
grep -q "0 judge call(s) pending" "$TMP/j2.log" || fail "stage 13: rerun should hit the cache"
pass "stage 13: rerun skips cached cells"

printf '\nAppended after judging.\n' >> "$EV/specs_x/acme__t1.lv1.md"
( cd "$EV" && $PY scripts/13_doc_judge.py --claude-cmd "$MOCK" --repeats 2 \
    --corpus "x=$EV/specs_x:$EV/report_x.md" --corpus "y=$EV/specs_y:$EV/report_y.md" >"$TMP/j3.log" )
grep -q "4 judge call(s) pending" "$TMP/j3.log" || fail "stage 13: rewritten spec must re-judge its 4 cells only"
pass "stage 13: stale spec fingerprint re-judges"

echo "smoke_doc_quality: all ok"

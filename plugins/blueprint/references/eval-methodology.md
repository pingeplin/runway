# Blueprint Plugin Comparison Methodology

Reusable methodology for comparing two versions of the Blueprint TDD plugin
(or any TDD agent workflow) on a panel of small/medium tasks.

First applied to the v3.3.1 → v3.4.0 comparison (8 tasks, May 2026). The
per-task evaluation reports and scripts from that run are archived
outside the repo; the headline findings live in the v3.4.0 CHANGELOG
entry. This document is the *method* — reusable for the next version
comparison.

## 1. Goal framing

**Right question:** "On dimensions X, Y, Z, how does version B differ from version A on a representative panel?"

**Wrong question:** "Is version B better?" — too aggregate; no single answer.

Pick the dimensions before running anything. Don't add dimensions mid-panel to chase findings. The dimensions that fit the v3.3.1 vs v3.4.0 study:

- Correctness (vs hidden oracle)
- Mutation score (own test suite quality)
- Plan compactness (lines + units + critical path)
- Process discipline (git log: failing-test commits, per-step commits, audit trail)
- Scope discipline (LOC vs minimum the task requires)
- Code quality (cyclomatic complexity, structure, readability)
- API ergonomics (defaults, import paths, ease-of-use)
- Wall time (only directional — no transcripts to time precisely)

## 2. Setup: parallel-version environment

### Two isolated config dirs

Claude Code stores auth + plugin caches in `$CLAUDE_CONFIG_DIR`. To run two
plugin versions side-by-side:

```bash
# Per-version config dir (auth must be set up in each, separately)
mkdir -p ~/.claude-bpA ~/.claude-bpB

# Manually configure each:
#   ~/.claude-bpA/plugins/known_marketplaces.json → marketplace path to version A worktree
#   ~/.claude-bpA/plugins/installed_plugins.json  → plugin entry
#   ~/.claude-bpA/settings.json                    → enabledPlugins: { "X@marketplace": true }
# Repeat for ~/.claude-bpB/ pointing at version B worktree
```

**Practical gotcha:** auth is per-config-dir. A fresh `$CLAUDE_CONFIG_DIR`
hits the login screen. The shortcut we used for the second version was
**unsetting `$CLAUDE_CONFIG_DIR` so it uses the default `~/.claude` config**,
which is already authenticated. Acceptable when the default config can be
temporarily pointed at the second version.

### Git worktrees pinned to versions

```bash
git tag vA <commit-sha-of-version-A>
git tag vB <commit-sha-of-version-B>
git worktree add ../runway-bpA vA
git worktree add ../runway-bpB vB
```

Each config dir's marketplace points at one worktree. Verify with:

```bash
cat ~/.claude-bpA/plugins/cache/<marketplace>/<plugin>/<version>/plugin.json
```

The cache directory name reveals which version is actually loaded.

### Two tmux windows

```bash
tmux new-session -d -s eval -n bpA -c <task-dir-A>
tmux new-window  -t eval -n bpB -c <task-dir-B>
# Each window: export CLAUDE_CONFIG_DIR=..., then `claude`
```

Attach with `tmux attach -t eval`. Switch windows with `Ctrl-b n` / `Ctrl-b 0/1`.

**Avoid dots in tmux window names** — tmux interprets them as pane separators.

## 3. Task panel design

### Pick tasks before running anything

Don't pick tasks after seeing intermediate results — that's confirmation bias.

For a TDD-plugin study, 6–8 tasks suffice. They should **stress different things**:

- 2 well-defined algorithmic katas (e.g. LCD, Roman numerals) — baseline
- 2 stateful/ruled katas (Poker, Bowling, Tennis) — interactions across rules
- 1 structurally complex feature (Markdown→HTML) — exercises slice batching
- 1 modification task with a starter codebase (BankAccount bug) — read-before-write
- 1 vague spec (one-sentence brief) — stresses spec stage

The first task surfaces the methodology's blind spots; assume task #1's evaluation will need re-running once you've learned what to measure.

### Each task gets one identical `KATA.md`

Both versions read the same `KATA.md`. Differences in output come from the
plugin, not the brief. Stage the kata directory the same way (git init, drop
KATA.md, optional starter code) for both versions.

### Pre-register tasks in a state file

```json
{
  "current_task": 3,
  "tasks": {
    "3": {"name": "bowling", "dir_prefix": "runway-bowling", "status": "in_progress"},
    ...
  }
}
```

This lets the orchestration cron (see §5) know where you are and what's next without re-deriving from the filesystem.

## 4. Per-task scoring methodology

For each task, run this **before reading either agent's tests**:

### Step 1: Author the hidden oracle from KATA.md alone

A pure reference implementation derived from the kata text only. Save as
`oracle.py` in the per-task eval directory. If your spec interpretation
diverges from one or both agents', that's *signal*, not a bug — it surfaces
spec ambiguity in the kata.

Where the kata's contract is unambiguous, write a function oracle returning
the expected output. Where the kata leaves room (e.g. "the output indicates
the winner" without specifying format), write a *partial* oracle that
extracts the load-bearing parts (e.g. winner + category, not exact wording)
via regex.

Where the kata is deliberately vague (e.g. the one-sentence Undo brief), no
oracle is possible — skip Step 2 and rely on artifact comparison only.

### Step 2: Run the oracle against both impls

```python
# run_hidden_tests.py — shared shape:
import sys, importlib.util
spec = importlib.util.spec_from_file_location("oracle", "oracle.py")
oracle = importlib.util.module_from_spec(spec); spec.loader.exec_module(oracle)

def load_impl(root):
    """Import the impl from the per-version worktree."""
    for k in list(sys.modules):
        if k == "<module-name>": del sys.modules[k]
    sys.path.insert(0, str(root))
    from <module> import <entry_point>
    return <entry_point>

# Define CASES = [(label, args, expected), ...]
# Run both impls against the same CASES, count passes/fails.
```

**Test cases must include the kata's own worked examples plus a fan-out of
edge cases the kata mentions explicitly** (wheel straight, 10th-frame
bonus, boundary values). Don't author cases that go beyond the kata's
stated scope — that biases toward whichever impl is more permissive.

### Step 3: Targeted mutation testing on each agent's own suite

Run each agent's own pytest suite, but with strategic source mutations
applied to the production code:

```python
# mutation_test.py — shared shape:
MUTATIONS = [
    ("flip a boundary",   "src.py", "if x >= 3:", "if x >= 2:"),
    ("swap an operator",  "src.py", "winner = a if a > b else b", "... < ..."),
    ("break a table",     "src.py", '"M": 1000', '"M": 999'),
    ...
]
# For each mutation: backup file, apply, run pytest, record killed/survived, restore.
```

**Hand-pick 7–10 mutations** that hit load-bearing semantics (comparison
operators, lookup table entries, default values, boundary conditions).
Mutation score = killed / total. Both versions should hit 100% on a
well-designed task; if either survives a mutation, that's a real test-suite
gap to investigate.

**Don't use mutmut directly on each impl** — its random mutations include
many that are uninteresting (whitespace, equivalent expressions). Manual
strategic mutations give more signal per minute of runtime.

### Step 4: Artifact review (spec, plan)

For each version's `specs/` and `plans/`:

- Count scenarios in the spec.
- Count units in the plan (triplets vs slices, nodes vs slices).
- Count lines in each.
- Note structural differences (streams, dependency depth, REFACTOR ceremony).
- Look for places the spec drifts from the source artifact (KATA.md) — this is the gate where most correctness failures originate.

### Step 5: Code review (implementation)

- LOC for production code and tests, separately.
- Cyclomatic complexity via `radon cc -s`.
- Structure (single file vs split modules).
- Ergonomic gotchas (empty `__init__.py`, required params with no defaults, packaging that needs `pip install -e .` for tests to import).

### Step 6: Git audit

```bash
git log --oneline       # commit count
git log --stat          # per-commit changes
git log --pretty=format:"%s" | grep -c "^test: add failing"   # fail-test checkpoints
```

For each version, count:

- Total commits
- Failing-test commits (e.g. `test: add failing tests for X` — Blueprint v3.4's slice-loop signature)
- Per-slice / per-triplet implementation commits
- Final single-squash commit (or its absence)

### Step 7: Write the per-task `EVALUATION_<task>.md`

Use a fixed schema. Headline TL;DR table first, then notable findings,
then a "what we didn't learn" section. Keep it to ~1 page per task — the
*synthesis* is where you aggregate across tasks.

## 5. Orchestration: how to run 16 cells (8 tasks × 2 versions)

### Cron-driven auto-orchestration

Use Claude Code's `CronCreate` (or `/loop <interval> <prompt>`) to fire a
checkup prompt every N minutes. The prompt should be self-contained
(each fire is a fresh-context invocation) and instruct the orchestrator
to:

1. Read the panel state file.
2. Capture both tmux windows.
3. Auto-approve standard gates: spec/plan/commit gates → approve; language
   menu → Python; refactor-direction → skip; trust-folder → Enter.
4. If both versions completed the current task, score it (Steps 1–7),
   advance the state file, set up the next task, relaunch claude in both
   tmux windows.
5. If task N is the last, write the synthesis report and self-delete.

**Interval choice:** 10–15 minutes is right for small/medium TDD tasks.
Shorter (5 min) bombs the rate limit with no-op cron fires; longer (30+ min)
loses responsiveness on gate approvals.

### Auto-approval gate defaults

| Gate type | Auto-action |
|---|---|
| TUI menu, option 1 highlighted ("Approve") | `Enter` |
| Chat-style "approve, or revise?" | type `approve` + `Enter` |
| Language selection menu | `1` (Python) |
| Refactor-direction menu | `3` (skip) |
| `/commit` confirmation | `yes` + `Enter` |
| Trust-folder dialog | `Enter` |
| Rate-limit options | `Escape` (or wait for reset, then Escape) |

**Claude Code vi-mode quirk:** typing `text` then `Enter` in INSERT mode
submits. But if vi normal mode is active, you need `i` first, then text,
then `Enter`. Sometimes the agent shows a *placeholder hint* in the input
(e.g. "yes, commit it" pre-filled) — that text is NOT real input; you
still need to type your answer.

### Real-world failure modes encountered

- Sessions hit the **5-hour Claude Max usage block** mid-panel. Cron is
  useless until block resets. **Mitigation:** budget the panel across
  multiple usage blocks; pause cron when the rate-limit menu appears.
- Background `claude` processes can **linger** after `/exit`. If a fresh
  `claude` invocation collides with an old one, the new one may inherit
  the old conversation context. **Mitigation:** confirm shell prompt visible
  before relaunching; `pgrep claude` as a sanity check.
- A `claude` process **mid-tool-call** ignores `/exit`. The slash command
  becomes a chat message instead. **Mitigation:** wait for idle prompt,
  or use `Ctrl+C Ctrl+C` to force-quit if stuck.
- Tmux `send-keys` with **dots in window names** silently fails (`bp3.4` is
  interpreted as pane 4 of window 3). **Mitigation:** dot-free names.

## 6. Synthesis report structure

Write the synthesis **after** all per-task reports are done. It should:

1. **Headline:** one paragraph stating the dimensions where one version
   reliably wins and where they're tied. Don't pick an aggregate winner.
2. **Per-task summary table:** one row per task, columns for each
   measured dimension. Lets the reader spot patterns at a glance.
3. **Confirmed findings:** repeating patterns across 5+ tasks. Number them.
4. **Mixed findings:** patterns visible on some tasks but not others.
   Note the task shape that triggers each.
5. **What the panel can't tell us:** N=1 caveats, missing dimensions,
   generalization limits. Be honest here — the report is more credible
   when it states what it doesn't claim.
6. **Recommendations:** if the goal was "should we ship version B?", give
   the answer + the conditions. If the goal was research, list follow-up
   questions worth scaling.

## 7. Caveats to repeat in every report

- **N=1 per cell** — LLM sampling variance is real; one run doesn't
  generalize.
- **Single rater** — whoever authored the hidden oracle has a coherence
  bias toward their own interpretation.
- **Task panel may not cover real-world feature shapes** — small Python
  katas are a narrow slice.
- **No transcripts** — wall-time and token comparisons are directional
  only, not precise.
- **Workflow rate-limits and pauses** affect timing; comparable wall times
  require the same usage block.

## 8. When to scale up

Run a **multi-cell-per-task panel** (3+ runs per version per task) when:

- A correctness divergence in the N=1 panel needs replication.
- A wall-time claim needs to be sized.
- The plugin is going into production and the cost of being wrong is high.

For a 6-task × 2-version × 3-run panel: ~36 runs at 20–40 minutes each =
12–24 hours of agent runtime, across multiple usage blocks. Worth it for a
production decision; overkill for a hypothesis-generation pass.

---

**Origin:** authored after the v3.3.1 → v3.4.0 comparison panel (May 2026).
The methodology was iterated mid-panel — early tasks used a slightly
different approach; later tasks converged on the form documented here.

---
name: run
description: Execute a plan's TDD execution graph — walk RED/GREEN/REFACTOR triplets in dependency order, auto-verify against the spec when complete. ALWAYS use this skill when the user wants to run a plan, execute a plan, start implementing from a plan, implement the plan, begin the TDD cycle, execute the graph, or says anything like "let's start building" when a plan graph file exists. Also trigger when the user references a plans/*_graph.md file and wants to begin implementation, or says "unskip the tests and make them pass".
argument-hint: [path-to-plan-graph-file]
---

# Run

Execute a plan graph by walking its TDD triplets in dependency order, enforcing RED-GREEN-REFACTOR discipline at every step, and auto-verifying against the spec when complete.

## When to Use

This skill sits after `/plan` and before `/refactor` in the blueprint workflow:

```
/spec → /plan → /run → /refactor → /commit
```

The full orchestrator is `/tdd`, which chains all of these.

## Inputs

The skill needs a **plan graph file**: `plans/{yymm.xxxx}_{feature_name}_graph.md`

**Finding the input:**

- If the user provides a path as `$ARGUMENTS`, use it directly.
- If no path is provided, scan `plans/` for the most recently modified `*_graph.md` file and confirm with the user.
- If no graph files exist, tell the user to run `/plan` first.

## Step 1 — Parse the Graph

Read the plan graph file and build the execution model:

1. **Extract streams** (A, B, C...) and their triplets (A1, A2, A3, B1...).
2. **Parse each triplet node:**
   - **ID** (e.g., A1)
   - **Type**: RED, GREEN, or REFACTOR
   - **Dependencies**: `depends: A2, B2` or none
   - **Payload**: test code location (RED), implementation target (GREEN), or refactor direction (REFACTOR)
   - **Skip marker**: whether a REFACTOR node is marked `(skip)` or `(optional)`
3. **Build the dependency DAG** and compute a topological ordering.
4. **Identify ready nodes** — those with no unmet dependencies.
5. **Check for already-completed nodes** — read checkbox state from the plan file. If some triplets are already checked off (from a previous interrupted run), mark them complete and adjust the ready set.

**Present the execution order to the user for confirmation:**

```
## Execution Order: {feature_name}

{N} triplets across {M} streams
Critical path: {stream(s)}

Order:
  1. A1 [RED]  — {test description}
  2. A2 [GREEN] — {implementation target}
  3. A3 [REFACTOR] — {direction or "(skip)"}
  4. B1 [RED]  — {test description}
  ...

{If resuming}: Resuming from triplet {X} ({Y}/{N} already complete)

Proceed? (y/n)
```

Wait for user confirmation before executing.

## Step 2 — Execute Triplets

### Decide execution strategy

After parsing the graph, analyze stream independence to choose the execution strategy automatically:

1. **Count independent streams** — streams with no cross-stream dependencies in their first RED node are independent at launch.
2. **Choose strategy:**
   - **1 stream, or all streams have cross-dependencies** → **Sequential**: process triplets in topological order, one at a time.
   - **2+ independent streams** → **Parallel**: spawn one agent per independent stream. Each agent runs its stream's triplets sequentially. When a stream depends on another stream's GREEN node, it waits for that agent to report completion.
   - **Mixed** — some streams are independent, some depend on others → **Hybrid**: launch independent streams in parallel; dependent streams queue behind their prerequisites.

3. **Present the strategy to the user:**
   ```
   Strategy: Parallel (3 independent streams detected)
     Agent 1: Stream A (coupon validation) — 3 triplets
     Agent 2: Stream B (shipping calc) — 3 triplets
     Queued:  Stream C (checkout) — depends on A2, B2 — starts after both complete
   ```

**Parallel execution rules:**
- Each agent gets its own stream and runs RED→GREEN→REFACTOR sequentially within it.
- Agents write to different files (each stream targets different modules) — no merge conflicts.
- After all agents complete, run the full test suite once to catch cross-stream integration issues.
- If any agent escalates, pause all agents and report to the user.
- Progress tracking and plan checkbox updates still apply — each agent updates its own stream's checkboxes.

**When NOT to parallelize** (fall back to sequential even if streams look independent):
- The plan has fewer than 6 total triplets (overhead not worth it)
- Multiple streams target the same file
- The user explicitly asks for sequential execution

Process each triplet in dependency order. After each GREEN node, update the plan file to check off the completed triplet.

### RED Nodes

A RED node introduces a failing test. The expectation is that the test FAILS.

1. **Unskip the test** — remove the skip marker (`pytest.mark.skip`, `it.skip`, `t.Skip`, `@Disabled`, etc.) from the test identified in the node's payload.
2. **Run the test suite.**
3. **Evaluate results:**
   - The target test FAILS, all other tests PASS — this is correct. Proceed.
   - The target test PASSES unexpectedly — the behavior is already implemented or the test is trivially true. Flag it:
     ```
     WARNING: {test_name} passed unexpectedly (RED should fail).
     This test may be trivially true or the behavior is already implemented.
     Options: (a) inspect and proceed, (b) investigate before continuing
     ```
     Ask the user how to proceed.
   - Other tests BREAK — a dependency issue or test isolation problem. Stop and report:
     ```
     STOP: {N} unrelated test(s) broke when unskipping {test_name}.
     This indicates a dependency or isolation issue.
     Broken tests: {list}
     ```
     Do not proceed until the user resolves this.

### GREEN Nodes

A GREEN node implements the minimal code to make the test pass. The expectation is that ALL tests PASS.

1. **Read the implementation target** from the node's payload (file path and description).
2. **Implement the minimal code** to make the RED test pass. Follow the principle of simplest thing that could work — do not gold-plate.
3. **Run the test suite.**
4. **Evaluate results:**
   - ALL tests pass — success. Update the plan file checkbox. Proceed.
   - The new test still fails — iterate on the implementation. Make a second attempt with a different approach. If it still fails after 2 attempts, escalate:
     ```
     ESCALATE: Could not make {test_name} pass after 2 attempts.
     Last error: {error message}
     Please review and provide guidance.
     ```
   - Other previously-passing tests break — the implementation has a side effect. Fix the regression before proceeding. If the fix is not obvious, escalate to the user.

5. **Update the plan file** — check off this triplet's checkbox.

### REFACTOR Nodes

A REFACTOR node restructures code without changing behavior. The expectation is that all tests REMAIN green.

1. **Check the node's markers:**
   - If marked `(skip)` or `(optional)`: skip it, note it in progress output, proceed.
   - Otherwise: read the refactoring direction from the node's payload.
2. **Apply the refactoring** following the direction.
3. **Run the test suite.**
4. **Evaluate results:**
   - All tests pass — success. Proceed.
   - Tests break — the refactoring changed behavior or hit a structure-sensitive test. **Revert the refactoring** and flag it:
     ```
     REVERTED: Refactoring {node_id} broke {N} test(s).
     This may indicate structure-sensitive tests or an unsafe refactoring.
     Broken tests: {list}
     Continuing with next triplet.
     ```
     Do not block execution on a failed optional refactoring. Note it for the verification summary.

## Progress Tracking

Show progress as execution proceeds:

```
[3/12 triplets] Stream A complete, starting Stream B...
[7/12 triplets] B2 [GREEN] -- all tests passing
```

**Resumability:** If execution is interrupted (user stops, error escalation, etc.), the plan file's checkbox state records progress. When `/run` is invoked again on the same plan, it detects completed triplets and resumes from the first incomplete node.

## Step 3 — Auto-Verification

After all triplets are executed, verify the implementation against the spec. This absorbs what was previously the `/post-verification` skill.

1. **Locate the spec file** — follow the plan's spec link (in the plan header).
2. **Read acceptance scenarios** (S1, S2, S3...) from the spec.
3. **Cross-check each scenario against active tests:**
   - Find a test that covers the scenario's behavior.
   - Confirm the test is active (not skipped).
   - Confirm the implementation satisfies the scenario.
4. **Check for remaining issues:**
   - Skipped tests that were not unskipped during execution.
   - Acceptance scenarios with no test coverage.
   - Implementation deviations from the spec.
   - Reverted refactorings from Step 2.

### Lightweight Verification (< 5 scenarios)

```markdown
## Verification: {feature}

**Status:** {N}/{M} scenarios verified
**Gaps:** {list or "none"}
**Reverted refactorings:** {list or "none"}
**Next:** /refactor or address gaps
```

### Full Verification (5+ scenarios)

```markdown
## Verification Report: {feature}

**Spec:** {path} | **Plan:** {path} | **Date:** {YYYY-MM-DD}

### Acceptance Scenarios

| # | Scenario | Status | Test | Notes |
|---|----------|--------|------|-------|
| S1 | {summary} | Verified / Missing / Partial | {test name} | {evidence} |
| S2 | ... | ... | ... | ... |

### Skipped Tests

| Test | File | Reason |
|------|------|--------|
| {name} | {path} | {reason} |

*(If none: "All tests are active.")*

### Implementation Deviations

| Area | Spec Says | Implementation Does | Intentional? |
|------|-----------|---------------------|--------------|
| {area} | {spec} | {reality} | {Yes/No} |

*(If none: "Implementation matches spec.")*

### Reverted Refactorings

| Node | Direction | Failure Reason |
|------|-----------|----------------|
| {id} | {direction} | {what broke} |

*(If none: "All refactorings applied successfully.")*

### Summary

- **Scenarios:** {N}/{M} verified
- **Skipped tests:** {N} remaining
- **Deviations:** {N} found
- **Reverted refactorings:** {N}
```

## Escalation Policy

After verification, determine next steps:

- **All green, all scenarios verified** — suggest `/refactor` if there is cleanup direction remaining, or `/commit` if the code is clean.
- **Minor gaps (1-2 partial scenarios)** — present gaps. Ask the user whether to fix them now or proceed to refactoring.
- **Significant gaps (missing scenarios, multiple failures)** — recommend fixing gaps before refactoring. Do not suggest proceeding with known missing functionality.
- **Test failure unresolved after 2 attempts** — already escalated during Step 2. Summarize unresolved items and wait for user guidance.

## Scaling

- **Small plan** (1 stream, < 6 triplets): Sequential execution. Lightweight verification.
- **Medium plan** (2-3 streams, 6-15 triplets): Auto-parallelize independent streams. Full verification.
- **Large plan** (4+ streams, 15+ triplets): Auto-parallelize. If the plan has more than 20 triplets, suggest breaking into phases — run the foundational streams first, verify, then run the dependent streams.

## General Guidelines

- **RED means red** — if a test passes during a RED step, something is wrong. Do not silently proceed.
- **GREEN means all green** — a GREEN step is not done until the entire test suite passes, not just the new test.
- **REFACTOR is optional pressure relief** — a failed refactoring should never block forward progress. Revert and move on.
- **Minimal implementation** — during GREEN steps, write the simplest code that makes the test pass. Resist the urge to implement ahead of the tests.
- **Parse gracefully** — the plan graph format may have minor variations in whitespace, header casing, or delimiter style. Match on semantic content (node IDs, types, dependency lists), not exact formatting.
- **Preserve test integrity** — never modify a test to make it pass during a GREEN step. The test is the spec. If the test seems wrong, escalate to the user.
- **Update the plan file** — check off triplets as they complete so that progress is durable across interruptions.

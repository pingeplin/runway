---
name: plan
description: Generate an execution graph of TDD triplets (RED/GREEN/REFACTOR) with dependency tracking from a spec or source code. Merges behavioral analysis, test ordering, and implementation planning into a single artifact. Use when the user asks to "create a plan", "generate plan", "implementation plan", "execution graph", "TDD plan", "break down into tasks", or wants a structured plan for test-driven development.
argument-hint: [path-to-spec-or-source]
---

# Plan — TDD Execution Graph Generator

Generate a complete execution graph of TDD triplets from a spec or design
document. Each node in the graph is one step of the RED-GREEN-REFACTOR
cycle, with explicit dependency tracking that enables parallel execution
of independent streams.

This skill replaces the old three-skill chain (`/test-generator` ->
`/test-orderer` -> `/implementation-plan`) with a single, integrated
workflow that produces one artifact: the execution graph.

## Output Artifact

A single file written to:

```
plans/{yymm.xxxx}_{feature_name}_graph.md
```

Create the `plans/` directory if it does not exist.

## ID System

IDs follow arXiv-style `yymm.xxxx` format:

- `yy` — 2-digit year
- `mm` — 2-digit month
- `xxxx` — zero-padded sequential number, scoped per `yymm`

**To determine the ID:**

1. **If a spec is referenced** (provided as argument, linked
   in conversation, or discoverable in `specs/` for the current
   feature) — **reuse its ID**. The plan and spec form a pair and must share
   the same ID for unambiguous cross-referencing.
2. **Only if no spec exists** — generate a new ID:
   1. Scan `specs/` and `plans/` for files matching `yymm.*`
      where `yymm` is the current year+month
   2. Find the highest `xxxx` across both directories
   3. Increment by 1
   4. If no files exist for the current month, start at `0001`
   5. If none of the directories exist yet, start at `yymm.0001`

## Workflow

Follow these phases in order. Each phase produces visible output for the
user and waits for confirmation before proceeding. If the user provides a
test list or explicitly asks to skip analysis, begin at Phase 2.

---

### Phase 1 — Behavioral Analysis (Beck's "Test List")

Read the spec (or source code or feature description) and
extract:

1. **Behavioral requirements** — What the system should DO, not how it is
   built. Ask: "If I were an observer with no knowledge of internals, what
   behaviors would I expect?"
2. **API contracts / interfaces** — Input/output boundaries, request/response
   shapes, function signatures.
3. **State transitions** — How entities change state and under what conditions.
4. **Error scenarios** — What can go wrong? Timeouts, invalid input, missing
   data, permission failures, race conditions.
5. **Edge cases** — Boundary values, empty collections, maximum sizes,
   unicode, concurrent access.
6. **Invariants** — Things that must ALWAYS be true regardless of code path.

Map each extracted behavior to a scenario ID from the spec (S1, S2, etc.)
when scenario IDs exist. If the spec does not use scenario IDs, assign
them sequentially.

Present the analysis as a **Test List** (Beck's Canon TDD Step 1):

```markdown
## Test List

### [Feature/Component Name]

**Happy Path**
1. [ ] S1 — Given X, when Y, then Z
2. [ ] S2 — ...

**Edge Cases**
3. [ ] S5 — Given empty input, when Y, then Z
4. [ ] ...

**Error Scenarios**
5. [ ] S3 — Given X, when service times out, then Z
6. [ ] ...

**Invariants**
7. [ ] S7 — After any operation, X must remain true
```

Number tests sequentially across all categories. Group by behavior type
for readability — this is a logical grouping for review, not the
implementation order.

**Property-based test candidates:** While building the Test List, identify
behaviors best expressed as properties rather than individual examples:

- Invariants (e.g., "balance never goes negative")
- Roundtrip properties (e.g., "encode then decode returns original")
- Commutativity / associativity of operations
- "No matter what valid input, X always holds"

Mark these with `[property]` in the Test List.

**Vague or incomplete specs:** If the spec lacks sufficient detail to
extract behavioral requirements, ask the user clarifying questions about
expected inputs/outputs, error handling, and key behaviors before
proceeding. Do not generate a plan from ambiguous requirements.

**Source code instead of a spec:** If the user provides source code rather
than a spec, extract behaviors from the code's public API, docstrings,
and usage patterns, then proceed with the same workflow.

> **Beck:** "This is analysis, but behavioral analysis. You're thinking
> of all the different cases in which the behavior change should work.
> Mistake: mixing in implementation design decisions. Chill."

**Wait for user confirmation before proceeding to Phase 2.**

---

### Phase 2 — Stream Decomposition

Group related tests into **streams**. A stream is a sequence of related
TDD triplets that can be developed as a coherent unit — typically
organized by component, feature area, or concern.

**How to identify streams:**

- Tests that share the same target module or class tend to group together
- Tests that share setup or domain context belong together
- Tests where one behavior is a prerequisite for another are in the same
  stream, or linked by cross-stream dependencies
- A degenerate case and its corresponding happy path belong in the same
  stream

**Build the dependency graph:**

- Within each stream: order from degenerate -> happy path -> edge cases
  -> error handling (the TDD ordering principle)
- Across streams: identify which streams depend on behaviors established
  by other streams
- Identify parallelizable streams — streams with no cross-dependencies
  can be executed simultaneously

Present the stream structure for user review:

```markdown
## Stream Structure

### Stream A: Coupon Validation (4 triplets)
Tests: S3, S5, S8, S12
Depends: (none) — can start immediately

### Stream B: Order Persistence (3 triplets)
Tests: S1, S2, S4
Depends: Stream A (needs CouponValidator from A2)

### Stream C: Notification Dispatch (2 triplets)
Tests: S6, S9
Depends: (none) — can run in parallel with A

Parallelizable: Streams A and C
Critical path: A -> B
```

**Scaling guidance:**

- **Small bug fix (1-3 tests):** Single stream, skip the graph
  visualization. Keep it lightweight.
- **Single feature (4-10 tests):** 2-3 streams typical. Brief dependency
  summary.
- **Large feature (10+ tests):** Multiple streams with complex
  dependencies, full graph visualization, critical path analysis.

**Wait for user confirmation before proceeding to Phase 3.**

---

### Phase 3 — Triplet Generation

For each stream, generate the full TDD triplets. Every triplet has three
nodes: RED (write a failing test), GREEN (make it pass), REFACTOR
(improve structure).

**Before generating test code:** Examine existing test files in the
project to discover naming conventions, directory structure, import
patterns, and test framework. Match these conventions in generated code.
If the project has no existing tests, ask the user which language and
framework to use if not already clear from context.

**Node ID scheme:** Stream letter + sequential number within the stream.
RED nodes are odd-numbered starting at 1, GREEN nodes follow their RED,
REFACTOR nodes follow their GREEN:

- A1 (RED), A2 (GREEN), A3 (REFACTOR)
- A4 (RED), A5 (GREEN), A6 (REFACTOR)
- B1 (RED), B2 (GREEN), B3 (REFACTOR)

#### RED Nodes — Write a Failing Test

Each RED node contains executable, skipped test code following these
conventions:

**All tests are generated as skipped.** Use the framework's skip
mechanism. The skip reason describes the behavior being tested.

| Framework   | Skip syntax                                          |
|-------------|------------------------------------------------------|
| pytest      | `@pytest.mark.skip(reason="...")`                    |
| Jest/Vitest | `it.skip("...", () => { ... })` or `xit("...", ...)` |
| Go testing  | `t.Skip("...")`                                      |
| JUnit       | `@Disabled("...")`                                   |
| RSpec       | `xit "..." do ... end` or `pending("...")`           |

**Naming:** `test_[action]_[scenario]_[expected_outcome]`

**Structure:** Every test uses AAA (Arrange/Act/Assert) with clear inline
setup. Prefer a bit of repetition over indirection — keep the full
context visible within each test function.

**Test Desiderata:** Apply the checklist from
`../../references/test-desiderata.md` to every RED node. Read that file
now. Prioritize: Behavioral > Structure-insensitive > Readable > Specific
> Deterministic > Isolated.

**Anti-patterns:** Apply every item from `../../references/anti-patterns.md`.
Read that file now. In particular:

- No structure-sensitive assertions (AP-1)
- Every test has meaningful assertions (AP-2)
- No non-deterministic sources (AP-3)
- Expected values derived from the spec, not copy-pasted (AP-4)
- Mocking only at external boundaries (AP-5)
- Inline setup over shared fixtures (AP-6)
- Organize by behavior, not by class (AP-7)
- Descriptive test names with scenario and outcome (AP-8)

**Async behaviors:** When the spec describes async operations, test
command side and query side separately. Assert on eventual state, never
on timing.

**Property-based tests:** For items marked `[property]` in the Test List,
generate property-based tests using the project's property-based testing
library (Hypothesis, fast-check, etc.).

#### GREEN Nodes — Make It Pass

Each GREEN node specifies:

- **Target file(s):** Where to write or modify production code
- **Size estimate:** `[S]` (a few lines), `[M]` (file-sized change),
  `[L]` (multi-file, should be broken down further if possible)
- **Guidance:** What minimal implementation makes the RED test pass.
  Describe the approach without writing full production code — the
  developer (or `/run`) implements it.

#### REFACTOR Nodes — Improve Structure

Each REFACTOR node is optional — include it when there is a concrete
refactoring opportunity. Skip it (mark as "no refactoring needed") when
the implementation is already clean.

When included, describe:

- What structural improvement to make (extract method, introduce
  abstraction, consolidate duplication)
- Why now is the right time (pattern has emerged, duplication threshold
  reached)
- The constraint: behavior must not change, all tests must stay green

#### Triplet Format

Use this exact format for machine-parseability by `/run`:

````markdown
### A1: RED — test_reject_expired_coupon
**Depends:** (none)
**Scenario:** S3
```python
@pytest.mark.skip(reason="expired coupon is rejected with validation error")
def test_reject_expired_coupon():
    order = Order(items=[Item("widget", 10.00)])
    expired = Coupon("SAVE10", expired=True)
    result = order.apply_coupon(expired)
    assert result.error == "Coupon expired"
    assert order.total == 10.00
```

### A2: GREEN — implement CouponValidator.validate()
**Depends:** A1
**Target:** `src/validators/coupon.py`
**Size:** [S]
Make the failing test pass. Add an `expired` check to `Coupon` and return
a validation error when `expired=True`. Minimal implementation — do not
add other validation logic yet.

### A3: REFACTOR — (none needed)
**Depends:** A2
No refactoring needed at this stage.

### A4: RED — test_apply_valid_coupon_reduces_total
**Depends:** A2
**Scenario:** S5
```python
@pytest.mark.skip(reason="valid coupon reduces order total by discount amount")
def test_apply_valid_coupon_reduces_total():
    order = Order(items=[Item("widget", 10.00)])
    coupon = Coupon("SAVE10", discount_pct=10)
    order.apply_coupon(coupon)
    assert order.total == 9.00
```

### A5: GREEN — implement Coupon.apply() discount logic
**Depends:** A4
**Target:** `src/models/coupon.py`
**Size:** [S]
Apply the percentage discount to the order total. Handle the case where
the coupon is valid (not expired).

### A6: REFACTOR — extract discount calculation
**Depends:** A5
Extract discount calculation into a `DiscountCalculator` if the method
is growing. Only if warranted — if `apply_coupon` is still simple,
skip this.
````

**Dependency declarations are explicit:**

- `(none)` for root nodes that can start immediately
- Single dependency: `A2` (the GREEN node that must complete first)
- Multiple dependencies: `A2, B2` (needs behaviors from two streams)
- RED nodes typically depend on the prior GREEN node in their stream
  (the previous behavior must be implemented before testing the next)
- RED nodes may depend on GREEN nodes from other streams when they need
  cross-stream behavior
- GREEN nodes always depend on their RED node
- REFACTOR nodes always depend on their GREEN node

**Within-stream ordering:** Follow the TDD ordering principle:

1. Degenerate cases first — force the function signature and skeleton
2. Simplest happy path — the minimal "it works" case
3. Additional happy paths — each adds one new concept
4. Edge cases for established behaviors
5. Error handling — graceful failure modes
6. Integration-level behaviors last — combine multiple features

Each step should drive exactly one design decision forward.

---

### Phase 4 — Desiderata Self-Review

After generating all triplets, perform a self-review of every RED node.
Score each test against the priority Desiderata properties:

```markdown
## Desiderata Review

| Node | Test Name                        | Behavioral | Struct-Insensitive | Deterministic | Specific | Readable | Notes        |
|------|----------------------------------|:----------:|:------------------:|:-------------:|:--------:|:--------:|--------------|
| A1   | test_reject_expired_coupon       | pass       | pass               | pass          | pass     | pass     | --           |
| A4   | test_apply_valid_coupon_...      | pass       | pass               | pass          | pass     | pass     | --           |
| B1   | test_save_order_persists_...     | pass       | warn               | pass          | pass     | pass     | Uses DB fake |
```

**Flag any test scoring `warn` on Behavioral or Structure-insensitive** —
these are the two properties Beck emphasizes most. A `warn` on either
requires explicit justification in the Notes column. A test that would
score `fail` on either must be rewritten before finalizing the plan.

---

### Phase 5 — Plan Self-Review

Before presenting the plan to the user, validate the graph and auto-fix
what you can. This phase is the plan's quality gate — it catches issues
that would cause `/run` to fail or produce incomplete results.

**Run these checks in order:**

#### 5a. Scenario Coverage

Map every acceptance scenario ID from the spec (S1, S2, S3...) to at
least one RED node in the graph. If a scenario has no corresponding RED
node, **generate the missing triplet** and insert it into the
appropriate stream.

```
Coverage check:
  S1 → A1 ✅
  S2 → A4 ✅
  S3 → (none) ❌ — generating triplet B4/B5/B6
  S4 → C1 ✅
```

#### 5b. Dependency Validity

Verify the dependency graph is executable:

- **No cycles** — if A depends on B and B depends on A, restructure.
- **No orphaned references** — every `Depends: X` must reference a node
  that exists in the graph.
- **No missing GREEN nodes** — every RED node must have a corresponding
  GREEN node immediately after it.

Auto-fix: restructure dependencies to break cycles; add missing GREEN
nodes with inferred implementation targets.

#### 5c. Stream Balance

Check for imbalanced streams that hurt parallelism:

- **Overloaded stream** (10+ triplets) — suggest splitting into
  sub-streams. Ask the user where to split.
- **Trivial stream** (1 triplet) — consider merging into a related
  stream to reduce coordination overhead.

This check suggests rather than auto-fixes — stream boundaries are a
design decision.

#### 5d. Ordering Sanity

Within each stream, verify TDD ordering discipline:

- Degenerate cases come before happy paths
- Happy paths come before edge cases
- Edge cases come before error handling
- Each step builds on the previous one

Auto-fix: reorder triplets within a stream if the ordering violates
these principles. Preserve cross-stream dependencies.

#### 5e. File Conflict Detection

Check whether parallel streams target the same production files:

- Extract all `**Target:**` paths from GREEN nodes
- If two independent streams write to the same file, parallel execution
  risks merge conflicts

If conflicts are found, present options to the user:
1. Merge the conflicting streams into one (sequential safety)
2. Sequence the conflicting triplets (partial parallelism)
3. Proceed anyway (the developer will handle conflicts manually)

#### Self-Review Output

Append a summary to the plan before presenting it:

```markdown
## Self-Review

| Check | Status | Action |
|-------|--------|--------|
| Scenario coverage | {N}/{M} covered | {auto-generated N missing triplets / "all covered"} |
| Dependency validity | {pass/fixed} | {what was fixed or "no issues"} |
| Stream balance | {pass/warning} | {suggestion or "balanced"} |
| Ordering sanity | {pass/fixed} | {what was reordered or "correct"} |
| File conflicts | {pass/warning} | {conflict details or "no conflicts"} |
```

If any check required user input (stream balance, file conflicts), ask
before finalizing. Otherwise, present the validated plan directly.

---

## Output Format

The final artifact combines all phases into a single document. Use this
exact structure for the output file:

````markdown
# Plan: {yymm.xxxx} {Feature Title}

**Date:** {YYYY-MM-DD}
**Spec:** [{yymm.xxxx}](../specs/{yymm.xxxx}_{feature_name}.md)
**Test file:** {path to test file}

## Summary
- **Streams:** {N}
- **Total triplets:** {N} ({N} RED, {N} GREEN, {N} REFACTOR)
- **Parallelizable:** Streams {A, C} can run in parallel
- **Critical path:** A1->A2->B1->B2->B3

## Execution Graph

```
A1 ─> A2 ─> A3 ─> A4 ─> A5 ─> A6
                          │
B1 ─> B2 ─> B3 ──────────┘
                   │
C1 ─> C2 ─> C3 ───┘
```

## Stream A: {Stream Name}

### A1: RED — {test_name}
**Depends:** (none)
**Scenario:** {scenario_id}
```{language}
{skipped test code}
```

### A2: GREEN — {implementation_description}
**Depends:** A1
**Target:** `{file_path}`
**Size:** [{S|M|L}]
{implementation guidance}

### A3: REFACTOR — {refactoring_description or "(none needed)"}
**Depends:** A2
{refactoring guidance or "No refactoring needed at this stage."}

...

## Stream B: {Stream Name}

...

## Desiderata Review

{desiderata table}

## Self-Review

| Check | Status | Action |
|-------|--------|--------|
| Scenario coverage | {N}/{M} | {details} |
| Dependency validity | {pass/fixed} | {details} |
| Stream balance | {pass/warning} | {details} |
| Ordering sanity | {pass/fixed} | {details} |
| File conflicts | {pass/warning} | {details} |

## Design Feedback

{Optional — only include when the spec has testability issues.}

- **Untestable behaviors** — requirements that cannot be verified without
  accessing internals (suggests interface redesign)
- **Missing specifications** — behaviors implied but not explicitly stated
- **Coupled concerns** — areas where testing one behavior requires
  unrelated setup (suggests decomposition)
````

Omit `**Spec:**` if no spec exists. Omit `**Test file:**` if not yet
determined (it may be decided during Phase 3 based on project conventions).
Omit `## Design Feedback` if there are no issues to report.

For small bug fixes (single stream, 1-3 triplets), omit the Execution
Graph visualization and the Summary's parallelization/critical-path lines.
Keep the plan proportional to the work.

## Workflow Chain

This skill sits in the middle of the blueprint workflow:

```
/spec → /plan → /run → /refactor → /commit
```

**Before `/plan`:** A spec should exist. If no spec is
found, check before generating and suggest the user create one first with
`/spec`. A plan without a spec to ground it risks solving the wrong
problem. However, if the user explicitly wants to plan from a description
or source code, proceed.

**After `/plan`:** Suggest the next step:

```
Plan generated: plans/{filename}_graph.md
Next: /run plans/{filename}_graph.md
```

`/run` will parse the execution graph and execute triplets in dependency
order, unskipping tests and implementing code one node at a time.

## Key Principles

These principles govern every decision in this skill:

1. **Behavioral, not structural.** Every RED node tests observable
   behavior. No test peeks into internals. If a refactoring changes zero
   behaviors, zero tests should break.

2. **One design decision per step.** Each triplet drives exactly one
   design decision forward. If a GREEN node requires implementing two
   unrelated things, split the triplet.

3. **Dependencies are explicit.** The graph must be parseable. Any node
   with `Depends: (none)` can execute immediately. Any node listing
   dependencies must wait for all of them.

4. **Small steps.** Beck: "If you can take smaller steps, take smaller
   steps." When in doubt, split a triplet into two. A plan with too many
   small steps is better than one with steps that are too large.

5. **The plan is a hypothesis.** The execution graph represents the best
   ordering given current understanding. During `/run`, the developer may
   discover that the order needs adjustment. That is normal — the plan
   enables structured iteration, not rigid adherence.

6. **Difficult tests signal design problems.** If a behavior is hard to
   test, report it in Design Feedback. Beck: "Difficult-to-write tests
   are the canary in the bad interface coal mine."

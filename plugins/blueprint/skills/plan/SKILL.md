---
name: plan
description: Generate an execution graph of TDD triplets (RED/GREEN/REFACTOR) with dependency tracking from a spec or source code. ALWAYS use this skill when the user wants to create a plan, generate a plan, break down work into tasks, create an implementation plan, generate an execution graph, plan a TDD approach, or figure out the order to implement things. Also trigger when the user has a spec and wants to know "what do I build first?", wants test cases generated from requirements, or asks to break a feature into implementable steps with dependencies.
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

For each stream, generate the TDD triplets as **behavioral milestones**.
Every triplet has three nodes: RED (describe a failing test), GREEN
(describe what "passing" looks like), REFACTOR (describe structural
improvement opportunity).

**The plan stays high-level.** Triplets describe *what* to test and
*what behavior* to implement — not *how*. No test code, no implementation
code. `/run` reads the codebase, discovers conventions, and writes the
actual code. This prevents cascading errors from wrong assumptions made
at planning time and gives the executing agent room to make informed
implementation decisions.

> Anthropic's harness design research found that "if the planner tried
> to specify granular technical details upfront and got something wrong,
> the errors in the spec would cascade into the downstream
> implementation. It seemed smarter to constrain the agents on the
> deliverables to be produced and let them figure out the path."

**Node ID scheme:** Stream letter + sequential number within the stream.
RED nodes are odd-numbered starting at 1, GREEN nodes follow their RED,
REFACTOR nodes follow their GREEN:

- A1 (RED), A2 (GREEN), A3 (REFACTOR)
- A4 (RED), A5 (GREEN), A6 (REFACTOR)
- B1 (RED), B2 (GREEN), B3 (REFACTOR)

#### RED Nodes — Behavioral Test Description

Each RED node describes the test to write in behavioral terms — **no
test code**. The description must be specific enough for `/run` to write
the test after reading the codebase.

Each RED node specifies:

- **Behavior under test:** What observable behavior to verify (in
  Given/When/Then or equivalent prose)
- **Key assertions:** What the test should check — expressed as expected
  outcomes, not code
- **Test type hint:** `[example]` for standard example-based tests,
  `[property]` for property-based tests (roundtrip, invariant, etc.)

**Quality criteria for RED descriptions** (from `../../references/test-desiderata.md`
and `../../references/anti-patterns.md` — read both files now):

- Describes **observable behavior**, not implementation details (AP-1)
- Specific enough to write a test from, with concrete input/output
  examples (AP-2, AP-8)
- Structure-insensitive — would survive refactoring (Desiderata #2)
- No assumptions about internal data structures, private methods, or
  specific libraries
- For async behaviors: describe command-side and query-side separately;
  assert on eventual state, not timing

#### GREEN Nodes — Expected Outcome

Each GREEN node describes what "done" looks like — **not how to build
it**. The executing agent reads the codebase and decides the
implementation approach.

Each GREEN node specifies:

- **Done when:** The observable outcome that signals completion (e.g.,
  "the RED test passes and all existing tests remain green")
- **Scope hint:** `[S]` (a few lines of change), `[M]` (file-sized
  change), `[L]` (multi-file — consider splitting the triplet)
- **Constraints** (only if critical): Boundary conditions the
  implementation must respect, e.g., "must not break the existing
  `/api/orders` contract" or "must work without adding new dependencies"

Do NOT specify target files, function names, or implementation approach.
`/run` discovers these by reading the codebase.

#### REFACTOR Nodes — Structural Improvement Opportunity

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

Use this exact format for parseability by `/run`:

````markdown
### A1: RED — reject expired coupon
**Depends:** (none)
**Scenario:** S3
**Behavior:** Given an order with items, when applying an expired coupon,
then the operation fails with a validation error and the order total
remains unchanged.
**Assertions:** Error indicates coupon is expired; total is unaffected.

### A2: GREEN — expired coupon validation
**Depends:** A1
**Done when:** The RED test passes. Applying an expired coupon returns
an error without modifying the order.
**Scope:** [S]

### A3: REFACTOR — (none needed)
**Depends:** A2
No refactoring needed at this stage.

### A4: RED — valid coupon reduces total
**Depends:** A2
**Scenario:** S5
**Behavior:** Given an order with items, when applying a valid
percentage-discount coupon, then the order total is reduced by the
discount percentage.
**Assertions:** A 10% coupon on a $10 order yields a $9 total.

### A5: GREEN — coupon discount application
**Depends:** A4
**Done when:** The RED test passes. Valid coupons reduce the order total
by their discount percentage.
**Scope:** [S]

### A6: REFACTOR — extract discount calculation
**Depends:** A5
Extract discount calculation into its own unit if the method is growing.
Only if warranted — if the code is still simple, skip this.
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

## Output Format

The final artifact combines all phases into a single document. Use this
exact structure for the output file:

````markdown
# Plan: {yymm.xxxx} {Feature Title}

**Date:** {YYYY-MM-DD}
**Spec:** [{yymm.xxxx}](../specs/{yymm.xxxx}_{feature_name}.md)

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

### A1: RED — {behavioral description}
**Depends:** (none)
**Scenario:** {scenario_id}
**Behavior:** Given {precondition}, when {action}, then {expected outcome}.
**Assertions:** {key outcomes to verify}

### A2: GREEN — {outcome description}
**Depends:** A1
**Done when:** {observable outcome that signals completion}
**Scope:** [{S|M|L}]

### A3: REFACTOR — {refactoring_description or "(none needed)"}
**Depends:** A2
{refactoring guidance or "No refactoring needed at this stage."}

...

## Stream B: {Stream Name}

...

## Design Feedback

{Optional — only include when the spec has testability issues.}

- **Untestable behaviors** — requirements that cannot be verified without
  accessing internals (suggests interface redesign)
- **Missing specifications** — behaviors implied but not explicitly stated
- **Coupled concerns** — areas where testing one behavior requires
  unrelated setup (suggests decomposition)
````

Omit `**Spec:**` if no spec exists.
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

**After `/plan`:** Before suggesting `/run`, **dispatch the `plan-evaluator`
subagent** using the `Agent` tool with `subagent_type: plan-evaluator`.
Pass the plan file path in the prompt. The evaluator has fresh context, no
sunk-cost bias, and will edit the plan directly to resolve autonomous
fixes (missing triplets, dependency issues, ordering problems). Surface
its report to the user and address any "Needs Human Input" items, then
suggest:

```
Plan generated: plans/{filename}_graph.md
Next: /run plans/{filename}_graph.md
```

`/run` will parse the execution graph and execute triplets in dependency
order — reading the codebase, writing tests, and implementing code
guided by the plan's behavioral descriptions.

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

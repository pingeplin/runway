---
name: plan
description: Generate an execution graph of behavioral slices with dependency tracking from a spec or source code. ALWAYS use this skill when the user wants to create a plan, generate a plan, break down work into tasks, create an implementation plan, generate an execution graph, plan a TDD approach, or figure out the order to implement things. Also trigger when the user has a spec and wants to know "what do I build first?", wants test cases generated from requirements, or asks to break a feature into implementable steps with dependencies.
argument-hint: [path-to-spec-or-source]
---

# Plan — Sliced Execution Graph Generator

Generate a complete execution graph of **behavioral slices** from a spec or
design document. Each slice in the graph bundles a small set of related
tests with their implementation target, with explicit dependency tracking
that enables parallel execution of independent streams.

A *slice* is a single behavioral surface — 1 to 6 acceptance scenarios that
share enough context that the same agent can write the tests, then the
implementation, in one pass. The slice — not the individual test — is the
unit of TDD discipline in this plugin: tests are batched within a slice,
written before implementation, committed once failing, then made green.

## Output Artifact

A single file written to:

```
blueprint/plans/{yymm.xxxx}_{feature_name}_graph.md
```

Create the `blueprint/plans/` directory if it does not exist.

## ID System

IDs follow arXiv-style `yymm.xxxx` format:

- `yy` — 2-digit year
- `mm` — 2-digit month
- `xxxx` — zero-padded sequential number, scoped per `yymm`

**To determine the ID:**

1. **If a spec is referenced** (provided as argument, linked
   in conversation, or discoverable in `blueprint/specs/` for the current
   feature) — **reuse its ID**. The plan and spec form a pair and must share
   the same ID for unambiguous cross-referencing.
2. **Only if no spec exists** — generate a new ID:
   1. Scan `blueprint/specs/`, `blueprint/plans/`, and `docs/designs/` for files
      matching `yymm.*` where `yymm` is the current year+month
   2. Find the highest `xxxx` across the directories
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
slices that can be developed as a coherent unit — typically organized by
component, feature area, or concern.

**How to identify streams:**

- Tests that share the same target module or class tend to group together
- Tests that share setup or domain context belong together
- Tests where one behavior is a prerequisite for another are in the same
  stream, or linked by cross-stream dependencies
- A degenerate case and its corresponding happy path belong in the same
  stream

**Build the dependency graph:**

- Within each stream: order from degenerate → happy path → edge cases
  → error handling (the TDD ordering principle)
- Across streams: identify which streams depend on behaviors established
  by other streams
- Identify parallelizable streams — streams with no cross-dependencies
  can be executed simultaneously

Present the stream structure for user review:

```markdown
## Stream Structure

### Stream A: Coupon Validation (2 slices, 7 tests)
Slices: A1 (S3, S5, S8), A2 (S12, S15)
Depends: (none) — can start immediately

### Stream B: Order Persistence (1 slice, 3 tests)
Slices: B1 (S1, S2, S4)
Depends: A1 (needs coupon validation behavior)

### Stream C: Notification Dispatch (1 slice, 2 tests)
Slices: C1 (S6, S9)
Depends: (none) — can run in parallel with A

Parallelizable: Streams A and C
Critical path: A1 → B1
```

**Scaling guidance:**

- **Small bug fix (1-3 tests):** Single stream, single slice. Skip the
  graph visualization. Keep it lightweight.
- **Single feature (4-15 tests):** 2-3 streams typical, 1-2 slices per
  stream. Brief dependency summary.
- **Large feature (15+ tests):** Multiple streams, multiple slices,
  full graph visualization, critical path analysis.

**Wait for user confirmation before proceeding to Phase 3.**

---

### Phase 3 — Slice Generation

For each stream, generate **slices** as behavioral milestones. Each slice
bundles a coherent set of tests with the implementation target they drive
out.

**The plan stays high-level.** Slices describe *what* to test and
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

**Node ID scheme:** Stream letter + sequential slice number within the
stream: `A1`, `A2`, `B1`, `C1`. There is no separate RED/GREEN/REFACTOR
node type — the slice loop (in `/run`) drives RED→GREEN internally without
needing distinct graph nodes. Refactoring happens once at the end of the
whole run via the `/refactor` skill, not per slice.

#### Slice Sizing

Each slice should bundle **1–6 acceptance scenarios** that share a
behavioral surface. Hard limits:

- **1 scenario per slice is fine** for high-risk or foundational behaviors
  where you want the smallest possible step.
- **6 scenarios per slice is the soft cap.** Beyond that, the batched
  test-writing pass loses anchoring (the writing agent starts forgetting
  earlier tests' assumptions).
- **8 scenarios is the hard cap.** A slice with 8 must split into two.

If a stream contains more behaviors than fit in one slice, create multiple
slices: `A1`, `A2`, `A3` … each with its own scenarios and its own
implementation target.

#### Slice Format

Use this exact format for parseability by `/run`:

````markdown
### A1: Coupon expiry validation
**Depends:** (none)
**Scenarios:** S3, S5
**Tests:**
- [example] Given an order with items, when applying an expired coupon,
  then the operation fails with a validation error and the order total
  remains unchanged. (S3)
- [example] Given an order with items, when applying a coupon past the
  grace period, then the operation fails with a validation error. (S3)
- [example] Given an order with items, when applying a coupon within the
  grace period, then the discount is applied normally. (S5)
**Implementation:**
- A coupon validator that rejects coupons past their expiry date,
  honoring the configured grace period.
- The order's `apply_coupon` path consults the validator before
  mutating the total.
**Done when:** All three tests pass; pre-existing tests still pass.
**Scope:** [M] (a file-sized change in the coupon module)

### A2: Coupon discount application
**Depends:** A1
**Scenarios:** S12, S15
**Tests:**
- [example] Given an order with eligible items, when applying a 10%
  percentage coupon, then the order total is reduced by 10%. (S12)
- [example] Given an order, when applying a fixed-amount coupon, then
  the order total is reduced by that amount, floored at zero. (S15)
**Implementation:**
- Discount calculator handling percentage and fixed-amount coupons,
  invoked from `apply_coupon` after validation succeeds.
**Done when:** Both tests pass; the percentage and fixed-amount paths
both reduce the total correctly.
**Scope:** [S]
````

**Each slice specifies:**

- **`Depends:`** — `(none)` for slices that can start immediately;
  otherwise the slice IDs that must complete first (e.g. `A1, B2`).
- **`Scenarios:`** — comma-separated S-IDs from the spec. Every scenario
  in the slice must appear here.
- **`Tests:`** — one bullet per test the slice will produce. Each test
  has a type hint (`[example]` or `[property]`) and a behavioral
  description in Given/When/Then prose. **No test code.** Reference the
  relevant S-IDs in parentheses at the end of each test line. Multiple
  tests may cover one scenario; one test may cover multiple scenarios.
- **`Implementation:`** — bullet list describing the implementation
  target in behavioral terms. Describe what the code must achieve, not
  the specific file, class, or function names — `/run` discovers those.
- **`Done when:`** — the observable outcome that signals the slice is
  complete. Usually "all slice tests pass and pre-existing tests still
  pass", with any slice-specific addenda.
- **`Scope:`** — `[S]` (a few lines of change), `[M]` (file-sized
  change), `[L]` (multi-file — consider splitting the slice).

**Quality criteria for test descriptions** (from
`../../references/test-desiderata.md` and `../../references/anti-patterns.md`
— read both files now):

- Describes **observable behavior**, not implementation details (AP-1)
- Specific enough to write a test from, with concrete input/output
  examples (AP-2, AP-8)
- Structure-insensitive — would survive refactoring (Desiderata #2)
- No assumptions about internal data structures, private methods, or
  specific libraries
- For async behaviors: describe command-side and query-side separately;
  assert on eventual state, not timing

#### Dependency Rules

- `(none)` for root slices that can start immediately
- Single dependency: `A1`
- Multiple dependencies: `A1, B2` (needs behaviors from two streams)
- A slice depends on every prior slice in its stream whose behavior
  it builds on (typically the immediately preceding slice — `A2`
  depends on `A1`).
- A slice may depend on slices from other streams when it needs
  cross-stream behavior.

#### Within-stream Ordering

Order slices within a stream by the TDD ordering principle:

1. Degenerate cases first — force the function signature and skeleton
2. Simplest happy path — the minimal "it works" case
3. Additional happy paths — each adds one new concept
4. Edge cases for established behaviors
5. Error handling — graceful failure modes
6. Integration-level behaviors last — combine multiple features

Each slice should drive forward exactly one cohesive behavior. If you
find yourself wanting to put two unrelated behaviors in one slice,
split it.

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
- **Total slices:** {N}
- **Total tests:** {N}
- **Parallelizable:** Streams {A, C} can run in parallel
- **Critical path:** A1 → A2 → B1 → B2

## Execution Graph

```
A1 ─> A2
       │
B1 ────┘
```

## Stream A: {Stream Name}

### A1: {slice description}
**Depends:** (none)
**Scenarios:** {S-IDs}
**Tests:**
- [{example|property}] {behavioral description} ({S-IDs})
- ...
**Implementation:**
- {what the code must achieve}
- ...
**Done when:** {observable outcome}
**Scope:** [{S|M|L}]

### A2: {slice description}
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

For small bug fixes (single stream, single slice with 1-3 tests), omit
the Execution Graph visualization and the Summary's parallelization /
critical-path lines. Keep the plan proportional to the work.

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
fixes (missing tests for declared scenarios, dependency issues, ordering
problems). Surface its report to the user and address any "Needs Human
Input" items, then suggest:

```
Plan generated: blueprint/plans/{filename}_graph.md
Next: /run blueprint/plans/{filename}_graph.md
```

`/run` will parse the slices and execute them in dependency order —
batching test writing, running a fresh-context test-batch evaluator,
committing failing tests, then implementing — guided by each slice's
behavioral descriptions.

## Key Principles

These principles govern every decision in this skill:

1. **Behavioral, not structural.** Every test description specifies
   observable behavior. No test peeks into internals. If a refactoring
   changes zero behaviors, zero tests should break.

2. **One behavioral surface per slice.** Each slice drives forward one
   cohesive behavior. If a slice requires implementing two unrelated
   things, split it.

3. **Dependencies are explicit.** The graph must be parseable. Any node
   with `Depends: (none)` can execute immediately. Any node listing
   dependencies must wait for all of them.

4. **Small slices over large.** Beck: "If you can take smaller steps,
   take smaller steps." When in doubt, split a slice. A plan with too
   many small slices is better than one with slices that are too large
   — the cap of 6 scenarios per slice exists for the same reason as
   Beck's "small steps".

5. **The plan is a hypothesis.** The execution graph represents the best
   ordering given current understanding. During `/run`, the developer may
   discover that the order needs adjustment. That is normal — the plan
   enables structured iteration, not rigid adherence.

6. **Difficult tests signal design problems.** If a behavior is hard to
   test, report it in Design Feedback. Beck: "Difficult-to-write tests
   are the canary in the bad interface coal mine."

7. **No refactor nodes in the plan.** Refactoring happens once at the
   end of the whole run via the standalone `/refactor` skill. Per-slice
   "pressure-relief" refactor nodes were dropped in v3.4 — they added
   bookkeeping without clear ROI, and the failing-test commit checkpoint
   in `/run` provides a cleaner safety net for the structure→behavior
   discipline.

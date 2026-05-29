---
name: run
description: Execute a plan's sliced execution graph — walk slices in dependency order, batching test writing and implementation per slice with a failing-test commit checkpoint between them. Verification is handled by an independent evaluator subagent after completion. ALWAYS use this skill when the user wants to run a plan, execute a plan, start implementing from a plan, implement the plan, begin the TDD cycle, execute the graph, or says anything like "let's start building" when a plan graph file exists. Also trigger when the user references a blueprint/plans/*_graph.md file and wants to begin implementation.
argument-hint: [path-to-plan-graph-file]
---

# Run

Execute a plan graph by walking its **slices** in dependency order. For
each slice, batch the slice's tests in one writing pass, verify them all
fail, commit the failing batch as a git checkpoint, implement, then run
a bounded fix loop until green. After the last slice, a `refactor-runner`
subagent cleans up the run's code (structure only, tests stay green) and
a `run-evaluator` subagent verifies the result — `/run` itself is a pure
builder and delegates both cleanup and verification to fresh-context
agents.

## When to Use

This skill sits after `/plan` and before `/refactor` in the blueprint workflow:

```
/spec → /plan → /run → /refactor → /commit
```

The full orchestrator is `/tdd`, which chains all of these.

## Inputs

The skill needs a **plan graph file**: `blueprint/plans/{yymm.xxxx}_{feature_name}_graph.md`

**Finding the input:**

- If the user provides a path as `$ARGUMENTS`, use it directly.
- If no path is provided, scan `blueprint/plans/` (and `plans/` as a fallback for pre-migration repos) for the most recently modified `*_graph.md` file and confirm with the user.
- If no graph files exist, tell the user to run `/plan` first.

## Step 1 — Parse the Graph

Read the plan graph file and build the execution model:

1. **Extract streams** (A, B, C…) and their slices (A1, A2, B1…).
2. **Parse each slice:**
   - **ID** (e.g., A1)
   - **Dependencies**: `Depends: A2, B2` or `(none)`
   - **Scenarios:** S-IDs from the paired spec
   - **Tests:** the behavioral test descriptions (prose, with `[example]` or `[property]` hint and trailing S-ID references)
   - **Implementation:** the implementation target bullets
   - **Done when** and **Scope** annotations
3. **Build the dependency DAG** and compute a topological ordering at the slice level.
4. **Identify ready slices** — those with no unmet dependencies.
5. **Check for already-completed slices** — read checkbox state from the plan file. If some slices are already checked off (from a previous interrupted run), mark them complete and adjust the ready set.

**Present the execution order to the user for confirmation:**

```
## Execution Order: {feature_name}

{N} slices ({M} tests total) across {K} streams
Critical path: {stream(s)}

Order:
  1. A1 — {slice description} ({N tests}, scenarios {S-IDs})
  2. A2 — {slice description} ({N tests}, scenarios {S-IDs})
  3. B1 — {slice description} ({N tests}, scenarios {S-IDs})
  ...

{If resuming}: Resuming from slice {X} ({Y}/{N} already complete)

Proceed? (y/n)
```

Wait for user confirmation before executing.

## Step 2 — Execute Slices

### Decide execution strategy

After parsing the graph, analyze stream independence to choose the execution strategy automatically:

1. **Count independent streams** — streams whose first slice has no cross-stream dependencies are independent at launch.
2. **Choose strategy:**
   - **1 stream, or all streams have cross-dependencies** → **Sequential**: process slices in topological order, one at a time.
   - **2+ independent streams** → **Parallel**: spawn one agent per independent stream. Each agent runs its stream's slices sequentially. When a stream depends on another stream's slice, it waits for that agent to report completion.
   - **Mixed** — some streams are independent, some depend on others → **Hybrid**: launch independent streams in parallel; dependent streams queue behind their prerequisites.

3. **Present the strategy to the user:**
   ```
   Strategy: Parallel (3 independent streams detected)
     Agent 1: Stream A (coupon validation) — 2 slices, 5 tests
     Agent 2: Stream B (shipping calc) — 1 slice, 3 tests
     Queued:  Stream C (checkout) — depends on A2, B1 — starts after both complete
   ```

**Parallel execution rules:**
- Each agent gets its own stream and walks the slice loop (below) one slice at a time within that stream.
- Agents write to different files (each stream targets different modules) — no merge conflicts.
- After all agents complete, dispatch the `test-runner` subagent (`Agent` tool, `subagent_type: test-runner`) to run the full test suite once and catch cross-stream integration issues. Keeping this run in a subagent keeps verbose framework output out of `/run`'s context — only the pass/fail summary comes back.
- If any agent escalates, pause all agents and report to the user.
- Progress tracking and plan checkbox updates still apply — each agent updates its own stream's checkboxes.

**When NOT to parallelize** (fall back to sequential even if streams look independent):
- The plan has fewer than 3 total slices (overhead not worth it)
- Multiple streams are likely to touch the same module area
- The user explicitly asks for sequential execution

### Slice Loop

For each slice ready to execute, walk these eight sub-steps in order.
Test runs in sub-steps 5, 8, and inside the fix loop stay **in-context**
— execute via `Bash` directly, not via the `test-runner` subagent. The
loop needs the raw failure output in main context to drive the next edit.
The `test-runner` subagent is reserved for verification-only runs (the
cross-stream integration check above, and the `/refactor` skill).

#### 1. Read codebase context

Before writing anything, examine:

- Existing test files relevant to this slice: naming conventions, directory structure, import patterns, test framework, helper utilities.
- The module(s) related to the behaviors under test: public APIs, data shapes, existing patterns.
- Any existing tests that exercise overlapping behavior — don't duplicate them.

Match the project's conventions exactly. If the project has no existing tests, ask the user which framework to use.

#### 2. Write the batched tests

Translate every `Tests:` bullet in the slice into executable test code, **in a single writing pass**, all in the same test file (or files, if the slice naturally spans multiple test files). All tests are written as **active** — do not use skip markers. The whole batch will fail collectively in sub-step 5.

For each test:

- Use AAA structure (Arrange / Act / Assert) with clear inline setup.
- Apply Test Desiderata priorities: Behavioral > Structure-insensitive > Readable > Specific > Deterministic > Isolated (see `../../references/test-desiderata.md`).
- Apply the anti-patterns checklist (see `../../references/anti-patterns.md`): no structure-sensitive assertions (AP-1), meaningful assertions (AP-2), no non-deterministic sources (AP-3), no copy-pasted expected values (AP-4), mocking only at external boundaries (AP-5), inline setup over shared fixtures (AP-6), organize by behavior not class (AP-7), descriptive names (AP-8).
- Name tests for the **behavior** they verify, never for the plan coordinate. `test_expired_coupon_is_rejected`, not `test_slice_A2` or `test_S3`. Slice IDs and S-IDs are build-time bookkeeping — they belong in the failing-test commit message (sub-step 5), not in test names, docstrings, or comments.
- For `[property]` type hints: use property-based testing (Hypothesis, fast-check, etc.).

This is the single batched test-writing pass for the slice — do not write tests one at a time, do not iterate against the suite here, just write the whole batch from the slice's `Tests:` bullets in one go.

#### 3. Dispatch the test-batch-evaluator subagent

Once the batch is written, **dispatch the `test-batch-evaluator` subagent** via the `Agent` tool with `subagent_type: test-batch-evaluator`. Pass:

- The path of the test file(s) the slice just wrote
- The slice ID and its `Scenarios:` line from the plan
- The path of the paired spec

The evaluator runs in a **fresh context** — it has none of the assumptions the batched writing pass accumulated. It checks:

- Every S-ID in the slice's `Scenarios:` line has at least one test in the batch
- No two tests in the batch contradict each other (e.g. same input, different expected outcome without a stated difference)
- No hallucinated APIs (every called symbol is either present in the spec or a known framework / stdlib primitive)
- AP-4 quick scan (no copy-paste expected values), AP-1 quick scan (no structure-sensitive assertions)

It returns a tight report with **must-fix** and **nice-to-have** lists. Apply every must-fix item before proceeding to sub-step 4. Note nice-to-have items in your progress output but don't block on them.

The evaluator does NOT auto-edit — the tests must remain stable across this check so the next sub-step (commit failing batch) captures a clean checkpoint.

#### 4. Verify all new tests fail

Run the project's test suite via `Bash`.

Required outcome: **every newly written test in the batch fails**, and **no pre-existing test breaks**.

- If every new test fails / errors-as-not-implemented → proceed.
- If any new test passes unexpectedly → the behavior is already implemented or the test is trivially true. Stop and ask the user:
  ```
  WARNING: {test_name} passed unexpectedly.
  This test may be trivially true or the behavior is already implemented.
  Options: (a) inspect and proceed, (b) investigate before continuing.
  ```
- If any pre-existing test broke → a dependency or isolation issue was introduced by the batch. Stop and report:
  ```
  STOP: {N} pre-existing test(s) broke when adding the slice {slice_id} batch.
  This indicates a dependency or isolation issue.
  Broken tests: {list}
  ```

Do not proceed until the user resolves either.

#### 5. Commit the failing batch

Commit just the test file(s) — not implementation, which doesn't exist yet — with a message in this format:

```
test: add failing tests for {slice short description} ({S-IDs})
```

Example: `test: add failing tests for coupon expiry validation (S3, S5)`.

This is the **failing-test commit checkpoint**. It exists for two reasons: (a) it's a git-level checkpoint inside the slice for resumability, and (b) any test edits that happen during implementation (sub-steps 6–7) will be visible in subsequent diffs, so silent test rewriting can't hide.

Use `Bash` to run `git add` on the relevant test file(s) and `git commit -m "{message}"`. Do **not** dispatch `commit-writer` here — that agent is for end-of-feature commits. The failing-test commit is short, formulaic, and tied to the slice; the calling skill writes it directly.

#### 6. Write the implementation

Translate every `Implementation:` bullet in the slice into production code. Read the codebase first to decide where the implementation belongs (file, module, naming). Implement the minimal code that satisfies the slice's `Done when:` outcome — do not gold-plate.

**Comments as you write, not as an afterthought** (full rule in General Guidelines): a docstring only where it captures purpose, a contract, or non-obvious behavior; an inline comment only for a *why* the code can't show. Never restate *what* well-named code already says, and never write a task-referential comment — no slice IDs, S-IDs, ticket numbers, or "added for the X flow". That context lives in the commit message. Getting this right here is cheaper than letting `run-evaluator` flag it later.

#### 7. Bounded fix loop (production code only)

Run the suite via `Bash`.

- All tests pass → proceed to sub-step 8.
- Some slice tests still fail → enter the fix loop:

  ```
  for attempt in 1..5:
      read the failing test output
      edit production code only
      run the suite via Bash
      if all green: break
  ```

  **Never edit the slice's tests inside this loop.** The failing-test commit from sub-step 5 froze them. If you genuinely believe a test is wrong (e.g. spec mismatch found during implementation), stop the loop and escalate to the user — do not silently rewrite the test. The Anthropic Claude Code best-practices guidance is explicit: with the failing tests committed, the model is constrained from quietly rewriting them; the user must approve any test edit by re-entering sub-step 2 (which means a new failing-test commit will follow).

- After 5 attempts still failing → escalate:
  ```
  ESCALATE: Could not make slice {slice_id} pass after 5 production-code attempts.
  Last error: {error message}
  Please review and provide guidance.
  ```

#### 8. Mark the slice complete

Update the plan file — check off this slice's checkbox so progress is durable across interruptions. Advance to the next ready slice.

## Progress Tracking

Show progress as execution proceeds:

```
[1/4 slices] Stream A starting...
[1/4 slices] A1 batch written (3 tests), evaluator: 0 must-fix, 1 nice-to-have
[1/4 slices] A1 batch fails as expected — committing failing tests
[1/4 slices] A1 implementation in progress
[1/4 slices] A1 — all tests passing, slice complete
[2/4 slices] A2 batch written (2 tests)...
```

**Resumability:** If execution is interrupted (user stops, error escalation, etc.), the plan file's checkbox state records progress at the slice level, and git records progress at the failing-test-commit level. When `/run` is invoked again on the same plan, it detects completed slices and resumes from the first incomplete slice. If a slice is mid-flight (failing-test commit present but implementation incomplete), resume at sub-step 6.

## Post-Run: Cleanup, then Evaluation (Independent Subagents)

After all slices are executed, `/run` is done building — it is a pure
builder, so it hands the finished code to two fresh-context subagents in
sequence: one cleans, one verifies. Run them in this order; the evaluator
should score a tree that has already been tidied.

### 1. Cleanup — dispatch the `refactor-runner` subagent

**Dispatch the `refactor-runner` subagent** via the `Agent` tool with
`subagent_type: refactor-runner`. Pass the plan file path and the run's
starting commit (so it can scope its diff). It invokes the `/refactor`
skill in autonomous mode — a structure-only pass over the code the run
just wrote: collapse duplication, improve names, flatten nesting, fix
comment/docstring hygiene, all while keeping every test green. This
replaces the old `/simplify` step. Because it is a separate spawned agent
with fresh context, it isn't anchored to whatever shape the builder
happened to leave behind. Surface its one-paragraph report (what changed,
any structure-sensitive tests it flagged, any behavior-change follow-ups
it left undone).

### 2. Verification — dispatch the `run-evaluator` subagent

**Dispatch the `run-evaluator` subagent** via the `Agent` tool with
`subagent_type: run-evaluator`. Pass the plan file path so the evaluator
knows which plan was just executed. It has fresh context and no sunk-cost
bias, and performs:

1. **Test suite** — run all tests, report pass/fail counts
2. **Scenario coverage** — map spec acceptance scenarios to tests (the
   full coverage matrix lives here, not in `plan-evaluator`)
3. **Desiderata Review** — score tests against Kent Beck's Test Desiderata
4. **Implementation quality** — flag stale/low-value comments and other
   code-quality issues over the run's diff (flagging only; the human decides)

This separation follows Anthropic's harness-design principle: separate the
generator from the evaluator — and here, the refactorer from both.

### 3. Recommend the next step

The autonomous cleanup already ran, so the question left for the human is
narrow: **is a human-directed `/refactor` worth it, or go straight to
`/commit`?** Don't leave this implicit. After surfacing both reports,
synthesize them into an explicit recommendation:

- **Recommend `/refactor`** when there is concrete, named signal that a
  structure-only pass can't or shouldn't make autonomously — `refactor-runner`'s
  "behavior-change follow-ups left undone", structure-sensitive tests it
  flagged, or `run-evaluator` quality flags that need a judgment call. Name the
  specific targets and the one-line reason for each, so the human can approve
  or redirect rather than re-derive them.
- **Recommend skipping to `/commit`** when both reports come back clean —
  refactor-runner reported no follow-ups and run-evaluator's verdict is green.
  Say so plainly; don't invent refactoring work to justify a step.

Format it as a short go/no-go the human can act on in one read, e.g.:

```
Recommendation: run /refactor before committing.
  • PaymentService and OrderController still share tax-rounding logic with
    subtly different rules — consolidating needs a behavior decision (refactor-runner follow-up).
  • settings.py:42 — stale docstring flagged by run-evaluator.
Otherwise the tree is green and ready to commit.
```

or:

```
Recommendation: skip /refactor — go to /commit.
Cleanup pass made 3 structure-only changes, all tests green, no flags left open.
```

The human owns the decision; `/run`'s job is to make it a one-read decision,
not a guess.

## Scaling

- **Small plan** (1 stream, 1–2 slices): Sequential execution.
- **Medium plan** (2–3 streams, 3–8 slices): Auto-parallelize independent streams.
- **Large plan** (4+ streams, 8+ slices): Auto-parallelize. If the plan has more than 12 slices, suggest breaking into phases — run the foundational streams first, verify, then run the dependent streams.

## General Guidelines

- **One batch per slice, one commit per batch.** Don't dribble tests in one at a time, and don't roll the failing-test commit into the implementation commit.
- **Test runs inside the slice loop stay in main context.** Use `Bash` directly for sub-steps 4, 7, and the fix loop. Use the `test-runner` subagent only for verification-only runs (cross-stream integration check, `/refactor` baseline / per-step / final).
- **Never modify tests inside the fix loop.** The failing-test commit is the contract. If the test is wrong, stop and ask the human; do not silently rewrite. This is the single most important safeguard added in v3.4.
- **Minimal implementation.** During implementation, write the simplest code that satisfies the slice's `Done when:` outcome. Resist the urge to implement ahead of the tests.
- **Docstrings and comments — write only what the code can't say, and keep them current.** Function and method docstrings that capture purpose, contracts, or non-obvious behavior are valuable; write them when they help and keep them tight — one or two lines, not a paragraph that re-narrates the body. Inline comments only for the *why* — a hidden constraint, a workaround, a counterintuitive invariant — never to restate *what* well-named code already shows. When the fix loop (sub-step 7) changes a function's signature, behavior, or contract, update or delete its docstring in the same edit — a stale docstring is worse than none. **No task-referential comments** — no slice IDs, S-IDs, ticket numbers, or "added for slice A2 / for the X flow". That context rots immediately and belongs in the commit message, not the source. The same goes for test names (sub-step 2): name them for behavior, not plan coordinates.
- **Parse gracefully** — the plan graph format may have minor variations in whitespace, header casing, or delimiter style. Match on semantic content (slice IDs, `Depends:` / `Scenarios:` / `Tests:` / `Implementation:` lines), not exact formatting.
- **Update the plan file** — check off slices as they complete so that progress is durable across interruptions.

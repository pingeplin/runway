---
name: tdd
description: Full TDD workflow orchestrator. Chains /spec → /plan → /run → /refactor → /commit with human approval gates. ALWAYS use this when the user wants to build a feature end-to-end with TDD, start a new feature from scratch, go through the full development workflow, or says "let's build X", "add feature X with TDD", "take me through the whole process", or "full workflow". Also trigger when the user has a spec and wants to go all the way to implementation and commit.
---

If invoked **without arguments**, display this workflow map and ask what the user wants to build:

```
Blueprint TDD Workflow (v3.4)

/spec ──→ /plan ──→ /run ──→ /refactor ──→ /commit
  │          │         │                       │
  │          │         │                       └── commit-writer subagent
  │          │         │                             (fresh-context draft)
  │          │         │
  │          │         └── Per slice:
  │          │             1. Write batched tests
  │          │             2. test-batch-evaluator subagent (fresh context)
  │          │             3. Verify all-fail, commit failing batch
  │          │             4. Implement, fix-loop, mark slice done
  │          │             After last slice → run-evaluator subagent
  │          │
  │          └── plan-evaluator subagent (GATE)
  └── spec-evaluator subagent (GATE)

Standalone: /review (any artifact, any time)
```

If invoked **with a description** (e.g., `/tdd "add coupon validation to orders"`), begin immediately at Step 1.

## Detect task size first

Before starting, assess scope and recommend the right entry point:

- **Small bug fix** — Skip /spec. Start at /plan with the description inline.
- **Single feature** — Full workflow. /spec can be lightweight (~200 words).
- **Large feature** — Break into sub-features. Run /tdd for each one.
- **Prototype / spike** — Use `/proto` instead. Explore first, formalize later.
- **Refactoring only** — Jump to /refactor directly (verify tests pass first).
- **Test review only** — Jump to /review.

State your size assessment and recommended path. Proceed unless the user overrides.

## Human decision points

The human's role is thinking clearly and quality gates:

1. **Requirements** — articulate what to build (input to /spec)
2. **Spec approval** — review the generated spec (after spec-evaluator) before /plan
3. **Plan approval** — review the slice graph (after plan-evaluator) before /run
4. **Refactoring direction** — tell the AI what structural improvements to make (input to /refactor)
5. **Final review** — verify the result before /commit stages the change

Everything else — running test-batch-evaluator, committing failing batches, running run-evaluator, drafting the final commit — is automated within the skills and their sub-agents.

## Workflow steps

### Step 1: /spec
Invoke `/spec` with the user's description. The spec skill generates a spec and dispatches `spec-evaluator` to review it.
**GATE — Present the spec summary. Ask: "Approve spec, or revise?"** Do not continue until approved.

### Step 2: /plan
Invoke `/plan` with the approved spec path. The plan skill generates a slice-based execution graph and dispatches `plan-evaluator` to review it.
**GATE — Present the execution graph. Ask: "Approve plan, or revise?"** Do not continue until approved.

### Step 3: /run
Invoke `/run` with the approved plan. `/run` analyzes the dependency graph and automatically decides whether to execute slices sequentially or in parallel (spawning one agent per independent stream). No flag needed — the graph structure determines the strategy.

For each slice, `/run` internally walks: write batched tests → dispatch `test-batch-evaluator` (fresh context) → apply must-fix → verify all-fail → commit failing batch → implement → bounded fix loop → mark slice done.

After the last slice, `/run` dispatches the `run-evaluator` subagent — an independent fresh-context agent that runs `/simplify`, the test suite, the authoritative scenario coverage matrix, and Desiderata Review. Surface its report before moving on.

### Step 4: /refactor
After /run completes, review the result for cleanup opportunities (duplication, naming, structure). If any exist, suggest `/refactor` with specific targets. If the code is already clean, skip. There is no per-slice refactor step in v3.4 — refactoring is a single pass at the end.

### Step 5: /commit
Invoke `/commit`, which dispatches the `commit-writer` subagent — a fresh-context agent that drafts the message from `git diff` alone, independent of the implementation conversation. Note: the failing-test commits emitted by `/run` per slice are separate from this final commit — `/commit` writes the feature-level message.

## Jumping to a step

If the user says "start from step N" or provides an existing artifact path (spec, plan), skip to the appropriate step. If they provide a spec path, start at Step 2. If they provide a plan path, start at Step 3.

## Step-to-skill mapping

| Step | Skill | Who decides |
|------|-------|---|
| 1 | `/spec` | AI drafts, human approves |
| 2 | `/plan` | AI drafts, human approves |
| 3 | `/run` | AI executes; run-evaluator verifies |
| 4 | `/refactor` | Human gives direction, AI applies |
| 5 | `/commit` | commit-writer drafts, human reviews/edits |
| Any time | `/review` | AI reports, human acts |

## What's new in v3.4

(For anyone returning from v3.3.x or earlier.)

- **Slices replace RED/GREEN/REFACTOR triplets in `/plan`.** Each slice
  is a small batched cycle (1–6 scenarios) with its own tests and
  implementation target.
- **`/run` now batches tests per slice** instead of writing them one at
  a time, drops the skip/unskip machinery entirely, and adds a
  failing-test commit checkpoint between writing the batch and
  implementing.
- **`test-batch-evaluator` is new** — fresh-context check after each
  batch is written, before commit. Catches intra-batch contradictions,
  hallucinated APIs, and scenario coverage gaps within the slice.
- **REFACTOR nodes in the plan graph are gone.** Refactoring is one
  pass at the end via `/refactor`.
- **Scenario coverage matrix is deduped** — `plan-evaluator` does a
  binary upstream check, `run-evaluator` owns the authoritative
  scenario↔test matrix.
- **`/proto` writes active tests** (no skip markers), aligning with
  `/run`'s convention.

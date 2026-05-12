---
name: tdd
description: Full TDD workflow orchestrator. Chains /spec → /plan → /run → /refactor → /commit with human approval gates. ALWAYS use this when the user wants to build a feature end-to-end with TDD, start a new feature from scratch, go through the full development workflow, or says "let's build X", "add feature X with TDD", "take me through the whole process", or "full workflow". Also trigger when the user has a spec and wants to go all the way to implementation and commit.
---

If invoked **without arguments**, display this workflow map and ask what the user wants to build:

```
Blueprint TDD Workflow (v3)

/spec ──→ /plan ──→ /run ──→ /refactor ──→ /commit
  │          │         │                       │
  │          │         │                       └── commit-writer subagent
  │          │         │                             (fresh-context draft)
  │          │         └── run-evaluator subagent
  │          │               (/simplify, tests, coverage, Desiderata)
  │          └── plan-evaluator subagent (GATE)
  └── spec-evaluator subagent (GATE)

Standalone: /review (any artifact, any time)
```

If invoked **with a description** (e.g., `/tdd "add coupon validation to orders"`), begin immediately at Step 1.

## Headless mode

If the arguments begin with the token `--headless` (e.g., `/tdd --headless "add coupon validation to orders"`), the workflow runs **without any human-in-the-loop pause**. Use this only when the caller has signaled they cannot answer prompts — batch evaluation harnesses, scheduled runs, or automation. The default (no `--headless`) keeps the gates and waits for human approval.

In headless mode you MUST:

1. **Propagate the flag.** Pass `--headless` through to `/spec` and `/plan` as their first argument so they honor the same rules. Do NOT strip it. (`/run`, `/refactor`, `/commit` need no flag — they have no human gates.)
2. **Skip the Step 1 and Step 2 approval gates.** Surface the spec / plan summary inline, then continue immediately without asking "Approve, or revise?".
3. **Self-resolve evaluator "Needs Human Input" items.** When the spec-evaluator or plan-evaluator subagent returns open questions, do not stop to ask. Pick the most reasonable default for each, **edit the artifact file to record your decision in-place** (replace the open question with the chosen answer in the spec/plan body, and remove it from any "Open Questions" / "Needs Human Input" section), surface a one-line note for each — `Q→A (rationale)` — and proceed. The artifact is now self-contained and `/run` can execute it.
4. **Never end your turn waiting on the user.** Headless callers exit on `end_turn`. If you stop mid-workflow asking a question, the entire chain dies. Always carry the workflow through to `/commit` (or to the first hard failure).

When in doubt about a defensible default, pick the *simpler* and *more permissive* option — headless runs are about producing an end-to-end implementation to evaluate, not about getting every design choice perfect.

## Detect task size first

Before starting, assess scope and recommend the right entry point:

- **Small bug fix** — Skip /spec. Start at /plan with the description inline.
- **Single feature** — Full workflow. /spec can be lightweight (~200 words).
- **Large feature** — Break into sub-features. Run /tdd for each one.
- **Prototype / spike** — Use `/proto` instead. Explore first, formalize later.
- **Refactoring only** — Jump to /refactor directly (verify tests pass first).
- **Test review only** — Jump to /review.

State your size assessment and recommended path. Proceed unless the user overrides.

## Workflow steps

### Step 1: /spec
Invoke `/spec` with the user's description. The spec skill generates a spec and self-reviews it.
**GATE — Present the spec summary. Ask: "Approve spec, or revise?"** Do not continue until approved. *(In headless mode: surface the summary, then proceed without pausing.)*

### Step 2: /plan
Invoke `/plan` with the approved spec path.
**GATE — Present the execution graph. Ask: "Approve plan, or revise?"** Do not continue until approved. *(In headless mode: surface the graph summary, then proceed without pausing.)*

### Step 3: /run
Invoke `/run` with the approved plan. `/run` analyzes the dependency graph and automatically decides whether to execute streams sequentially or in parallel (spawning one agent per independent stream). No flag needed — the graph structure determines the strategy. After `/run` finishes the last triplet, it dispatches the `run-evaluator` subagent — an independent fresh-context agent that runs `/simplify`, the test suite, scenario coverage check, and Desiderata Review. Surface its report before moving on.

### Step 4: /refactor
After /run completes, review the result for cleanup opportunities (duplication, naming, structure). If any exist, suggest `/refactor` with specific targets. If the code is already clean, skip.

### Step 5: /commit
Invoke `/commit`, which dispatches the `commit-writer` subagent — a fresh-context agent that drafts the message from `git diff` alone, independent of the implementation conversation. Review the draft with the user, then stage and commit.

## Jumping to a step

If the user says "start from step N" or provides an existing artifact path (spec, plan), skip to the appropriate step. If they provide a spec path, start at Step 2. If they provide a plan path, start at Step 3.

## Step-to-skill mapping

| Step | Skill |
|------|-------|
| 1 | `/spec` |
| 2 | `/plan` |
| 3 | `/run` |
| 4 | `/refactor` |
| 5 | `/commit` |
| Any time | `/review` |

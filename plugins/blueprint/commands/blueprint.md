---
name: blueprint
description: Full workflow orchestrator. Chains [/design] → /spec → ⟦any coding agent implements⟧ → /verify → /commit with human approval gates. ALWAYS use this when the user wants to build a feature end-to-end, start a new feature from scratch, go through the full development workflow, or says "let's build X", "add feature X", "take me through the whole process", or "full workflow". Also trigger when the user has a spec and wants to go all the way to a verified, committed implementation.
---

If invoked **without arguments**, display this workflow map and ask what the user wants to build:

```
Blueprint Workflow (v4.0 — producer → referee)

[/design] ──→ /spec ──→ ⟦ any coding agent implements ⟧ ──→ /verify ──→ /commit
    │           │                                              │            │
    │           │                                              │            └── commit-writer subagent
    │           │                                              │                  (fresh-context draft)
    │           │                                              │
    │           │                                              └── referee subagent (GATE, fresh context):
    │           │                                                    test suite · scenario coverage ·
    │           │                                                    anti-vacuity (thought-mutation) ·
    │           │                                                    desiderata · impl-quality flags
    │           │
    │           └── spec-evaluator subagent (GATE)
    └── design-evaluator subagent (GATE — only when /design runs)

Standalone utilities, any time:  /refactor · /review
```

If invoked **with a description** (e.g., `/blueprint "add coupon validation to orders"`), begin immediately at Step 1.

## The shape of this workflow

Blueprint **produces intent** and **referees the result**; it does not drive the implementation. You (or any coding agent — Claude Code, Codex, Cursor, a teammate) build against the spec however works best. Blueprint owns the two brackets: the contract going in (`/spec`) and the verdict coming out (`/verify`). The durable artifact is the test suite; the spec is the contract that produces it.

## Detect task size first

Before starting, assess scope and recommend the right entry point:

- **Architectural decision / approach in question** — Start at `/design`. Pick a doc type (Mini RFC, RFC, ADR, Feature Doc, SDD, PR/FAQ); approve the design before continuing to `/spec`.
- **Single feature, approach is clear** — Skip `/design`. Start at `/spec`; the spec can be lightweight (~200 words) but must still carry an interface contract, scenarios, the agent instruction, and a Definition of Done.
- **Single feature, approach is open** — Start at `/design` for a Mini RFC, then `/spec`.
- **Small bug fix** — A lightweight `/spec` (a handful of scenarios + Definition of Done) is still worth it so `/verify` has something to check. For a one-line fix, skip the ceremony and just `/verify` against the existing tests.
- **Large feature** — Break into sub-features, each with its own spec. Run `/blueprint` for each. Use `/design` if any have non-obvious approaches.
- **Prototype / spike** — Don't use blueprint. Just explore directly with your coding agent — no spec, no gate. If a decision falls out of the spike, formalize it with `/design` or `/spec` and build it for real.
- **Refactoring only** — Jump to `/refactor` directly (verify tests pass first).
- **Review only** — Jump to `/review` (single-lens audit) or `/verify` (full post-implementation gate).

**Heuristic for whether `/design` is worth running:** if the user can't yet answer "why this approach over the alternatives" with a one-sentence trade-off, `/design` is worth running. If they can, skip it and go to `/spec`.

State your size assessment and recommended path. Proceed unless the user overrides.

## Human decision points

The human's role is thinking clearly and quality gates:

1. **Problem & approach** — articulate the underlying problem (input to /design when used, or to /spec when the approach is settled)
2. **Design approval** — when /design runs, review the design doc (after design-evaluator) before /spec
3. **Spec approval** — review the generated contract (after spec-evaluator) before handing it off to implement
4. **Implementation** — build it, or hand the spec to a coding agent. This step is yours; blueprint doesn't drive it
5. **Verdict review** — read the referee's report (after /verify); decide whether to commit, send a punch list back to the implementing agent, or refactor
6. **Final review** — confirm the result before /commit stages the change

## Workflow steps

### Step 0 (optional): /design
Run `/design` only when the approach itself is in question — architectural decisions, cross-cutting changes, or any case where "why this over alternatives" doesn't have a one-sentence answer yet. The design skill drafts a doc and dispatches `design-evaluator` to review it.
**GATE — Present the design summary. Ask: "Approve design, or revise?"** Do not continue until approved. Skip this step entirely when the approach is settled.

### Step 1: /spec
Invoke `/spec` with the user's description (or, if Step 0 ran, the approved design doc path). The spec skill generates the **agent-executable contract** — interface contract, acceptance scenarios, the implementing-agent instruction, bundled test-quality principles, and a Definition of Done worded as exactly what `/verify` checks — then dispatches `spec-evaluator` to review it.
**GATE — Present the spec summary. Ask: "Approve spec, or revise?"** Do not continue until approved.

### Step 2: Implement (handoff)
Hand the approved spec to a coding agent. This can be:
- **This session** — Claude Code implements against the contract directly.
- **Another agent** — paste/route the spec (and linked design) to Codex, Cursor, a teammate, etc. The spec is self-contained for this purpose.

Blueprint does **not** prescribe how the implementation proceeds — order, cadence, and commit structure are the implementing agent's choice. Only the result is checked. There is no `/plan` step and no driven `/run`; the agent's own loop does the building.

### Step 3: /verify
When the implementation comes back, invoke `/verify` with the approved spec path (and, if available, the git ref the implementation started from). It dispatches the `referee` subagent — fresh context, treating the code as unknown-provenance — which runs the test suite, builds the scenario-coverage matrix, performs the **anti-vacuity thought-mutation check**, scores tests against the Desiderata, and flags implementation-quality issues.
**GATE — Present the referee's verdict.** If it meets the spec's Definition of Done, proceed to Step 4. If not, surface the punch list (uncovered scenarios, covered-but-vacuous scenarios with the surviving mutation, quality blockers) and send it back to the implementing agent for another pass, then re-`/verify`.

### Step 4: /commit
Invoke `/commit`, which dispatches the `commit-writer` subagent — a fresh-context agent that drafts the message from `git diff` alone, independent of the implementation conversation.

### Optional: /refactor
If `/verify` surfaced structural cleanup worth doing (or you simply want to improve structure before committing), run `/refactor` while the suite is green. It's a standalone utility, not a pipeline stage — the human gives the direction.

## Jumping to a step

If the user says "start from step N" or provides an existing artifact path, skip ahead. A design doc path → start at Step 1. A spec path → start at Step 2 (implement), or Step 3 if the implementation already exists.

## Step-to-skill mapping

| Step | Skill | Who decides |
|------|-------|---|
| 0 (optional) | `/design` | AI drafts, human approves |
| 1 | `/spec` | AI drafts, human approves |
| 2 | (any coding agent) | Human or external agent builds |
| 3 | `/verify` | referee judges, human acts on the verdict |
| 4 | `/commit` | commit-writer drafts, human reviews/edits |
| Optional | `/refactor` | Human gives direction, AI applies |
| Any time | `/review` | AI reports, human acts |

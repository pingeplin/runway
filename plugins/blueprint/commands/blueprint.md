---
name: blueprint
description: Full workflow orchestrator. Chains [/design ⟲] → /spec ⟲ → ⟦ implement ⟲ /verify ⟧ → /commit, running each stage's produce→judge→revise loop and stopping for human approval only at loop exits. ALWAYS use this when the user wants to build a feature end-to-end, start a new feature from scratch, go through the full development workflow, or says "let's build X", "add feature X", "take me through the whole process", or "full workflow". Also trigger when the user has a spec and wants to go all the way to a verified, committed implementation.
---

If invoked **without arguments**, display this workflow map and ask what the user wants to build:

```
Blueprint Workflow (producer → judge → revise, bounded at 3 rounds per stage)

/design ⟲ ──→ /spec ⟲ ──→ ⟦ implement ⟲ /verify ⟧ ──→ /commit
    │           │                        │                 └── inline, from the diff
    │           │                        └── implement loop: any coding agent builds,
    │           │                            referee judges (fresh context), punch list → next round
    │           └── spec loop: this session writes, evaluator judges
    └── design loop (only when /design runs): this session writes, evaluator judges

⟲ = the loop in references/loop.md. Human gates sit at loop exits only.
```

If invoked **with a description** (e.g., `/blueprint "add coupon validation to orders"`), begin immediately at Step 1.

## The shape of this workflow

Blueprint **produces intent** and **referees the result**; it does not prescribe how the implementation proceeds. Every stage runs the same loop from `${CLAUDE_PLUGIN_ROOT}/references/loop.md`: a producer makes the whole artifact, a fresh judge reports, the producer revises the whole artifact, up to three rounds. The human reviews once per stage, at the loop's exit. The durable artifact is the test suite; the spec is the contract that produces it.

## Detect task size first

Before starting, assess scope and recommend the right entry point:

- **Architectural decision / approach in question** — Start at `/design`. Pick a doc type (Mini RFC, RFC, ADR, Feature Doc, SDD, PR/FAQ); approve the design before continuing to `/spec`.
- **Single feature, approach is clear** — Skip `/design`. Start at `/spec`; the spec can be lightweight (~200 words) but must still carry an interface contract, scenarios, the agent instruction, and a Definition of Done.
- **Single feature, approach is open** — Start at `/design` for a Mini RFC, then `/spec`.
- **Small bug fix** — A lightweight `/spec` (a handful of scenarios + Definition of Done) is still worth it so `/verify` has something to check. For a one-line fix, skip blueprint entirely — there is no contract for `/verify` to check.
- **Large feature** — Break into sub-features, each with its own spec. Run `/blueprint` for each. Use `/design` if any have non-obvious approaches.
- **Prototype / spike** — Don't use blueprint. Just explore directly with your coding agent — no spec, no gate. If a decision falls out of the spike, formalize it with `/design` or `/spec` and build it for real.

**Heuristic for whether `/design` is worth running:** if the user can't yet answer "why this approach over the alternatives" with a one-sentence trade-off, `/design` is worth running. If they can, skip it and go to `/spec`.

State your size assessment and recommended path. Proceed unless the user overrides.

## Human decision points

Exactly three gates, each at a loop exit:

1. **Design approval** — when `/design` ran, review the design doc and its final ledger before `/spec`.
2. **Spec approval** — review the contract and its final ledger before implementation begins.
3. **Verdict review** — when the implement loop exits, read the referee's verdict and the ledger; decide whether to commit, send the remaining punch list back for more work, or stop.

Before gate 1 the human also supplies the problem: articulate what is broken, as input to `/design` (or to `/spec` when the approach is settled). Inside a loop there is no gate.

## Workflow steps

### Step 0 (optional): /design ⟲
Run `/design` only when the approach itself is in question. The skill runs the design loop: draft, dispatch `evaluator` with `references/review-design.md`, rewrite on `REVISE`, up to three rounds.
**GATE — Present the design and its ledger. Ask: "Approve design, or revise?"** Do not continue until approved. Skip this step entirely when the approach is settled.

### Step 1: /spec ⟲
Invoke `/spec` with the user's description (or, if Step 0 ran, the approved design doc path). The skill runs the spec loop: write the agent-executable contract, dispatch `evaluator` with `references/review-spec.md`, rewrite on `REVISE`, up to three rounds.
**GATE — Present the spec and its ledger. Ask: "Approve spec, or revise?"** Do not continue until approved.

### Step 2: implement ⟲ /verify
Run the implement loop from `references/loop.md`. Each round:

1. **Produce.** The implementing agent builds against the spec. By default that is **this session**; alternatively hand the spec (and linked design) to any coding agent — Codex, Cursor, a teammate. On round 2 and later, hand the implementer the handoff prompt defined in `references/loop.md` — the previous verdict plus the ledger — and work on the current working tree.
2. **Judge.** Invoke `/verify` with the spec path, the base git ref the implementation started from, and the ledger's open rows. `/verify` dispatches the referee and returns the verdict.
3. **Merge.** Turn the referee's punch list into ledger rows (one per uncovered scenario, covered-but-vacuous scenario, or quality blocker), mark rows the report no longer lists as `resolved`, and apply the stop rules: `READY` (the referee's Done) → exit; round 3 → exit; nothing resolved and nothing new → exit as stuck; otherwise next round.

Do not pause for the human between rounds. Blueprint does not prescribe how the implementer works inside a round — order, cadence, and commit structure are its own.
**GATE — Present the final verdict and ledger.** If it meets the spec's Definition of Done, proceed to Step 3. If the loop exited on the round cap or stuck, present what is still open and let the human decide.

### Step 3: /commit
Invoke `/commit`. It writes the message inline, from the diff, not from the implementation conversation.

## Jumping to a step

If the user says "start from step N" or provides an existing artifact path, skip ahead. A design doc path → start at Step 1. A spec path → start at Step 2.

## Step-to-skill mapping

| Step | Skill | Judge | Who decides |
|------|-------|-------|---|
| 0 (optional) | `/design` ⟲ | `evaluator` | AI writes and revises, human approves at exit |
| 1 | `/spec` ⟲ | `evaluator` | AI writes and revises, human approves at exit |
| 2 | implement ⟲ `/verify` | `referee` | any coding agent builds and revises, human reviews the verdict at exit |
| 3 | `/commit` | — | AI drafts, human reviews/edits |

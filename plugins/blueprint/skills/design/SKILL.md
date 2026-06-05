---
name: design
description: Write or critique a design doc, RFC, ADR, or technical proposal — anything that makes a case for a non-trivial engineering decision. Outputs to docs/designs/ directory. ALWAYS use this skill when the user wants to write, create, draft, or improve a design doc, system design document, RFC, ADR, architecture proposal, or technical decision document. Also trigger on requests to "review my design doc", "critique this draft", "document this decision", "write up our approach", "align the team on X before we build", "should we build this way", "convince me X is the right approach", or any request to argue for a non-trivial engineering decision in writing. Use this BEFORE /spec when the approach itself is in question; use /spec instead when the approach is settled and you need testable acceptance scenarios.
argument-hint: '[topic] [optional-description-or-draft-path]'
---

# Design

Write or critique a design doc. A design doc is an **argument for a decision**, not documentation of one. Its job is to expose the load-bearing trade-offs so reviewers can find the holes before code gets written. If a reader can't tell what decision is being proposed, why this option over the alternatives, and what's being given up — the doc has failed, regardless of how many sections it has.

This skill handles two distinct tasks. The mode matters; do not default to "fill in a template":

- **Writing a new doc** (work starts before the template — see Workflow A below)
- **Critiquing an existing draft** (work is finding what's missing or hand-waved — see Workflow B below)

After the doc is written, dispatch the `design-evaluator` subagent to review it. The evaluator is a separate agent with fresh context and no sunk-cost bias — it scans for the common failure modes and surfaces what genuinely needs human judgment.

## Where this fits in the blueprint pipeline

```
/design ──→ /spec ──→ ⟦ any coding agent implements ⟧ ──→ /verify ──→ /commit
   │
   │  Optional — use when the approach itself is in question.
   │  Skip and go straight to /spec when the design is settled.
```

`/design` is **upstream** of `/spec`. The two skills do different jobs:

- `/design` argues *which approach to take*. Output is an argument with alternatives, trade-offs, and a load-bearing assumption.
- `/spec` defines *the testable behavior* of the chosen approach. Output is the agent-executable contract that an implementing agent builds against and `/verify` checks.

After a design is approved, run `/spec` to translate the chosen approach into a behavioral contract.

## ID System

IDs follow arXiv-style `yymm.xxxx` format, shared across designs and specs so a feature's artifacts can be matched by ID.

- `yy` — 2-digit year
- `mm` — 2-digit month
- `xxxx` — zero-padded sequential number, scoped per `yymm`

**To determine the next ID:**

1. Scan `docs/designs/` and `.blueprint/specs/` for files matching `yymm.*` where `yymm` is the current year+month
2. Find the highest `xxxx` across both directories
3. Increment by 1
4. If no files exist for the current month, start at `0001`
5. If none of those directories exist yet, start at `yymm.0001`

## Output File

Write the document to:

```
docs/designs/{yymm.xxxx}_{topic}.md
```

Where `topic` is derived from `$ARGUMENTS` — lowercase, underscores, no special characters.

Create the `docs/designs/` directory if it does not exist.

## Workflow A — New doc (writing mode)

The most common failure mode for AI-generated design docs is producing a structurally complete doc that says nothing — every section filled in, no actual argument. The second most common failure mode, ironically, is the over-correction: asking the user a checklist of abstract questions when you had enough context to write a useful first draft.

The right default is **draft with named assumptions**, not "interview first." Drafting forces you to commit to specifics, and the assumptions you mark inline become the questions — but in a form the user can correct in seconds, not paragraphs.

### Step 1 — Read the codebase

Before writing anything, investigate:

1. Related modules and how they're structured today
2. The constraints that exist in the current system (data shapes, existing APIs, deployment model)
3. Naming conventions and architectural patterns the project uses
4. Any prior design docs in `docs/designs/` that touch the same area

This ensures the design argues from the real state of the system, not a hypothetical one.

### Step 2 — Pick the mode

#### Default: draft with named assumptions

If the user has given you enough to make a first cut, make it. Pick the most defensible interpretation of anything ambiguous, write the draft, and surface load-bearing assumptions inline as `[ASSUMPTION: …]` markers (or in a short consolidated list at the end). The user can scan, push back on the wrong ones, and the second turn produces a much better doc than four turns of interview would have.

This works because:

- A draft makes the trade-offs concrete. Abstract questions ("what's your underlying problem?") rarely surface the same insights that a draft does ("oh, this draft assumes per-API-key limits, but actually we need per-tenant").
- The user is calibrating against an artifact, not a hypothetical. People are much better at reacting to a wrong answer than at producing a right one from scratch.
- Naming the assumption is the same epistemic act as asking the question — just packaged for less friction.

Close your first-cut response with:

> **Things to confirm or correct before this goes for review:** [list of 3-7 inline assumptions, especially anything load-bearing — scope, audience, decided-vs-open, constraints, success metric].

#### Switch to interview-mode in two specific cases

Drafting becomes harmful when:

1. **The prompt is a solution dressed as a problem, with no problem evidence.** "Help me write an RFC to migrate our monolith to microservices" gives you nothing to draft against — the underlying problem (deploy speed? team coupling? scaling?) drives the entire shape of the doc, and any draft you produce will commit to a story that may be wrong. Push back on the framing first.

2. **The prompt has internal tension that needs resolving before drafting.** Example: "We've already decided X, write me an RFC." A real RFC argues for X over alternatives; if X is decided, the doc is actually an alignment doc or ADR. Drafting an RFC anyway produces performative alternatives. Surface the tension; offer to draft the right kind of doc instead.

When you do interview, ask 2-4 high-leverage questions, not a sprawling checklist. The questions worth asking, in priority order:

- **What's the underlying problem?** (Not the proposed solution; the thing that's broken in the world.)
- **Is the decision actually open, or already made?** Honest answer changes everything.
- **Who's the audience?** Approvers want different content than implementers.
- **What's the binding constraint?** Deadline, headcount, existing system, regulatory. Constraints are *why* the easy answer doesn't work.

If you're unsure which mode to use, default to **draft with assumptions** and offer the user the option to redirect.

### Step 3 — Pick the doc type by audience and decision, not by duration

Forget rules like "SDD if 1+ months." Pick by what the doc is *for*:

- **Decision-making doc (RFC, design doc, ADR)** — the doc is an argument for one approach over alternatives. Reviewers' job is to challenge the choice. Lead with the decision and the trade-off.
- **Alignment doc (feature spec, design proposal)** — the decision is mostly settled; the doc helps a team build the same thing. Lead with the user-facing behavior and the technical contract.
- **Record doc (ADR, post-decision write-up)** — the decision has been made; the doc captures *why* for future archaeology. Be terse, focus on context and constraints that future readers won't have.
- **Working-backwards doc (PR/FAQ)** — useful when the customer value is the thing in doubt. Write the press release first; if the value isn't crisp, the project may not be worth doing.

`${CLAUDE_PLUGIN_ROOT}/references/design-templates.md` has starting templates for each. If the user's organization has a named template, prefer that — local conventions win.

### Step 4 — Write the doc

Every design doc — regardless of format — needs to answer these questions in roughly this order. If a section in your draft doesn't help answer one of them, it's probably filler.

1. **What is the decision being proposed?** (TL;DR. One paragraph. A reviewer should be able to stop here and know what they're approving.)
2. **What is the problem, and what evidence shows it's real?** Numbers if you have them. Not "search is slow" — "p95 search latency is 800ms, target is <200ms, this affects 50K daily searches."
3. **What constraints shape the solution?** Deadlines, existing systems, team capacity, regulatory, political. Constraints are *why* the easy answer doesn't work.
4. **What's the proposed approach, in just enough detail to evaluate it?** Interfaces, data flow, load-bearing components. Not implementation.
5. **What alternatives were considered, and why were they rejected?** Make rejected options look defensible; explain why the chosen one wins *given the constraints*.
6. **What are the trade-offs the chosen approach accepts?** "We're accepting [X downside] in order to gain [Y]." If you can't name a downside, you haven't thought hard enough about the choice.
7. **What's the riskiest assumption, and what happens if it's wrong?** The thing that would force a rewrite. State it explicitly.
8. **How will we know it worked?** Concrete metrics with targets, not "improve performance."
9. **What's explicitly out of scope?** Bounds the conversation. Prevents scope creep mid-review.

For smaller proposals (Mini RFC), questions 1, 2, 4, 6, 8 are usually enough. For a major architectural change, expect to answer all of them plus implementation phasing, migration, rollback, and observability.

### Step 5 — Add the header

Every design doc starts with:

```markdown
# {yymm.xxxx} {Doc Title}

**Date:** {YYYY-MM-DD}
**Status:** draft
**Author:** {infer from `git config user.name` or leave blank}
**Doc type:** {RFC | Mini RFC | ADR | Feature Doc | SDD | PR/FAQ}
```

Status values: `draft` → `in-review` → `approved` → `implemented` → `superseded`.

If a downstream spec exists in `.blueprint/specs/` with the same ID, link it:

```markdown
**Implementing spec:** [yymm.xxxx](../../.blueprint/specs/{yymm.xxxx}_{feature_name}.md)
```

## Workflow B — Critique mode

If the user pastes or links a draft, do this before anything else:

1. **Read for the decision.** What is being proposed? In one sentence. If you can't find it in the first page, that's the first finding.
2. **Find the trade-off.** What is the author giving up by choosing this? If the doc reads like the chosen option is dominant on every axis, the alternatives are straw men or the trade-offs are hidden.
3. **Find the load-bearing claim.** There's usually one assumption the whole design rests on (e.g., "writes are read 100x more often," "the data fits in memory," "we'll have a 6-month migration window"). Is it stated explicitly, and is it justified?
4. **Check what's been punted.** "Open questions" and "future work" sections are where uncomfortable problems hide. Flag any open question that, if answered the wrong way, would invalidate the design.

Then give feedback as a reviewer would, prioritized: structural problems first (missing decision, missing alternatives), then specific weaknesses, then nits last. Don't rewrite the doc unless asked.

If the draft is already in `docs/designs/`, dispatch the `design-evaluator` subagent on it directly rather than reviewing it inline.

## Writing technique that matters

A few things that disproportionately separate good docs from mediocre ones:

- **Bottom line up front.** First paragraph names the decision. Don't make a reviewer scroll for the punchline.
- **State the trade-off in one sentence somewhere.** "We chose X over Y because we value [A] more than [B] given [constraint]." If you can't write that sentence, the design isn't ready.
- **Numbers beat adjectives.** "Fast" is meaningless. "p95 < 200ms" is reviewable.
- **Make the riskiest assumption visible.** A doc that admits "this all rests on the read/write ratio staying above 10:1" is more trustworthy than one that hides it.
- **Right-size the doc.** A two-paragraph proposal for a one-line index is correct; a 30-page document for the same thing is malpractice. Match weight to stakes.
- **Use code blocks for interfaces (API specs, schemas, function signatures) — not implementation.** A design doc shows the contract, not how to fulfill it. If a code block is over ~20 lines or shows internal logic, it probably belongs in the code, not the doc.
- **Prefer prose for arguments, lists for inventories.** Trade-offs are an argument; bulleting them flattens the reasoning. Components, dependencies, and risks are inventories; lists work fine.

## Common failure modes (worth checking against)

When writing or reviewing, scan for these — they're the most frequent ways design docs fail. See `${CLAUDE_PLUGIN_ROOT}/references/design-failure-modes.md` for fuller before/after examples.

- **Solution disguised as problem.** "We need to add Redis." That's a solution. The problem is upstream.
- **Straw-man alternatives.** Alternatives listed only to be dismissed. A reader can tell. Real alternatives have plausible champions.
- **Hidden trade-offs.** Every section says the chosen option wins. Real engineering choices have downsides.
- **Open questions as escape hatches.** "How will we handle X? (open question)" — if X could invalidate the design, it's not an open question, it's an unaddressed risk.
- **Vague success criteria.** "Improve performance" is not measurable. Always pin to a number with a baseline and target.
- **Scope creep mid-doc.** Doc starts about caching, ends up redesigning the data model. Either split the doc or shrink the scope.
- **Template completionism.** Every section filled in, no actual argument.

## References

Read these on demand, not eagerly:

- **`${CLAUDE_PLUGIN_ROOT}/references/design-templates.md`** — concrete starting templates for Mini RFC, RFC, ADR, Feature Doc, SDD, and PR/FAQ. Read when the user asks for a specific format or wants a structural starting point.
- **`${CLAUDE_PLUGIN_ROOT}/references/design-failure-modes.md`** — annotated examples of common design-doc failures with before/after fixes. Read when critiquing a draft or self-checking a draft you wrote.
- **`${CLAUDE_PLUGIN_ROOT}/references/design-company-practices.md`** — how Google, Uber, Amazon, Stripe, etc. approach design docs. Read when the user asks about "the Amazon way" / "PR/FAQ" / "ADRs" / similar named approaches.

## Style

Don't write a design doc that reads like it was generated. Signs that you've slipped into that mode: every section starts with the section name as a sentence ("The goal of this design is to..."), checklists where prose belongs, hedging language ("This solution may potentially..."), excessive headers for short content. Write like an engineer making a case to a colleague who will push back. Confident, specific, and willing to name what's hard.

## Next Step

After generating or substantially revising the design file, **dispatch the `design-evaluator` subagent** using the `Agent` tool with `subagent_type: design-evaluator`. Pass the design file path in the prompt. Wait for its report, surface the findings to the user, and address any "Needs Human Input" items before suggesting:

```
/spec docs/designs/{yymm.xxxx}_{topic}.md
```

`/spec` will use the design as input to generate the agent-executable contract for the chosen approach.

The full workflow chain:
```
/design → /spec → ⟦ any coding agent implements ⟧ → /verify → /commit
```

Or via the orchestrator: `/blueprint "feature name"` (which auto-detects when `/design` is worth running).

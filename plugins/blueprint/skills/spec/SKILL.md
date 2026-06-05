---
name: spec
description: Write a technical spec with structured acceptance scenarios and built-in testability review. Outputs to .blueprint/specs/ directory. ALWAYS use this skill when the user wants to write, create, or draft a technical spec, feature spec, behavioral spec, or acceptance criteria. Also trigger when the user describes a feature they want to build and needs requirements, acceptance criteria, or a written specification — even if they don't explicitly say "spec". If someone says "I want to add X to our system" and the approach is already settled, this skill should be consulted to define the testable behavior. For decision-making docs (RFCs, ADRs, design docs that argue for one approach over alternatives), use /design instead — /design runs upstream of /spec.
argument-hint: '[feature-name] [optional-description]'
---

# Spec

Write a technical spec with structured acceptance scenarios. The spec is the
**executable contract** you hand to a coding agent — any coding agent — and
say *build this*. It captures the *why* and *how* of a change as testable
behavior, and it is the single thing `/verify` checks the result against.

A spec defines the **testable behavioral contract** of a feature. If the question is "which approach should we take" rather than "what should this approach do," use `/design` first — design docs argue for a decision; specs translate a chosen decision into the contract.

The spec is the keystone of blueprint's producer→referee pipeline:

```
/design ──→ /spec ──→ ⟦ any coding agent implements ⟧ ──→ /verify ──→ /commit
              ▲                                              ▲
       the contract                                  checks against it
```

Because blueprint no longer drives the implementation step, the spec has to
carry everything the implementing agent needs and everything the referee
will check: the interface contract inherited from the design, the
acceptance scenarios, an explicit instruction to the agent, the test-quality
principles, and a Definition of Done worded as exactly what `/verify`
verifies. A spec that's merely "a list of nice-to-haves" will produce
code no one can referee.

After the spec is written, dispatch the `spec-evaluator` subagent to review it. The evaluator is a separate agent with fresh context and no sunk-cost bias — it reviews the spec for testability, fixes what it can directly in the file, and surfaces only items needing human input.

## ID System

IDs follow arXiv-style `yymm.xxxx` format:

- `yy` — 2-digit year
- `mm` — 2-digit month
- `xxxx` — zero-padded sequential number, scoped per `yymm`

**To determine the next ID:**

1. Scan `.blueprint/specs/` and `docs/designs/` for files matching `yymm.*` where `yymm` is the current year+month
2. Find the highest `xxxx` across both directories
3. Increment by 1
4. If no files exist for the current month, start at `0001`
5. If none of those directories exist yet, start at `yymm.0001`
6. **If an upstream design doc with ID `yymm.xxxx` exists in `docs/designs/`**, reuse that ID for this spec so the feature's artifacts can be matched

## Output File

Write the document to:

```
.blueprint/specs/{yymm.xxxx}_{feature_name}.md
```

Where `feature_name` is derived from `$ARGUMENTS` — lowercase, underscores, no special characters.

Create the `.blueprint/specs/` directory if it does not exist.

## Workflow

### Step 1 — Read the Codebase

Before writing anything, investigate:

1. Related modules and their structure
2. Naming conventions used in the project
3. Data models that would be affected
4. Existing APIs or interfaces the change touches
5. Current test patterns for similar code

This ensures the spec uses real file paths, function names, and data shapes — not hypothetical ones.

### Step 2 — Write the Spec

Use the template below. Omit sections that the Section Guide marks as skippable — do not include empty sections with placeholder text.

## Template

```markdown
# {yymm.xxxx} {Feature Title}

**Date:** {YYYY-MM-DD}
**Status:** draft
**Author:** {infer from `git config user.name` or leave blank}

## Context

{What is the current situation? What problem or opportunity exists? Provide enough background for a reader unfamiliar with the topic to understand why this document exists.}

## Motivation

{Why should we do this now? What happens if we don't? Include user impact, business value, or technical debt consequences.}

## Proposed Solution

{Describe the design at a level of detail appropriate for the scope.}

### Overview

{High-level summary — one or two paragraphs explaining the approach.}

### Key Components

{Break down the solution into its major parts. For each component:}

- **{Component name}** — {what it does, where it lives, key interfaces}

### Data Flow

{How data moves through the system. Use a numbered list or diagram description.}

1. {Step 1}
2. {Step 2}
3. {Step 3}

### Interface Contract

{Inherited from the design doc when one exists — the externally visible API shapes, error taxonomy, and breaking-change rules the implementing agent must honor (don't make the agent reinvent them). If there is no design doc, state the contract here. Use code blocks for signatures.}

```
{example API signature, error codes, or config snippet}
```

## Alternatives Considered

### {Alternative 1 name}

{Brief description and why it was not chosen.}

### {Alternative 2 name}

{Brief description and why it was not chosen.}

## Migration & Rollback

{If this change involves data migration, schema changes, or deployment coordination:}

### Migration Steps

1. {Step 1}
2. {Step 2}
3. {Step 3}

### Rollback Plan

{What happens if we need to revert? Can we roll back independently of data migration? Is there data loss risk?}

## Security Considerations

{Authentication, authorization, data exposure, input validation, or compliance impact.}

## Acceptance Scenarios

{Concrete behavioral scenarios that define what "done" looks like. Each scenario MUST be verifiable without knowledge of internals. These are the contract the implementing agent builds against and the baseline `/verify` checks coverage and non-vacuity against — use the structured format below.}

{Each scenario gets a sequential ID (S1, S2, ...) so `/verify` can reference them in its coverage matrix.}

### Happy Path
- **S1:** Given {precondition}, when {action}, then {expected outcome}
- **S2:** Given {precondition}, when {action}, then {expected outcome}

### Edge Cases
- **S3:** Given {boundary condition}, when {action}, then {expected outcome}
- **S4:** Given {boundary condition}, when {action}, then {expected outcome}

### Error Scenarios
- **S5:** Given {invalid state}, when {action}, then {expected error behavior}
- **S6:** Given {invalid state}, when {action}, then {expected error behavior}

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that would *fail if the behavior were wrong*. A green suite that passes for the wrong reason does not satisfy this contract — `/verify` will hunt for vacuous tests by asking, of each behavior, "what is the smallest change that breaks this, and would any test catch it?"

Implement however you work best — blueprint does not prescribe order, cadence, or commit structure. Only the result is checked. Write tests to the project's conventions and to these principles (the same ones `/verify` scores against — see `references/test-desiderata.md` and `references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects, not internals; the suite must survive refactoring.
- **Every test can fail** — no copy-pasted expected values, no asserting a constant, no tautologies (AP-2, AP-4).
- **Deterministic, isolated, readable** — inject clocks/randomness, no cross-test state, AAA structure with inline setup.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Test suite is green.
- [ ] Every acceptance scenario (S1…SN) maps to at least one test.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under the smallest break of its behavior (thought-mutation).
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale docstrings).

## Trade-offs and Limitations

- {Known limitation or trade-off 1}
- {Known limitation or trade-off 2}

## Open Questions

- [ ] {Unresolved question 1}
- [ ] {Unresolved question 2}

## References

- {Link or reference 1}
- {Link or reference 2}

```

## Section Guide

| Section | Purpose | When to skip |
|---|---|---|
| Context | Orient the reader | Never |
| Motivation | Justify the work | Never |
| Proposed Solution | The actual design | Never |
| Interface Contract | The API/error/breaking-change surface the agent must honor | No public surface (purely internal change) |
| Acceptance Scenarios | The behavioral contract the agent builds against | Never — this is what `/verify` checks |
| For the Implementing Agent | The build instruction + test-quality principles | Never — this is what makes the spec executable |
| Definition of Done | The `/verify` pass criteria, restated as a checklist | Never |
| Alternatives Considered | Show due diligence | Truly obvious solution with no alternatives |
| Trade-offs and Limitations | Honest assessment | Never |
| Migration & Rollback | Deployment safety | No migrations, schema changes, or multi-step deploys |
| Security Considerations | Threat surface | No auth, data exposure, or compliance impact |
| Open Questions | Track unknowns | All questions resolved |
| References | Link related material | No related material |

## General Guidelines

- **Be concrete** — use real file paths, function names, and data shapes from the codebase where possible
- **Right-size the doc** — a small feature (1-3 files) needs ~200-500 words; a cross-cutting change needs 1000+ words with data flow and migration details. Use the Section Guide to decide what to skip
- **Write testable requirements** — every behavior in the Proposed Solution should appear as an Acceptance Scenario. Beck's principle: scenarios describe observable behaviors (Given/When/Then), not implementation steps
- **No implementation code** — use pseudo-code or interface signatures, not copy-pasteable implementations. The spec says *what* and *what done looks like*; the implementing agent decides *how*
- **The spec must be self-contained for handoff** — an agent that has only this file (plus the linked design) should be able to build and self-check. If a scenario can't be turned into a test that fails when the behavior breaks, it isn't done being specified
- **Status values:** `draft` -> `accepted` -> `implemented` -> `superseded`
- If the user provides `$ARGUMENTS`, use it as the feature name and description context
- If no `$ARGUMENTS` are provided, ask the user for a feature name and a brief description before generating
- **If an upstream `/design` doc exists with the same ID in `docs/designs/`, link it:** `**Design doc:** [yymm.xxxx](../../docs/designs/{yymm.xxxx}_{topic}.md)` — and use its chosen approach as the starting point for the Proposed Solution

## Next Step

After generating the spec file, **dispatch the `spec-evaluator` subagent** using the `Agent` tool with `subagent_type: spec-evaluator`. Pass the spec file path in the prompt so the evaluator knows which file to review. Wait for its report, surface the findings to the user, and address any "Needs Human Input" items.

Once the spec is approved, it is ready to **hand to a coding agent** — Claude Code, Codex, Cursor, a teammate, whoever. The spec is self-contained: the agent builds against the acceptance scenarios and the "For the Implementing Agent" instruction. Blueprint does not drive that step.

When the implementation comes back, referee it:

```
/verify .blueprint/specs/{yymm.xxxx}_{feature_name}.md
```

`/verify` checks the result against this spec — coverage, non-vacuity (thought-mutation), desiderata, and implementation quality — and recommends `/commit` or returns a punch list.

The full workflow chain:
```
[/design] → /spec → ⟦ any coding agent implements ⟧ → /verify → /commit
```

`/design` is optional and runs upstream when the approach itself is in question. Or via the orchestrator: `/blueprint "feature name"` (which auto-detects whether `/design` is worth running). Standalone utilities — `/refactor`, `/review` — are available any time.

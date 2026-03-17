---
name: spec
description: Write a technical spec with structured acceptance scenarios and built-in testability review. Outputs to specs/ directory. ALWAYS use this skill when the user wants to write, create, or draft any kind of spec, design doc, technical spec, RFC, ADR, architecture document, feature spec, or technical proposal. Also trigger when the user describes a feature they want to build and needs requirements, acceptance criteria, or a written specification — even if they don't explicitly say "spec". If someone says "I want to add X to our system" and the request is complex enough to need a written plan, this skill should be consulted.
argument-hint: [feature-name] [optional-description]
---

# Spec

Write a technical spec and self-review it for testability in a single pass. Specs capture the *why* and *how* of a feature or system change before implementation begins, with structured acceptance scenarios that feed directly into `/plan`.

## ID System

IDs follow arXiv-style `yymm.xxxx` format:

- `yy` — 2-digit year
- `mm` — 2-digit month
- `xxxx` — zero-padded sequential number, scoped per `yymm`

**To determine the next ID:**

1. Scan `specs/` and `plans/` for files matching `yymm.*` where `yymm` is the current year+month
2. Find the highest `xxxx` across both directories
3. Increment by 1
4. If no files exist for the current month, start at `0001`
5. If neither directory exists yet, start at `yymm.0001`

## Output File

Write the document to:

```
specs/{yymm.xxxx}_{feature_name}.md
```

Where `feature_name` is derived from `$ARGUMENTS` — lowercase, underscores, no special characters.

Create the `specs/` directory if it does not exist.

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

### Step 3 — Self-Review Loop

After writing the spec body, review it by reading and applying `../../references/review-spec.md` (Phases 1–5: Structural Completeness, Testability Analysis, Acceptance Scenario Audit, Ambiguity and Contradiction Detection, Summary). This is not a one-shot appendix — it is a fix loop.

**Loop:**

1. Apply the spec review phases from `../../references/review-spec.md` against the spec you just wrote.
2. For each finding, decide: **can I fix this without new information from the human?**
   - **Yes** — fix it in the spec body now. Rewrite the vague requirement, add the missing edge case, restructure the implementation-coupled scenario. Then re-run the review on the updated spec.
   - **No** — the finding requires a decision, clarification, or domain knowledge only the human has. Collect it into the Self-Review section.
3. Repeat until no more autonomous fixes remain.
4. Present the spec with only the unresolvable findings in the Self-Review section.

**Examples of autonomous fixes (do not ask the human):**
- "Handles errors gracefully" → rewrite to "Returns 400 with a JSON body containing field-level validation errors"
- Missing edge case for empty input → add an acceptance scenario
- Requirement describes HOW not WHAT → rewrite as behavioral: "Users see updated totals within 1 second" instead of "Use WebSocket to push updates"
- Ambiguous language ("should", "might", "ideally") → commit to specific behavior

**Examples of findings that need the human (stop and ask):**
- Contradictory business rules that could go either way
- Scope decisions ("should this also handle X?")
- Domain-specific behavior the codebase doesn't clarify ("are expired coupons soft-deleted or hard-deleted?")
- Security/compliance trade-offs with no obvious default

When the loop stops, the Self-Review section should contain **only** items that need human input — not a laundry list of problems you could have fixed yourself.

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

### API / Interface Changes

{If applicable, describe new or modified APIs, CLI commands, config options, or public interfaces. Use code blocks for signatures.}

```
{example API signature or config snippet}
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

{Concrete behavioral scenarios that define what "done" looks like. Each scenario MUST be verifiable without knowledge of internals. These feed directly into `/plan` — use the structured format below so scenarios are parseable by downstream skills.}

{Each scenario gets a sequential ID (S1, S2, ...) so `/plan` can reference them.}

### Happy Path
- **S1:** Given {precondition}, when {action}, then {expected outcome}
- **S2:** Given {precondition}, when {action}, then {expected outcome}

### Edge Cases
- **S3:** Given {boundary condition}, when {action}, then {expected outcome}
- **S4:** Given {boundary condition}, when {action}, then {expected outcome}

### Error Scenarios
- **S5:** Given {invalid state}, when {action}, then {expected error behavior}
- **S6:** Given {invalid state}, when {action}, then {expected error behavior}

## Trade-offs and Limitations

- {Known limitation or trade-off 1}
- {Known limitation or trade-off 2}

## Open Questions

- [ ] {Unresolved question 1}
- [ ] {Unresolved question 2}

## References

- {Link or reference 1}
- {Link or reference 2}

## Self-Review

### Autonomous Fixes Applied

{List what the self-review loop fixed. Brief — just enough for the human to see what changed.}

- {e.g., "Rewrote S3 from implementation-coupled ('uses Redis cache') to behavioral ('responds within 50ms for repeated queries')"}
- {e.g., "Added S7 for empty input edge case (was missing)"}
- {e.g., "Removed hedge word 'should' in Proposed Solution — committed to specific behavior"}

*(If no fixes were needed: "All requirements were testable as written.")*

### Needs Human Input

{Only items you could NOT resolve autonomously. Each item is a question, not a statement.}

- {e.g., "S4 says expired coupons are 'rejected' — does that mean return an error, or silently ignore? This affects whether we need an error scenario."}
- {e.g., "Sections 'Proposed Solution' and 'Migration' imply different ordering for the schema change. Which takes priority?"}

*(If none: "No unresolved items. Ready for /plan.")*

### Verdict

**Overall testability:** {High / Medium / Low}

**Ready for /plan:** {Yes / Yes, after resolving the above}
```

## Section Guide

| Section | Purpose | When to skip |
|---|---|---|
| Context | Orient the reader | Never |
| Motivation | Justify the work | Never |
| Proposed Solution | The actual design | Never |
| API / Interface Changes | Surface area impact | No public API changes |
| Acceptance Scenarios | Testable behavioral contract | Never — this is the bridge to `/plan` |
| Alternatives Considered | Show due diligence | Truly obvious solution with no alternatives |
| Trade-offs and Limitations | Honest assessment | Never |
| Migration & Rollback | Deployment safety | No migrations, schema changes, or multi-step deploys |
| Security Considerations | Threat surface | No auth, data exposure, or compliance impact |
| Open Questions | Track unknowns | All questions resolved |
| References | Link related material | No related material |
| Self-Review | Testability gate | Never — always include |

## Self-Review Guidelines

The full review methodology is in `../../references/review-spec.md`. Read that file and apply its five phases during the self-review loop. The Self-Review section in the output captures only what you could NOT fix autonomously — everything else should already be fixed in the spec body.

## General Guidelines

- **Be concrete** — use real file paths, function names, and data shapes from the codebase where possible
- **Right-size the doc** — a small feature (1-3 files) needs ~200-500 words; a cross-cutting change needs 1000+ words with data flow and migration details. Use the Section Guide to decide what to skip
- **Write testable requirements** — every behavior in the Proposed Solution should appear as an Acceptance Scenario. Beck's principle: scenarios describe observable behaviors (Given/When/Then), not implementation steps
- **No implementation code** — use pseudo-code or interface signatures, not copy-pasteable implementations
- **Link to plans** — if an execution plan exists with the same ID in `plans/`, add a link: `**Execution plan:** [yymm.xxxx](../plans/{yymm.xxxx}_{feature_name}.md)`
- **Status values:** `draft` -> `accepted` -> `implemented` -> `superseded`
- If the user provides `$ARGUMENTS`, use it as the feature name and description context
- If no `$ARGUMENTS` are provided, ask the user for a feature name and a brief description before generating

## Next Step

After generating the spec, suggest:

```
/plan specs/{yymm.xxxx}_{feature_name}.md
```

This generates the execution graph — an ordered execution graph of TDD triplets derived from the acceptance scenarios.

The full workflow chain:
```
/spec → /plan → /run → /refactor → /commit
```

Or via the orchestrator: `/tdd "feature name"`

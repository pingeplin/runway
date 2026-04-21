---
name: spec
description: Write a technical spec with structured acceptance scenarios and built-in testability review. Outputs to specs/ directory. ALWAYS use this skill when the user wants to write, create, or draft any kind of spec, design doc, technical spec, RFC, ADR, architecture document, feature spec, or technical proposal. Also trigger when the user describes a feature they want to build and needs requirements, acceptance criteria, or a written specification — even if they don't explicitly say "spec". If someone says "I want to add X to our system" and the request is complex enough to need a written plan, this skill should be consulted.
argument-hint: '[feature-name] [optional-description]'
---

# Spec

Write a technical spec with structured acceptance scenarios. Specs capture the *why* and *how* of a feature or system change before implementation begins, with acceptance scenarios that feed directly into `/plan`.

After the spec is written, dispatch the `spec-evaluator` subagent to review it. The evaluator is a separate agent with fresh context and no sunk-cost bias — it reviews the spec for testability, fixes what it can directly in the file, and surfaces only items needing human input.

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

After generating the spec file, **dispatch the `spec-evaluator` subagent** using the `Agent` tool with `subagent_type: spec-evaluator`. Pass the spec file path in the prompt so the evaluator knows which file to review. Wait for its report, surface the findings to the user, and address any "Needs Human Input" items before suggesting:

```
/plan specs/{yymm.xxxx}_{feature_name}.md
```

This generates the execution graph — an ordered execution graph of TDD triplets derived from the acceptance scenarios.

The full workflow chain:
```
/spec → /plan → /run → /refactor → /commit
```

Or via the orchestrator: `/tdd "feature name"`

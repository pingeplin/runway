---
name: design-doc
description: Generate a design document in the docs/ directory. Covers motivation, proposed solution, alternatives, and open questions. Use when the user asks to write a design doc, technical spec, RFC, or architecture document for a feature or system change.
argument-hint: [feature-name] [optional-description]
---

# Design Doc Generator

Create a design document in the `docs/` directory. Design docs capture the *why* and *how* of a feature or system change before implementation begins.

## ID System

IDs follow arXiv-style `yymm.xxxx` format:

- `yy` — 2-digit year
- `mm` — 2-digit month
- `xxxx` — zero-padded sequential number, scoped per `yymm`

**To determine the next ID:**

1. Scan both `docs/` and `plans/` for files matching `yymm.*` where `yymm` is the current year+month
2. Find the highest `xxxx` across both directories
3. Increment by 1
4. If no files exist for the current month, start at `0001`

## Output File

Write the document to:

```
docs/{yymm.xxxx}_{feature_name}.md
```

Where `feature_name` is derived from `$ARGUMENTS` — lowercase, underscores, no special characters.

Create the `docs/` directory if it does not exist.

## Template

Use this exact structure:

```markdown
# {yymm.xxxx} {Feature Title}

**Date:** {YYYY-MM-DD}
**Status:** draft
**Author:** {infer from git config or leave blank}

## Context

{What is the current situation? What problem or opportunity exists? Provide enough background for a reader unfamiliar with the topic to understand why this document exists.}

## Motivation

{Why should we do this now? What happens if we don't? Include user impact, business value, or technical debt consequences.}

## Proposed Solution

{Describe the design at a level of detail appropriate for the scope. Include:}

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
| Alternatives Considered | Show due diligence | Truly obvious solution with no alternatives |
| Trade-offs and Limitations | Honest assessment | Never |
| Open Questions | Track unknowns | All questions resolved |
| References | Link related material | No related material |

## General Guidelines

- **Read the codebase first** — understand existing patterns, naming conventions, and architecture before writing the doc
- **Be concrete** — use real file paths, function names, and data shapes from the codebase where possible
- **Right-size the doc** — a small feature needs a short doc; don't pad sections for the sake of completeness
- **No implementation code** — use pseudo-code or interface signatures, not copy-pasteable implementations
- **Link to plans** — if an implementation plan exists with the same ID in `plans/`, add a link: `**Implementation plan:** [yymm.xxxx](../plans/{yymm.xxxx}_{feature_name}_checklist.md)`
- **Status values:** `draft` → `accepted` → `implemented` → `superseded` (update as the doc progresses)
- If the user provides `$ARGUMENTS`, use it as the feature name and description context

## Next Step

After generating the design doc, suggest the user create an implementation plan by running `/implementation-plan {feature-name}`. The implementation plan will automatically link back to this design doc if they share the same ID.

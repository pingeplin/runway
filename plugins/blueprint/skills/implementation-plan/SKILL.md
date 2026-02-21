---
name: implementation-plan
description: Generate an implementation plan with a progress checklist for a feature or task. Breaks work into parallelizable work streams for agent teams. Supports optional TDD mode. Use when the user asks to create a plan, implementation checklist, or task breakdown for upcoming work.
argument-hint: [feature-name] [optional-description]
---

# Implementation Plan Generator

Create an implementation plan with a progress checklist in the `plans/` directory. Plans are structured for parallel execution by an agent team.

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

Write the plan to:

```
plans/{yymm.xxxx}_{feature_name}_checklist.md
```

Where `feature_name` is derived from `$ARGUMENTS` — lowercase, underscores, no special characters.

Create the `plans/` directory if it does not exist.

## Template

Use this exact structure:

```markdown
# Plan: {yymm.xxxx} {Feature Title}

**Date:** {YYYY-MM-DD}
**Design doc:** [yymm.xxxx](../docs/{yymm.xxxx}_{feature_name}.md) *(if exists, omit if not)*
**Mode:** {standard | tdd}

## Goal

{One or two sentences describing what we are building and why.}

## Work Streams

Tasks are grouped into parallel work streams. Streams with no dependencies between them can be executed concurrently by separate agents. Dependencies across streams are marked explicitly.

### Stream 1: {name} (e.g., "Backend API", "Data layer", "Tests")
- [ ] {Task}: {file path if known} — {brief description}
- [ ] {Task}: {file path} — {description}

### Stream 2: {name}
**Depends on:** Stream 1 tasks 1-2 *(only if blocked; omit if independent)*
- [ ] {Task}: {file path} — {description}
- [ ] {Task}: {file path} — {description}

### Stream 3: {name}
- [ ] {Task}: {file path} — {description}

### Verify
**Depends on:** All streams
- [ ] Tests pass
- [ ] Manual verification
```

## TDD Mode

When the user mentions TDD, test-driven, or red-green-refactor, use TDD mode. Structure work streams around the TDD cycle:

```markdown
### Stream 1: Test scaffolding (Red)
- [ ] {Test case}: {test file path} — {what it asserts, pseudo-code only}
- [ ] {Test case}: {test file path} — {what it asserts}

### Stream 2: Implementation (Green)
**Depends on:** Stream 1
- [ ] {Component}: {file path} — {pseudo-code description, NO copy-pasteable code}
- [ ] {Component}: {file path} — {description}

### Stream 3: Refactor
**Depends on:** Stream 2
- [ ] {Improvement}: {file path} — {what to optimize}
```

**TDD constraints:**
- NO implementation code — use pseudo-code and high-level logic only
- Group test cases from simple to complex: happy path, error handling, edge cases, integration
- Each implementation task references which test(s) it satisfies

## Parallelization Guidelines

When breaking tasks into work streams:

1. **Identify independent axes** — e.g., backend vs frontend, data layer vs API layer, different modules
2. **Minimize cross-stream dependencies** — tasks within a stream are sequential; streams themselves should be parallel when possible
3. **Mark dependencies explicitly** — use `**Depends on:** Stream N task M` when one stream needs output from another
4. **Keep streams cohesive** — each stream should be a logical unit one agent can own end-to-end
5. **Shared contracts first** — if streams must agree on interfaces (types, API shapes), put those in an early unblocking task

## General Guidelines

- Keep it lightweight — the checklist IS the plan
- Each task should be concrete and actionable (not vague like "implement feature")
- Include file paths when known (e.g., `- [ ] Add handler in src/api/routes.py`)
- If a design doc exists with the same ID in `docs/`, link to it; otherwise omit the design doc line
- If the user provides `$ARGUMENTS`, use it as the feature name and description context
- Read the codebase first to understand existing patterns before generating the plan

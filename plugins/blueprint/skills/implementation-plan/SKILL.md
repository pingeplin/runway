---
name: implementation-plan
description: Generate a progress checklist for tracking implementation of a feature. Breaks work into concrete tasks with file paths, references the design doc and test cases, and includes workflow-level checkpoints (CI, refactor, final review). Use when the user asks to create a plan, implementation checklist, or task breakdown for upcoming work.
argument-hint: [feature-name] [optional-description]
---

# Implementation Plan Generator

Create a progress checklist in the `plans/` directory. The checklist tracks implementation progress from "tests written" through "human sign-off," referencing the design doc and test cases as inputs.

## When to Use

This skill sits after test generation and human review in the workflow:

```
/design-doc → /design-doc-reviewer → /test-generator (auto-chains /test-orderer) → human review → /implementation-plan → implement → CI (auto-chains /post-verification) → /refactor → CI → human review
```

The test cases define WHAT to build. This checklist tracks the progress of building it.

## ID System

IDs follow arXiv-style `yymm.xxxx` format:

- `yy` — 2-digit year
- `mm` — 2-digit month
- `xxxx` — zero-padded sequential number, scoped per `yymm`

**To determine the ID:**

1. **If a design doc is referenced** (provided as argument, linked in conversation, or discoverable in `docs/` for the current feature) — **reuse the design doc's ID**. The implementation plan and design doc form a pair and must share the same ID so they can be cross-referenced unambiguously. Scan `docs/` for a matching design doc by feature name or conversation context.
2. **Only if no design doc exists** — generate a new ID:
   1. Scan both `docs/` and `plans/` for files matching `yymm.*` where `yymm` is the current year+month
   2. Find the highest `xxxx` across both directories
   3. Increment by 1
   4. If no files exist for the current month, start at `0001`
   5. If neither `docs/` nor `plans/` directory exists yet, start at `yymm.0001`

## Output File

Write the plan to:

```
plans/{yymm.xxxx}_{feature_name}_checklist.md
```

Where `feature_name` is derived from `$ARGUMENTS` — lowercase, underscores, no special characters. If `$ARGUMENTS` is empty, infer the feature name and scope from conversation context. If there is not enough context to produce a meaningful plan, ask the user before generating.

Create the `plans/` directory if it does not exist.

## Template

Use this exact structure:

```markdown
# Plan: {yymm.xxxx} {Feature Title}

**Date:** {YYYY-MM-DD}
**Design doc:** [yymm.xxxx](../docs/{yymm.xxxx}_{feature_name}.md) *(if exists, omit if not)*
**Test cases:** {path to test file(s)} *(if exists, omit if not)*

## Goal

{One or two sentences describing what we are building and why.}

## Implementation Tasks

Tasks are grouped by area. Each task is a concrete, checkable unit of work.

### {Area 1} (e.g., "Data layer", "API", "UI")
- [ ] {Task}: {file path if known} — {brief description} `[S]`
- [ ] {Task}: {file path} — {description} `[M]`

### {Area 2}
- [ ] {Task}: {file path} — {description} `[M]`
- [ ] {Task}: {file path} — {description} `[S]`

### {Area 3}
- [ ] {Task}: {file path} — {description} `[L]`

## Workflow Checkpoints

Track progress through the full development cycle:

- [ ] **All tests pass** — run test suite, all generated test cases go green
- [ ] **CI green** — automated verification passes
- [ ] **Post-verification** — auto-runs `/post-verification` to cross-check implementation against design doc and plan
- [ ] **Refactor** — human gives direction, AI refactors (`/refactor`)
- [ ] **CI green (post-refactor)** — verify refactoring preserved behavior
- [ ] **Human review** — structural review and sign-off

## Risks & Rollback

{Optional — include when the plan involves data migration, external integrations, or breaking changes. Omit for simple features.}

- **Risk:** {e.g., "Migration may lock the users table for >30s"}
  **Mitigation:** {e.g., "Use batched migration with 1000-row chunks"}
- **Rollback:** {e.g., "Revert deploy; migration is backwards-compatible"}
```

## General Guidelines

- **Right-size the plan** — for trivial changes (single file, clear fix), produce a minimal plan with one area and skip Risks & Rollback. Reserve multi-area plans for features spanning multiple files or modules.
- Keep it lightweight — the checklist IS the plan
- Each task should be concrete and actionable (not vague like "implement feature")
- Include file paths when known (e.g., `- [ ] Add handler in src/api/routes.py`)
- **Size each task** with `[S]`, `[M]`, or `[L]` suffix — S = a few lines, M = a file-sized change, L = multi-file or requires research
- **S tasks** should take a single focused edit; **L tasks** should be broken down further if possible
- If a design doc exists with the same ID in `docs/`, link to it; otherwise omit the design doc line
- If test cases exist, link to them; otherwise omit the test cases line
- If the user provides `$ARGUMENTS`, use it as the feature name and description context
- Read the codebase first to understand existing patterns before generating the plan. Focus on files and modules directly related to the feature — read entry points, relevant tests, and type definitions rather than exhaustively exploring the entire codebase
- **If no design doc or test cases exist yet**, check before generating the plan and suggest the user create them first. The recommended workflow is `/design-doc` → `/design-doc-reviewer` → `/test-generator` → `/test-orderer` → `/implementation-plan`. A plan without tests to ground it risks solving the wrong problem.

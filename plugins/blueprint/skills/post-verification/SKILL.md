---
name: post-verification
description: Verify that the implementation fully satisfies the design doc and implementation plan. Cross-checks acceptance scenarios, key components, and plan tasks against the actual codebase. Use after implementation is complete and all tests pass.
argument-hint: [plan-or-design-doc-path]
---

# Post-Verification

Verify that the implementation fulfills all requirements from the design doc and implementation plan. This skill catches gaps between what was specified and what was actually built — before the human review step.

## When to Use

This skill sits after implementation and CI in the workflow:

```
/design-doc → /design-doc-reviewer → /test-generator → /test-orderer → human review → /implementation-plan → implement → CI → /post-verification → /refactor → CI → human review
```

Run this after all tests pass and CI is green, but **before** refactoring. The goal is to catch missing functionality early — refactoring should only happen on a complete implementation.

## Inputs

The skill needs:

1. **Design doc** — the `docs/{yymm.xxxx}_*.md` file for the feature
2. **Implementation plan** — the `plans/{yymm.xxxx}_*_checklist.md` file (same ID)
3. **The codebase** — to verify what was actually implemented

**Finding the inputs:**

- If the user provides a path as `$ARGUMENTS`, use it. Determine the ID from the filename and locate the counterpart (design doc ↔ plan) using the same ID.
- If no path is provided, check conversation context for a recently discussed feature ID.
- If still ambiguous, scan `docs/` and `plans/` for the most recently modified files and confirm with the user.

## Verification Process

### Step 1 — Gather Requirements

Read the design doc and extract:

1. **Acceptance scenarios** — every Given/When/Then from the "Acceptance Scenarios" section
2. **Key components** — every component listed in "Proposed Solution → Key Components"
3. **API / interface changes** — every new or modified interface from the design doc
4. **Data flow steps** — the numbered steps in the "Data Flow" section

Read the implementation plan and extract:

5. **Implementation tasks** — every `- [ ]` / `- [x]` task item
6. **Workflow checkpoints** — the checkpoint items

### Step 2 — Cross-Check Against Codebase

For each extracted requirement, verify it exists in the codebase:

| Requirement type | How to verify |
|---|---|
| Acceptance scenario | A corresponding test exists AND the behavior is implemented (test is not skipped) |
| Key component | The file/module/class exists at the expected location |
| API / interface change | The interface is implemented with the specified signature |
| Data flow step | The code path exists and connects the described components |
| Implementation task | The described change is present in the codebase |

**Read the actual code** — do not rely on file existence alone. Open relevant files and confirm the described behavior is implemented, not just stubbed or partially built.

### Step 3 — Check for Skipped Tests

Scan test files for any remaining skipped tests related to this feature:

- `pytest.mark.skip` / `pytest.mark.xfail`
- `it.skip` / `xit` / `test.skip` (Jest/Vitest)
- `t.Skip` (Go)
- `@Disabled` (JUnit)
- `xit` / `pending` (RSpec)

Any skipped test is a potential gap — it means a specified behavior was not implemented.

### Step 4 — Generate Report

Output a verification report in this format:

```markdown
## Post-Verification Report: {yymm.xxxx} {Feature Title}

**Design doc:** {path}
**Implementation plan:** {path}
**Date:** {YYYY-MM-DD}

### Acceptance Scenarios

| # | Scenario | Status | Evidence |
|---|----------|--------|----------|
| 1 | {Given/When/Then summary} | ✅ Verified / ❌ Missing / ⚠️ Partial | {file:line or explanation} |
| 2 | ... | ... | ... |

### Key Components

| Component | Status | Location |
|-----------|--------|----------|
| {name} | ✅ / ❌ / ⚠️ | {file path} |

### Implementation Tasks

| Task | Status |
|------|--------|
| {task description} | ✅ Done / ❌ Not done / ⚠️ Partial |

### Skipped Tests

| Test | File | Reason |
|------|------|--------|
| {test name} | {file:line} | {skip reason} |

*(If no skipped tests: "None — all tests are active.")*

### Summary

- **Total requirements:** {N}
- **Verified:** {N} ✅
- **Missing:** {N} ❌
- **Partial:** {N} ⚠️

### Action Items

{If any ❌ or ⚠️ items exist, list concrete next steps:}

1. {What needs to be implemented/fixed}
2. {What needs to be implemented/fixed}

{If all items are ✅: "All requirements verified. Ready for refactoring and human review."}
```

## Decision Logic

After generating the report:

- **All ✅** → Tell the user the implementation is complete and suggest proceeding to `/refactor`.
- **Any ❌ or ⚠️** → Present the action items and suggest the user address gaps before moving on. Do NOT proceed to refactoring with known gaps.

## General Guidelines

- **Be thorough but not pedantic** — verify substance, not wording. If the design doc says "validate email format" and the code uses a regex email check, that counts as verified.
- **Check behavior, not structure** — if the design doc describes a component called "EmailValidator" but the code achieves the same behavior through a different structure, that's fine. Flag it only if the behavior is missing.
- **Read actual code** — do not guess from file names. Open files and read the implementation.
- **Mark partial honestly** — if a feature is implemented but missing edge case handling described in the design doc, mark it as ⚠️ Partial, not ✅.
- **Update the implementation plan** — after verification, offer to update the plan's task checkboxes to reflect actual completion status.

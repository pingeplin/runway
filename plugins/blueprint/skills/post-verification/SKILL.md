---
name: post-verification
description: Verify that the implementation satisfies the design doc and implementation plan. Cross-checks acceptance scenarios, key components, data flow, and plan tasks against the actual codebase. Generates a structured gap report. Use after implementation is complete and all tests pass.
argument-hint: [plan-or-design-doc-path]
---

# Post-Verification

Verify that the implementation fulfills all requirements from the design doc and implementation plan. This skill catches gaps between what was specified and what was actually built — before the human review step.

Why this matters: without a systematic cross-check, it's easy to miss partially-implemented features, stubbed methods that were never filled in, or acceptance scenarios that have no corresponding test. Catching these gaps before refactoring prevents wasted effort refactoring incomplete code.

## When to Use

This skill sits after implementation in the workflow:

```
/design-doc → /design-doc-reviewer → /test-generator (auto-chains /test-orderer) → human review → /implementation-plan → implement (auto-chains /post-verification) → /refactor → human review
```

This skill is **auto-chained** after the implement step completes. It can also be invoked standalone. The goal is to catch missing functionality early — refactoring should only happen on a complete implementation.

**Scaling to task size:**

- **Small change (1-3 files, <5 acceptance scenarios):** Use lightweight mode — produce a brief summary with a flat checklist instead of the full tabular report. Skip the Data Flow and Implementation Tasks sections if the plan has fewer than 5 tasks.
- **Medium feature (4-10 files):** Full report, all sections.
- **Large feature (10+ files, multiple modules):** Full report. Consider splitting verification by component area if the design doc covers multiple subsystems.

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

### Phase 1 — Extract Requirements

Read the design doc and build a requirements checklist. Extract from each section:

| Design doc section | What to extract | Why it matters |
|---|---|---|
| Acceptance Scenarios | Every Given/When/Then scenario | These are the behavioral contract — the primary verification target |
| Key Components | Each named component, its purpose, and expected location | Ensures all described parts exist and are not stubbed |
| API / Interface Changes | Every function signature, parameter, and return type | Ensures the public surface area matches the spec |
| Data Flow | Each numbered step as a discrete claim about code behavior | Ensures the components are wired together, not just individually present |
| Trade-offs and Limitations | Stated constraints (e.g., "max 3 retries", "cache eviction not in v1") | Constraints are requirements too — verify limits are enforced or explicitly deferred |

Read the implementation plan and extract:

| Plan section | What to extract |
|---|---|
| Implementation Tasks | Every `- [ ]` / `- [x]` task, including its file path and description |
| Workflow Checkpoints | The checkpoint items — note which ones should already be checked |

**Output of this phase:** A numbered checklist of every requirement, grouped by source section. Present this to yourself (do not output yet) — it becomes the input for Phase 2.

### Phase 2 — Verify Each Requirement

For each requirement, **read the actual source code** and determine its status. Do not guess from file names or import statements alone.

**Verification methods by requirement type:**

**Acceptance scenarios:**
1. Search test files for a test that covers this scenario (match by behavior described, not by name)
2. Confirm the test is NOT skipped — a skipped test means the behavior is specified but not implemented
3. Read the implementation code the test exercises — confirm the behavior is actually there, not a trivial stub that happens to pass
4. Mark: Verified (test exists, active, behavior implemented), Missing (no test or no implementation), Partial (test exists but skipped, or implementation is incomplete)

**Key components:**
1. Check the file exists at the expected path
2. Open the file and verify the class/module is implemented, not just a skeleton with `raise NotImplementedError` or `pass` stubs
3. Check that the component's described purpose is fulfilled — e.g., if the design doc says "caches compiled templates," look for actual cache storage and lookup logic
4. Mark: Verified (implemented), Missing (file doesn't exist), Partial (file exists but methods are stubbed or key described behavior is absent)

**API / interface changes:**
1. Open the implementation file and locate the function/method
2. Compare the signature (parameters, types, return type) against the design doc
3. Check that the function body implements the described behavior, not just `pass` or `raise NotImplementedError`
4. Mark: Verified (signature matches and body is implemented), Missing (function doesn't exist), Partial (signature exists but body is stubbed, or signature differs from spec)

**Data flow steps:**
1. For each step like "Router calls TemplateEngine.render()", trace the call chain: open the caller file, find the line where the call happens, confirm it passes the described arguments
2. For integration steps (e.g., "Worker picks up job and calls DeliveryTracker.update_status"), verify both sides of the integration exist
3. Mark: Verified (call chain exists), Missing (call doesn't exist), Partial (call exists but passes wrong arguments or is commented out)

**Implementation tasks:**
1. Check whether the described change is present at the specified file path
2. Cross-reference with the task's `[x]` or `[ ]` status in the plan — flag any mismatch (plan says done but code doesn't reflect it, or plan says not done but code is present)

### Phase 3 — Check Test Coverage Quality

Go beyond just counting skipped tests. Assess whether the test suite actually covers the acceptance scenarios.

**3a. Find skipped tests:**

Scan test files for framework-specific skip markers:

| Framework | Patterns to search |
|---|---|
| pytest | `pytest.mark.skip`, `pytest.mark.xfail`, `@skip`, `skipIf`, `skipUnless` |
| Jest/Vitest | `it.skip`, `test.skip`, `xit`, `xtest`, `describe.skip` |
| Go | `t.Skip` |
| JUnit | `@Disabled`, `@Ignore` |
| RSpec | `xit`, `pending` |

Each skipped test is a gap — it means a specified behavior was not implemented.

**3b. Map active tests to acceptance scenarios:**

For each acceptance scenario from the design doc, identify which active test (if any) covers it. This catches a subtle gap: all tests might be unskipped, but if they don't actually cover a scenario, that scenario is unverified.

Build a mapping:
```
Scenario: "Given invalid channel, when send() is called, then ValueError is raised"
  → Covered by: test_send_with_invalid_channel_raises_value_error (tests/test_notifications.py:78)

Scenario: "Given a template rendered twice, when same template requested, then served from cache"
  → NOT COVERED by any active test
```

### Phase 4 — Detect Implementation Deviations

Look for places where the implementation intentionally or accidentally differs from the design doc. These are not necessarily gaps — they may be reasonable decisions made during implementation.

Examples:
- Design doc specifies Jinja2 for templates, but implementation uses `str.format_map` — is this intentional simplification or a TODO?
- Design doc describes async job queue, but implementation is synchronous — is this a phased rollout or a gap?
- Component exists at a different path than specified

For each deviation: note it, and flag whether it looks intentional (has a TODO comment, is documented) or accidental.

### Phase 5 — Generate Report

**For small features (fewer than 5 acceptance scenarios and fewer than 5 plan tasks), use the lightweight format:**

```markdown
## Post-Verification: {yymm.xxxx} {Feature Title}

**Design doc:** {path} | **Plan:** {path} | **Date:** {YYYY-MM-DD}

### Status: {N}/{M} requirements verified

**Gaps:**
- {requirement} — {what's missing and where to fix it}
- {requirement} — {what's missing}

**Deviations:**
- {what differs from design doc and whether it looks intentional}

**Skipped tests:** {N remaining — list them}

**Next step:** {what to do — implement gaps, or proceed to /refactor}
```

**For medium and large features, use the full format:**

```markdown
## Post-Verification Report: {yymm.xxxx} {Feature Title}

**Design doc:** {path}
**Implementation plan:** {path}
**Date:** {YYYY-MM-DD}

### Acceptance Scenarios

| # | Scenario | Status | Test | Evidence |
|---|----------|--------|------|----------|
| 1 | {Given/When/Then summary} | Verified / Missing / Partial | {test name or "none"} | {file path:line — what was checked} |
| 2 | ... | ... | ... | ... |

### Key Components

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| {name} | Verified / Missing / Partial | {file path} | {e.g., "3 of 5 methods implemented", "cache logic missing"} |

### Data Flow

| Step | Status | Evidence |
|------|--------|----------|
| {step description} | Verified / Missing | {caller file:line → callee file:line, or "call not found"} |

### Implementation Plan Tasks

| # | Task | Plan status | Code status | Match? |
|---|------|-------------|-------------|--------|
| 1 | {task} | Done/Not done | Present/Absent/Partial | Yes/No |

### Skipped Tests

| Test | File | Skip Reason |
|------|------|-------------|
| {name} | {file:line} | {reason from skip marker} |

*(If none: "All tests are active.")*

### Deviations from Design Doc

| Area | Design Doc Says | Implementation Does | Intentional? |
|------|----------------|--------------------:|--------------|
| {area} | {spec} | {reality} | {Yes — has TODO / No — looks accidental} |

*(If none: "Implementation matches design doc.")*

### Summary

- **Requirements:** {N} total — {N} verified, {N} missing, {N} partial
- **Test coverage:** {N}/{M} acceptance scenarios covered by active tests
- **Skipped tests:** {N} remaining
- **Deviations:** {N} found

### Action Items

{If any gaps exist, list concrete next steps with file paths:}

1. Implement `{method}` in `{file path}` — currently raises NotImplementedError
2. Unskip and implement `{test name}` in `{test file}` — covers "{scenario}"
3. Add test coverage for acceptance scenario #{N}: "{scenario summary}"

{If all verified: "All requirements verified. Ready for `/refactor` and human review."}
```

**Report quality checklist** (verify before outputting):
- Every Missing or Partial item has an action item with a specific file path
- Evidence column contains actual file paths and line references, not vague descriptions
- Deviations are flagged but not automatically treated as failures
- The summary is scannable — a human should understand the status in 10 seconds

## Decision Logic

After generating the report:

- **All verified, no skipped tests** — tell the user the implementation is complete and suggest proceeding to `/refactor`
- **Minor gaps (1-2 partial items, no missing)** — present the gaps and ask the user whether to address them now or proceed. Minor gaps might be intentional (e.g., "cache eviction not in v1" is a stated trade-off, not a bug)
- **Significant gaps (any missing items)** — present the action items and recommend addressing gaps before moving on. Do NOT suggest proceeding to refactoring with known missing functionality
- **Plan checkbox mismatch** — offer to update the implementation plan's task checkboxes to reflect actual completion status. Show the diff of what would change and get user confirmation before editing

## General Guidelines

- **Verify substance, not wording** — if the design doc says "validate email format" and the code uses a regex check, that counts. Focus on whether the behavior exists, not whether variable names match
- **Check behavior, not structure** — if the design doc describes "EmailValidator" but the code achieves the same validation through a utility function, the behavior is satisfied. Flag only if the behavior itself is missing
- **Read actual code** — do not infer from file names or class names. Open files, read method bodies, check for `NotImplementedError`, `pass`, `TODO`, and other stub markers
- **Mark partial honestly** — if a component exists but is missing functionality described in the design doc, mark it Partial with a specific note about what's missing. Do not round up to Verified
- **Distinguish intentional trade-offs from gaps** — the design doc's "Trade-offs and Limitations" section describes known scope boundaries. If something is listed there as out of scope for v1, note it as a known limitation, not a gap
- **Include file paths in evidence** — every verification claim should reference a specific file and ideally a line number. "The router validates channel" is vague. "`src/notifications/router.py:25` checks `channel not in SUPPORTED_CHANNELS`" is actionable
- **Don't duplicate the design doc** — the report should be a delta. Assume the reader has the design doc open. Focus on what's missing, partial, or different — not on restating what was built

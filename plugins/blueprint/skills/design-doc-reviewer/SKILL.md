---
name: design-doc-reviewer
description: Review a design document for completeness, testability, and ambiguity. Checks that acceptance scenarios are behavioral and verifiable, flags missing edge cases, and identifies requirements that will be hard to test. Uses Kent Beck's Test Desiderata principles to evaluate testability before any code is written. Use when the user asks to review, check, or audit a design doc.
argument-hint: [path-to-design-doc]
---

# Design Doc Reviewer

Review a design document for completeness, testability, and clarity — catching problems before they propagate to tests and implementation.

## Workflow

### Phase 1 — Structural Completeness

Check the design doc against the standard template sections. Report missing or empty sections:

| Section | Present | Assessment |
|---------|:-------:|------------|
| Context | ✅/❌ | |
| Motivation | ✅/❌ | |
| Proposed Solution | ✅/❌ | |
| Acceptance Scenarios | ✅/❌ | |
| Alternatives Considered | ✅/❌ | |
| Trade-offs and Limitations | ✅/❌ | |
| Open Questions | ✅/❌ | |

If the doc uses a non-standard structure, adapt — don't penalize reasonable variations.

### Phase 2 — Testability Analysis

This is the highest-value phase. For each requirement or behavior described in the doc, evaluate whether it can be tested using Beck's behavioral testing principles.

**For each requirement, ask:**

1. **Is it behavioral?** — Does it describe WHAT the system does (observable output/state change), or HOW it works (implementation detail)?
   - ✅ "Returns a 404 when the resource doesn't exist"
   - ❌ "Uses a HashMap for O(1) lookup" (implementation detail, not testable behavior)

2. **Is it specific enough to write a test?** — Can you derive a Given/When/Then scenario from it?
   - ✅ "Expired coupons are rejected with a validation error"
   - ❌ "Handles errors gracefully" (too vague — which errors? what's graceful?)

3. **Is it structure-insensitive?** — Can you verify it without knowing the internal architecture?
   - ✅ "Search returns results ranked by relevance"
   - ❌ "The cache is invalidated when data changes" (requires knowing cache exists)

**Output a testability scorecard:**

```
## Testability Assessment

### Fully Testable Requirements
- [Requirement]: can be verified via [approach]

### Needs Clarification (vague or ambiguous)
- [Requirement]: unclear because [reason]. Suggest: [specific question]

### Implementation-Coupled (rewrite needed)
- [Requirement]: describes HOW not WHAT. Suggest rewriting as: [behavioral version]

### Untestable (missing interface)
- [Requirement]: cannot be verified without accessing internals. Consider: [interface suggestion]
```

### Phase 3 — Acceptance Scenario Audit

If the doc includes Acceptance Scenarios, audit them:

1. **Coverage check** — Map each behavior from Proposed Solution to at least one scenario. Flag behaviors without scenarios.

2. **Scenario quality** — Each scenario should follow Given/When/Then and describe observable behavior:
   - ✅ `Given an expired coupon, when applied to an order, then the order total is unchanged and an error is returned`
   - ❌ `Given an expired coupon, when applied, then the system calls validateCoupon()` (structure-sensitive)

3. **Missing edge cases** — Check for common gaps:
   - Empty/null/missing inputs
   - Boundary values (0, 1, max)
   - Concurrent operations
   - Permission/authorization boundaries
   - Timeout and failure modes
   - Unicode / special characters (where applicable)

4. **Redundant scenarios** — Flag scenarios that test the same behavior with trivially different inputs.

If no Acceptance Scenarios section exists, flag this as a critical gap and suggest the user add one before proceeding to test generation.

### Phase 4 — Ambiguity and Contradiction Detection

Scan for:

- **Ambiguous language** — "should", "might", "ideally", "as appropriate", "etc." — these create undefined behavior that leads to undertested code
- **Contradictions** — Two sections that imply different behavior for the same scenario
- **Implicit requirements** — Behaviors implied by the design but never stated (e.g., the doc describes creation but never mentions what happens on duplicate creation)
- **Missing error handling** — Happy path is described but failure modes are not

### Phase 5 — Summary and Recommendations

```
## Design Doc Review Summary

**Document:** {doc title and ID}
**Overall testability:** High / Medium / Low

### Critical Issues (block test generation)
- [ ] {Issue — what to fix and why}

### Improvements (strengthen the doc)
- [ ] {Suggestion — what to add or clarify}

### Ready for Test Generation
{Yes / No — with conditions if No}
```

## Finding the Design Doc

If `$ARGUMENTS` contains a file path, read that file. Otherwise:

1. Check `docs/` for the most recently modified `.md` file
2. If the conversation contains a design doc in a previous message, use that
3. Ask the user which doc to review

## Relationship to Other Skills

This skill sits between `/design-doc` (creation) and `/test-generator` (test creation) in the workflow:

```
/design-doc → /design-doc-reviewer → /test-generator
```

The review ensures the design doc is testable BEFORE tests are generated, avoiding wasted effort on vague or implementation-coupled requirements.

## Handling Non-Standard Docs

Not all design docs follow the blueprint template. For external or legacy docs:

- Focus on Phases 2-4 (testability, scenarios, ambiguity) which apply universally
- Skip Phase 1 structural checks or adapt them to the doc's own structure
- Still recommend adding Acceptance Scenarios if missing — they're the critical bridge to test generation

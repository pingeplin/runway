# Spec Review Methodology

Review a technical spec for structural completeness, testability, and clarity. Apply these phases in order.

## Phase 1 — Structural Completeness

Check the spec against standard template sections (Context, Motivation, Proposed Solution, Acceptance Scenarios, Alternatives Considered, Trade-offs and Limitations, Open Questions, Self-Review). Report a table of present/missing sections with assessment notes. If the spec uses a non-standard structure, adapt — focus on content presence, not heading names.

## Phase 2 — Testability Analysis

The highest-value phase. For each requirement or behavior in the spec, evaluate whether it can be tested using Beck's behavioral testing principles.

**For each requirement, ask:**

1. **Is it behavioral?** Does it describe WHAT the system does (observable output/state change), or HOW it works (implementation detail)?
   - Good: "Returns a 404 when the resource doesn't exist"
   - Bad: "Uses a HashMap for O(1) lookup" (implementation detail, not testable behavior)

2. **Is it specific enough to write a test?** Can you derive a Given/When/Then scenario from it?
   - Good: "Expired coupons are rejected with a validation error"
   - Bad: "Handles errors gracefully" (too vague — which errors? what's graceful?)

3. **Is it structure-insensitive?** Can you verify it without knowing the internal architecture?
   - Good: "Search returns results ranked by relevance"
   - Bad: "The cache is invalidated when data changes" (requires knowing cache exists)

**Output a testability scorecard:**

```
#### Fully Testable Requirements
- [Requirement]: can be verified via [approach]

#### Needs Clarification (vague or ambiguous)
- [Requirement]: unclear because [reason]. Suggest: [specific question]

#### Implementation-Coupled (rewrite needed)
- [Requirement]: describes HOW not WHAT. Suggest rewriting as: [behavioral version]

#### Untestable (missing interface)
- [Requirement]: cannot be verified without accessing internals. Consider: [interface suggestion]
```

## Phase 3 — Acceptance Scenario Audit

If the spec includes Acceptance Scenarios, audit them:

1. **Coverage check** — Map each behavior from Proposed Solution to at least one scenario. Flag behaviors without scenarios.
2. **Scenario quality** — Each scenario should follow Given/When/Then and describe observable behavior. Flag scenarios that assert implementation details (method calls, internal state, call order).
3. **Missing edge cases** — Check for common gaps:
   - Empty/null/missing inputs
   - Boundary values (0, 1, max)
   - Concurrent operations
   - Permission/authorization boundaries
   - Timeout and failure modes
   - Unicode / special characters (where applicable)
4. **Redundant scenarios** — Flag scenarios that test the same behavior with trivially different inputs.

If no Acceptance Scenarios section exists, flag this as a critical gap.

## Phase 4 — Ambiguity and Contradiction Detection

Scan for:

- **Ambiguous language** — "should", "might", "ideally", "as appropriate", "etc." — these create undefined behavior that leads to undertested code
- **Contradictions** — Two sections that imply different behavior for the same scenario
- **Implicit requirements** — Behaviors implied by the design but never stated (e.g., creation described but duplicate creation unaddressed)
- **Missing error handling** — Happy path described but failure modes absent

## Phase 5 — Spec Summary

Output: overall testability (High/Medium/Low), critical issues blocking downstream work, improvement suggestions, and a Ready for /plan verdict (Yes/No with conditions).

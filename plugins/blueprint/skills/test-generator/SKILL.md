---
name: test-generator
description: >
  Generate executable test cases from design documents, guided by Kent Beck's
  Test Desiderata and Canon TDD principles. Use this skill whenever the user
  provides a design doc, RFC, ADR, technical spec, or feature description and
  wants test cases, test plans, or test code generated from it. Also trigger
  when the user says "write tests for this design", "generate test cases",
  "review my design with tests", "what should I test", or references
  design-doc-to-test workflows. This skill works for any programming language.
---

# Test Generator

Generate high-quality, executable test cases from design documents using
Kent Beck's testing philosophy.

## When to Use

- User provides a design doc (Markdown, pasted text, Confluence export) and
  wants test cases derived from it.
- User asks "what should I test?" after describing a feature or system change.
- User wants to review a design through the lens of testability.

## Workflow

Follow these steps in order. Do NOT skip the analysis phase.

### Phase 1 — Behavioral Analysis (Beck's "Test List")

Read the design doc and extract:

1. **Behavioral requirements** — What the system should DO (not how it's built).
   Ask: "If I were an observer with no knowledge of internals, what behaviors
   would I expect?"
2. **API contracts / interfaces** — Input/output boundaries, request/response
   shapes, function signatures.
3. **State transitions** — How entities change state and under what conditions.
4. **Error scenarios** — What can go wrong? Timeouts, invalid input, missing
   data, permission failures, race conditions.
5. **Edge cases** — Boundary values, empty collections, maximum sizes, unicode,
   concurrent access.
6. **Invariants** — Things that must ALWAYS be true regardless of code path.

Present this analysis to the user as a **Test List** (Beck's Canon TDD Step 1)
before writing any code. Format:

```
## Test List

### [Feature/Component Name]

**Happy Path**
- [ ] Given X, when Y, then Z
- [ ] ...

**Edge Cases**
- [ ] Given empty input, when Y, then Z
- [ ] ...

**Error Scenarios**
- [ ] Given X, when service times out, then Z
- [ ] ...

**Invariants**
- [ ] After any operation, X must remain true
- [ ] ...
```

> **Key principle from Beck:** "This is analysis, but behavioral analysis.
> You're thinking of all the different cases in which the behavior change
> should work. Mistake: mixing in implementation design decisions. Chill."

Wait for user confirmation before proceeding to Phase 2.

### Phase 2 — Test Code Generation

After user approves (or adjusts) the Test List, generate executable test code.

**Language detection:** Ask the user which language/framework to use if not
already clear from context. Support any language — common combos include
pytest, Jest/Vitest, Go testing, JUnit, RSpec, etc.

For each test, apply the **Test Desiderata checklist** from
`references/test-desiderata.md`. Read that file now for the full checklist.

**Code structure per test:**

```
1. ARRANGE — Set up the scenario (minimal, inline fixtures preferred)
2. ACT     — Invoke the behavior under test
3. ASSERT  — Verify the expected outcome
```

**Naming convention:** Test names should read as behavioral specifications:

```
test_[action]_[scenario]_[expected_outcome]
# Example: test_create_order_with_expired_coupon_returns_validation_error
```

### Phase 3 — Desiderata Self-Review

After generating tests, perform a self-review. For each test, briefly annotate
which Desiderata properties it satisfies and any deliberate trade-offs.

Output a summary table:

```
| Test Name | Behavioral | Struct-Insensitive | Deterministic | Specific | Readable | Trade-off |
|-----------|:---:|:---:|:---:|:---:|:---:|-----------|
| test_... | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| test_... | ✅ | ⚠️ | ✅ | ✅ | ✅ | Uses mock for external API |
```

Flag any test scoring ⚠️ on **Behavioral** or **Structure-insensitive** —
these are the two properties Beck emphasizes most.

### Phase 4 — Design Feedback (Optional)

If the design doc has testability issues, report them:

- **Untestable behaviors** — Requirements that can't be verified without
  accessing internals (suggests interface redesign).
- **Missing specifications** — Behaviors implied but not explicitly stated.
- **Coupled concerns** — Areas where testing one behavior requires setting up
  unrelated state (suggests decomposition).

This feedback loop is one of the highest-value outputs of the skill — Beck
noted that difficult-to-write tests are "the canary in the bad interface
coal mine."

## Anti-Patterns to Avoid

Read `references/anti-patterns.md` for the full list. Key ones:

- **NO structure-sensitive tests.** Never assert internal method calls,
  private state, or execution order unless the design doc explicitly
  specifies ordering as a requirement.
- **NO copy-paste assertions.** Never copy computed values into expected
  values. Always derive expected values independently.
- **NO mocking without justification.** Each mock must be justified by a
  specific boundary (network, filesystem, clock, randomness). Excessive
  mocking is a structure-sensitivity nightmare.
- **NO test-per-method.** Tests map to BEHAVIORS, not to methods or classes.
  One behavior may span multiple methods; one method may have multiple
  behaviors.

## Output Format

Deliver as a single executable test file (or multiple if the design doc
covers distinct modules). Include:

1. Clear section comments grouping tests by Test List category
2. Minimal but sufficient fixtures/factories
3. The Desiderata summary table as a comment block at the end of the file

If the user's project structure is known, match their existing test
conventions (file location, naming, import style).

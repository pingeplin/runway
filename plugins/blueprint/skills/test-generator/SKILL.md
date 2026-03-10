---
name: test-generator
description: Generate executable test cases from design documents, source code, or feature descriptions using Kent Beck's Test Desiderata and Canon TDD principles. Applies to design docs, RFCs, ADRs, technical specs, or existing code. Works for any programming language.
argument-hint: [path-to-design-doc-or-source]
---

# Test Generator

Generate high-quality, executable test cases from design documents using
Kent Beck's testing philosophy. After generating tests, this skill
automatically chains to `/test-orderer` to produce the implementation
sequence — so this skill focuses on **what to test**, not **what order
to implement in**.

## Workflow

Follow these steps in order. If the user already provides a test list or
explicitly asks to skip analysis, begin at Phase 2.

### Phase 1 — Behavioral Analysis (Beck's "Test List")

Read the design doc (or source code — see notes below) and extract:

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
1. [ ] Given X, when Y, then Z
2. [ ] ...

**Edge Cases**
3. [ ] Given empty input, when Y, then Z
4. [ ] ...

**Error Scenarios**
5. [ ] Given X, when service times out, then Z
6. [ ] ...

**Invariants**
7. [ ] After any operation, X must remain true
8. [ ] ...
```

Number tests sequentially across all categories for easy reference. Group
by behavior type (happy path, edge cases, error scenarios, invariants) —
this is a logical grouping for review, not an implementation order.
Implementation ordering is handled by `/test-orderer` after code generation.

> **Key principle from Beck:** "This is analysis, but behavioral analysis.
> You're thinking of all the different cases in which the behavior change
> should work. Mistake: mixing in implementation design decisions. Chill."

**Property-based test candidates:** While building the Test List, identify
behaviors that are best expressed as properties rather than individual examples:

- Invariants (e.g., "balance never goes negative")
- Roundtrip properties (e.g., "encode then decode returns original")
- Commutativity / associativity of operations
- "No matter what valid input, X always holds"

Mark these with `[property]` in the Test List. They'll be implemented using
the project's property-based testing library (Hypothesis, fast-check, etc.)
in Phase 2.

**Vague or incomplete design docs:** If the design doc lacks sufficient detail
to extract behavioral requirements (e.g., a one-paragraph idea with no
interfaces defined), ask the user clarifying questions about expected
inputs/outputs, error handling, and key behaviors before building the Test List.

**Source code instead of a design doc:** If the user provides source code rather
than a design doc, extract behaviors from the code's public API, docstrings,
and usage patterns, then proceed with the same workflow.

Wait for user confirmation before proceeding to Phase 2.

### Phase 2 — Test Code Generation

After user approves (or adjusts) the Test List, generate executable test code.

**Discover existing conventions:** Before generating tests, examine existing
test files in the project to identify naming conventions, directory structure,
import patterns, and test framework. Match these conventions in generated code.

**Language detection:** If the project has no existing tests, ask the user which
language/framework to use if not already clear from context. Support any
language — common combos include pytest, Jest/Vitest, Go testing, JUnit,
RSpec, etc.

For each test, apply the **Test Desiderata checklist** from
`../../references/test-desiderata.md`. Read that file now for the full checklist.

**All tests are generated as skipped.** Every test must use the framework's
skip mechanism. The skip reason should describe the behavior being tested,
not an implementation order — ordering is handled downstream by
`/test-orderer`.

Skip mechanism by framework:

| Framework | Skip syntax |
|-----------|------------|
| pytest | `@pytest.mark.skip(reason="...")` |
| Jest/Vitest | `it.skip("...", () => { ... })` or `xit("...", ...)` |
| Go testing | `t.Skip("...")` |
| JUnit | `@Disabled("...")` |
| RSpec | `xit "..." do ... end` or `pending("...")` |

The skip reason should be a concise description of the behavior:
```
@pytest.mark.skip(reason="registration with valid input creates unverified account")
```

Do NOT include phase/order numbers in skip reasons. Those numbers would
become stale when `/test-orderer` establishes the real implementation
sequence. Describe the behavior instead — it stays correct regardless
of ordering.

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

**Test organization in the file:** Group tests by behavior category using
section comments that match the Test List. Within each category, order
tests from simple to complex — but don't assign implementation phase
numbers. The file reads as a behavioral specification organized by topic;
`/test-orderer` will later produce the cross-cutting implementation
sequence.

```python
# --- Registration ---

@pytest.mark.skip(reason="valid registration creates unverified account")
def test_register_with_valid_input_creates_account():
    ...

@pytest.mark.skip(reason="duplicate email is rejected")
def test_register_with_existing_email_returns_conflict():
    ...

# --- Login ---

@pytest.mark.skip(reason="valid credentials return token pair")
def test_login_with_valid_credentials_returns_tokens():
    ...

# --- Error Handling ---

@pytest.mark.skip(reason="account locks after repeated failures")
def test_login_after_five_failures_returns_locked():
    ...
```

**Async behaviors:** When the design doc describes async operations
(queues, events, eventual consistency), test command side and query side
separately. Assert on eventual state, never on timing.

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

Read `../../references/anti-patterns.md` for the full list of anti-patterns to
avoid when generating tests. Apply every item during Phase 2 and Phase 3.

## Output Format

Deliver as a single executable test file (or multiple if the design doc
covers distinct modules). Include:

1. All tests marked as **skipped** with behavioral descriptions (no phase numbers)
2. Clear section comments grouping tests by behavior category
3. Minimal but sufficient fixtures/factories
4. The Desiderata summary table as a comment block at the end of the file

The test file should be immediately runnable — all tests skip, the suite
is green.

## Next Step — Auto-chain to /test-orderer

After generating the test file and presenting the Desiderata review,
automatically invoke `/test-orderer {path-to-generated-test-file}`.

This is why test-generator does not assign implementation phase numbers:
`/test-orderer` analyzes dependencies between tests and produces the
implementation sequence with its own phased groupings (Skeleton, Core
Behavior, Extended Behavior, etc.). If test-generator pre-assigned
phase numbers, test-orderer would have to undo them, and the skip
annotations in the test file would become misleading.

The division of responsibility:
- **test-generator** decides WHAT to test (behavioral analysis + code)
- **test-orderer** decides WHICH ORDER to implement (dependency analysis + sequencing)

The full workflow chain:
```
/design-doc → /design-doc-reviewer → /test-generator (auto-chains /test-orderer) → human review → /implementation-plan → implement (auto-chains /post-verification) → /refactor → human review
```

---
name: test-generator
description: Generate executable test cases from design documents, source code, or feature descriptions using Kent Beck's Test Desiderata and Canon TDD principles. Applies to design docs, RFCs, ADRs, technical specs, or existing code. Works for any programming language.
---

# Test Generator

Generate high-quality, executable test cases from design documents using
Kent Beck's testing philosophy.

## Workflow

Follow these steps in order. If the user already provides a test list or explicitly asks to skip analysis, begin at Phase 2.

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

**Implementation order:** Number tests sequentially across all categories.
The ordering follows the TDD progression — simple behaviors first, then
edge cases, then error handling, then invariants:

1. **Start with the simplest happy path** — the one that forces you to
   create the basic interface and return the most obvious correct result.
2. **Add happy path variations** — each one should require a small,
   incremental change to the implementation.
3. **Edge cases** — boundary values and special inputs that reveal
   handling logic.
4. **Error scenarios** — invalid inputs, failures, and exceptional paths.
5. **Invariants / properties** — cross-cutting rules verified last, once
   the implementation is stable enough.

The human reviews and may reorder this list before implementation begins
(Step 5 in the workflow). The numbering gives them a concrete sequence
to approve, adjust, or reprioritize.

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
`references/test-desiderata.md`. Read that file now for the full checklist.

**All tests are generated as skipped.** Every test must be marked with the
framework's skip mechanism and annotated with its implementation phase
number from the Test List. This is the key enabler for the TDD loop —
the developer (or AI) unskips one test at a time, makes it pass, then
moves to the next.

Skip mechanism by framework:

| Framework | Skip syntax |
|-----------|------------|
| pytest | `@pytest.mark.skip(reason="Phase N: ...")` |
| Jest/Vitest | `it.skip("...", () => { ... })` or `xit("...", ...)` |
| Go testing | `t.Skip("Phase N: ...")` |
| JUnit | `@Disabled("Phase N: ...")` |
| RSpec | `xit "..." do ... end` or `pending("Phase N: ...")` |

The skip reason must include the phase number and a brief description:
```
@pytest.mark.skip(reason="Phase 1: simplest happy path — create returns success")
```

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

**Test ordering in the file:** Tests must appear in the file in their
implementation phase order. Group them with section comments that match
the Test List categories, but within and across categories, maintain
the numbered sequence:

```python
# --- Happy Path ---

@pytest.mark.skip(reason="Phase 1: create with valid input returns success")
def test_create_order_with_valid_items_returns_confirmation():
    ...

@pytest.mark.skip(reason="Phase 2: create applies tax to taxable items")
def test_create_order_with_taxable_items_includes_regional_tax():
    ...

# --- Edge Cases ---

@pytest.mark.skip(reason="Phase 3: empty cart is rejected")
def test_create_order_with_empty_cart_returns_validation_error():
    ...

# --- Error Scenarios ---

@pytest.mark.skip(reason="Phase 4: payment failure rolls back order")
def test_create_order_when_payment_fails_does_not_persist_order():
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

Read `references/anti-patterns.md` for the full list of anti-patterns to
avoid when generating tests. Apply every item during Phase 2 and Phase 3.

## Output Format

Deliver as a single executable test file (or multiple if the design doc
covers distinct modules). Include:

1. All tests marked as **skipped**, ordered by implementation phase number
2. Clear section comments grouping tests by Test List category
3. Minimal but sufficient fixtures/factories
4. The Desiderata summary table as a comment block at the end of the file

The test file should be immediately runnable — all tests skip, the suite
is green, and the developer begins the TDD loop by unskipping Phase 1.

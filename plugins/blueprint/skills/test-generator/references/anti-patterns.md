# Test Anti-Patterns to Avoid

Common mistakes derived from Kent Beck's Canon TDD, Test Desiderata, and
Programmer Test Principles articles.

## Structure-Sensitive Tests

**The problem:** Tests that assert internal method calls, private state,
or execution order. Beck: "I frequently see tests that assert, 'Assert
that this object sends this message to that object with these parameters
and then sends this other message to that other object.' An assertion
like this is basically the world's clumsiest programming language syntax."

**How to detect:** Ask "If I refactor the internals without changing the
observable behavior, will this test break?" If yes, it's structure-sensitive.

**How to fix:** Test through public interfaces. Assert on outputs, return
values, observable state changes, and externally visible side effects.

## Excessive Mocking

**The problem:** Mocking internal collaborators rather than external
boundaries. Strict mocking (verifying call order and exact parameters)
is especially harmful.

**When mocking is justified:**
- Network calls (HTTP clients, gRPC stubs)
- Filesystem operations
- Clock/time providers
- Random number generators
- Third-party services with rate limits or costs

**When mocking is NOT justified:**
- Internal helper methods
- Data transformation functions
- Domain logic collaborators within the same module

**Beck's rule:** "Too much mocking, especially strict mocking, is a
structure sensitivity nightmare."

## Copy-Paste Assertions

**The problem:** Running the code, copying the actual output, and
pasting it as the expected value. Beck: "That defeats double checking,
which creates much of the validation value of TDD."

**How to fix:** Derive expected values independently from the design
doc specification. The expected value should come from YOUR understanding
of the requirement, not from what the code currently produces.

## Test-Per-Method Mapping

**The problem:** One test class per production class, one test method
per production method. This creates tight coupling to structure.

**How to fix:** Organize tests by BEHAVIOR, not by class structure.
One test may exercise multiple methods. One method may appear in
multiple behavioral tests.

Example — instead of:
```
test_calculate_tax()
test_apply_discount()
test_compute_total()
```

Write:
```
test_order_with_taxable_items_includes_regional_tax()
test_order_with_coupon_reduces_total_by_discount_amount()
test_order_total_equals_sum_of_items_plus_tax_minus_discount()
```

## Tests Without Assertions

**The problem:** Tests that only exercise code for coverage without
verifying behavior. Beck: "Mistake: write tests without assertions
just to get code coverage."

**How to detect:** The test calls methods but never asserts anything
(or only asserts `is not None`).

**How to fix:** Every test must assert a specific behavioral outcome.
If you can't figure out what to assert, the behavior isn't well-defined
in the design doc — flag it as missing specification.

## Premature Test Concretization

**The problem:** Converting the entire Test List into concrete test code
before making any of them pass. Beck: "What happens when making the first
test pass causes you to reconsider a decision that affects all those
speculative tests? Rework."

**How this applies to design-doc-derived tests:** When generating tests
from a design doc (before implementation exists), this is less of a
concern since we're establishing the behavioral contract. However, mark
tests that depend on design decisions that feel uncertain — these should
be reviewed first during implementation.

## Mixing Interface and Implementation Design in Tests

**The problem:** Tests that bake in assumptions about HOW something is
implemented rather than WHAT it does.

**Beck's distinction:**
- Interface design = How a behavior is invoked (this SHOULD be in tests)
- Implementation design = How the system implements that behavior
  (this should NOT be in tests)

**Checklist question:** "Does this test tell me WHAT the system does,
or HOW it does it?"

## DRY Tests (Over-Abstracted)

**The problem:** Applying DRY (Don't Repeat Yourself) too aggressively
in test code. Shared setup methods, helper abstractions, and constant
extraction can make individual tests incomprehensible.

**Beck's insight:** In tests, readability trumps DRY. Each test should
be understandable in isolation. A reader should not need to trace through
multiple files to understand what a test verifies.

**Acceptable repetition:** Inline fixture construction, repeated assert
patterns, duplicated setup between related tests. Keep the full context
visible within each test function.

## Non-Deterministic Tests (Flaky Tests)

**The problem:** Tests that sometimes pass and sometimes fail without
code changes. Common sources: time-dependent logic, random values,
concurrent state, network dependencies.

**How to fix:**
- Inject clocks and random seeds
- Use deterministic ordering for collections
- Isolate concurrent tests with proper synchronization
- Replace real network calls with controlled test doubles

## Behavioral Gaps

**The problem:** The test suite is green but doesn't actually predict
production success because important behaviors are untested.

**How to detect from a design doc:** After generating tests, map each
design doc requirement to at least one test. Requirements without
corresponding tests are behavioral gaps.

**Beck on Predictive:** "If the tests all pass, then the code under
test should be suitable for production."

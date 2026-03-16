# Test Anti-Patterns

How to avoid and detect common testing mistakes. Derived from Kent Beck's
Canon TDD, Test Desiderata, and Programmer Test Principles.

## 🔴 Critical Anti-Patterns

### AP-1: Structure-Sensitive Assertions

**The problem:** Tests that assert internal method calls, private state,
or execution order. Beck: "I frequently see tests that assert, 'Assert
that this object sends this message to that object with these parameters.'
An assertion like this is basically the world's clumsiest programming
language syntax."

**How to detect:** Ask "If I refactor the internals without changing the
observable behavior, will this test break?" If yes, it's structure-sensitive.

**Code smells to grep for:**
- `.assert_called_with(`, `.assert_called_once_with(`
- `mock.call_args`, `mock.call_count`
- `verify(mock).method(` (Mockito-style)
- `expect(spy).toHaveBeenCalledWith(` (Jest)
- Assertions on private/protected attributes (`obj._internal_state`)
- Assertions on execution order of internal methods

**How to fix:** Test through public interfaces. Assert on outputs, return
values, observable state changes, and externally visible side effects.

### AP-2: Tests Without Meaningful Assertions

**The problem:** Tests that only exercise code for coverage without
verifying behavior. Beck: "Mistake: write tests without assertions
just to get code coverage."

**Code smells:**
- Test function with no `assert` / `expect` / `should` statement
- Only asserting truthiness: `assert result`, `expect(result).toBeTruthy()`
- Only asserting non-null: `assert result is not None`
- Only asserting type: `assertIsInstance(result, dict)`
- `# no assertion needed, just checking it doesn't throw`

**How to fix:** Every test must assert a specific behavioral outcome.
If you can't figure out what to assert, the behavior isn't well-defined
— flag it as missing specification.

### AP-3: Non-Deterministic Tests

**The problem:** Tests that sometimes pass and sometimes fail without
code changes. Common sources: time-dependent logic, random values,
concurrent state, network dependencies.

**Code smells:**
- Direct use of `datetime.now()`, `time.time()`, `Date.now()`
- `random.random()`, `Math.random()`, `uuid4()` in assertions
- `time.sleep()` / `setTimeout` for synchronization
- Assertions on collection ordering without explicit sort
- File system paths that vary by environment
- Port numbers or network resources

**How to fix:** Inject clocks and random seeds. Use deterministic ordering
for collections. Replace real network calls with controlled test doubles.
Replace sleep with explicit state checks.

### AP-4: Copy-Paste Expected Values

**The problem:** Running the code, copying the actual output, and
pasting it as the expected value. Beck: "Copying actual, computed values
and pasting them into the expected values of the test defeats double
checking, which creates much of the validation value of TDD."

**Code smells (harder to detect, look for):**
- Large literal expected values (long strings, big dicts/objects)
- Expected values that look machine-generated
- Comments like `# generated from actual output`
- Snapshot tests that were auto-updated without review

**How to fix:** Derive expected values independently from the design
doc specification. The expected value should come from YOUR understanding
of the requirement, not from what the code currently produces. For complex
structures, assert on key fields rather than full equality.

## 🟡 Warning Anti-Patterns

### AP-5: Excessive Mocking

**The problem:** Mocking internal collaborators rather than external
boundaries. Strict mocking (verifying call order and exact parameters)
is especially harmful. Beck: "Too much mocking, especially strict mocking,
is a structure sensitivity nightmare."

**Code smells:**
- More than 3 mocks/patches in a single test
- Mocking classes within the same module
- `@mock.patch` on internal helper functions
- Mock setup longer than the actual test logic
- `mock.patch.object` on domain models

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

**How to fix:** Replace internal mocks with real collaborators. Push mocks
to the outermost boundary. Consider using fakes instead of mocks for
complex interactions.

### AP-6: Over-DRY Test Code

**The problem:** Applying DRY too aggressively in test code. Shared setup
methods, helper abstractions, and constant extraction can make individual
tests incomprehensible. Beck: "Some things that make code more readable
actually reduce the readability of tests... You're not supposed to repeat
yourself, unless you're supposed to repeat yourself."

**Code smells:**
- `setUp` / `beforeEach` longer than 10 lines
- Shared fixture files (conftest.py, factories) referenced from many tests
- Helper methods that construct test scenarios with parameters
- Test code that requires reading 3+ files to understand one test
- Base test classes with shared behavior

**Acceptable repetition:** Inline fixture construction, repeated assert
patterns, duplicated setup between related tests. Keep the full context
visible within each test function.

### AP-7: Test-Per-Method Organization

**The problem:** One test class per production class, one test method
per production method. This creates tight coupling to structure.

**Code smells:**
- Test class named `TestClassName` mirroring production class exactly
- Test methods named `test_method_name` mirroring production methods
- One-to-one mapping between test files and production files
- Tests that break when a method is renamed (even though behavior didn't change)

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

### AP-8: Unclear Test Names

**Code smells:**
- `test_1`, `test_basic`, `test_it_works`
- Names describing implementation: `test_calls_validate_then_save`
- Names missing the scenario: `test_create_order` (which scenario?)
- Names missing the expected outcome: `test_expired_coupon`

**Good naming pattern:** `test_[action]_[scenario]_[expected_outcome]`

Examples:
- `test_create_order_with_expired_coupon_returns_validation_error`
- `test_transfer_exceeding_balance_is_rejected`
- `test_search_with_empty_query_returns_all_results`

## 🟢 Suggestion Patterns

### AP-9: Missing Edge Cases

**Common gaps to check for:**
- Empty inputs (empty string, empty list, None/null)
- Boundary values (0, -1, MAX_INT, empty vs single-element collection)
- Unicode / special characters in string inputs
- Concurrent access scenarios
- Permission / authorization boundaries
- Timeout and retry behavior

### AP-10: Assertion Message Quality

**Look for:** Bare assertions without messages. When a test fails in CI,
the developer should immediately understand what went wrong.

```
# Weak
assert result.status == "active"

# Strong
assert result.status == "active", (
    f"Expected order {order_id} to be active after payment, "
    f"but got status={result.status}"
)
```

### AP-11: Test Isolation Leaks

**Code smells:**
- Class-level mutable state (`cls.shared_data = []`)
- Module-level variables modified by tests
- Database state not cleaned up between tests
- Tests that pass alone but fail in suite (or vice versa)
- `@pytest.mark.order` or similar ordering dependencies

### AP-12: Slow Tests Without Justification

**Code smells:**
- `time.sleep()` in unit tests
- Real database/network calls in unit tests
- Large data fixtures loaded from files
- Tests marked as `@slow` or `@pytest.mark.timeout(30)`

**Beck's insight:** Sub-second is the threshold where you don't glance
away. If a unit test takes more than that, question whether it needs
real I/O.

## Generator-Specific Anti-Patterns

These apply specifically when generating new tests from specs.

### Premature Test Concretization

**The problem:** Converting the entire Test List into concrete test code
before making any of them pass. Beck: "What happens when making the first
test pass causes you to reconsider a decision that affects all those
speculative tests? Rework."

**For spec-derived tests:** This is less of a concern since we're
establishing the behavioral contract. However, mark tests that depend on
design decisions that feel uncertain — these should be reviewed first
during implementation.

### Mixing Interface and Implementation Design

**The problem:** Tests that bake in assumptions about HOW something is
implemented rather than WHAT it does.

**Beck's distinction:**
- Interface design = How a behavior is invoked (this SHOULD be in tests)
- Implementation design = How the system implements that behavior
  (this should NOT be in tests)

**Checklist question:** "Does this test tell me WHAT the system does,
or HOW it does it?"

### Behavioral Gaps

**The problem:** The test suite is green but doesn't actually predict
production success because important behaviors are untested.

**How to detect from a spec:** After generating tests, map each
spec requirement to at least one test. Requirements without
corresponding tests are behavioral gaps.

**Beck on Predictive:** "If the tests all pass, then the code under
test should be suitable for production."

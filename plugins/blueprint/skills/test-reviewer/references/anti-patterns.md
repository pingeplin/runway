# Test Anti-Patterns Detection Guide

How to spot each anti-pattern when reviewing existing test code.
Derived from Kent Beck's Canon TDD, Test Desiderata, and Programmer
Test Principles.

## 🔴 Critical Anti-Patterns

### AP-1: Structure-Sensitive Assertions

**Code smells to grep for:**
- `.assert_called_with(`, `.assert_called_once_with(`
- `mock.call_args`, `mock.call_count`
- `verify(mock).method(` (Mockito-style)
- `expect(spy).toHaveBeenCalledWith(` (Jest)
- Assertions on private/protected attributes (`obj._internal_state`)
- Assertions on execution order of internal methods

**Beck's words:** "I frequently see tests that assert, 'Assert that this
object sends this message to that object with these parameters.' An
assertion like this is basically the world's clumsiest programming
language syntax."

**Refactoring direction:** Replace with assertions on observable outputs,
return values, or state changes visible through public interfaces.

### AP-2: Tests Without Meaningful Assertions

**Code smells:**
- Test function with no `assert` / `expect` / `should` statement
- Only asserting truthiness: `assert result`, `expect(result).toBeTruthy()`
- Only asserting non-null: `assert result is not None`
- Only asserting type: `assertIsInstance(result, dict)`
- `# no assertion needed, just checking it doesn't throw`

**Beck's words:** "Mistake: write tests without assertions just to get
code coverage."

**Refactoring direction:** Add specific behavioral assertions. If you
can't figure out what to assert, the behavior isn't well understood.

### AP-3: Non-Deterministic Tests

**Code smells:**
- Direct use of `datetime.now()`, `time.time()`, `Date.now()`
- `random.random()`, `Math.random()`, `uuid4()` in assertions
- `time.sleep()` / `setTimeout` for synchronization
- Assertions on collection ordering without explicit sort
- File system paths that vary by environment
- Port numbers or network resources

**Beck's words:** "Code that uses a clock or random numbers should be
passed those values by their unit tests."

**Refactoring direction:** Inject time/randomness as parameters. Use
deterministic IDs in tests. Replace sleep with explicit state checks.

### AP-4: Copy-Paste Expected Values

**Code smells (harder to detect, look for):**
- Large literal expected values (long strings, big dicts/objects)
- Expected values that look machine-generated
- Comments like `# generated from actual output`
- Snapshot tests that were auto-updated without review

**Beck's words:** "Copying actual, computed values and pasting them into
the expected values of the test defeats double checking, which creates
much of the validation value of TDD."

**Refactoring direction:** Derive expected values from spec independently.
For complex structures, assert on key fields rather than full equality.

## 🟡 Warning Anti-Patterns

### AP-5: Excessive Mocking

**Code smells:**
- More than 3 mocks/patches in a single test
- Mocking classes within the same module
- `@mock.patch` on internal helper functions
- Mock setup longer than the actual test logic
- `mock.patch.object` on domain models

**Legitimate mock boundaries:**
- HTTP clients / API calls
- Database connections (when testing service logic, not queries)
- File system operations
- Message queues / event buses
- Clock / time providers
- External service SDKs

**Beck's words:** "Too much mocking, especially strict mocking, is a
structure sensitivity nightmare."

**Refactoring direction:** Replace internal mocks with real collaborators.
Push mocks to the outermost boundary. Consider using fakes instead of
mocks for complex interactions.

### AP-6: Over-DRY Test Code

**Code smells:**
- `setUp` / `beforeEach` longer than 10 lines
- Shared fixture files (conftest.py, factories) referenced from many tests
- Helper methods that construct test scenarios with parameters
- Test code that requires reading 3+ files to understand one test
- Base test classes with shared behavior

**Beck's words:** "Some things that make code more readable actually
reduce the readability of tests... You're not supposed to repeat
yourself, unless you're supposed to repeat yourself."

**Refactoring direction:** Inline fixtures into individual tests. Accept
duplication if it improves readability. Each test should tell its full
story without external context.

### AP-7: Test-Per-Method Organization

**Code smells:**
- Test class named `TestClassName` mirroring production class exactly
- Test methods named `test_method_name` mirroring production methods
- One-to-one mapping between test files and production files
- Tests that break when a method is renamed (even though behavior didn't change)

**Refactoring direction:** Reorganize tests by behavior/feature. One test
may exercise multiple methods. Multiple tests may exercise the same method
for different scenarios.

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

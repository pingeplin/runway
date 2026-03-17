# Test Review Methodology

Review test files for quality using Beck's Test Desiderata as the primary framework. Also read `test-desiderata.md` for full property definitions and `anti-patterns.md` for smell detection patterns.

## Phase 1 — Desiderata Audit

Score every test against Beck's 12 Test Desiderata properties (Isolated, Composable, Deterministic, Fast, Writable, Readable, **Behavioral**, **Structure-insensitive**, Automated, Specific, Predictive, Inspiring). Use a table with Score and Notes columns.

**Behavioral** and **Structure-insensitive** are the two critical properties. Any test scoring poorly on either is high priority for refactoring.

Exception: some structure-sensitive tests are legitimate — tests verifying middleware ordering, decorator composition, or event emission for monitoring. Acknowledge these cases rather than automatically flagging them.

Present a **summary scorecard** first, then detailed per-test findings.

## Phase 2 — Smell Detection

Scan for the anti-patterns listed in `anti-patterns.md`. Categorize findings by severity:

**Critical** — Tests that give false confidence or will break on legitimate refactoring:
- Structure-sensitive assertions (AP-1): mocking internals, asserting call order
- Tests without meaningful assertions (AP-2): no real behavioral verification
- Copy-pasted expected values (AP-4): machine-generated expected output
- Non-deterministic tests (AP-3): time, randomness, ordering dependencies
- Flaky tests (AP-3, AP-11): isolation leaks, shared mutable state

**Warning** — Tests that work but have maintainability problems:
- Excessive mocking beyond external boundaries (AP-5)
- Over-DRY test code hiding context (AP-6)
- Test-per-method organization instead of test-per-behavior (AP-7)
- Unclear test names that don't describe the scenario (AP-8)

**Suggestion** — Nice-to-have improvements:
- Better naming for readability
- Inline fixtures for clarity
- Grouping tests by behavior rather than by class
- Adding missing edge cases (AP-9)
- Assertion message quality (AP-10)

## Phase 3 — Coverage Gap Analysis

1. **List the behaviors** the production code implements (scan function signatures, branches, error handling)
2. **Map tests to behaviors** — which tests cover which behaviors?
3. **Flag gaps** — behaviors with zero test coverage, especially error paths and edge cases
4. **Flag redundancy** — multiple tests asserting the exact same thing (wasted maintenance cost)

Present gaps as a prioritized list, ranked by risk (public API > internal helpers, error paths > happy paths already covered).

## Phase 4 — Refactoring Plan

For each finding, propose a concrete refactoring. Group refactorings by type:

**R1: Behavior Extraction** — Test asserts on internals; rewrite to assert on observable output.
```
# Before: structure-sensitive
mock_repo.save.assert_called_once_with(expected_entity)

# After: behavioral
result = service.create(input_data)
assert result.id is not None
assert db.query(Entity).filter_by(id=result.id).first() is not None
```

**R2: Mock Boundary Correction** — Mock placed on internal collaborator; move mock to external boundary.
```
# Before: mocking internal logic
with mock.patch('myapp.services.calculator.compute_tax'):

# After: mocking external boundary only
with mock.patch('myapp.clients.tax_api.fetch_rate'):
```

**R3: Inline Fixture Restoration** — Shared setup obscuring test intent; inline the relevant setup.
```
# Before: context hidden in setUp/conftest
def test_expired_order_cannot_be_modified(self):
    with pytest.raises(OrderExpiredError):
        self.order.modify(new_items)

# After: full context visible
def test_expired_order_cannot_be_modified():
    order = Order(created_at=datetime(2024, 1, 1), ttl_days=30)
    order.expire()
    with pytest.raises(OrderExpiredError):
        order.modify(new_items=[Item("widget")])
```

**R4: Behavioral Rename** — Test name describes implementation; rename to describe behavior.
```
# Before
test_process_method_calls_validate_and_save

# After
test_valid_submission_is_persisted_and_confirmation_returned
```

**R5: Determinism Injection** — Test uses live clock/random; inject controlled values.
```
# Before
def test_token_expiry():
    token = create_token()
    time.sleep(2)
    assert token.is_expired()

# After
def test_token_created_before_ttl_is_expired():
    fixed_now = datetime(2024, 6, 1, 12, 0, 0)
    token = create_token(now=fixed_now, ttl_seconds=60)
    assert token.is_expired(at=fixed_now + timedelta(seconds=61))
```

**R6: Assertion Strengthening** — Weak assertion; replace with specific behavioral assertion.
```
# Before
assert result is not None

# After
assert result.status == "completed"
assert result.total == Decimal("150.00")
```

**R7: Test Splitting** — One test verifying multiple unrelated behaviors; split into focused tests.

**R8: Coverage Gap Fill** — Missing test for a behavior implied by the code; add new test.

## Phase 5 — Refactored Code (optional)

If the user wants refactored code (not just a report), apply the refactoring plan:

1. Never change test behavior while refactoring structure — one hat at a time (Beck)
2. If the refactoring changes WHAT is being tested (not just HOW), note the change explicitly and confirm with the user before applying
3. Group tests by behavior, not by class or method
4. Ensure each test name describes the behavioral scenario being verified

## Phase 6 — Before/After Summary

Output a desiderata score improvement table (Before/After percentages per property) and a numbered list of key changes (mocks removed, fixtures inlined, tests renamed, edge cases added, flaky tests fixed).

Skip Phases 5-6 for a quick review. Ask whether to proceed with refactoring after delivering Phases 1-4.

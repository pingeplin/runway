---
name: test-reviewer
description: Review existing test suites for quality, flakiness, and maintainability using Kent Beck's Test Desiderata framework. Scores tests against 12 desirable properties, detects anti-patterns (excessive mocking, structure-sensitivity, non-determinism), identifies coverage gaps, and produces a concrete refactoring plan with code examples. Works for any programming language and test framework.
---

# Test Reviewer

Review and refactor existing test code through the lens of Kent Beck's
testing philosophy.

## Workflow

### Phase 1 — Desiderata Audit

Score every test against Beck's 12 Test Desiderata properties. Read
`references/test-desiderata.md` for full definitions and checklist.

For each test function/method, evaluate:

| Property | Score | Notes |
|----------|:-----:|-------|
| Isolated | ✅/⚠️/❌ | |
| Composable | ✅/⚠️/❌ | |
| Deterministic | ✅/⚠️/❌ | |
| Fast | ✅/⚠️/❌ | |
| Writable | ✅/⚠️/❌ | |
| Readable | ✅/⚠️/❌ | |
| **Behavioral** | ✅/⚠️/❌ | |
| **Structure-insensitive** | ✅/⚠️/❌ | |
| Automated | ✅/⚠️/❌ | |
| Specific | ✅/⚠️/❌ | |
| Predictive | ✅/⚠️/❌ | |
| Inspiring | ✅/⚠️/❌ | |

**Behavioral** and **Structure-insensitive** are the two critical
properties. Any test scoring ❌ on either should be flagged as high
priority for refactoring.

Note: some structure-sensitive tests are legitimate — for example,
tests verifying middleware ordering, decorator composition, or event
emission for monitoring. Acknowledge these cases rather than
automatically flagging them.

Present a **summary scorecard** first, then detailed findings.

### Phase 2 — Smell Detection

Scan for the anti-patterns listed in `references/anti-patterns.md`.
Read that file now. Categorize findings by severity:

**🔴 Critical** — Tests that give false confidence or will break on
legitimate refactoring:
- Structure-sensitive assertions (mocking internals, asserting call order)
- Tests without meaningful assertions
- Copy-pasted expected values from actual output
- Non-deterministic tests (time, randomness, ordering)
- Flaky tests (see AP-3, AP-11 in `references/anti-patterns.md`)

**🟡 Warning** — Tests that work but have maintainability problems:
- Excessive mocking beyond external boundaries
- Over-DRY test code (shared setup hiding context)
- Test-per-method organization instead of test-per-behavior
- Unclear test names that don't describe the scenario

**🟢 Suggestion** — Nice-to-have improvements:
- Better naming for readability
- Inline fixtures for clarity
- Grouping tests by behavior rather than by class
- Adding missing edge cases

#### Coverage Gap Analysis

After smell detection, perform a lightweight gap analysis:

1. **List the behaviors** the production code implements (scan function signatures, branches, error handling)
2. **Map tests to behaviors** — which tests cover which behaviors?
3. **Flag gaps** — behaviors with zero test coverage, especially error paths and edge cases
4. **Flag redundancy** — multiple tests asserting the exact same thing (wasted maintenance cost)

Present gaps as a prioritized list, ranked by risk (public API > internal helpers, error paths > happy paths already covered).

### Phase 3 — Refactoring Plan

For each finding, propose a concrete refactoring. Group refactorings by
type to allow batch application:

#### Refactoring Types

**R1: Behavior Extraction**
Test asserts on internals → Rewrite to assert on observable output.
```
# Before: structure-sensitive
mock_repo.save.assert_called_once_with(expected_entity)

# After: behavioral
result = service.create(input_data)
assert result.id is not None
assert db.query(Entity).filter_by(id=result.id).first() is not None
```

**R2: Mock Boundary Correction**
Mock placed on internal collaborator → Move mock to external boundary.
```
# Before: mocking internal logic
with mock.patch('myapp.services.calculator.compute_tax'):

# After: mocking external boundary only
with mock.patch('myapp.clients.tax_api.fetch_rate'):
```

**R3: Inline Fixture Restoration**
Shared setup obscuring test intent → Inline the relevant setup.
```
# Before: context hidden in setUp/conftest
def test_expired_order_cannot_be_modified(self):
    # What is self.order? What state is it in? Reader must look elsewhere.
    with pytest.raises(OrderExpiredError):
        self.order.modify(new_items)

# After: full context visible
def test_expired_order_cannot_be_modified():
    order = Order(created_at=datetime(2024, 1, 1), ttl_days=30)
    order.expire()  # explicit state transition
    with pytest.raises(OrderExpiredError):
        order.modify(new_items=[Item("widget")])
```

**R4: Behavioral Rename**
Test name describes implementation → Rename to describe behavior.
```
# Before
test_process_method_calls_validate_and_save

# After
test_valid_submission_is_persisted_and_confirmation_returned
```

**R5: Determinism Injection**
Test uses live clock/random → Inject controlled values.
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

**R6: Assertion Strengthening**
Weak assertion → Specific behavioral assertion.
```
# Before
assert result is not None

# After
assert result.status == "completed"
assert result.total == Decimal("150.00")
```

**R7: Test Splitting**
One test verifying multiple unrelated behaviors → Split into focused tests.

**R8: Coverage Gap Fill**
Missing test for a behavior implied by the code → Add new test.

### Phase 4 — Refactored Code

Apply the refactoring plan and produce the refactored test file.

**Rules for refactoring:**
1. Never change test behavior while refactoring structure (Beck's
   "wearing two hats" — one hat at a time).
2. If the refactoring changes what's being tested (not just how), note
   the change explicitly and confirm with the user before applying.
3. Group tests by behavior, not by class or method.
4. Ensure each test name describes the behavioral scenario being
   verified. Add a comment only when the scenario has nuance that the
   name alone can't convey.

### Phase 5 — Before/After Summary

Present a concise comparison:

```
## Review Summary

**Tests reviewed:** N
**Critical issues (🔴):** N — [list]
**Warnings (🟡):** N — [list]
**Suggestions (🟢):** N — [list]

### Desiderata Score Improvement
| Property | Before | After |
|----------|:------:|:-----:|
| Behavioral | 60% ✅ | 95% ✅ |
| Structure-insensitive | 40% ✅ | 90% ✅ |
| Readable | 70% ✅ | 95% ✅ |
| ... | ... | ... |

### Key Changes
1. Removed N structure-sensitive mocks → replaced with boundary mocks
2. Inlined N shared fixtures for readability
3. Renamed N tests to describe behavior
4. Added N missing edge case tests
5. Fixed N non-deterministic tests
```

## Handling Partial Context

Sometimes the user provides only test code without the production code
or design doc.

- **Test code only:** Review is still possible. Focus on Desiderata
  properties that can be assessed without seeing production code
  (Readable, Isolated, Deterministic, Specific, naming quality,
  mock usage patterns). Flag items where production code is needed
  to assess Behavioral and Structure-insensitive properties.

- **Test code + production code:** Full review is possible. Check
  alignment between test assertions and actual behavior.

- **Test code + design doc:** Ideal scenario. Can verify that tests
  cover the specified behaviors and follow Desiderata. Can identify
  behavioral gaps.

## Handling Large Test Suites

When the test suite spans many files or thousands of lines:

- Ask the user to scope the review to specific files or modules.
- Alternatively, prioritize the most problematic files (highest mock
  count, most test failures, largest setup blocks).
- Offer a **summary-only mode**: deliver Phases 1-2 (scorecard and
  findings) without generating refactored code, so the user can decide
  where to invest effort.

## Output Format

1. Summary scorecard (Phase 1)
2. Categorized findings (Phase 2)
3. Refactoring plan with code examples (Phase 3)
4. Complete refactored test file (Phase 4)
5. Before/after comparison (Phase 5)

If the user only wants a quick review (not full refactoring), deliver
Phases 1-2 only and ask if they want to proceed with refactoring.

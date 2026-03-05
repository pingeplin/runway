---
name: test-reviewer
description: Review and refactor existing test code using Kent Beck's Test Desiderata, Canon TDD, and Programmer Test Principles. Use this skill whenever the user provides existing test code and wants it reviewed, improved, refactored, or audited for quality. Also trigger when the user says "review my tests", "refactor these tests", "are my tests good", "improve test quality", "my tests are flaky", "my tests break when I refactor", "too many mocks", or any request to evaluate or improve existing test suites. Works for any programming language and test framework.
---

# Test Reviewer

Review and refactor existing test code through the lens of Kent Beck's
testing philosophy.

## When to Use

- User provides existing test code and wants a quality review.
- User complains about flaky tests, brittle tests, or tests that break
  on refactoring.
- User asks whether their tests are "good enough" or wants improvement
  suggestions.
- User wants to refactor a test suite to follow best practices.
- User has both production code and test code and wants alignment review.

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
properties. Any test scoring ❌ on either must be flagged as high
priority for refactoring.

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
2. Preserve the original test as a comment if the refactoring changes
   what's being tested (not just how).
3. Group tests by behavior, not by class or method.
4. Add a brief comment on each test explaining the behavioral scenario
   being verified.

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
  cover the specified behaviors AND follow Desiderata. Can identify
  behavioral gaps.

## Output Format

1. Summary scorecard (Phase 1)
2. Categorized findings (Phase 2)
3. Refactoring plan with code examples (Phase 3)
4. Complete refactored test file (Phase 4)
5. Before/after comparison (Phase 5)

If the user only wants a quick review (not full refactoring), deliver
Phases 1-2 only and ask if they want to proceed with refactoring.

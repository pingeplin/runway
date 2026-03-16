# Test Desiderata Reference

Kent Beck's 12 desirable properties of tests. Think of these as sliders —
more of one property sometimes means less of another. No property should be
given up without receiving a property of greater value in return.

## The 12 Properties

### 1. Isolated
Tests return the same results regardless of the order in which they run.
Each test creates its own fixtures from scratch.

**Checklist:** Does this test depend on state left by another test? Does it
modify shared state that could affect other tests?

### 2. Composable
If tests are isolated, I can run 1 or 10 or 1,000,000 and get the same
results. Test different dimensions of variability separately and combine
the results.

**Checklist:** Can I run this test alone AND as part of the full suite
with identical results?

### 3. Deterministic
If nothing changes, the test result shouldn't change. Code that uses a
clock or random numbers should be passed those values by their tests.

**Checklist:** Does this test use `time.now()`, `random()`, or any
non-deterministic source directly? If so, inject it.

### 4. Fast
Tests should run quickly. Sub-second is one discontinuity — that's the
amount of wait time that isn't worth glancing away. Ten seconds is long
enough to glance away but not long enough to start something new.

**Checklist:** Does this test hit the network, disk, or database when it
doesn't need to? Can the same assertion be made with an in-memory substitute?

### 5. Writable
Tests should be cheap to write relative to the cost of the code being
tested. Good interface design makes writing tests easier. Difficult-to-write
tests are the canary in the bad interface coal mine.

**Checklist:** Did this test require excessive setup? If so, the
interface under test may need redesign.

### 6. Readable
Tests should be comprehensible for the reader, invoking the motivation for
writing this particular test. Some things that make production code more
readable (DRY, shared constants) actually reduce test readability. In tests,
a bit of repetition is preferable to indirection.

**Checklist:** Can a new team member understand what behavior this test
verifies just by reading it? Are the arrange-act-assert sections clear?

### 7. Behavioral ⭐
Tests should be sensitive to changes in the BEHAVIOR of the code under test.
If the behavior changes, the test result should change. This is the most
important property for spec-derived tests.

**Checklist:** Does this test verify an observable output or side effect?
Or does it peek into internals?

### 8. Structure-insensitive ⭐
Tests should NOT change their result if the STRUCTURE of the code changes.
Refactoring should not break tests. Too much mocking, especially strict
mocking, is a structure-sensitivity nightmare.

**Checklist:** If I refactor the implementation without changing behavior,
will this test still pass? Does it assert method call order or internal
state?

### 9. Automated
Tests should run without human intervention.

**Checklist:** Can CI run this test without manual steps?

### 10. Specific
If a test fails, the cause of the failure should be obvious. If a unit test
fails, the code of interest should be short.

**Checklist:** Does the test name clearly describe the scenario? Does the
assertion message explain what went wrong?

### 11. Deterministic → Predictive
If the tests all pass, then the code under test should be suitable for
production. Unit tests passing gives moderate confidence; unit tests
FAILING should give great confidence something is broken.

**Checklist:** If this test passes, does it actually mean the feature works?
Or is it testing something trivially true?

### 12. Inspiring
Passing the tests should inspire confidence that programming is progressing.

**Checklist:** After this test passes, will the developer feel meaningfully
closer to "done"?

## Priority for Spec-Derived Tests

When generating tests from a spec, prioritize these properties
(in order):

1. **Behavioral** — Tests MUST verify observable behavior described in the doc
2. **Structure-insensitive** — Tests MUST NOT depend on implementation choices
3. **Readable** — Tests serve as executable specification; readability is
   critical for review
4. **Specific** — Each test targets one behavioral variant
5. **Deterministic** — No flaky tests
6. **Isolated** — No test ordering dependencies

Properties that may be traded off for spec-derived tests:
- **Fast** — Integration-level tests from a spec may be slower; that's OK
- **Writable** — Some tests require more setup; invest the effort for coverage

## Applying Desiderata as Review Criteria

After generating tests, score each one:

- ✅ = Property fully satisfied
- ⚠️ = Property partially satisfied (document the trade-off)
- ❌ = Property violated (must justify or rewrite)

A test with ❌ on Behavioral or Structure-insensitive should be rewritten.
A test with ⚠️ on either should have explicit justification.

# Test-Batch Review Methodology

Review the batched tests written by `/run` for a single slice. Apply
these four phases in order. The checks are intentionally narrow — this
evaluator runs inside `/run`'s slice loop and turnaround time matters.
Depth (full Desiderata scoring, AP-5..AP-12) lives in `run-evaluator` at
the end of the run, not here.

The batch's failure modes are *batched-writing specific*: one agent wrote
all the slice's tests in one pass, so it carries sunk-cost bias and is
prone to issues that single-test writing would expose immediately.

## Phase 1 — Scenario Coverage Within Slice

Read the slice's `Scenarios:` line from the plan (passed in the prompt).
For each S-ID listed:

1. Check whether at least one test in the batch references that S-ID.
   References may appear in: the test name, a trailing comment, or by
   matching the Given/When/Then of the corresponding spec scenario.
2. If an S-ID has zero tests, this is a **must-fix** — the slice
   promised to cover it.

Output: a small table of `S-ID | covered? | test names`.

Do NOT check whether *spec-level* S-IDs missing from this slice's
`Scenarios:` are covered elsewhere — that's the plan-evaluator's job
upstream and `run-evaluator`'s job downstream. Your check is
slice-local.

## Phase 2 — Intra-Batch Consistency

Scan the batch for contradictions:

1. **Same input, different expected outcome** — two tests that hand the
   same (or substantively equivalent) input to the system under test and
   expect different observable outcomes, without an explicit precondition
   that distinguishes them. **Must-fix** unless one explicitly varies a
   parameter the other holds constant.
2. **Conflicting invariants** — two tests that imply mutually
   incompatible invariants (e.g., "method always returns a non-empty
   string" and "method returns `None` when X"). **Must-fix.**
3. **Conflicting naming or fixture conventions** — two tests using
   different names for the same conceptual entity (e.g., `user_id` in
   one, `userId` in another, both as fields on the same returned object).
   **Nice-to-have** unless it implies different invariants.

Cite the offending test pair when reporting.

## Phase 3 — Hallucinated API Surface

For every symbol the batch *calls* on the system under test (function,
class, method, attribute), verify it exists:

1. **In the paired spec** — referenced by name in any section, or
   implied by an acceptance scenario's Given/When/Then.
2. **In the codebase** — if you have a codebase pointer in the prompt,
   use `Glob` and `Grep` to confirm the symbol exists at the target
   module(s). Allow for the possibility that the slice introduces new
   symbols — those are fine, but they must be in the slice's
   `Implementation:` bullets.
3. **In a documented framework or stdlib primitive** — `pytest.raises`,
   `expect(...).toBe(...)`, `Decimal`, `datetime`, etc. — these are
   never hallucinated.

A symbol that fails all three is **must-fix**: either the test is
calling something that doesn't and won't exist, or the slice's
`Implementation:` bullets need to declare it. Cite the symbol and the
test that calls it.

A symbol that fails (1) and (2) but you can't confidently rule out (3)
within a quick check is **nice-to-have: verify {symbol} exists**.

## Phase 4 — AP-1 and AP-4 Quick Scan

Two anti-patterns are common in batched writing and must be caught
upstream. Reference `anti-patterns.md` for full definitions; this is a
quick scan.

### AP-1 — Structure-sensitive assertions

Grep the batch for:
- `.assert_called_with(`, `.assert_called_once_with(`
- `mock.call_args`, `mock.call_count`
- `verify(mock).method(`, `expect(spy).toHaveBeenCalledWith(`
- Assertions on private/protected attributes (`obj._internal_state`)
- Assertions on execution order of internal methods

Each hit is **must-fix** unless the slice description explicitly tests
ordering or interaction (rare — usually middleware ordering or event
emission). Cite the test and the offending assertion.

### AP-4 — Copy-pasted expected values

Look for:
- Large literal expected values (long strings, large dicts/objects).
- Expected values that look machine-generated.
- Comments like "# from actual output" or "# copied from result".
- Multiple tests with byte-identical large expected blocks.

Each suspicious case is **nice-to-have: verify {expected_value} derives
from the spec, not from running the code**. Promote to **must-fix** only
when the expected value is large enough that a hand-derived expected
value would obviously look different.

## Output Shape

Return one report:

```markdown
## Test-Batch Review: Slice {slice_id}

### Coverage
| S-ID | Covered? | Test(s) |
|---|---|---|
| ... | ✅ / ❌ | ... |

### Must-fix
- {bullet}
(or: "None.")

### Nice-to-have
- {bullet}
(or: "None.")

### Verdict
- Ready to verify-and-commit: Yes / No
```

If any must-fix item exists, the verdict is **No** — the calling skill
must apply the must-fix items, then re-dispatch this evaluator (or
proceed if the calling skill is confident the fix doesn't change the
batch shape; pragmatic, not mandatory).

If only nice-to-have items remain, the verdict is **Yes** — note the
items in progress output but don't block.

---
name: review
description: Review any project artifact for quality, completeness, and correctness — specs, plans, test files, or implementation code. ALWAYS use this skill when the user asks to review, check, audit, or assess quality of any code or document. Trigger on "review my spec", "check the tests", "audit the plan", "review my implementation", "check for anti-patterns", "score tests against desiderata", "is this testable?", "did I miss anything?", or any request to evaluate quality of specs, plans, tests, or code against best practices. Even casual requests like "take a look at this" or "what do you think of these tests?" should trigger this skill.
argument-hint: [path-to-file] [--type=spec|plan|test|impl]
---

# Review

Review any project artifact with a single command. Auto-detects the artifact type and applies the appropriate review methodology — testability analysis for specs, graph validation for plans, desiderata audit for tests, and behavioral coverage checks for implementations.

## Type Detection

Determine the artifact type from the file path, content, or explicit `--type` override:

| Signal | Type |
|--------|------|
| `specs/*.md` | **spec** |
| `plans/*_graph.md` | **plan** |
| `.test.`, `_test.`, `test_`, `tests/`, `__tests__/` in path | **test** |
| `--type=spec\|plan\|test\|impl` in `$ARGUMENTS` | **explicit override** |
| None of the above | **impl** |

If the type cannot be determined, ask the user.

## Finding the File

If `$ARGUMENTS` contains a file path, read that file. Otherwise check for the most recently modified file in `specs/`, `plans/`, or `tests/`. If nothing found, ask the user.

## Shared Output Structure

All review modes use this wrapper — mode-specific content goes in "Findings":

```
## Review: {type} -- {file name}

### Summary
**Type:** Spec / Plan / Test / Implementation
**Overall quality:** High / Medium / Low
**Critical issues:** {N}  |  **Warnings:** {N}

### Findings
(mode-specific content)

### Recommendations
- [ ] {actionable item with file path}
```

---

## Mode: Spec Review

For reviewing specs written outside the `/spec` skill, or for a second opinion on `/spec` output. The `/spec` skill includes a built-in self-review — this mode provides an independent audit with fresh eyes, and may catch issues the self-review missed.

### Phase 1 — Structural Completeness

Check the spec against standard template sections (Context, Motivation, Proposed Solution, Acceptance Scenarios, Alternatives Considered, Trade-offs and Limitations, Open Questions, Self-Review). Report a table of present/missing sections with assessment notes. If the spec uses a non-standard structure, adapt — focus on content presence, not heading names.

### Phase 2 — Testability Analysis

The highest-value phase. For each requirement or behavior in the spec, evaluate whether it can be tested using Beck's behavioral testing principles.

**For each requirement, ask:**

1. **Is it behavioral?** Does it describe WHAT the system does (observable output/state change), or HOW it works (implementation detail)?
   - Good: "Returns a 404 when the resource doesn't exist"
   - Bad: "Uses a HashMap for O(1) lookup" (implementation detail, not testable behavior)

2. **Is it specific enough to write a test?** Can you derive a Given/When/Then scenario from it?
   - Good: "Expired coupons are rejected with a validation error"
   - Bad: "Handles errors gracefully" (too vague — which errors? what's graceful?)

3. **Is it structure-insensitive?** Can you verify it without knowing the internal architecture?
   - Good: "Search returns results ranked by relevance"
   - Bad: "The cache is invalidated when data changes" (requires knowing cache exists)

**Output a testability scorecard:**

```
#### Fully Testable Requirements
- [Requirement]: can be verified via [approach]

#### Needs Clarification (vague or ambiguous)
- [Requirement]: unclear because [reason]. Suggest: [specific question]

#### Implementation-Coupled (rewrite needed)
- [Requirement]: describes HOW not WHAT. Suggest rewriting as: [behavioral version]

#### Untestable (missing interface)
- [Requirement]: cannot be verified without accessing internals. Consider: [interface suggestion]
```

### Phase 3 — Acceptance Scenario Audit

If the spec includes Acceptance Scenarios, audit them:

1. **Coverage check** — Map each behavior from Proposed Solution to at least one scenario. Flag behaviors without scenarios.
2. **Scenario quality** — Each scenario should follow Given/When/Then and describe observable behavior. Flag scenarios that assert implementation details (method calls, internal state, call order).
3. **Missing edge cases** — Check for common gaps:
   - Empty/null/missing inputs
   - Boundary values (0, 1, max)
   - Concurrent operations
   - Permission/authorization boundaries
   - Timeout and failure modes
   - Unicode / special characters (where applicable)
4. **Redundant scenarios** — Flag scenarios that test the same behavior with trivially different inputs.

If no Acceptance Scenarios section exists, flag this as a critical gap.

### Phase 4 — Ambiguity and Contradiction Detection

Scan for:

- **Ambiguous language** — "should", "might", "ideally", "as appropriate", "etc." — these create undefined behavior that leads to undertested code
- **Contradictions** — Two sections that imply different behavior for the same scenario
- **Implicit requirements** — Behaviors implied by the design but never stated (e.g., creation described but duplicate creation unaddressed)
- **Missing error handling** — Happy path described but failure modes absent

### Phase 5 — Spec Summary

Output: overall testability (High/Medium/Low), critical issues blocking downstream work, improvement suggestions, and a Ready for /plan verdict (Yes/No with conditions).

---

## Mode: Plan Review

For reviewing execution plans (dependency graphs produced by `/plan`).

### Phase 1 — Dependency Graph Validation

Parse the plan's task graph and check:

1. **No cycles** — Follow dependency chains; report any circular dependencies
2. **No orphaned nodes** — Every task referenced as a dependency must exist as a defined task
3. **No dangling dependencies** — Every dependency listed for a task must be defined in the plan
4. **Stream structure** — If the plan uses parallel streams, verify they are labeled and organized

Report graph issues as critical — a broken graph blocks `/run`.

### Phase 2 — Triplet Completeness

Every TDD cycle should have a complete RED-GREEN-REFACTOR triplet. Check:

1. **Every RED has a GREEN** — A failing test (RED) must be followed by an implementation task (GREEN) that makes it pass
2. **REFACTOR is explicit** — Every GREEN should be followed by either a REFACTOR task with specific direction, or an explicit skip notation (e.g., "REFACTOR: skip — minimal implementation, nothing to clean up")
3. **RED tasks contain test specifications** — RED nodes should describe what test to write and what behavior it verifies, not just "write test"

Flag incomplete triplets as warnings.

### Phase 3 — Scenario Coverage

Map plan tasks back to spec acceptance scenarios:

1. **Parse scenario IDs** — Extract S1, S2, S3... references from plan tasks
2. **Build coverage matrix** — Which tasks cover which scenarios?
3. **Flag uncovered scenarios** — Any spec scenario (S1, S2...) not referenced by at least one RED task
4. **Flag orphan tasks** — Tasks that don't map to any acceptance scenario (may be legitimate infrastructure tasks — note but don't auto-flag as errors)

Output as a coverage matrix table: Scenario | RED Task(s) | GREEN Task(s) | Status (Covered/MISSING).

### Phase 4 — Stream Independence

If the plan defines parallel streams:

1. **Check for shared dependencies** — Two streams claiming to be parallel should not have tasks that depend on each other
2. **Check for resource conflicts** — Parallel streams modifying the same files or modules may cause merge conflicts during `/run`
3. **Suggest reordering** if dependencies are found between parallel streams

### Phase 5 — RED Node Quality

For each RED task, apply test desiderata principles (read `../../references/test-desiderata.md`):

- Does the test description specify **observable behavior** (not implementation details)?
- Is the test **specific** enough to write directly from the description?
- Is the test **structure-insensitive** — will it survive refactoring?

Flag RED tasks that describe implementation-coupled tests.

### Phase 6 — Plan Summary

Output: graph validation stats (nodes, dependencies, cycles, orphans), triplet completeness ratio, scenario coverage matrix, and a Ready for /run verdict (Yes/No with conditions).

---

## Mode: Test Review

For reviewing existing test files. Uses Beck's Test Desiderata as the primary framework. Read `../../references/test-desiderata.md` for full definitions and `../../references/anti-patterns.md` for smell detection patterns.

### Phase 1 — Desiderata Audit

Score every test against Beck's 12 Test Desiderata properties (Isolated, Composable, Deterministic, Fast, Writable, Readable, **Behavioral**, **Structure-insensitive**, Automated, Specific, Predictive, Inspiring). Use a table with Score and Notes columns.

**Behavioral** and **Structure-insensitive** are the two critical properties. Any test scoring poorly on either is high priority for refactoring.

Exception: some structure-sensitive tests are legitimate — tests verifying middleware ordering, decorator composition, or event emission for monitoring. Acknowledge these cases rather than automatically flagging them.

Present a **summary scorecard** first, then detailed per-test findings.

### Phase 2 — Smell Detection

Scan for the anti-patterns listed in `../../references/anti-patterns.md`. Categorize findings by severity:

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

### Phase 3 — Coverage Gap Analysis

1. **List the behaviors** the production code implements (scan function signatures, branches, error handling)
2. **Map tests to behaviors** — which tests cover which behaviors?
3. **Flag gaps** — behaviors with zero test coverage, especially error paths and edge cases
4. **Flag redundancy** — multiple tests asserting the exact same thing (wasted maintenance cost)

Present gaps as a prioritized list, ranked by risk (public API > internal helpers, error paths > happy paths already covered).

### Phase 4 — Refactoring Plan

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

### Phase 5 — Refactored Code (optional)

If the user wants refactored code (not just a report), apply the refactoring plan:

1. Never change test behavior while refactoring structure — one hat at a time (Beck)
2. If the refactoring changes WHAT is being tested (not just HOW), note the change explicitly and confirm with the user before applying
3. Group tests by behavior, not by class or method
4. Ensure each test name describes the behavioral scenario being verified

### Phase 6 — Before/After Summary

Output a desiderata score improvement table (Before/After percentages per property) and a numbered list of key changes (mocks removed, fixtures inlined, tests renamed, edge cases added, flaky tests fixed).

Skip Phases 5-6 for a quick review. Ask whether to proceed with refactoring after delivering Phases 1-4.

---

## Mode: Implementation Review

Lightweight review of implementation code against its spec and plan.

### Phase 1 — Spec Cross-Check

If a spec is available (check `specs/` for a matching ID or ask the user):

1. **Map acceptance scenarios to code** — For each scenario S1, S2..., identify the code path that implements it
2. **Flag unimplemented scenarios** — Scenarios with no corresponding code path
3. **Flag extra behaviors** — Code paths that don't correspond to any spec scenario (scope creep or missing spec updates)
4. **Check error handling** — Verify that error scenarios from the spec have corresponding error handling in the implementation

### Phase 2 — Plan Cross-Check

If a plan is available (check `plans/` for a matching ID):

1. **Task completion status** — Which plan tasks appear to be implemented?
2. **Skipped tasks** — Any tasks with no corresponding implementation
3. **Out-of-order work** — Implementation that appears to skip RED (no test) or GREEN (no implementation for a written test)

### Phase 3 — Code Quality Flags

Scan the implementation for common issues regardless of spec/plan availability:

- **Stubs** — `NotImplementedError`, `pass`, `TODO`, `FIXME`, `HACK`, `raise NotImplemented`
- **Missing error handling** — Bare `except:`, `catch(e) {}`, missing null checks on external data
- **Untested behaviors** — Public methods or exported functions with no corresponding test (check nearby test files)
- **Dead code** — Unreachable branches, unused imports, commented-out code blocks

### Phase 4 — Implementation Summary

Output: spec alignment (scenarios implemented/total, unimplemented list, extra behaviors), plan progress (tasks completed/total, skipped list), code quality counts (stubs, missing error handling, untested public methods), and a Ready for /commit verdict.

---

## Handling Partial Context

The review adapts to available context. Test code only: assess Readable, Isolated, Deterministic, Specific, naming, mock patterns — flag where production code is needed for Behavioral/Structure-insensitive. Test + production code: full desiderata review. Test + spec: ideal — verify behavioral coverage and gaps. Impl only: code quality flags (stubs, error handling, dead code). Impl + spec: full scenario cross-check.

## Handling Large Files

For large test suites or multi-file reviews: ask the user to scope to specific files, or prioritize the most problematic areas (highest mock count, largest setup blocks). Offer a **summary-only mode** (Phases 1-3 without refactored code) so the user can decide where to invest.

## Relationship to Other Skills

`/review` is a standalone quality gate that can be invoked at any point:

```
/spec  -->  /review --type=spec   (second opinion on spec testability)
/plan  -->  /review --type=plan   (validate graph before /run)
/run   -->  /review --type=test   (audit generated tests)
/run   -->  /review --type=impl   (check implementation coverage)
```

It complements but does not replace the main workflow chain:
```
/spec → /plan → /run → /refactor → /commit
```

Note: `/spec` includes a built-in self-review for testability. Use `/review` on specs when you want an independent second opinion, or when reviewing specs that were written without the `/spec` skill.

## General Guidelines

- Always read the referenced files (`../../references/test-desiderata.md` and `../../references/anti-patterns.md`) before starting a test review
- Be concrete — reference specific line numbers, function names, and file paths in findings
- Prioritize findings — critical issues first, suggestions last
- Be opinionated but fair — acknowledge when a pattern that looks like a smell is actually justified
- For test reviews, the goal is behavioral tests that survive refactoring — this is the north star
- For spec reviews, the goal is unambiguous, testable requirements — every requirement should map to a test
- For plan reviews, the goal is a valid, complete graph that `/run` can execute without issues
- For implementation reviews, the goal is verifying that the spec contract is fulfilled

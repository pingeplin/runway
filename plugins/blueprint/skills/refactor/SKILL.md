---
name: refactor
description: Refactor production code with a given direction while keeping all tests green. Follows Kent Beck's "two hats" discipline — change structure OR behavior, never both at once. Use when the user asks to refactor, restructure, extract, inline, rename, or reorganize production code after tests are passing.
argument-hint: [direction or goal, e.g. "extract payment logic into a service"]
---

# Refactor

Refactor production code safely, guided by a human-provided direction, with tests as the safety net.

## Core Principle: Two Hats

Beck's "two hats" rule: at any moment, you are either **changing behavior** (adding features, fixing bugs) or **changing structure** (refactoring). Never both at once.

This skill wears the **structure hat only**. If the refactoring requires behavior changes, stop and tell the user — they need to decide whether to change behavior first (with new tests) or adjust the refactoring goal.

## Workflow

### Phase 1 — Understand the Direction

Parse the user's refactoring direction from `$ARGUMENTS` or conversation context. Common directions:

- **Extract** — Pull code into a new function, class, module, or service
- **Inline** — Collapse an unnecessary abstraction back into its caller
- **Move** — Relocate code to a more appropriate module/package
- **Rename** — Change names to better reflect purpose
- **Simplify** — Reduce complexity without changing behavior
- **Decompose** — Break a large unit into smaller, focused units
- **Consolidate** — Merge duplicated logic into a shared implementation

If the direction is unclear, ask the user before proceeding.

### Phase 2 — Assess the Safety Net

Before making any changes, verify the test coverage:

1. **Run the existing tests** — they must all pass. If tests are failing, stop. Refactoring on a red test suite is unsafe.

2. **Identify coverage of the target code** — read the test files that exercise the code being refactored. Understand what behaviors are currently verified.

3. **Flag coverage gaps** — if the code being refactored has significant untested behavior, warn the user:
   ```
   ⚠️ The following behaviors in [file] have no test coverage:
   - [behavior 1]
   - [behavior 2]
   Refactoring without tests risks undetected behavior changes.
   Recommend: add tests for these behaviors first, then refactor.
   ```

4. **Decide whether to proceed** — if coverage is adequate, proceed. If not, recommend writing tests first and ask the user how to proceed.

### Phase 3 — Plan the Refactoring

Present a concrete plan before executing. The plan should be a sequence of small, individually-safe steps:

```
## Refactoring Plan

**Direction:** {user's stated goal}
**Target:** {file(s) being refactored}
**Safety net:** {test file(s) providing coverage}

### Steps
1. {Step — e.g., "Create PaymentService class in src/services/payment.py"}
2. {Step — e.g., "Move calculate_total() from OrderController to PaymentService"}
3. {Step — e.g., "Update OrderController to delegate to PaymentService"}
4. {Step — e.g., "Update imports in affected modules"}
5. {Step — e.g., "Run tests to verify no behavior change"}

### Behavior preservation check
- {Assertion: "OrderController.checkout() still returns the same response shape"}
- {Assertion: "Tax calculation logic is unchanged"}

### Risk areas
- {Risk: "Shared state in X may cause issues when moved"}
```

Wait for user confirmation before executing.

### Phase 4 — Execute the Refactoring

Apply each step from the plan. After each meaningful step:

1. **Verify tests still pass** — run the relevant test suite
2. **If a test breaks** — stop immediately. The break means either:
   - The refactoring accidentally changed behavior → undo the step and try a different approach
   - The test is structure-sensitive → flag it for the user (this is a test quality issue, not a refactoring issue). Do NOT modify the test to make it pass without user approval.

**Rules during execution:**
- Do NOT add new behavior, features, or functionality
- Do NOT change function signatures that are part of the public API without flagging it
- Do NOT "improve" code beyond what the direction asks for
- Do NOT modify tests to accommodate structural changes — if a test breaks on a pure refactoring, that test is structure-sensitive and should be flagged
- Do NOT delete tests, even if they seem redundant after refactoring

### Phase 5 — Verification and Summary

After completing all steps:

1. **Run the full test suite** — all tests must pass
2. **Present a summary:**

```
## Refactoring Summary

**Direction:** {goal}
**Files changed:** {list}
**Tests status:** All passing ✅

### What changed (structure)
- {Change 1 — e.g., "Extracted PaymentService from OrderController"}
- {Change 2}

### What did NOT change (behavior)
- {Preserved behavior 1}
- {Preserved behavior 2}

### Structure-sensitive tests found
- {Test name — broke on refactoring despite no behavior change. Consider reviewing with /review}

### Suggested follow-ups
- {e.g., "Run /review on the affected test files to check for structure sensitivity"}
- {e.g., "Consider extracting the tax logic next — it's now isolated enough"}
```

## Handling Structure-Sensitive Tests

When a test breaks during refactoring but behavior hasn't changed, this reveals a structure-sensitive test (AP-1 in the anti-patterns guide). This is valuable diagnostic information.

**Do NOT** silently fix the test. Instead:
1. Revert the refactoring step that broke the test
2. Flag the test to the user with an explanation
3. Ask whether to:
   - Fix the test first (make it behavioral), then resume refactoring
   - Skip that refactoring step
   - Proceed anyway with user-approved test modification

This feedback loop between refactoring and test quality is a key part of Beck's methodology — "difficult-to-write tests are the canary in the bad interface coal mine," and tests that break on refactoring are the canary in the structure-sensitive test coal mine.

## Relationship to Other Skills

This skill runs after implementation, before committing:

```
/spec → /plan → /run → /refactor → /commit
```

If the refactoring reveals structure-sensitive tests, suggest `/review` to clean them up.

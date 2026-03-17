# Implementation Review Methodology

Review implementation code against its spec and plan for completeness, correctness, and quality. Apply these phases in order.

## Phase 1 — Spec Cross-Check

If a spec is available (check `specs/` for a matching ID or ask the user):

1. **Map acceptance scenarios to code** — For each scenario S1, S2..., identify the code path that implements it
2. **Flag unimplemented scenarios** — Scenarios with no corresponding code path
3. **Flag extra behaviors** — Code paths that don't correspond to any spec scenario (scope creep or missing spec updates)
4. **Check error handling** — Verify that error scenarios from the spec have corresponding error handling in the implementation

## Phase 2 — Plan Cross-Check

If a plan is available (check `plans/` for a matching ID):

1. **Task completion status** — Which plan tasks appear to be implemented?
2. **Skipped tasks** — Any tasks with no corresponding implementation
3. **Out-of-order work** — Implementation that appears to skip RED (no test) or GREEN (no implementation for a written test)

## Phase 3 — Code Quality Flags

Scan the implementation for common issues regardless of spec/plan availability:

- **Stubs** — `NotImplementedError`, `pass`, `TODO`, `FIXME`, `HACK`, `raise NotImplemented`
- **Missing error handling** — Bare `except:`, `catch(e) {}`, missing null checks on external data
- **Untested behaviors** — Public methods or exported functions with no corresponding test (check nearby test files)
- **Dead code** — Unreachable branches, unused imports, commented-out code blocks

## Phase 4 — Implementation Summary

Output: spec alignment (scenarios implemented/total, unimplemented list, extra behaviors), plan progress (tasks completed/total, skipped list), code quality counts (stubs, missing error handling, untested public methods), and a Ready for /commit verdict.

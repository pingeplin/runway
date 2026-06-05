# Implementation Review Methodology

Review implementation code against its spec for completeness, correctness,
and quality. Assume nothing about how the code was produced — which agent
wrote it, in what order, with what discipline. Judge the result, not the
process. Apply these phases in order.

## Phase 1 — Spec Cross-Check

If a spec is available (check `.blueprint/specs/` for a matching ID or ask
the user):

1. **Map acceptance scenarios to code** — For each scenario S1, S2…, identify the code path that implements it.
2. **Flag unimplemented scenarios** — Scenarios with no corresponding code path.
3. **Flag extra behaviors** — Code paths that don't correspond to any spec scenario (scope creep or a missing spec update).
4. **Check error handling** — Verify that error scenarios from the spec have corresponding error handling in the implementation.

## Phase 2 — Code Quality Flags

Scan the implementation for common issues regardless of spec availability:

- **Stubs** — `NotImplementedError`, `pass`, `TODO`, `FIXME`, `HACK`, `raise NotImplemented`
- **Missing error handling** — Bare `except:`, `catch(e) {}`, missing null checks on external data
- **Untested behaviors** — Public methods or exported functions with no corresponding test (check nearby test files)
- **Dead code** — Unreachable branches, unused imports, commented-out code blocks
- **Stale or low-value comments and docstrings** — Flag any of the following:
  - **Stale docstring** — a function/method docstring whose described arguments, return type, raised errors, or behavior no longer match the current signature or implementation. Fix: update or delete.
  - **Restated *what*** — comments or docstrings that paraphrase what well-named code already shows (e.g. `# increment counter` above `counter += 1`, or a docstring that just re-narrates the function body). Fix: delete; if a real *why* is buried in there, keep only that line.
  - **Task-referential rot** — comments naming a ticket, fix, or caller ("added for the X migration", "used by handler Y"). Fix: delete; that context belongs in the commit message or PR description.
  - **Commented-out code** — leftover blocks the author meant to clean up. Fix: delete (git remembers).

  Function and method docstrings explaining purpose, contracts, or non-obvious behavior are still encouraged — the issue is rot, not their presence.

## Phase 3 — Implementation Summary

Output: spec alignment (scenarios implemented/total, unimplemented list,
extra behaviors), code-quality counts (stubs, missing error handling,
untested public methods, comment/docstring rot), and an overall assessment.
When this methodology is applied by the `referee` agent, these flags feed
its implementation-quality check; flag only, and leave fixes to the human or
the implementing agent.

# Plan Review Methodology

Review an execution plan (dependency graph of behavioral slices) for
validity, completeness, and executability. Apply these phases in order.

## Phase 1 — Dependency Graph Validation

Parse the plan's slice graph and check:

1. **No cycles** — Follow dependency chains; report any circular dependencies
2. **No orphaned references** — Every slice referenced as a dependency must exist as a defined slice
3. **No dangling dependencies** — Every dependency listed for a slice must be defined in the plan
4. **Stream structure** — If the plan uses parallel streams, verify they are labeled and organized

Report graph issues as critical — a broken graph blocks `/run`.

## Phase 2 — Slice Completeness

Every slice must be self-contained enough for `/run` to execute. Check:

1. **Every slice has `Scenarios:`** — at least one S-ID, and every S-ID
   listed must exist in the paired spec.
2. **Every slice has `Tests:`** — at least one test entry. Each test is a
   behavioral bullet with a type hint (`[example]` or `[property]`) and a
   prose description in Given/When/Then form, with the relevant S-IDs in
   parentheses at the end.
3. **Every test references at least one S-ID from the slice's `Scenarios:`** —
   no orphan tests inside the slice.
4. **Every slice has an `Implementation:` target** — at least one bullet
   describing what the code must achieve, in behavioral terms (no specific
   file, class, or function names).
5. **Every slice has `Done when:` and `Scope:`** lines.
6. **Tests describe behavior, not test code** — slice tests are prose
   descriptions only. If a `Tests:` bullet contains executable code (def,
   function, assert, fixture), it must be rewritten as behavioral prose.
   `/run` writes the actual tests after reading the codebase.

Flag incomplete slices as warnings or auto-fix where possible.

## Phase 3 — Scenario Coverage Check (lightweight)

For every S-ID present in the spec, verify it appears in at least one
slice's `Scenarios:` line.

- All covered → pass.
- Any missing → list under "Needs Human Input". **Do not auto-add a slice**
  for the missing scenario — placement (which stream, what slice size,
  what implementation target) requires human judgment.

This is a binary upstream check, not a full matrix. The full
scenario↔test coverage matrix lives in `run-evaluator` (Step 3),
which runs against actual tests after `/run` completes — that is the
authoritative coverage check.

## Phase 4 — Stream Independence

If the plan defines parallel streams:

1. **Check for shared dependencies** — Two streams claiming to be parallel
   should not have slices that depend on each other.
2. **Check for resource conflicts** — Parallel streams modifying the same
   files or modules may cause merge conflicts during `/run`.
3. **Suggest reordering** if cross-stream dependencies are found between
   slices that the plan marks parallelizable.

## Phase 5 — Test Description Quality

For each slice's `Tests:` bullets, apply test desiderata principles (see
`test-desiderata.md`):

- Does the description specify **observable behavior** (not implementation
  details)?
- Is the description **specific** enough — with concrete input/output
  examples — for `/run` to write a test from it?
- Is it **structure-insensitive** — would the described test survive
  refactoring?
- Does it avoid prescribing implementation details (specific files, class
  names, libraries)?

Flag test descriptions that are implementation-coupled or too vague to
write a test from. Apply anti-pattern checks **AP-1** (structure-sensitive
assertions) and **AP-8** (unclear test naming) by reading the descriptions
as if they were already test bodies — does the prose hint at structure
sensitivity? Does it hint at a meaningful test name?

## Phase 6 — Plan Summary

Output:

- Graph validation stats (slices, dependencies, cycles, orphans)
- Slice completeness ratio (slices fully specified / total)
- Scenario coverage check result (all covered / N missing)
- A "Ready for /run" verdict (Yes / No / Yes-with-conditions)

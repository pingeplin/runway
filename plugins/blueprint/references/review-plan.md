# Plan Review Methodology

Review an execution plan (dependency graph of TDD triplets) for validity, completeness, and executability. Apply these phases in order.

## Phase 1 — Dependency Graph Validation

Parse the plan's task graph and check:

1. **No cycles** — Follow dependency chains; report any circular dependencies
2. **No orphaned nodes** — Every task referenced as a dependency must exist as a defined task
3. **No dangling dependencies** — Every dependency listed for a task must be defined in the plan
4. **Stream structure** — If the plan uses parallel streams, verify they are labeled and organized

Report graph issues as critical — a broken graph blocks `/run`.

## Phase 2 — Triplet Completeness

Every TDD cycle should have a complete RED-GREEN-REFACTOR triplet. Check:

1. **Every RED has a GREEN** — A failing test (RED) must be followed by an implementation task (GREEN) that makes it pass
2. **REFACTOR is explicit** — Every GREEN should be followed by either a REFACTOR task with specific direction, or an explicit skip notation (e.g., "REFACTOR: skip — minimal implementation, nothing to clean up")
3. **RED tasks contain test specifications** — RED nodes should describe what test to write and what behavior it verifies, not just "write test"

Flag incomplete triplets as warnings.

## Phase 3 — Scenario Coverage

Map plan tasks back to spec acceptance scenarios:

1. **Parse scenario IDs** — Extract S1, S2, S3... references from plan tasks
2. **Build coverage matrix** — Which tasks cover which scenarios?
3. **Flag uncovered scenarios** — Any spec scenario (S1, S2...) not referenced by at least one RED task
4. **Flag orphan tasks** — Tasks that don't map to any acceptance scenario (may be legitimate infrastructure tasks — note but don't auto-flag as errors)

Output as a coverage matrix table: Scenario | RED Task(s) | GREEN Task(s) | Status (Covered/MISSING).

## Phase 4 — Stream Independence

If the plan defines parallel streams:

1. **Check for shared dependencies** — Two streams claiming to be parallel should not have tasks that depend on each other
2. **Check for resource conflicts** — Parallel streams modifying the same files or modules may cause merge conflicts during `/run`
3. **Suggest reordering** if dependencies are found between parallel streams

## Phase 5 — RED Node Quality

For each RED task, apply test desiderata principles (see `test-desiderata.md`):

- Does the test description specify **observable behavior** (not implementation details)?
- Is the test **specific** enough to write directly from the description?
- Is the test **structure-insensitive** — will it survive refactoring?

Flag RED tasks that describe implementation-coupled tests.

## Phase 6 — Plan Summary

Output: graph validation stats (nodes, dependencies, cycles, orphans), triplet completeness ratio, scenario coverage matrix, and a Ready for /run verdict (Yes/No with conditions).

---
name: review
description: Review any project artifact for quality, completeness, and correctness — specs, plans, test files, or implementation code. ALWAYS use this skill when the user asks to review, check, audit, or assess quality of any code or document. Trigger on "review my spec", "check the tests", "audit the plan", "review my implementation", "check for anti-patterns", "score tests against desiderata", "is this testable?", "did I miss anything?", or any request to evaluate quality of specs, plans, tests, or code against best practices. Even casual requests like "take a look at this" or "what do you think of these tests?" should trigger this skill.
argument-hint: '[path-to-file] [--type=spec|plan|test|impl]'
---

# Review

Review any project artifact with a single command. Auto-detects the artifact type, reads the appropriate review methodology from `references/`, and applies it. Produces a full report without modifying the artifact.

## Type Detection

Determine the artifact type from the file path, content, or explicit `--type` override:

| Signal | Type | Methodology |
|--------|------|-------------|
| `.blueprint/specs/*.md` | **spec** | Read `../../references/review-spec.md` |
| `docs/designs/*.md` | **design** | Read `../../references/review-design.md` |
| `.test.`, `_test.`, `test_`, `tests/`, `__tests__/` in path | **test** | Read `../../references/review-test.md` |
| `--type=spec\|design\|test\|impl` in `$ARGUMENTS` | **explicit override** | Read the corresponding reference file |
| None of the above | **impl** | Read `../../references/review-impl.md` |

If the type cannot be determined, ask the user.

## Finding the File

If `$ARGUMENTS` contains a file path, read that file. Otherwise check for the most recently modified file in `.blueprint/specs/`, `docs/designs/`, or `tests/`. If nothing found, ask the user.

## Workflow

1. **Detect type** using the table above.
2. **Read the methodology file** — the reference file contains the full phase-by-phase review process.
3. **Read supporting references** as needed:
   - Test reviews: also read `../../references/test-desiderata.md` and `../../references/anti-patterns.md`
4. **Apply all phases** from the methodology file in order.
5. **Output findings** using the shared output structure below.

## Shared Output Structure

All review modes use this wrapper — mode-specific content goes in "Findings":

```
## Review: {type} -- {file name}

### Summary
**Type:** Spec / Design / Test / Implementation
**Overall quality:** High / Medium / Low
**Critical issues:** {N}  |  **Warnings:** {N}

### Findings
(phase-by-phase content from the methodology file)

### Recommendations
- [ ] {actionable item with file path}
```

## Handling Partial Context

The review adapts to available context. Test code only: assess Readable, Isolated, Deterministic, Specific, naming, mock patterns — flag where production code is needed for Behavioral/Structure-insensitive. Test + production code: full desiderata review. Test + spec: ideal — verify behavioral coverage and gaps. Impl only: code quality flags (stubs, error handling, dead code). Impl + spec: full scenario cross-check.

## Handling Large Files

For large test suites or multi-file reviews: ask the user to scope to specific files, or prioritize the most problematic areas (highest mock count, largest setup blocks). Offer a **summary-only mode** (early phases without refactored code) so the user can decide where to invest.

## Relationship to Other Skills

`/review` serves two roles:

**1. Shared methodology** — The review reference files (`references/review-*.md`) are the single source of truth for review logic. The independent evaluator subagents (`agents/design-evaluator.md`, `agents/spec-evaluator.md`, `agents/referee.md`) and this standalone skill all read the same files. Update a reference file once, all consumers benefit.

**2. Independent evaluator subagents** — Each producing/refereeing skill dispatches a fresh-context evaluator as its final step. `/design` dispatches `design-evaluator`; `/spec` dispatches `spec-evaluator`; `/verify` dispatches the `referee`. Each gets fresh context with no sunk-cost bias and applies the relevant methodology. This follows Anthropic's harness-design principle: separate the generator from the evaluator. For `/design` and `/spec`, the evaluator runs a fix loop — editing the artifact directly to resolve autonomous issues and surfacing only what needs human input. The `referee` (behind `/verify`) is read-only: it judges the produced code against the spec and reports; it never edits.

**3. Standalone quality gate** — `/review` can also be invoked directly at any point for an on-demand audit:

```
/spec     -->  /review --type=spec   (second opinion on spec testability)
implement -->  /review --type=test   (audit the produced tests)
implement -->  /review --type=impl   (check implementation coverage)
```

For the full post-implementation gate — coverage, anti-vacuity, desiderata, and quality together — use `/verify`, not `/review`. Standalone `/review` is a lighter, single-lens, read-only audit you can run any time.

The main workflow chain:
```
[/design] → /spec → ⟦ any coding agent implements ⟧ → /verify → /commit
    ↓         ↓                                          ↓
    └── design-evaluator, spec-evaluator, and the referee run in fresh context
```

## General Guidelines

- Be concrete — reference specific line numbers, function names, and file paths in findings
- Prioritize findings — critical issues first, suggestions last
- Be opinionated but fair — acknowledge when a pattern that looks like a smell is actually justified
- For test reviews, the goal is behavioral tests that survive refactoring — this is the north star
- For spec reviews, the goal is unambiguous, testable requirements — every requirement should map to a test
- For implementation reviews, the goal is verifying that the spec contract is fulfilled

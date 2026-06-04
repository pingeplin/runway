---
name: verify
description: Referee an implementation against its spec — the post-implementation gate of the blueprint workflow. ALWAYS use this skill after any coding agent (or a human) has implemented a spec, when the user wants to verify the implementation, referee the result, check that the code satisfies the spec, check scenario coverage, ask "are these tests actually testing anything?", "did the agent really build what the spec asked?", "is this vacuous?", or run the final quality gate before /commit. Works regardless of which agent produced the code — blueprint does not need to have driven the implementation.
argument-hint: '[path-to-spec] [optional-base-git-ref]'
---

# Verify

Referee a finished implementation against its spec. `/verify` is the
**referee** end of blueprint's producer→referee architecture: `/design` and
`/spec` produce the contract, any coding agent satisfies it, and `/verify`
decides whether it actually did — no matter how the code was built.

## Where this fits

```
/design ──→ /spec ──→ ⟦ any coding agent implements ⟧ ──→ /verify ──→ /commit
                                                              ▲
                                              you are here — the gate
```

`/verify` does **not** assume blueprint drove the implementation. The agent
that wrote the code may have been Claude Code, Codex, Cursor, a human, or
anything else. The spec is the only thing `/verify` trusts; the code is
treated as code of unknown provenance.

## What it checks

`/verify` dispatches the `referee` subagent (fresh context, no sunk-cost
bias) to run five checks against the produced code + tests:

1. **Test suite** — does it run, and is it green? A red suite stops the gate.
2. **Scenario coverage** — every acceptance scenario in the spec maps to at
   least one test.
3. **Anti-vacuity (thought-mutation)** ⭐ — for each covered behavior, what
   is the smallest implementation change that would break it, and would any
   test catch that break? Covered-but-vacuous scenarios are flagged. This is
   the check that replaces TDD's fail-first guarantee with a
   procedure-independent one.
4. **Test Desiderata** — scores tests against Kent Beck's properties
   (`references/test-desiderata.md`) and the anti-patterns checklist
   (`references/anti-patterns.md`).
5. **Implementation quality** — flags stale docstrings, restated-*what*
   comments, dead code, stubs (`references/review-impl.md`).

The desiderata + anti-patterns references are the **same** files `/spec`
bundles as generator guidance — the contract and the rubric are one list
read from two ends.

## Inputs

- **Spec** — if `$ARGUMENTS` names a spec path, use it. Otherwise locate the
  most recently modified spec under `.blueprint/specs/` and confirm with the
  user. `/verify` needs **no plan file** — none exists in this workflow.
- **Base git ref (optional)** — if the user provides the commit the
  implementation started from, pass it to the referee so it can scope its
  review to `git diff {base}..HEAD`. Without one, the referee reviews the
  working tree and the files relevant to the spec's scenarios.

## Workflow

1. **Resolve the spec** (and base ref, if given) per Inputs above.
2. **Dispatch the `referee` subagent** via the `Agent` tool with
   `subagent_type: referee`. Pass the spec path and the base ref (if any) in
   the prompt. The referee runs the five checks in a fresh context.
3. **Surface the referee's report** — coverage matrix, the thought-mutation
   table, desiderata scores, implementation-quality flags, and the verdict.
4. **Recommend the next step** based on the verdict:
   - **Meets Definition of Done** (green suite, full coverage, no vacuous
     scenarios, no blocking quality flags) → recommend `/commit`.
   - **Does not meet Done** → summarize exactly what's missing — uncovered
     scenarios, covered-but-vacuous scenarios (with the surviving mutation),
     or quality blockers — as a punch list for the implementing agent's next
     pass. Do **not** fix it here; `/verify` referees, it does not build.

## Principles

- **Coverage is necessary, not sufficient.** A scenario with a test that
  wouldn't fail when the behavior breaks is not done. The thought-mutation
  check (3) is where this gate earns its keep — treat it as the headline,
  not an afterthought.
- **Honest verdict.** Until real mutation tooling backs check 3, the verdict
  is *advisory-strong*, not *proven* — say so. Don't launder a reasoning
  pass into a guarantee.
- **The referee assesses; it never edits.** Fixes are the implementing
  agent's job (or a human's). Keep generation and judgment separate.

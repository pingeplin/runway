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
bias) to run six checks against the produced code + tests. The rule is
**determinism over judgment**: a question that a tool in the repo can decide
goes to that tool, and the referee's own judgment is kept for design
questions that no tool can decide.

1. **Test suite** — does it run, and is it green? A red suite stops the gate.
2. **The repo's deterministic checks** — the formatter, linter, type checker,
   dependency/architecture rules and coverage tool that the repo already
   uses, run in check mode. A category with no tool is reported as
   `not checked`, not replaced by judgment. Nothing is installed.
3. **Scenario coverage** — every acceptance scenario in the spec, named by
   its title, maps to at least one test.
4. **Anti-vacuity** ⭐ — would any test catch the smallest break of each
   covered behavior? The repo's mutation tool answers first (a *proven*
   result); thought-mutation answers only where no tool does (an
   *advisory-strong* result). Covered-but-vacuous scenarios are flagged.
   This is the check that replaces TDD's fail-first guarantee with a
   procedure-independent one.
5. **Test Desiderata** — scores tests against the repo's own test
   conventions first, then Kent Beck's properties
   (`${CLAUDE_PLUGIN_ROOT}/references/test-desiderata.md`) and the
   anti-patterns checklist (`${CLAUDE_PLUGIN_ROOT}/references/anti-patterns.md`)
   where the repo is silent.
6. **Design judgment** — checks the code against the repo's own design
   principles (`CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, ADRs, design
   docs), then the spec's Interface Contract, then the plugin's principles
   (`${CLAUDE_PLUGIN_ROOT}/references/review-impl.md`).

The test-quality principles `/spec` writes into every spec are drawn from
the **same** desiderata + anti-patterns references — the contract and the
rubric are one list read from two ends.

## Inputs

- **Spec** — if `$ARGUMENTS` names a spec path, use it. Otherwise locate the
  most recently modified spec under `.blueprint/specs/` and confirm with the
  user.
- **Base git ref (optional)** — if the user provides the commit the
  implementation started from, pass it to the referee so it can scope its
  review to `git diff {base}..HEAD`. Without one, the referee reviews the
  working tree and the files relevant to the spec's scenarios.

## Workflow

1. **Resolve the spec** (and base ref, if given) per Inputs above.
2. **Dispatch the `referee` subagent** via the `Agent` tool with
   `subagent_type: referee`. Pass the spec path and the base ref (if any) in
   the prompt. The referee runs the six checks in a fresh context.
   **Do not end the turn while that dispatch is outstanding** — see
   *Running headless* below before you dispatch.
3. **Surface the referee's report** — the deterministic-check table, the
   coverage matrix, the anti-vacuity table, desiderata scores, design flags,
   and the verdict. Name every scenario by its title.
4. **Recommend the next step** based on the verdict:
   - **Meets Definition of Done** (green suite, clean deterministic checks,
     full coverage, no vacuous scenarios, no blocking design flags) →
     recommend `/commit`.
   - **Does not meet Done** → summarize exactly what's missing — failing
     tool checks, uncovered scenarios, covered-but-vacuous scenarios (with
     the surviving mutation), or design blockers — as a punch list, with
     each scenario named by its title, for the implementing agent's next
     pass. Do **not** fix it here; `/verify` referees, it does not build.

## Running headless

Dispatching the referee costs nothing interactively — the subagent finishes and
notifies you. **Non-interactively it loses the whole run.** A subagent is
background work; `claude -p` waits a bounded time for background work and then
terminates it, so the turn ends with no report, after the tokens are spent. The
tell is a run that finishes in ~5 turns instead of ~50.

**How to tell.** You cannot see how you were launched, so decide from what is
in front of you. Treat the run as headless when the caller's instructions say
nobody will read a question, approve a gate or receive a notification; when
you are told to write your result to a named file rather than reply; or when
no interactive tool is available to you. **If you genuinely cannot tell, ask
whether a notification could reach anyone — and if the answer is "probably
not", go inline.** A verdict produced inline is worth more than a dispatch
that gets killed.

So, when there is no human in the loop — `claude -p`, a CI step, a benchmark
harness, any run where nothing will deliver a notification:

- **Run the six checks inline, in this session.** Do not dispatch, and do not
  wait on a notification that is not coming.
- **Do not end the reply until the report exists** — on disk if the caller
  named an output path, otherwise in the reply itself.
- **Say what was traded.** Inline execution gives up the fresh-context
  independence that step 2 buys; the verdict is still honest, but it was
  produced by the agent that has been reading this conversation. Note it in the
  report rather than letting the reader assume separation that did not happen.

Interactive sessions keep the dispatch — the independence is worth more there,
and it costs nothing.

## Principles

- **Coverage is necessary, not sufficient.** A scenario with a test that
  wouldn't fail when the behavior breaks is not done. The anti-vacuity
  check (4) is where this gate earns its keep — treat it as the headline,
  not an afterthought.
- **Determinism over judgment.** A tool result beats a reading of the code.
  Where the repo has no tool, say `not checked` or label the verdict
  *advisory-strong* — never present a reasoning pass as a tool result.
- **The repo's principles come first.** The plugin's references fill the
  gaps the repo leaves; they do not override it.
- **The referee assesses; it never edits.** Fixes are the implementing
  agent's job (or a human's). Keep generation and judgment separate.
- **Output guideline.** Keep the report and the punch list 80% of the way to
  ASD-STE100 (Simplified Technical English).

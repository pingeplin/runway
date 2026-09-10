# blueprint

An **intent producer + invariant referee** for Claude Code, with one bounded loop at every stage:

```
/design ⟲ ──→ /spec ⟲ ──→ ⟦ implement ⟲ /verify ⟧ ──→ /commit
```

Blueprint does not drive your implementation. It produces the **intent** (a human-facing design doc and an agent-executable spec contract), hands the build off to whatever coding agent works best — Claude Code, Codex, Cursor, a teammate — and then **referees the result** against the spec, no matter how the code was produced. Each ⟲ is the same produce → judge → revise loop: a fresh judge reports, the producer rewrites the whole artifact, up to three rounds, and the human reviews once at the exit.

Grounded in Kent Beck's Test Desiderata and Canon TDD. **Tests remain the durable behavioral contract** — that survives from blueprint's TDD roots and is, if anything, strengthened here: the referee actively hunts for tests that *look* like they verify behavior but wouldn't fail if the behavior broke. See [Philosophy](#philosophy-tests-as-the-executable-spec).

## Install

```
/plugin install blueprint@runway
```

## Pipeline

```
/design ⟲ ──→ /spec ⟲ ──→ ⟦ implement ⟲ /verify ⟧ ──→ /commit
   │            │                      │
   │            │                      └─ The implement loop. Any coding agent builds;
   │            │                         the referee — on code of unknown provenance —
   │            │                         runs the suite, maps scenarios → tests, hunts
   │            │                         vacuous tests (thought-mutation), scores
   │            │                         desiderata, flags quality. Its punch list
   │            │                         feeds the next round. Human reads the verdict once.
   │            │
   │            └─ The contract. Interface + acceptance scenarios + an explicit
   │               instruction to the implementing agent + a Definition of Done
   │               worded as exactly what /verify checks. Judged by the evaluator,
   │               rewritten whole against its ledger. Tests are the durable
   │               contract; the spec is what produces them.
   │
   └─ Optional. Argue for an engineering decision. Same loop, same judge.
      Skip when the approach is already settled.
```

The architecture is **producer → judge → revise**. Blueprint owns the two brackets — the contract going in and the verdict coming out — and the loop that tightens each one. How the contract gets satisfied inside a round is the implementing agent's business. This makes the workflow portable across coding agents: intent is the portable interface; procedure is not.

### The loop

One protocol, in `references/loop.md`, for all three stages:

- **Producer** makes the whole artifact — a document, or code on the working tree.
- **Judge** is a fresh subagent every round (`evaluator` for documents, `referee` for code). It sees only the artifact and the open rows of a **ledger**; it reports, it never edits. Every finding is a `contradiction`, an `uncovered` goal-related item, or a `behavior-change` question — and a judge may add scope, never remove it (the scope rule in `references/loop.md`).
- **Revise** regenerates the whole artifact against the ledger — no local patching by a critic who has lost its freshness.
- **Stop** in this order: `READY`; round 3; stuck (nothing resolved, nothing new); `NEEDS-HUMAN` when only `behavior-change` rows remain open. Otherwise `REVISE`. The ledger is written next to the artifact as `{artifact}.ledger.md`, one snapshot per round.

The human sees the artifact, the final ledger, and any open questions once, at loop exit. Inside a loop there is no gate.

## Why this shape

Earlier blueprint versions *drove* TDD with a choreographed executor — a dependency-sliced plan, batched test writing, a failing-test commit checkpoint, a bounded fix loop. That machinery existed to compensate for model weaknesses of its moment, and it bound the workflow to one specific agent that would follow the procedure faithfully. Blueprint dropped it in 4.0:

- **Procedure is model-compensation that decays; intent is durable.** As models improve, turn-by-turn scaffolding becomes a cage. The design + spec + test-quality principles outlast any model generation.
- **"Any coding agent" is a protocol problem.** Each agent has its own internal loop. Specifying *what to build and what done means* is portable; specifying *the order and cadence of how to build it* is not.
- **The one thing TDD's procedure bought — non-vacuous tests — is re-secured without the procedure.** Instead of proving non-vacuity *by construction* (fail-first commits), the referee proves it *by inspection* (thought-mutation), which works no matter how the code was made.

5.0 keeps that shape and adds the loop, for a different reason: the evaluators that edited documents in their own context produced specs with contradictions and muddled ordering, and the implement↔verify iteration that paid off on hard tasks was driven by hand. A whole-artifact rewrite against a fresh judge's ledger fixes the first; building the loop in fixes the second. The full argument lives in `docs/designs/` (the 4.0 and 5.0 design docs), written with blueprint's own `/design`.

## Artifact definitions

`design` and `spec` are overloaded terms across the industry. These are the definitions blueprint uses. They differ in **purpose**, **audience**, and **form**.

### Design doc — `docs/designs/{id}_{name}.md`

> **An argument for an engineering decision, plus the cross-team interface contract that decision implies.**

- **Purpose**: convince reviewers that *this approach* is right over the alternatives, and surface the consequences other teams need to know about.
- **Audience**: tech lead, cross-team consumers, future engineers reading the decision archaeology, compliance/audit.
- **Form**: argumentative. Context, goals/non-goals, proposed approach, alternatives considered, load-bearing assumption, trade-offs, and the externally visible interface contract.
- **When**: when the approach itself is in question. Skip when settled.
- **Lifecycle**: relatively stable. Changes trigger re-review because downstream depends on the contract.

A design doc is **not** documentation of a decision after the fact. It is the persuasion artifact that *makes* the decision reviewable.

### Spec — `.blueprint/specs/{id}_{name}.md`

> **The agent-executable contract. You hand it to a coding agent and say "build this"; you hand it to `/verify` and say "did it?"**

- **Purpose**: carry everything the implementing agent needs and everything the referee will check — the interface contract (inherited from the design), structured acceptance scenarios, an explicit instruction to the agent ("make every scenario pass with tests that would fail if the behavior were wrong"), the bundled test-quality principles, and a Definition of Done worded as exactly what `/verify` verifies.
- **Audience**: the implementing coding agent (primary); the engineer sanity-checking what it will build (secondary); the referee.
- **Form**: structured acceptance scenarios (Given/When/Then) plus the contract and done-criteria around them.
- **When**: once the approach is settled — after `/design`, or directly when the design is obvious.
- **Lifecycle**: consumed by the implementing agent and `/verify`. Behavior changes flow through **tests**, not by editing the spec; the spec is a snapshot of intent at build time.

A spec is **not** "a more detailed design doc." Design argues a decision; spec is the build-and-check contract for the chosen one.

**Commit or not — user choice.** Blueprint writes specs to `.blueprint/specs/` by default; the directory can be `.gitignore`d.

- *Don't commit*: cleanest reflection of "tests carry the contract." No drift risk.
- *Commit (recommended)*: reviewers see a Gherkin-style summary of intent alongside the test diff, and you preserve archaeology. The committed spec is a **snapshot, not a living document** — expect drift from tests over time and accept it, because tests carry the contract forward.

## Philosophy: tests as the executable spec

Blueprint is built on the TDD insight that the tests *are* the spec — the executable, version-controlled, continuously verified definition of behavior. The `.blueprint/specs/` artifact is **not** a competing source of truth; it is the contract that gets a human and a coding agent to agree on what tests to write, and that the referee checks the result against.

Blueprint keeps this and hardens it. The risk in *any* "satisfy the spec, write good tests" handoff is a green suite that passes for the wrong reason — 100% line coverage, ~4% mutation score (Meta, FSE'25). A "good tests" guideline alone under-triggers; advisory principles describe a good test in isolation but don't certify that the *suite* would catch a break. So blueprint moves the principles from advice the generator may skip into the **referee's enforced rubric**, and adds a procedure-independent anti-vacuity check:

- **Coverage is necessary, not sufficient.** `/verify` maps every scenario to a test *and* asks, per behavior, "what's the smallest change that breaks this, and would any test catch it?"
- **The verdict is honest about its limits.** Until real mutation tooling backs the check, the referee's verdict is *advisory-strong*, not *proven* — and it says so.
- **Behavior changes flow through tests**, not spec edits. The spec's job ends when the implementation is verified.

If you want a spec-as-source-of-truth model (BDD with maintained acceptance docs), blueprint is the wrong tool — Cucumber, Concordion, or a hand-maintained acceptance suite fits better.

## Benchmark

Does handing a coding agent a blueprint spec actually change what it builds? Measured on [FeatureBench](https://github.com/LiberCoders/FeatureBench), which grades a patch against hidden fail-to-pass tests the agent never sees.

**Panel:** 5 astropy tasks, FeatureBench `fast` split, paired, single seed, single day. The implementing agent is `claude_code` / `claude-sonnet-5` in **every** arm — the only thing that differs is the problem statement it receives. All arms are scored by the unmodified `fb eval` against the official dataset. The spec writer sees a masked tree **and a masked git history** (an earlier run leaked the oracle through `git show HEAD:`; those numbers are retracted — see the harness README).

| | **A** — problem statement | **B** — + 4.0 `/spec` | **B** — + 5.0 `/spec` ⟲ | **B** — + 5.1 `/spec` ⟲ |
|---|---|---|---|---|
| Resolved (every hidden test passes) | 0 / 5 | 1 / 5 | 1 / 5 | 1 / 5 |
| Mean pass rate (fraction of hidden tests) | 0.42 | **0.84** | **0.37** | **0.70** |
| Tasks where the agent wrote any tests | 0 / 5 | 3 / 5 | 4 / 5 | 4 / 5 |
| Mutation kill rate of the agent's own tests (no tests = 0) | 0.00 | 0.22 | 0.39 | 0.29 |
| Spec cost per task | — | $15.88 | $15.36 | $18.69 |
| In-container inference per task | $5.28 | $3.84 | $3.96 | $5.67 |

**The 4.0 spec makes the agent build most of the feature instead of a fraction of it.** Pass rate doubles; three tasks go from near-zero to near-complete (`lombscargle` 0.03 → 0.96, `vo` 0.00 → 0.95). Only one fully resolves — the hidden suites are strict — but the agent is no longer building the wrong thing.

**5.1 fixes most of it.** With findings typed and the judge forbidden to narrow scope (every neighbour the code path reaches is `uncovered` and gets added, marked `[INFERRED]`), pass rate recovers to 0.70 and `vo` resolves outright (0.00 → 1.00). The remaining gap to 4.0 is one task whose 5.1 spec relabelled the same fence "Known Environment Blockers — do not attempt to fix"; the next patch names that pattern too.

**The 5.0 loop made the spec worse for this job.** Pass rate falls below no-spec. The two specs for `vo` show why: 4.0's says "other definitions stripped from the same file are in scope — restore the prerequisites first"; 5.0's fences the task to the six members the problem statement names, and the agent's closing message reads *"extensive unrelated breakage outside my assigned scope … left untouched."* FeatureBench masks a whole feature, helpers included; a spec that fences the task to the literal request fences the agent away from what the oracle needs. The evaluator loop's scope discipline — a virtue in a design review — produces exactly that fence.

**The spec is what makes the agent write tests at all.** Without one it wrote zero tests on all five tasks, under both plugin versions and in every run to date. With one it wrote tests on 3–4 of 5, and 5.0's tests kill more planted bugs than 4.0's.

### What this does not show

- **N=5, one repository, one seed.** Directional, not significant. The 4.0-vs-5.0 gap is large and consistent on three tasks, but five tasks from one codebase cannot show it generalises.
- **Nothing here measures what 5.0 was built to fix** — contradictions and muddled ordering *inside* the spec. The harness does not capture the evaluator's ledger. A 5.0 spec may be the more coherent document and the worse briefing for this benchmark's task shape.
- **The benchmark rewards broad scope.** "Restore a stripped feature" penalises fencing; a task shape where over-reaching costs points would grade the same narrowing differently.
- **This is a self-run evaluation of our own plugin.** It is not independent.

Harness, full reports and the exact task list: [`evals/blueprint-featurebench/`](../../evals/blueprint-featurebench/README.md). Every number above is regenerable from [`reports/2609_clean_paired_astropy_n5/`](../../evals/blueprint-featurebench/reports/2609_clean_paired_astropy_n5/README.md); the retracted leaky runs are kept at `reports/2608_scale_astropy_n5/` and `reports/2609_v5_astropy_n5/` with their caveats.

## Comparison

| | Design doc | Spec |
|---|---|---|
| **Question it answers** | Which approach? | What does "build this" and "is it done" mean? |
| **Form** | Argumentative | Contract: scenarios + interface + done-criteria |
| **Audience** | Cross-team, future eng, compliance | Implementing agent + engineer + referee |
| **Location** | `docs/designs/` (or Confluence) | `.blueprint/specs/` (commit optional) |
| **Durable behavioral contract?** | No — owns the *decision* | No — tests own the behavior |
| **Survives implementation?** | Yes — decision archaeology | Optional snapshot; tests carry it forward |
| **Triggers re-review when changed?** | Yes — cross-team contract | No — review gates on tests via `/verify` |

## Skills

| Skill | Role | Purpose |
|---|---|---|
| `/design` | producer | Write or critique a design doc, looping until ready. Dispatches `evaluator`. |
| `/spec` | producer | Write the agent-executable contract, looping until ready. Dispatches `evaluator`. |
| `/verify` | referee | Check produced code against the spec — coverage, anti-vacuity, desiderata, quality. Dispatches `referee`. One round standalone; the judge of the implement loop inside `/blueprint`. |
| `/commit` | utility | Write a Conventional Commits message inline, from the diff. Dispatches nothing. |
| `/blueprint` | orchestrator | Chains the pipeline, runs each stage's loop, and stops for human approval only at loop exits. Dispatches nothing itself. |

## What blueprint deliberately does *not* produce

- **PRD / product spec** — "what business problem are we solving" is upstream of blueprint. The goal is assumed given.
- **A separate technical spec document** (data models, internal API tables) — blueprint folds the externally visible interface into the design doc and the spec, and lets the internal portion emerge from the implementation.
- **An execution plan / task graph** — sequencing, slicing, and parallelization are the implementing agent's job, not a blueprint artifact.
- **Cross-team coupling / architectural-drift detection** — review concerns that require humans or external tooling.
- **Repo-specific test conventions or human-directed refactoring** — earlier versions shipped both; neither earned use, and any coding agent does them on its own with the referee gating the result.

## ID system

IDs follow arXiv-style `yymm.xxxx` and are shared across `docs/designs/` and `.blueprint/specs/` so a feature's design and spec can be matched by ID.

## Conventions

- One feature → one design doc (optional) + one spec, sharing an ID.
- Cross-team interface changes are made in the **design doc**; the spec and tests follow downstream.
- Specs are not maintained in sync with implementation post-build. Treat any committed spec as a snapshot of intent at build time, not a living contract.
- Every stage runs the loop in `references/loop.md`: produce → judge → revise, at most 3 rounds, whole-artifact rewrite each round. The judge is a fresh subagent every round — `evaluator` for documents, `referee` for code.
- `evaluator` reports and never edits; the producer rewrites. `referee` (behind `/verify`) is likewise read-only — it judges and reports, never edits.

## Migrating from 4.x

5.0 is a breaking change for anything that dispatched the removed agents by name (the two per-document evaluators, the conventions evaluator, the test runner, the commit writer) or invoked the removed skills (refactoring, standalone review, test conventions). `CHANGELOG.md` lists them. Specs and design docs written under 4.x are unchanged in format and work as-is; the loop simply judges them more strictly. External loop wrappers around implement→verify are no longer needed.

## Migrating from 3.x

4.0 was a breaking change with no automated migration: the run and plan skills and their slice/plan-graph artifacts are gone; implementation now happens in any coding agent, checked by `/verify`. Tests written under 3.x continue to work — they were always the durable artifact.

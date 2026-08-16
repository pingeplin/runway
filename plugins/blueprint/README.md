# blueprint

An **intent producer + invariant referee** for Claude Code: `design → spec → ⟦any coding agent implements⟧ → verify → commit`.

Blueprint does not drive your implementation. It produces the **intent** (a human-facing design doc and an agent-executable spec contract), hands the build off to whatever coding agent works best — Claude Code, Codex, Cursor, a teammate — and then **referees the result** against the spec, no matter how the code was produced.

Grounded in Kent Beck's Test Desiderata and Canon TDD. **Tests remain the durable behavioral contract** — that survives from blueprint's TDD roots and is, if anything, strengthened here: the referee actively hunts for tests that *look* like they verify behavior but wouldn't fail if the behavior broke. See [Philosophy](#philosophy-tests-as-the-executable-spec).

## Install

```
/plugin install blueprint@runway
```

## Pipeline

```
/design ──→ /spec ──→ ⟦ any coding agent implements ⟧ ──→ /verify ──→ /commit
   │          │                                              │
   │          │                                              └─ The referee. On code of unknown
   │          │                                                 provenance: runs the suite, maps
   │          │                                                 scenarios → tests, hunts vacuous
   │          │                                                 tests (thought-mutation), scores
   │          │                                                 desiderata, flags quality.
   │          │
   │          └─ The contract. Interface + acceptance scenarios + an explicit
   │             instruction to the implementing agent + a Definition of Done
   │             worded as exactly what /verify checks. Tests are the durable
   │             contract; the spec is what produces them.
   │
   └─ Optional. Argue for an engineering decision.
      Skip when the approach is already settled.

Standalone utilities, any time:  /refactor · /review
```

The architecture is **producer → referee**. Blueprint owns the two brackets — the contract going in and the verdict coming out. How the contract gets satisfied is the implementing agent's business. This makes the workflow portable across coding agents: intent is the portable interface; procedure is not.

## Why this shape

Earlier blueprint versions *drove* TDD with a choreographed executor — a dependency-sliced plan, batched test writing, a failing-test commit checkpoint, a bounded fix loop. That machinery existed to compensate for model weaknesses of its moment, and it bound the workflow to one specific agent that would follow the procedure faithfully. v4.0 drops it:

- **Procedure is model-compensation that decays; intent is durable.** As models improve, turn-by-turn scaffolding becomes a cage. The design + spec + test-quality principles outlast any model generation.
- **"Any coding agent" is a protocol problem.** Each agent has its own internal loop. Specifying *what to build and what done means* is portable; specifying *the order and cadence of how to build it* is not.
- **The one thing TDD's procedure bought — non-vacuous tests — is re-secured without the procedure.** Instead of proving non-vacuity *by construction* (fail-first commits), the referee proves it *by inspection* (thought-mutation), which works no matter how the code was made.

The full argument lives in `docs/designs/` (the 4.0 design doc), written with blueprint's own `/design`.

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

v4.0 keeps this and hardens it. The risk in *any* "satisfy the spec, write good tests" handoff is a green suite that passes for the wrong reason — 100% line coverage, ~4% mutation score (Meta, FSE'25). A "good tests" guideline alone under-triggers; advisory principles describe a good test in isolation but don't certify that the *suite* would catch a break. So blueprint moves the principles from advice the generator may skip into the **referee's enforced rubric**, and adds a procedure-independent anti-vacuity check:

- **Coverage is necessary, not sufficient.** `/verify` maps every scenario to a test *and* asks, per behavior, "what's the smallest change that breaks this, and would any test catch it?"
- **The verdict is honest about its limits.** Until real mutation tooling backs the check, the referee's verdict is *advisory-strong*, not *proven* — and it says so.
- **Behavior changes flow through tests**, not spec edits. The spec's job ends when the implementation is verified.

If you want a spec-as-source-of-truth model (BDD with maintained acceptance docs), blueprint is the wrong tool — Cucumber, Concordion, or a hand-maintained acceptance suite fits better.

## Benchmark

Does handing a coding agent a blueprint spec actually change what it builds? Measured on [FeatureBench](https://github.com/LiberCoders/FeatureBench), which grades a patch against hidden fail-to-pass tests the agent never sees.

**Panel:** 5 astropy tasks, FeatureBench `fast` split, paired, single seed. The implementing agent is `claude_code` / `claude-sonnet-5` in **every** arm — the only thing that differs is the problem statement it receives. Both arms are scored by the unmodified `fb eval` against the official dataset.

| | **A** — problem statement | **B** — problem statement + `/spec` |
|---|---|---|
| Resolved (every hidden test passes) | 0 / 5 | **3 / 5** |
| Mean pass rate (fraction of hidden tests) | 0.42 | **0.79** |
| Tasks where the agent wrote any tests | **0 / 5** | 5 / 5 |
| Mutation kill rate of the agent's own tests | 0.00 | 0.25 |
| All-in cost | $26.42 | $41.16 (+56%) |

**$4.91 per additional task resolved.**

**The spec changes the outcome.** Three of five tasks flipped from unresolved to resolved, and pass rate moved on exactly those three while staying identical (0.94/0.94, 0.03/0.03) on the two that didn't. Arm A wasn't failing for mechanical reasons — every run in both arms terminated cleanly with a substantive patch. It simply built less, and built the wrong thing.

**The spec is what makes the agent write tests at all.** Without one it wrote **zero tests on all five tasks**; with one it wrote tests on all five. This replicates an earlier 3-task pilot on a different model, where Arm A also wrote zero tests on 3/3.

But read the next row too: Arm B's tests kill only 25% of planted bugs, and two of its four measurable cells killed **nothing**. A spec reliably gets tests *written*; it does not by itself make them *good*. That gap is exactly what `/verify` exists to catch — and the referee arm did raise kill rate (0.46 vs 0.25) without changing the resolved count.

### What this does not show

- **N=5, one repository, one seed.** The resolved delta rests on 3 discordant pairs, all one direction: exact McNemar **p = 0.25**. That is **not statistically significant**, and 5 tasks from a single codebase cannot show the effect generalises. A signal worth reproducing, not a proven result.
- **The `/verify` referee loop did not improve outcomes here.** A second round carrying the referee's verdict and a control second round carrying only "review it yourself" both scored 3/5, with per-task identical pass rates. On test quality the control (0.59) edged the referee (0.46). At this N the referee is not separable from a plain second pass.
- **On one task the spec actively hurt.** For `test_lombscargle_multiband` the spec declared the graded test file out of scope and told the agent not to restore it — but the hidden test set was composed entirely of that file. Arm A failed it too, so the score wasn't worsened, but the spec entrenched a wrong scope boundary.
- **This is a self-run evaluation of our own plugin.** It is not independent.

Harness, full reports and the exact task list: [`evals/blueprint-featurebench/`](../../evals/blueprint-featurebench/README.md). Every number above is regenerable from the archived run in [`reports/2608_scale_astropy_n5/`](../../evals/blueprint-featurebench/reports/2608_scale_astropy_n5/README.md).

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
| `/design` | producer | Write or critique a design doc. Dispatches `design-evaluator`. |
| `/spec` | producer | Write the agent-executable contract. Dispatches `spec-evaluator`. |
| `/test-conventions` | producer | Generate this repo's test-writing conventions by mining existing tests and projecting the Desiderata. Per-repo, regenerable. Dispatches `conventions-evaluator`. |
| `/verify` | referee | Check produced code against the spec — coverage, anti-vacuity, desiderata, quality. Dispatches `referee`. |
| `/commit` | utility | Write a Conventional Commits message. Dispatches `commit-writer`. |
| `/refactor` | utility | Change structure without changing behavior, tests green. Human-directed. |
| `/review` | utility | Standalone single-lens audit of any artifact (spec, design, test, code). |
| `/blueprint` | orchestrator | Chains the pipeline with human approval gates. |

## What blueprint deliberately does *not* produce

- **PRD / product spec** — "what business problem are we solving" is upstream of blueprint. The goal is assumed given.
- **A separate technical spec document** (data models, internal API tables) — blueprint folds the externally visible interface into the design doc and the spec, and lets the internal portion emerge from the implementation.
- **An execution plan / task graph** — sequencing, slicing, and parallelization are the implementing agent's job now, not a blueprint artifact.
- **Cross-team coupling / architectural-drift detection** — review concerns that require humans or external tooling.

## ID system

IDs follow arXiv-style `yymm.xxxx` and are shared across `docs/designs/` and `.blueprint/specs/` so a feature's design and spec can be matched by ID.

## Conventions

- One feature → one design doc (optional) + one spec, sharing an ID.
- Cross-team interface changes are made in the **design doc**; the spec and tests follow downstream.
- Specs are not maintained in sync with implementation post-build. Treat any committed spec as a snapshot of intent at build time, not a living contract.
- Evaluator subagents (`design-evaluator`, `spec-evaluator`, `conventions-evaluator`) run in fresh context and may edit the artifact they review, surfacing only items needing human judgment. The `referee` (behind `/verify`) is read-only — it judges and reports, never edits.

## Migrating from 3.x

v4.0 is a breaking change. There is no automated migration: finish in-flight work on 3.x, and start new work on 4.0. The `/run` and `/plan` skills and their slice/plan-graph artifacts are gone; implementation now happens in any coding agent, checked by `/verify`. Tests written under 3.x continue to work — they were always the durable artifact.

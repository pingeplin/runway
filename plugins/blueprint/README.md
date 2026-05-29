# blueprint

Full-cycle TDD workflow for Claude Code: `design → spec → plan → run → refactor → commit`. Each stage dispatches a fresh-context evaluator subagent before moving on.

Grounded in Kent Beck's Test Desiderata and Canon TDD. **Blueprint is TDD-pure: tests are the durable behavioral contract.** The `design` doc captures the decision; `spec` and `plan` are build-time scaffolding that produce the tests. See [Philosophy](#philosophy-tests-as-the-executable-spec) for why this matters.

## Install

```
/plugin install blueprint@runway
```

## Pipeline

```
/design ──→ /spec ──→ /plan ──→ /run ──→ /refactor ──→ /commit
   │          │         │         │
   │          │         │         └─ Walk slices in dependency order.
   │          │         │            Per slice: batch tests, commit failing,
   │          │         │            implement, commit green.
   │          │         │
   │          │         └─ Execution graph of behavioral slices.
   │          │            Pure implementation artifact for AI agents.
   │          │
   │          └─ Build-time scaffolding (not the source of truth).
   │             Acceptance scenarios that feed /plan and /run.
   │             Tests inherit the role of behavioral contract.
   │
   └─ Optional. Argue for an engineering decision.
      Skip when the approach is already settled.
```

## Artifact definitions

`design`, `spec`, and `plan` are overloaded terms across the industry. The following definitions are the ones blueprint uses. They differ in **purpose**, **audience**, and **form** — not just level of detail.

### Design doc — `docs/designs/{id}_{name}.md`

> **An argument for an engineering decision, plus the cross-team interface contract that decision implies.**

- **Purpose**: convince reviewers that *this approach* is the right one over alternatives, and surface the consequences other teams need to know about.
- **Audience**: tech lead, cross-team consumers, future engineers reading the decision archaeology, compliance/audit.
- **Form**: argumentative. Includes context, goals/non-goals, proposed approach, alternatives considered, load-bearing assumption, trade-offs, and the externally visible interface contract (API shapes, error taxonomy, breaking-change rules).
- **When to use**: when the approach itself is in question. Skip when the design is settled.
- **Lifecycle**: relatively stable. Changes trigger re-review because downstream teams depend on the contract.

A design doc is **not** documentation of a decision after the fact. It is the persuasion artifact that *makes* the decision reviewable. If a reader can't tell what is being proposed, why this option over the alternatives, and what's being given up, the doc has failed.

### Spec — `blueprint/specs/{id}_{name}.md`

> **Build-time scaffolding that drives `/plan` and `/run`. Tests — not the spec — are the durable behavioral contract.**

- **Purpose**: translate the chosen approach into acceptance scenarios that `/plan` slices into work and `/run` turns into failing tests.
- **Audience**: the AI agent (primary); the engineer at the keyboard sanity-checking what the AI will build (secondary).
- **Form**: structured acceptance scenarios (Given/When/Then-style), plus the data, edge cases, and non-functional requirements needed to write the tests.
- **When to use**: once the approach is settled — either after `/design`, or directly when the design is obvious.
- **Lifecycle**: consumed by `/plan` and `/run`. After the build, it is archival at best. Behavior changes flow through **tests**, not by editing the spec; the spec is not maintained in sync with the implementation.

A spec is **not** "a more detailed design doc." Design doc argues a decision; spec scaffolds the tests. The spec inherits the interface from the design doc and expresses it as verifiable scenarios that the AI can turn into tests.

**Commit or not — user choice.** Blueprint writes specs to `blueprint/specs/` by default, but the directory can be `.gitignore`d.

- *Don't commit*: cleanest reflection of "spec is scaffolding." No drift risk, no PR-side spec review.
- *Commit (recommended)*: reviewers see a 20-line Gherkin summary of intent alongside the test diff, and you preserve archaeology — "what scenarios drove this PR's tests?" The committed spec is a **snapshot, not a living document**; expect it to drift from tests over time and accept that, because tests carry the contract forward.

### Plan — `blueprint/plans/{id}_{name}_graph.md`

> **An execution graph of behavioral slices with dependency tracking.**

- **Purpose**: tell `/run` what to build first, what can run in parallel, and how to slice the work so each unit batches tests + implementation in one TDD pass.
- **Audience**: primarily the AI agent executing `/run`. Humans read it to sanity-check the slicing and dependency edges.
- **Form**: procedural. Numbered slices, each with a small batch of acceptance scenarios from the spec, explicit upstream/downstream edges, and a target file/module.
- **When to use**: after the spec is written and approved.
- **Lifecycle**: short-lived. Once `/run` completes the graph, the plan is mostly archaeological — useful for understanding "how this was sliced" but not the source of truth for behavior (the spec is) or implementation (the code is).

A plan is **not** a project-management Gantt chart. It is a TDD execution recipe.

## Philosophy: tests as the executable spec

Blueprint is built on TDD. In TDD, the tests *are* the spec — they are the executable, version-controlled, continuously verified definition of behavior. The `blueprint/specs/` artifact is **not** a competing source of truth; it is build-time scaffolding that gets humans and AI agents to agree on what tests to write.

This shapes a few choices that look unusual in a BDD-style world:

- **Spec lifecycle ends when `/run` finishes.** Behavior changes after that flow through tests, not spec edits.
- **Spec commits are optional.** The tests, not the spec, are the durable artifact.
- **Cross-team interface contracts live in the design doc, not the spec.** The design doc is where humans negotiate; the spec is where AI consumes the result.
- **Audit / archaeology of behavior queries the tests**, possibly with a `git log` of the historical spec snapshot for the human-readable view.

If you want a spec-as-source-of-truth model (BDD with maintained acceptance docs), blueprint is the wrong tool — Cucumber, Concordion, or a hand-maintained acceptance suite fits better.

## Comparison

| | Design doc | Spec | Plan |
|---|---|---|---|
| **Question it answers** | Which approach? | What scenarios should the tests cover? | What order do we build it in? |
| **Form** | Argumentative | Acceptance scenarios (Gherkin-ish) | Procedural |
| **Audience** | Cross-team, future eng, compliance | AI agent + implementing engineer | AI agent |
| **Location** | `docs/designs/` (or Confluence) | `blueprint/specs/` (commit optional) | `blueprint/plans/` |
| **Durable behavioral contract?** | No — owns the *decision*, not the behavior | No — tests own the behavior | No |
| **Survives implementation?** | Yes — decision archaeology | Optional snapshot; tests carry the contract forward | Mostly archaeological |
| **Triggers re-review when changed?** | Yes — cross-team contract | No — review gates on tests | No — internal scaffolding |

## What blueprint deliberately does *not* produce

- **PRD / product spec** — "what business problem are we solving" is upstream of blueprint. Blueprint assumes the goal is given.
- **Technical spec** (data models, internal API shapes, error code tables as a separate document) — blueprint folds the externally visible portion into the design doc's interface section, and lets the internal portion emerge from the code during `/run`. If you need a separate technical spec artifact (e.g., for an OpenAPI contract), keep it alongside the design doc; blueprint does not generate one.
- **Cross-team coupling detection / architectural-drift scanners** — these are review concerns that require humans or external tooling. Blueprint's evaluators check artifacts for internal consistency, not org-wide alignment.

## Skills

| Skill | Purpose |
|---|---|
| `/design` | Write or critique a design doc. Dispatches `design-evaluator`. |
| `/spec` | Write a spec with structured acceptance scenarios. Dispatches `spec-evaluator`. |
| `/plan` | Generate the execution graph. Dispatches `plan-evaluator`. |
| `/run` | Walk the graph, batch tests + implementation per slice. Dispatches `test-batch-evaluator` per slice, then `refactor-runner` (autonomous cleanup) and `run-evaluator` (verify) at the end. |
| `/refactor` | Change structure without changing behavior, with green-test discipline. Human-directed, or dispatched autonomously by `refactor-runner` as `/run`'s cleanup pass. |
| `/commit` | Write a Conventional Commits message. Dispatches `commit-writer`. |
| `/tdd` | Orchestrator that chains the above with human approval gates. |
| `/proto` | Prototyping orchestrator for spikes — skips the formal pipeline. |
| `/review` | Standalone review of any artifact (spec, plan, test, code). |

## ID system

IDs follow arXiv-style `yymm.xxxx` and are shared across `docs/designs/`, `blueprint/specs/`, and `blueprint/plans/` so a feature's three artifacts can be matched by ID.

## Conventions

- One feature → one design doc (optional) + one spec + one plan, sharing an ID.
- Cross-team interface changes are made in the **design doc**; specs and tests follow downstream.
- Specs are not maintained in sync with implementation post-`/run`. Treat any committed spec as a snapshot of intent at build time, not a living contract.
- Plans are not edited by hand mid-`/run`. Regenerate via `/plan` instead.
- Evaluator subagents run in fresh context and may directly edit the artifact they review. They surface only items needing human judgment.

# Changelog

All notable changes to the `blueprint` TDD plugin are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/);
versions follow SemVer.

## [4.0.0] — 2026-06-05

**Blueprint becomes an intent producer + invariant referee. The
prescriptive TDD driver is deleted.** The pipeline collapses from
`/design → /spec → /plan → /run → /refactor → /commit` to
`/design → /spec → ⟦any coding agent implements⟧ → /verify → /commit`,
with `/refactor` and `/review` as standalone utilities.
Blueprint no longer drives the build; it produces the contract, hands
implementation to any coding agent, and referees the result.

Design doc: `docs/designs/2606.0001_blueprint_4_referee_architecture.md`.
Spec: `.blueprint/specs/2606.0001_blueprint_4_referee_architecture.md`.
Both were written with blueprint's own `/design` and `/spec`.

### Why

Most of `/run`'s choreography (slice DAG, batched tests, failing-test
commit, bounded fix loop) was model-compensation for 2024–25 weaknesses
that decays into overhead as models improve, and it bound the workflow to
one agent that would follow the procedure. "Any coding agent" is a
*protocol* problem: intent (design + spec + test-quality principles) is
portable; procedure is not. The one thing the procedure bought —
non-vacuous tests — is re-secured procedure-independently by the referee.

### Added

- **`/verify` skill** (`skills/verify/`) — the referee, the post-implementation
  gate. Dispatches the `referee` subagent on code of unknown provenance and
  runs five checks: test suite, scenario-coverage matrix, **anti-vacuity
  thought-mutation** ("smallest change that breaks this behavior — would any
  test catch it?"), Test Desiderata scoring, and implementation-quality flags.
- **`referee` agent** (`agents/referee.md`) — the transformed, renamed
  `run-evaluator`. Agent-agnostic: no plan-file dependency, no "after /run"
  assumption, treats input adversarially. Model bumped to `opus` — it is now
  the load-bearing quality gate and the anti-vacuity reasoning is subtle.

### Changed

- **`/spec` elevated to the agent-executable contract.** The output template
  gains an **Interface Contract** section (inherited from the design), a
  **For the Implementing Agent** instruction ("make every scenario pass with
  tests that would fail if the behavior were wrong") with the bundled
  test-quality principles, and a **Definition of Done** worded as exactly what
  `/verify` checks. Next-step points to the implementing-agent handoff and
  `/verify`, not `/plan`.
- **`references/review-impl.md`** — slice/plan-loop phases stripped; the
  spec cross-check and implementation-quality flags retained as the referee's
  inputs.
- **`references/review-spec.md`** — structural check now expects the new
  contract sections; verdict is "Ready for handoff" rather than "Ready for
  /plan".
- **`references/test-desiderata.md` + `anti-patterns.md`** — unchanged in
  content, but their role is now dual: bundled into the spec as generator
  guidance *and* enforced by the referee as its rubric.
- **`/refactor`** — the autonomous post-`/run` mode is gone (its dispatcher,
  `refactor-runner`, is deleted). Now purely a human-directed standalone
  utility.
- **`/tdd` orchestrator renamed to `/blueprint`.** "TDD" named the
  deleted executor loop; the orchestrator now chains produce→referee, so it
  takes the plugin's own name. `commands/tdd.md` → `commands/blueprint.md`
  (`name: blueprint`); all references updated.
- **`/design`, `/review`, `/blueprint`** — all docs and pipeline diagrams
  updated to the new flow; the v3.x "what's new" recaps removed from the
  orchestrator.
- **README** reframed from "TDD-pure executor" to "intent producer + invariant
  referee." Tests-as-contract survives and is described as strengthened.
- **Spec directory is now `.blueprint/specs/`** (was `blueprint/specs/`).
  Hidden, so the tooling artifact stops colliding visually with a project's
  own `blueprint/` and reads as "tooling, not primary content." Design docs
  stay in the human-facing `docs/designs/`. All skills, agents, and
  references updated.
- **`plugin.json` / `marketplace.json`** — version `4.0.0`; descriptions
  reflect the producer→referee architecture.

### Removed

- **`/run` skill** — the prescriptive TDD executor.
- **`/plan` skill** — its only purpose was ordering `/run`'s execution; that
  is now the implementing agent's job. No more plan-graph artifact.
- **Agents** — `plan-evaluator`, `test-batch-evaluator`, `refactor-runner`
  (all `/run`/`/plan`-internal stages).
- **References** — `review-plan.md`, `review-test-batch.md`.
- **`/migrate-paths` command** and `scripts/migrate_paths.sh` — a vestigial
  v3.6 path-migration aid built around the now-deleted `plans/` concept.
- **`/proto` command** — the prescribed spike procedure (discover → 2–4
  tests → implement → promote/discard) is itself the kind of choreography
  4.0 sheds. Prototyping is just using your coding agent directly; formalize
  with `/design` or `/spec` if a decision falls out.

### Breaking changes

- **The whole `/plan` + `/run` surface is gone.** In-flight 3.x plan graphs
  cannot be executed. There is no automated 3.x → 4.0 migration: finish
  in-flight work on 3.x, start new work on 4.0. Tests written under 3.x are
  unaffected — they were always the durable artifact.

### Out of scope (named follow-ups)

- Real mutation-testing integration (mutmut / Stryker / PIT) to back the
  thought-mutation check and upgrade the verdict from advisory-strong to proven.
- A seeded-vacuous-suite benchmark to measure the referee's catch rate.
- Machine-readable spec serialization for programmatic external-agent ingestion.
- Multi-agent / colony orchestration (the referee architecture enables it).

## [3.7.0] — 2026-05-29

**`/refactor` replaces `/simplify` as `/run`'s cleanup pass, and it runs
in its own spawned agent.** The post-`/run` cleanup was a `/simplify`
call buried inside `run-evaluator`. It is now a structure-only
`/refactor` run — Beck's two-hats discipline with the green test suite
as the safety net — performed by a dedicated fresh-context agent before
verification, so cleanup is no longer entangled with scoring.

### Added

- **`refactor-runner` agent** — dispatched by `/run` after the last slice
  and before `run-evaluator`. Invokes `/refactor` in autonomous mode over
  the run's diff (collapse duplication, improve names, flatten nesting, fix
  comment hygiene), keeps every test green, and reports what it changed plus
  any structure-sensitive tests or behavior-change follow-ups it left undone.
- **`/refactor` autonomous mode** — a "Two ways in" section documents how the
  skill adapts when dispatched by `refactor-runner`: skip the human
  confirmation gate, scope to the run's diff, run tests via `Bash` (the caller
  is already a subagent), and escalate blockers by reporting rather than
  blocking. Human-directed `/refactor` is unchanged.

### Changed

- **`run-evaluator` is now pure verification.** Its Step 1 `/simplify` is
  gone; remaining steps renumber to Test Suite → Scenario Coverage →
  Desiderata → Implementation Quality. The `Skill` tool is dropped from its
  frontmatter (no longer needed).
- **`/run` Post-Run section** now spawns `refactor-runner` then
  `run-evaluator`, in that order, and documents both.
- **Explicit refactor recommendation.** After both agents report, `/run` now
  ends with a one-read go/no-go: "run `/refactor` on targets X, Y" (with a
  reason each, drawn from refactor-runner follow-ups and run-evaluator flags)
  or "skip to `/commit` — tree is clean". `/tdd` Step 4 presents this as a gate
  for the human to act on, instead of silently deciding whether to refactor.
- **`/tdd`** workflow map, Step 3, Step 4, and step-to-skill table updated;
  Step 4's human-directed `/refactor` is reframed as the larger restructurings
  the autonomous pass leaves alone.
- **Comment hygiene moved upstream.** The no-slice-IDs / why-only /
  keep-docstrings-current rule now appears at the point of authoring in `/run`
  (test-writing sub-step 2 and implementation sub-step 6), not only in General
  Guidelines and `run-evaluator`'s post-run flagging. Test names must describe
  behavior, never plan coordinates (slice IDs / S-IDs).
- **Every agent now pins an explicit `model`** instead of inheriting the
  session model, so quality doesn't silently drop on a cheaper session and
  mechanical agents don't waste a frontier model. Right-sized by cognitive
  demand and blast radius: `haiku` for `test-runner` (mechanical); `sonnet`
  for `test-batch-evaluator`, `commit-writer`, `plan-evaluator`, and
  `run-evaluator` (structured verification/generation); `opus` for
  `spec-evaluator`, `design-evaluator`, and `refactor-runner` (subtle judgment
  or production-code mutation). `test-batch-evaluator` moves up from `haiku` to
  `sonnet` for a better catch rate on contradictions and hallucinated APIs.

## [3.6.1] — 2026-05-20

**Curb stale comments in `/run` and flag them post-run.** Implementation
loops in `/run` were producing verbose docstrings and inline comments
that drifted out of sync with the code as the fix loop iterated.

### Changed

- **`/run` General Guidelines** add a "Docstrings and comments" rule:
  function/method docstrings are still encouraged when they capture
  purpose, contracts, or non-obvious behavior, but they must be updated
  or deleted in the same edit when the fix loop changes a function's
  signature or behavior. Inline comments only for the *why*. No
  task-referential comments (e.g. "added for slice A2") — that context
  belongs in the commit message.
- **`review-impl.md` Phase 3** adds a "stale or low-value comments and
  docstrings" scan category covering stale docstrings, restated-*what*
  comments, task-referential rot, and commented-out code.
- **`run-evaluator` agent** gains a new **Step 5 — Implementation
  Quality** that applies the Phase 3 scan over the run's diff and
  surfaces hits in a `File:Line | Flag | Detail` table. Flagging only;
  the human decides the fix. Verdict gains an `Implementation quality`
  line alongside `Test quality`.

## [3.6.0] — 2026-05-18

**Path migration.** Moves blueprint workflow artifacts into
namespaced subdirectories: `specs/` → `blueprint/specs/` and
`plans/` → `blueprint/plans/`. Design docs remain under
`docs/designs/` (humans look in `docs/` for RFCs/ADRs; specs and
plans are tooling artifacts that earn the tool-named root).

### Why

`specs/` and `plans/` at the repo root collide with other tools'
conventions and read as "what is this?" to a new engineer. Putting
them under `blueprint/` makes ownership obvious and groups the
tooling artifacts that share IDs and feed `/run`. Designs stay in
`docs/designs/` because they're human-facing arguments that should
be discoverable to anyone who looks in `docs/` for design
proposals — not just blueprint users.

### Changed

- **`/spec` output:** `blueprint/specs/{yymm.xxxx}_{feature}.md`
- **`/plan` output:** `blueprint/plans/{yymm.xxxx}_{feature}_graph.md`
- **All evaluator agents** (`spec-evaluator`, `plan-evaluator`,
  `run-evaluator`, `test-batch-evaluator`) look in the new paths
  with a fallback to the old paths for pre-migration repos.
- **`/review`** auto-detection table updated; adds a `design` row.
- **`/design`** spec back-link path updated from `../../specs/` to
  `../../blueprint/specs/`.

### Migration

New **`/migrate-paths` command** (and underlying
`scripts/migrate_paths.sh`) move existing `specs/` and `plans/`
directories into `blueprint/specs/` and `blueprint/plans/` with
`git mv` (history-preserving). Dry-run by default; pass `--apply`
to actually move. Updates cross-references in moved files so design
back-links keep resolving.

### Backwards compatibility

Skills and evaluators fall back to root-level `specs/`/`plans/`
when the new paths don't exist, so v3.5 specs/plans continue to
work without migration. Run `/migrate-paths` when you're ready to
move; nothing is forced.

## [3.5.0] — 2026-05-18

Adds a **`/design` skill** for decision-making docs (RFCs, ADRs,
design docs, PR/FAQs) — an optional upstream stage before `/spec`. The
pipeline becomes `[/design] → /spec → /plan → /run → /refactor → /commit`.

### Why

`/spec`'s description previously claimed "design doc, RFC, ADR" as
triggers, but `/spec`'s job is to define a *testable behavioral
contract*, not to argue for one approach over alternatives. Folding
both into one skill muddied the pipeline: a decision argument and an
acceptance-scenario contract are different artifacts with different
review criteria. `/plan` expects scenarios, not alternatives.

Splitting cleanly lets each skill stay sharp: `/design` handles the
*why this approach*, `/spec` handles the *what done looks like*. When
no decision is in question, `/design` is skipped; when a decision is
in question, `/design` runs first and `/spec` translates the chosen
approach into scenarios.

### Added

- **`/design` skill** at `skills/design/SKILL.md`. Two modes: write
  with named `[ASSUMPTION: …]` markers (default) or critique mode
  when the user pastes a draft. Switches to interview-mode only for
  solution-disguised-as-problem prompts or already-decided prompts.
- **`design-evaluator` subagent** (`agents/design-evaluator.md`)
  mirrors the `spec-evaluator` pattern. Fresh-context fix-loop against
  a 6-phase methodology: decision clarity, alternative quality,
  trade-off honesty, load-bearing assumption, success criteria, and
  ambiguity/scope. Verdict: "Ready for /spec" / "Yes, after resolving"
  / "No — fundamental rework needed."
- **Reference files:** `references/review-design.md`,
  `references/design-templates.md` (Mini RFC, RFC, ADR, Feature Doc,
  SDD, PR/FAQ), `references/design-failure-modes.md` (10 common
  failure modes with before/after fixes), and
  `references/design-company-practices.md` (Google, Uber, Amazon,
  Stripe approaches).
- **`docs/designs/` output path** for design docs. IDs are shared
  across `docs/designs/`, `specs/`, and `plans/` (arXiv-style
  `yymm.xxxx`), so a feature's artifacts can be matched by ID.

### Changed

- **`/spec` description narrowed** to focus on testable behavioral
  contracts. Removed "design doc / RFC / ADR / architecture document /
  technical proposal" triggers — those now route to `/design`.
- **`/spec` ID assignment** now scans `docs/designs/` in addition to
  `specs/` and `plans/`. When an upstream design doc exists with the
  same ID, `/spec` reuses the ID and adds a back-link to the design.
- **`/tdd` orchestrator** adds Step 0 (`/design`, optional). The
  workflow map, size-detection heuristics, and step-to-skill mapping
  all updated. New heuristic: if the user can't answer "why this
  approach over the alternatives" with a one-sentence trade-off,
  `/design` is worth running.
- **Marketplace + plugin description** updated to mention design docs.

### Not changed

- `/plan`, `/run`, `/refactor`, `/commit` — unchanged. `/spec` still
  produces the same acceptance-scenario format `/plan` expects.
- Existing specs/plans in `specs/` and `plans/` continue to work; the
  new `docs/designs/` directory is additive.

## [3.4.0] — 2026-05-17

A redesign of the planning/execution unit: **sliced batching replaces the
RED/GREEN/REFACTOR triplet model**. Each slice is a small batched cycle
(1–6 acceptance scenarios) with a failing-test commit checkpoint between
test writing and implementation. The sub-agent harness from 3.3.x stays
intact and gains a new evaluator for the batched-test risk surface.

### Why

The per-test ceremony of strict RED → GREEN → REFACTOR carried two costs
without proportional benefit on modern reasoning models: ~3 suite runs
per triplet (multiplicative with feature size) and N plan-file edits
per N triplets. But fully dropping the discipline and letting the agent
"write all tests, then all code, then declare victory" reintroduces real
failure modes documented in 2024–2026 research:

- **Fail-to-pass discipline collapses without a failing-test gate.** IBM's
  TDD-Bench Verified (2024) shows frontier models produce *properly
  failing-then-passing* tests only ~24% of the time when there is no
  enforced fail step. The other 76% are syntactically fine yet vacuous.
- **Coverage is a liar without mutation testing.** Meta's FSE '25
  production data shows test suites hitting 100% line coverage with 4%
  mutation score. The fix Meta deployed was an iterative loop, not
  single-shot batch generation.
- **Context rot starts well before the window fills.** Chroma's 2025
  study across 18 frontier models showed >30% accuracy drops with
  "lost in the middle" effects from ~50K tokens. "All tests + all code
  + all fixes in one context" is the regime that rots fastest.
- **Anthropic's own Claude Code guidance** still says commit the failing
  tests first — otherwise Claude will quietly rewrite tests to fit a
  broken implementation.

v3.4 takes the middle path: **per-slice batching with a failing-test
commit checkpoint**. The slice is small enough that a single writing
pass can stay coherent, and the git checkpoint structurally prevents
silent test rewriting during the implementation pass.

### Added

- **`agents/test-batch-evaluator.md`** — Fresh-context, Haiku-backed
  evaluator dispatched after `/run` writes the batch of tests for a
  slice, before the failing-test commit. Checks slice scenario coverage,
  intra-batch contradictions, hallucinated APIs, and AP-1 / AP-4 quick
  scans. Report-only (no auto-edit) so the batch stays stable across
  the check.
- **`references/review-test-batch.md`** — Methodology that the new
  evaluator reads.
- **Failing-test commit checkpoint** inside `/run` Step 2 (sub-step 5).
  Format: `test: add failing tests for {slice description} ({S-IDs})`.
- **CHANGELOG.md** (this file).
- **"What's new in v3.4"** section in `commands/tdd.md`.

### Changed

- **Plan graph format (BREAKING).** `/plan` Phase 3 now emits *slices*
  with `Depends:` / `Scenarios:` / `Tests:` / `Implementation:` /
  `Done when:` / `Scope:` payload. Slice IDs are `A1`, `A2`, `B1`, …
  (no more A1=RED, A2=GREEN, A3=REFACTOR offsets). Soft cap of 6
  scenarios per slice; hard cap of 8.
- **`/run` Step 2** rebuilt as an 8-substep **Slice Loop**: read codebase
  → write batched tests as active → dispatch `test-batch-evaluator`
  → verify all-fail → commit failing batch → implement → bounded fix
  loop (≤5 attempts, production code only, never edit tests) → mark
  slice complete. ~3 suite runs per slice instead of ~3 per triplet.
- **`agents/plan-evaluator.md`** — Phase 2 renamed *Slice Completeness*;
  Phase 3 *Scenario Coverage* downgraded to a binary upstream check
  (no full matrix); Phase 5 renamed *Test Description Quality*.
- **`agents/run-evaluator.md`** — Step 3 explicitly marked as the
  authoritative scenario coverage matrix for the whole run (deduping
  the duplicate check that existed in 3.3.x).
- **`references/review-plan.md`** — Methodology rewritten for slice
  schema; matches `plan-evaluator`'s new phases.
- **`references/review-impl.md`** Phase 2 — Rewritten in slice
  terminology; added a "missing failing-test commits" diagnostic.
- **`commands/tdd.md`** — Workflow diagram and step descriptions
  updated for the slice flow.
- **`commands/proto.md`** — Aligned with `/run`: active tests only,
  no `@pytest.mark.skip` markers, batch write + bounded fix loop.
- **`skills/spec/SKILL.md`** Next-Step text — "TDD triplets" →
  "behavioral slices".
- **`skills/review/SKILL.md`** — "RED node quality checks" → "test
  description quality checks".
- **`.claude-plugin/plugin.json`** — Version 3.3.1 → 3.4.0; description
  reflects sliced behavioral milestones and the failing-test commit
  checkpoint.

### Removed

- **REFACTOR nodes in the plan graph.** The standalone `/refactor`
  skill remains the only place refactoring happens, run once at the
  end of a feature. Per-slice "pressure-relief" refactor nodes were
  dropped — they added bookkeeping without clear ROI, and the
  failing-test commit checkpoint provides a cleaner safety net for the
  structure-vs-behavior discipline.
- **Skip/unskip machinery.** Tests are written as active in both
  `/run` and `/proto`. The `@pytest.mark.skip` convention from 3.3.x
  is gone.
- **`references/tdd-workflow.md`.** Content was duplicating
  `commands/tdd.md`; the unique parts (Who-decides framing, human
  decision-points list) are absorbed into the orchestrator doc.

### Breaking changes

- **Plan graph schema.** Plans written by `/plan` in 3.3.x cannot be
  executed by `/run` in 3.4 — the parser contract changed from
  RED/GREEN/REFACTOR triplets to slices. Re-run `/plan` to regenerate
  any in-flight plan files.
- **`/proto` skip-marker convention.** Existing prototype tests
  decorated with `@pytest.mark.skip` will not be automatically picked
  up by the new `/proto`. Strip the markers manually if you want the
  new flow.

### Migration from 3.3.x

For users with in-flight work:

- **In-flight specs and code** — Unaffected. Specs follow the same
  format, and already-written tests/implementation are not touched by
  the redesign.
- **In-flight plan files** — Regenerate with `/plan {spec_path}`. The
  spec → slice transformation is automatic.
- **Custom callers of `plan-evaluator` Phase 3** — Phase 3 no longer
  emits a coverage matrix; use `run-evaluator` Step 3 for the
  authoritative matrix after `/run` completes.

### Commits

- `a470108` `feat(blueprint): Add test-batch-evaluator subagent`
- `13be869` `feat(blueprint): Convert /plan and /run from triplets to slices`
- `895e0dd` `docs(blueprint): Align peripheral docs with v3.4 slice flow`
- `d813ce4` `chore(blueprint): Bump to 3.4.0`

### Open follow-ups (not in 3.4)

- **Mutation-test gate** as an opt-in for `/refactor` (Meta-style
  iterative loop) — deferred; independent of the triplet redesign.
- **Adversarial / pre-mortem evaluator pass** as an opt-in for `/plan`
  — deferred. The current `plan-evaluator` already mixes structural,
  cross-artifact, and feasibility lenses in a single pass and was
  catching real issues in production specs; the adversarial lens is
  worth adding only after observing failures the current pass misses.
- **Empirical comparison** of v3.4 vs 3.3.1 on the same feature with
  the same spec — recommended before merge for confidence beyond the
  literature evidence cited under "Why". **Done (2026-05-18):** ran
  8 tasks side-by-side across the two versions — LCD, Poker Hands,
  Bowling, Tennis, Roman Numerals, Markdown→HTML, Bank-Account bug fix,
  vague-spec Undo. Findings: v3.4 reliably wins on process discipline
  (per-slice commit trail) and plan compactness (1.6×–3.2× shorter
  plans, comparable scenario coverage). Correctness essentially tied
  (1 task each direction, both at spec-stage edges the kata didn't
  pin). v3.4's per-slice impl-commit pattern degrades on structurally
  complex features (markdown task: tests committed per slice, impl
  batched at end). Methodology preserved at
  `eval/blueprint/eval-methodology.md`; per-task evidence
  archived locally outside the repo.

## Earlier versions

Earlier versions are documented only in `git log` — this changelog
starts at the v3.4 redesign.

- `3.3.1` and earlier — see `git log --oneline plugins/blueprint/`.

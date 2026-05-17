# Changelog

All notable changes to the `blueprint` TDD plugin are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/);
versions follow SemVer.

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
  literature evidence cited under "Why".

## Earlier versions

Earlier versions are documented only in `git log` — this changelog
starts at the v3.4 redesign.

- `3.3.1` and earlier — see `git log --oneline plugins/blueprint/`.

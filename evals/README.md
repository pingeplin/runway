# Evals

Every measurement of the blueprint plugin, in one place. Three tiers,
cheapest first; each has its own README with the method and the traps.

| tier | question | cost | where |
|---|---|---|---|
| Transcript analysis | What do agents actually do in real sessions? | $0 — reads existing `~/.claude/projects/` transcripts | [`transcript-analysis/`](transcript-analysis/README.md) |
| Triggering | Does the right skill fire on a real prompt? | ~$3.60, ~6 min at `-j 3` | [`../plugins/blueprint/evals/`](../plugins/blueprint/evals/README.md) |
| Benchmark | Does a spec, or the referee, change what an agent builds? | ~$21 per task per arm all-in, podman, 20GB images | [`blueprint-featurebench/`](blueprint-featurebench/README.md) |

Only the triggering tier is a pre-PR check (see the root `CLAUDE.md`).

## What stands — 2026-09-16

Each line names the report it comes from. Every benchmark number is N=5, one
repository (astropy), one run per arm: directional, never significant.

**The spec (`/spec`, Arm B).** Mean pass rate on the pinned same-day panel:
no document 0.48, one breadth sentence 0.46, a generic brief 0.40, the 4.0
spec **0.71**; resolved 2 / 1 / 0 / 0. The lift is one task —
`lombscargle_multiband`, where the spec names a second stripped module — and
without it B − A is +0.06. A document costs $15.88 per task; all-in B is
$20.98 against A's $2.55. → `2609_control_arms_astropy_n5`

**Run-to-run noise.** Re-inferring the same specs swung `vo` by 0.55, so any
single-task difference below that is noise.
→ `2609_control_arms_astropy_n5`

<!--
Earlier same-spec runs: B pass rate 0.84 on 2026-09-10 (2609_clean_paired_astropy_n5),
0.71 and 0.73 on 2026-09-16 (2609_control_arms_astropy_n5, 2609_armc_clean_astropy_n5);
vo 0.95 → 0.40. Tests written by the spec arm: 3/5 on 2026-09-10, 1/5 on 2026-09-16.
-->

**Agent-written tests.** Without a spec the agent wrote no tests in any run
that measured it. With a spec, on the latest run, it wrote tests on 1 of 5
tasks. → `2609_armc_clean_astropy_n5`

**The referee (`/verify`, Arm C vs a generic self-review C0).** Headless, and
not allowed to run the suite. Pre-registered kill rate C − C0 = +0.125:
indistinguishable, read as **negative** for the referee. The post-hoc audit
splits it: every verifiable claim was true (22/22, judge-assessed), but the
claims covered 11 of 176 failing hidden tests, and the one hidden-test gain C
made traced to nothing the verdict said. Oracle-anchored kill rate B 0.18 /
C 0.39 / C0 0.23. Reading: the referee gets *reasonable, bug-catching tests*
written; it does not steer to *correct code*. → `2609_armc_clean_astropy_n5`

**Doc-quality metrics.** Breadth (oracle recall) and fenced ∩ oracle order
spec versions the way pass rate does; coherence did not (ρ 0.00, ±4 between
judge repeats) and was dropped; testability and grounding are saturated.
Design docs have a rubric (`blueprint-featurebench/DESIGN_RUBRIC.md`) and no
corpus. → `2609_doc_quality_validation`

**The abandoned 5.x line (Ouroboros).** Its produce → judge → revise loop
fenced scope: spec pass rate 0.37 vs 4.0's 0.84 (below no spec, 0.42); the
scope fix (Ouroboros B) recovered to 0.70. Post-mortem:
`docs/designs/2609.0003_blueprint_5_post_mortem.md`.
→ `2609_clean_paired_astropy_n5`

**Test weakening.** Across 116 real sessions and 43 red → green cycles, no
agent edited a test to turn a suite green; all 4 detector candidates were
false positives. The hook-ledger design (`docs/designs/2609.0004`) was
rejected on this. → `transcript-analysis/`

**Triggering.** 4 cases (`/spec` and `/design` routing, `/review` vs
`/verify`, a negative control), all green at 3 runs each.
→ `plugins/blueprint/evals/`

## Benchmark reports

All under `blueprint-featurebench/reports/`. Nothing here is deleted: a
retracted run stays as the record of what was retracted and why.

| report | date | question | status |
|---|---|---|---|
| `2608_pilot_n3` | 08-15 | A vs B vs C/C0, first masked pilot (sonnet-4-5, N=3) | **Leaky** — spec writer and referee had git-history access to the oracle. Superseded. |
| `2608_scale_astropy_n5` | 08-16 | A vs B vs C/C0 at N=5, sonnet-5 | **Retracted** (same leak). Arm A cells are valid and are borrowed by `2609_clean_paired`. |
| `2609_ouroboros_a_leaky_astropy_n5` | 09-10 | 5.0 loop spec vs 4.0 | **Retracted** (same leak). Abandoned line. |
| `2609_ouroboros_b_vo_probe` | 09-10 | Does the 5.1 scope fix keep stripped neighbours in scope? One task, spec only. | Clean. Abandoned line. |
| `2609_clean_paired_astropy_n5` | 09-10 | 4.0 vs Ouroboros A vs Ouroboros B specs, history masked | Clean. Its `v4/specs/` are the spec set every later run reuses; its 0.84 headline is corrected by `2609_control_arms`. |
| `2609_doc_quality_validation` | 09-12 | Which document metrics track pass rate? 15 specs. | **Current.** |
| `2609_control_arms_astropy_n5` | 09-16 | Is B's lift blueprint's, or any document's? Pinned agent. Pre-registered. | **Current** — the plugin README's benchmark numbers. |
| `2609_armc_clean_astropy_n5` | 09-16 | Does the referee beat a generic self-review? Pre-registered + post-hoc audit. | **Current** — the first clean referee measurement. |

## Open problems

Known, unfixed, and shared by any future run on this harness.

- **The referee never runs the suite** (`prompts/verify_headless.md`), so
  `/verify`'s first check has never been exercised in a benchmark. The audit's
  untested hypothesis is that its misses are runtime errors a suite run would
  show.
- **Round 2 restarts from the pristine repo** (`prompts/repair_instruction.md`),
  so C − B measures a fresh attempt, not a repair. C − C0 is unaffected.
- **Stage 07's kill rate grades whole test files.** Appending to a
  pre-existing file drags in tests the mask broke, and the cell is excluded as
  `baseline_red`; mutation sites are LLM-chosen per cell, so arms are not
  graded on the same mutants. The oracle-anchored grader in
  `2609_armc_clean_astropy_n5/referee_audit/layer3/` fixes both and is not yet
  a stage.
- **One run per arm, one repository.** No report meets ≥2 runs per arm.
  `blueprint-featurebench/samples/scale_n25.txt` (5 repos × 5 tasks) is
  committed and has never been run.
- **FeatureBench rewards breadth.** "Restore a stripped feature" penalises
  fencing and never penalises additive over-reach, so a spec's scope
  discipline cannot score here.

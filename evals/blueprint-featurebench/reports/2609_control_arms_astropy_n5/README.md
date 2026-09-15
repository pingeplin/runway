# Control arms 2609 — is the 4.0 spec's lift blueprint's? astropy, N=5

> **Status: pre-registered 2026-09-16 before any control cell ran; results
> appended the same day.** The reading rules were fixed first; the results
> section reads the numbers against them, and anything beyond them is
> labelled post-hoc.

## Question

The clean paired rerun ([`../2609_clean_paired_astropy_n5/`](../2609_clean_paired_astropy_n5/README.md))
measured mean pass rate A 0.42 → B 0.84. The A/B pair cannot rule out two
cheaper explanations:

1. **Any upfront document does it.** The spec stage spends ~$16 and ~33 min
   per task reading the masked repo. A plain brief from the same model, with
   no blueprint methodology, might carry the same lift.
2. **The lift is one sentence.** The post-mortem named the mechanism: the 4.0
   spec lists everything the mask stripped from the touched files as in
   scope. One instruction might carry it.

## Arms

Same panel (`panel_task_ids.txt`), same implementing agent
(`claude_code` / `claude-sonnet-5`), in-container Claude Code pinned to
**2.1.272** for all four arms, all inferred on the same day.

| arm | problem statement | host stage |
|---|---|---|
| A | original | — |
| A_hint | original + separator + `prompts/breadth_hint.md` | — |
| A_plan | original + separator + generic brief (`prompts/brief_headless.md`) | stage 14, blueprint disabled and proven absent per task |
| B | original + separator + the archived clean 4.0 spec | none today — specs reused from 2026-09-10 |

The separator is Arm B's (`## Implementation Spec`) for all three treatments,
so only the document body differs.

## Pre-registered reading

Mean pass rate over the five tasks is the primary number. Resolved counts
and McNemar p are reported, but at N=5 they cannot decide anything.
"Within 0.15" means the absolute mean pass-rate difference is below 0.15.

1. **Replication first — B − A today.** If below 0.15, the 2026-09-10 lift
   did not replicate on the same day and agent, and the control comparisons
   are not interpretable; report that as the finding.
2. **Seed noise — B today vs B on 2026-09-10** (same specs, different day and
   agent version). The largest per-task swing between the two bounds what any
   single-task difference below can mean.
3. **Methodology — B − A_plan.** A_plan within 0.15 of B → on this benchmark a
   generic brief does what the blueprint spec does, and the remaining
   question is cost (A_plan's brief cost vs B's $15.88). B ahead by ≥ 0.15 →
   the blueprint spec carries something a plain brief does not.
4. **One sentence — A_hint.** A_hint within 0.15 of B → the measured lift is
   reproducible with one sentence. A_hint within 0.15 of A → the mechanism is
   not a one-liner.
5. Every conclusion is directional: N=5, one repository, one seed per arm.

## Known before running

- B's specs were written 2026-09-10 with blueprint 4.0.0 (host Claude Code
  version not recorded). `/spec`'s `SKILL.md` in 4.1.0 differs from 4.0.0 by
  one line (a `/refactor` mention). A_plan's briefs are written today on host
  Claude Code 2.1.272 with every other user plugin loaded, as the spec writer
  had.
- A_hint's sentence was written after reading the 4.0 specs and the
  post-mortem: a ceiling test of the mechanism, not a prompt a user would
  have written blind.
- A_plan's cost is reported, not matched to B's (`max_budget_usd = 30` is a
  runaway ceiling only).
- FeatureBench rewards breadth; self-run evaluation of our own plugin.
- Estimated spend: briefs $25–80, inference 4 arms × 5 tasks × $4–6.

## Results (2026-09-16, 01:23–05:28)

Every cell terminated `success` with a non-empty patch. Every in-container
transcript reports Claude Code 2.1.272. Every A_plan brief meta has
`blueprint_leaks: []` and `mask_applied / git_reinit: true`. New spend
**$82.74** (briefs $8.48, inference $74.26); B's specs are the 2026-09-10
artefacts ($79.39 then).

| task | A | A_hint | A_plan | B | B, 09-10 (same specs) | A, 08-15 |
|---|---|---|---|---|---|---|
| `basic_rgb` | **1.00** ✓ | **1.00** ✓ | 0.94 | 0.94 | 0.94 | 0.94 |
| `containers` | **1.00** ✓ | 0.65 | 0.71 | 0.92 | 1.00 ✓ | 0.67 |
| `lombscargle_multiband` | 0.03 | 0.03 | 0.03 | **0.96** | 0.96 | 0.03 |
| `table` | 0.35 | **0.63** | 0.30 | 0.35 | 0.35 | 0.44 |
| `vo` | 0.01 | 0.01 | 0.01 | **0.40** | 0.95 | 0.00 |
| **mean pass rate** | 0.48 | 0.46 | 0.40 | **0.71** | 0.84 | 0.42 |
| resolved | 2/5 | 1/5 | 0/5 | 0/5 | 1/5 | 0/5 |
| document cost / task | — | — | $1.70 | $15.88 | | |
| all-in cost / task | $2.55 | $5.07 | $3.82 | $20.98 | | |

Full tables: `report.md` (four arms, paired comparisons), `report_ab.md`,
`cost_report.md`. Briefs and their metas: `briefs/`.

### Against the pre-registered reading

1. **Replication: yes, smaller.** B − A = **+0.24** (≥ 0.15), about half the
   2026-09-10 gap of +0.42.
2. **Seed noise is large.** Same specs, two runs: `vo` 0.95 → 0.40 (swing
   0.55), `containers` 1.00 → 0.92. A across runs: `containers` 0.67 → 1.00.
   A single-task difference below ~0.55 is inside run-to-run noise.
3. **Methodology: B ahead.** B − A_plan = **+0.32**. The generic brief scored
   *below* no document (A_plan − A = −0.08) at a ninth of the spec's cost.
4. **One sentence: no.** A_hint − A = **−0.01**; B − A_hint = +0.25.

### What carries the numbers (post-hoc, not pre-registered)

- **One task clears the noise bar: `lombscargle_multiband`.** B scored 0.96 on
  both runs of the spec; every other cell on this task, today and on
  2026-08-15, scored 0.03. The problem statement names only
  `lombscargle/core.py`. The 4.0 spec names
  `lombscargle_multiband/core.py` nine times and says `get_unit` /
  `strip_units` were stripped from it too; the brief mentions that file once.
  B's patch edits it and restores `strip_units`; no A, A_hint or A_plan patch
  touches it. The breadth hint says "the files you touch", and the agent never
  touched that file.
- **Without that task the lift is noise.** Means over the other four: A 0.59,
  A_hint 0.57, A_plan 0.49, B 0.65 — B − A = +0.06.
- **Resolved runs the other way.** A resolved `basic_rgb` and `containers`
  outright; B scored 0.94 / 0.92 on both.
- **`vo` is unstable under B** (0.95 → 0.40 with the same spec) and flat at
  0.01 under every control.

### Reading

The pre-registered answers are: the lift replicated, a generic brief does not
explain it, and one breadth sentence does not reproduce it. The evidence under
those answers is narrow. On one task of five — reproduced across two runs —
the spec found a second module with stripped definitions that neither a
generic brief nor a breadth hint led the agent to. On the other four tasks the
spec's effect is inside run-to-run noise, it costs ~8× all-in, and it resolved
fewer tasks. N=5, one repository, one run per arm today; a claim beyond
"found the second stripped module once, reproducibly" needs more tasks and
≥2 seeds per arm.

## Reproduce

```bash
cd evals/blueprint-featurebench
bash scripts/run_controls.sh reports/2609_clean_paired_astropy_n5/v4 reports/2609_control_arms_astropy_n5
```

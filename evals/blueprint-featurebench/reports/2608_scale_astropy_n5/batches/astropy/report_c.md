# Blueprint /verify referee loop on FeatureBench (Arm C)

Panel: `LiberCoders/FeatureBench` split `fast`, 5 paired task(s).  
Arm B = original + spec (round 1). Arm C = round 2 with the `/verify` referee verdict. Arm C0 = round 2 with a generic self-review instruction (control).  
Implementing agent: `claude_code` / `claude-sonnet-5` in all three arms. Referee model: `claude-sonnet-5`.

Reports: B `/Users/eplin/workspace/runway/evals/blueprint-featurebench/results/infer_arm_b/2026-08-15__23-31-04/report.json` · C `/Users/eplin/workspace/runway/evals/blueprint-featurebench/results/infer_arm_c/2026-08-16__01-58-50/report.json` · C0 `/Users/eplin/workspace/runway/evals/blueprint-featurebench/results/infer_arm_c0/2026-08-16__02-43-28/report.json`

## Per-task results

| task id | B resolved | C resolved | C0 resolved | B pass_rate | C pass_rate | C0 pass_rate | verdict cost USD | verdict seconds |
|---|---|---|---|---|---|---|---|---|
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | no | no | no | 0.94 | 0.94 | 0.94 | 1.0319 | 174 |
| `astropy__astropy.b0db0daa.test_containers.6079987d.lv1` | yes | yes | yes | 1.00 | 1.00 | 1.00 | 1.8273 | 272 |
| `astropy__astropy.b0db0daa.test_lombscargle_multiband.78687278.lv1` | no | no | no | 0.03 | 0.03 | 0.03 | 2.2608 | 334 |
| `astropy__astropy.b0db0daa.test_table.48eef659.lv1` | yes | yes | yes | 1.00 | 1.00 | 1.00 | 2.6631 | 364 |
| `astropy__astropy.b0db0daa.test_vo.8fd473ce.lv1` | yes | yes | yes | 1.00 | 1.00 | 1.00 | 1.3891 | 261 |
| **totals (5)** | **3** | **3** | **3** | **0.79** | **0.79** | **0.79** | **9.1722** | **1406** |

## Paired comparisons

- Resolved: B **3/5**, C **3/5**, C0 **3/5**
- **C − C0** (referee vs bare second pass (the attribution test)): delta **+0**, discordant b(C-only)=**0** c(C0-only)=**0**, exact McNemar **p = 1.0000**
- **C − B** (referee loop vs spec-only round 1): delta **+0**, discordant b(C-only)=**0** c(B-only)=**0**, exact McNemar **p = 1.0000**
- **C0 − B** (bare second pass vs spec-only round 1): delta **+0**, discordant b(C0-only)=**0** c(B-only)=**0**, exact McNemar **p = 1.0000**
- Verify-round cost: **$9.1722** over 5 task(s), 1406s wall

## Caveats

- **C0 is the attribution control.** C − B mixes "the referee helped" with
  "a second pass helps". Only **C − C0** isolates the referee's contribution;
  read C − C0 first and C − B second.
- **The referee ran blind to the test suite.** The verify round happens on the
  host, where the task's dependencies are not installed, so the referee scored
  scenario coverage, anti-vacuity, desiderata and implementation quality
  statically. A verdict that a green/red suite would have changed is invisible.
- **Round 2 restarts from the pristine repo.** Both C and C0 re-implement from
  scratch with the previous patch quoted in the prompt; neither continues an
  existing working tree, so this measures feedback quality, not patch repair.
- **Oracle masking is applied upstream.** Stage 01 writes its spec against a
  tree that has been masked exactly as `fb infer` masks it — the dataset's
  mask patch applied and the FAIL_TO_PASS test files deleted
  (`_common.mask_reference_solution`; a task whose mask fails to apply is
  hard-failed, and each spec's `.meta.json` records `mask_applied` /
  `f2p_deleted`). The verify round reproduces the same masking, so the referee
  saw what the implementing agent saw. An earlier, pre-masking run of this
  harness did leak the reference solution into the spec stage and its results
  were discarded.
- **Single seed, small N.** Discordant-pair counts are expected to be
  single-digit; the McNemar p-values are directional evidence only.
- **Cost is one-sided.** Arm C additionally pays the verify-round cost shown
  below, on top of Arm B's spec cost and both arms' inference cost.
- **Residual prompt confound.** C and C0 statements differ only in the feedback
  section, but C0's closing instruction still says "addressing the verdict",
  which for C0 refers to its own self-review.

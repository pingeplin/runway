# Blueprint /verify referee loop on FeatureBench (Arm C)

Panel: `LiberCoders/FeatureBench` split `fast`, 3 paired task(s).  
Arm B = original + spec (round 1). Arm C = round 2 with the `/verify` referee verdict. Arm C0 = round 2 with a generic self-review instruction (control).  
Implementing agent: `claude_code` / `claude-sonnet-4-5` in all three arms. Referee model: `claude-sonnet-4-5`.

Reports: B `/Users/eplin/workspace/runway/evals/blueprint-featurebench/results/infer_arm_b/2026-08-15__16-53-42/report.json` · C `/Users/eplin/workspace/runway/evals/blueprint-featurebench/results/infer_arm_c/2026-08-15__17-39-51/report.json` · C0 `/Users/eplin/workspace/runway/evals/blueprint-featurebench/results/infer_arm_c0/2026-08-15__17-58-32/report.json`

## Per-task results

| task id | B resolved | C resolved | C0 resolved | B pass_rate | C pass_rate | C0 pass_rate | verdict cost USD | verdict seconds |
|---|---|---|---|---|---|---|---|---|
| `Netflix__metaflow.b390a8d4.test_stub_generator.7bf08c98.lv1` | yes | yes | yes | 1.00 | 1.00 | 1.00 | 3.0201 | 676 |
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | no | no | no | 0.59 | 0.65 | 0.59 | 3.9823 | 736 |
| `astropy__astropy.b0db0daa.test_comparison.445d81a3.lv1` | no | no | no | 0.37 | 0.67 | 0.37 | 4.7280 | 734 |
| **totals (3)** | **1** | **1** | **1** | **0.65** | **0.77** | **0.65** | **11.7304** | **2147** |

## Paired comparisons

- Resolved: B **1/3**, C **1/3**, C0 **1/3**
- **C − C0** (referee vs bare second pass (the attribution test)): delta **+0**, discordant b(C-only)=**0** c(C0-only)=**0**, exact McNemar **p = 1.0000**
- **C − B** (referee loop vs spec-only round 1): delta **+0**, discordant b(C-only)=**0** c(B-only)=**0**, exact McNemar **p = 1.0000**
- **C0 − B** (bare second pass vs spec-only round 1): delta **+0**, discordant b(C0-only)=**0** c(B-only)=**0**, exact McNemar **p = 1.0000**
- Verify-round cost: **$11.7304** over 3 task(s), 2147s wall

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
- **The spec upstream of all three arms had oracle access.** Stage 01 writes
  its spec against the image's raw `/testbed`, which still contains the
  reference implementation — `fb infer` only strips it (and deletes the
  FAIL_TO_PASS tests) inside the container. B, C and C0 all inherit that spec,
  so it biases their common level, not the C/C0 contrast. The verify round
  here does reproduce the masked tree, so the referee saw what the
  implementing agent saw.
- **Single seed, small N.** Discordant-pair counts are expected to be
  single-digit; the McNemar p-values are directional evidence only.
- **Cost is one-sided.** Arm C additionally pays the verify-round cost shown
  below, on top of Arm B's spec cost and both arms' inference cost.
- **Residual prompt confound.** C and C0 statements differ only in the feedback
  section, but C0's closing instruction still says "addressing the verdict",
  which for C0 refers to its own self-review.

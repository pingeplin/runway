# Blueprint spec vs control arms on FeatureBench

Panel: `LiberCoders/FeatureBench` split `fast`, 5 task(s).  
A = original statement. A_hint = + one breadth sentence. A_plan = + a generic brief (blueprint disabled). B = + blueprint spec.  
Implementing agent: `claude_code` / `claude-sonnet-5` in every arm.

Reports: A `/Users/eplin/workspace/runway/.claude/worktrees/bench-compute-control/evals/blueprint-featurebench/results/infer_arm_a/2026-09-16__01-45-56/report.json` · A_hint `/Users/eplin/workspace/runway/.claude/worktrees/bench-compute-control/evals/blueprint-featurebench/results/infer_arm_a_hint/2026-09-16__04-22-24/report.json` · A_plan `/Users/eplin/workspace/runway/.claude/worktrees/bench-compute-control/evals/blueprint-featurebench/results/infer_arm_a_plan/2026-09-16__03-38-51/report.json` · B `/Users/eplin/workspace/runway/.claude/worktrees/bench-compute-control/evals/blueprint-featurebench/results/infer_arm_b/2026-09-16__02-33-54/report.json`

## Per-task pass rate (✓ = resolved)

| task id | A | A_hint | A_plan | B | A_plan doc USD | B doc USD |
|---|---|---|---|---|---|---|
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | 1.00 ✓ | 1.00 ✓ | 0.94 | 0.94 | 3.29 | 11.24 |
| `astropy__astropy.b0db0daa.test_containers.6079987d.lv1` | 1.00 ✓ | 0.65 | 0.71 | 0.92 | 1.16 | 16.19 |
| `astropy__astropy.b0db0daa.test_lombscargle_multiband.78687278.lv1` | 0.03 | 0.03 | 0.03 | 0.96 | 1.04 | 14.19 |
| `astropy__astropy.b0db0daa.test_table.48eef659.lv1` | 0.35 | 0.63 | 0.30 | 0.35 | 2.39 | 24.56 |
| `astropy__astropy.b0db0daa.test_vo.8fd473ce.lv1` | 0.01 | 0.01 | 0.01 | 0.40 | 0.60 | 13.20 |

## Per arm

| arm | resolved | mean pass rate | doc cost / task | doc wall / task |
|---|---|---|---|---|
| A | 2/5 | 0.48 | — | — |
| A_hint | 1/5 | 0.46 | — | — |
| A_plan | 0/5 | 0.40 | $1.70 | 10 min |
| B | 0/5 | 0.71 | $15.88 | 33 min |

## Paired comparisons

- **B − A_plan** (blueprint spec vs a generic brief (the attribution test)): mean pass rate **+0.32**, per task 3 up / 0 down / 2 tied (|Δ| < 0.05), discordant resolved b(B-only)=**0** c(A_plan-only)=**0**, exact McNemar **p = 1.0000**
- **B − A_hint** (blueprint spec vs one breadth sentence): mean pass rate **+0.25**, per task 3 up / 2 down / 0 tied (|Δ| < 0.05), discordant resolved b(B-only)=**0** c(A_hint-only)=**1**, exact McNemar **p = 1.0000**
- **A_plan − A** (generic brief vs nothing): mean pass rate **-0.08**, per task 0 up / 2 down / 3 tied (|Δ| < 0.05), discordant resolved b(A_plan-only)=**0** c(A-only)=**2**, exact McNemar **p = 0.5000**
- **A_hint − A** (breadth sentence vs nothing): mean pass rate **-0.01**, per task 1 up / 1 down / 3 tied (|Δ| < 0.05), discordant resolved b(A_hint-only)=**0** c(A-only)=**1**, exact McNemar **p = 1.0000**
- **B − A** (blueprint spec vs nothing): mean pass rate **+0.24**, per task 2 up / 2 down / 1 tied (|Δ| < 0.05), discordant resolved b(B-only)=**0** c(A-only)=**2**, exact McNemar **p = 0.5000**

## Caveats

- **Small N, one repository, one seed per arm.** Per-task outcomes swing hard
  with document wording (the same `vo` task scored 0.95 / 0.00 / 1.00 under
  three spec variants), so every delta here is directional evidence only.
- **A_plan's cost is reported, not matched.** The brief writer spends what it
  spends; read its document cost next to B's before reading its pass rate.
- **A_hint encodes a mechanism found by reading 4.0's specs.** It is a ceiling
  test of that mechanism, not a product a user would have written blind.
- **The benchmark rewards breadth.** FeatureBench strips whole features, so
  any document that widens scope is favoured; a task shape that penalises
  over-reach would grade all three treatments differently.
- **Self-run evaluation of our own plugin.**

# Blueprint spec ablation on FeatureBench

Panel: `LiberCoders/FeatureBench` split `fast`, 5 paired task(s).  
Arm A = original problem statement. Arm B = original + blueprint spec.  
Implementing agent: `claude_code` / `claude-sonnet-5` (identical in both arms). Spec model: `claude-sonnet-5`.

Reports: A `/Users/eplin/workspace/runway/evals/blueprint-featurebench/results/merged/report_A.json` · B `/private/tmp/claude-501/-Users-eplin-workspace-runway/d6ee0cad-9bef-4026-bc0b-e34357e17002/scratchpad/eval-v4/results/infer_arm_b/2026-09-10__13-15-28/report.json`

## Per-task paired results

| task id | A resolved | B resolved | A pass_rate | B pass_rate | spec cost USD | spec seconds |
|---|---|---|---|---|---|---|
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | no | no | 0.94 | 0.94 | 11.2384 | 1242 |
| `astropy__astropy.b0db0daa.test_containers.6079987d.lv1` | no | yes | 0.67 | 1.00 | 16.1912 | 2598 |
| `astropy__astropy.b0db0daa.test_lombscargle_multiband.78687278.lv1` | no | no | 0.03 | 0.96 | 14.1945 | 1842 |
| `astropy__astropy.b0db0daa.test_table.48eef659.lv1` | no | no | 0.44 | 0.35 | 24.5650 | 2568 |
| `astropy__astropy.b0db0daa.test_vo.8fd473ce.lv1` | no | no | 0.00 | 0.95 | 13.1982 | 1656 |
| **totals (5)** | **0** | **1** | **0.42** | **0.84** | **79.3873** | **9906** |

## Paired comparison

- Resolved: A **0/5**, B **1/5** (delta **+1**)
- Discordant pairs: b (A-only resolved) = **0**, c (B-only resolved) = **1**
- Exact McNemar (two-sided binomial on 1 discordant pairs): **p = 1.0000**
- Spec-stage cost: **$79.3873** total over 5 task(s), 9906s wall

## Caveats

- **Single seed.** One inference pass per arm per task. Agent runs are
  stochastic; a rerun will move these numbers.
- **Small N.** With FeatureBench-level resolve rates the discordant-pair count
  is expected to be single-digit, so the McNemar p-value is **directional
  evidence only** — it is not a verdict, and it is not corrected for anything.
- **End-to-end correctness only.** FeatureBench scores hidden fail-to-pass
  tests, so this table says nothing about the quality of the tests the agent
  itself wrote. That is measured separately by the mutation overlay
  (`mutation_report.md`); design-argument quality is measured by neither.
- **Cost is one-sided.** The spec-stage cost above is spent by Arm B and not by
  Arm A. It is not the whole picture: the implementing agent's own in-container
  token cost is reported separately in `cost_report.md` (stage 10), which is
  where the all-in A-vs-B comparison lives.
- **Model contamination** (the model may know these repos) dilutes both arms
  equally under pairing: it biases levels, not the A/B delta.

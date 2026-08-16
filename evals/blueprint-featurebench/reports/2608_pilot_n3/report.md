# Blueprint spec ablation on FeatureBench

Panel: `LiberCoders/FeatureBench` split `fast`, 3 paired task(s).  
Arm A = original problem statement. Arm B = original + blueprint spec.  
Implementing agent: `claude_code` / `claude-sonnet-4-5` (identical in both arms). Spec model: `claude-sonnet-4-5`.

Reports: A `/Users/eplin/workspace/runway/evals/blueprint-featurebench/results/infer_arm_a/2026-08-15__14-40-05/report.json` · B `/Users/eplin/workspace/runway/evals/blueprint-featurebench/results/infer_arm_b/2026-08-15__16-53-42/report.json`

## Per-task paired results

| task id | A resolved | B resolved | A pass_rate | B pass_rate | spec cost USD | spec seconds |
|---|---|---|---|---|---|---|
| `Netflix__metaflow.b390a8d4.test_stub_generator.7bf08c98.lv1` | yes | yes | 1.00 | 1.00 | 0.6874 | 228 |
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | no | no | 0.65 | 0.59 | 0.4523 | 183 |
| `astropy__astropy.b0db0daa.test_comparison.445d81a3.lv1` | no | no | 0.37 | 0.37 | 3.5400 | 795 |
| **totals (3)** | **1** | **1** | **0.67** | **0.65** | **4.6797** | **1207** |

## Paired comparison

- Resolved: A **1/3**, B **1/3** (delta **+0**)
- Discordant pairs: b (A-only resolved) = **0**, c (B-only resolved) = **0**
- Exact McNemar (two-sided binomial on 0 discordant pairs): **p = 1.0000**
- Spec-stage cost: **$4.6797** total over 3 task(s), 1207s wall

## Caveats

- **Single seed.** One inference pass per arm per task. Agent runs are
  stochastic; a rerun will move these numbers.
- **Small N.** With FeatureBench-level resolve rates the discordant-pair count
  is expected to be single-digit, so the McNemar p-value is **directional
  evidence only** — it is not a verdict, and it is not corrected for anything.
- **End-to-end correctness only.** FeatureBench scores hidden fail-to-pass
  tests. Test quality, anti-vacuity and design-argument quality — the referee
  half of blueprint's value — are invisible here.
- **Cost is one-sided.** The spec-stage cost above is spent by Arm B and not by
  Arm A; the implementing agent's own token cost is not included in either arm.
- **Model contamination** (the model may know these repos) dilutes both arms
  equally under pairing: it biases levels, not the A/B delta.

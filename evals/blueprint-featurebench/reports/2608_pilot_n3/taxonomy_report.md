# Failure taxonomy

Per-cell classification of WHY a (task, arm) combination failed: `spec_wrong` (blueprint's spec misled the agent — Arm B/treatment only), `impl_wrong` (agent failed despite a correct brief), `env_or_flaky` (harness/test environment), `unclear`.

## Per-cell classifications

| task id | arm | class | spec_contribution | rationale |
|---|---|---|---|---|
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | A | impl_wrong | — | The implementation correctly validates interval length and output_dtype types, raising ValueError in all expected cases, but error message wording doesn't ma... |
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | B | impl_wrong | neutral | The implementation correctly raises ValueError for all required error conditions but with error message text that doesn't match pre-existing test expectation... |
| `astropy__astropy.b0db0daa.test_comparison.445d81a3.lv1` | A | impl_wrong | — | 30 ERROR tests indicate broken format parsing infrastructure (runtime failures before test execution), while 8 FAILED tests show logic bugs. The agent unders... |
| `astropy__astropy.b0db0daa.test_comparison.445d81a3.lv1` | B | impl_wrong | neutral | Implementation has 30 test errors for astropy.row/table/yaml formats explicitly mentioned in spec scenarios S3/S9/S10/S17, plus 8 failures for astropy.model.... |

## Totals

| class | count |
|---|---|
| env_or_flaky | 0 |
| impl_wrong | 4 |
| spec_wrong | 0 |
| unclear | 0 |
| **total cells** | **4** |

## Caveats

- **Single-rater LLM.** One `claude -p` classification pass per cell, no
  cross-check, no human adjudication. Treat every row as directional
  evidence, not a verdict.
- **Blind to ground truth.** The rater sees the same task-side evidence a
  human triager would (statement, spec, patch, test log) but never the
  reference patch or reference tests — its `spec_wrong`/`impl_wrong` call is
  an inference, not a fact.
- **Truncated bundles.** Problem statement and patch are truncated to
  ~6k chars (head), the test log to ~4k chars (tail). A failure whose
  evidence lives outside those windows will read as `unclear`.

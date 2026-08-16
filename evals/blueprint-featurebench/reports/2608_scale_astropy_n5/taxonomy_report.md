# Failure taxonomy

Per-cell classification of WHY a (task, arm) combination failed: `spec_wrong` (blueprint's spec misled the agent — Arm B/treatment only), `impl_wrong` (agent failed despite a correct brief), `env_or_flaky` (harness/test environment), `unclear`.

## Per-cell classifications

| task id | arm | class | spec_contribution | rationale |
|---|---|---|---|---|
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | A | impl_wrong | — | Arm A had no spec; the original statement's error-handling requirement ('Validate input compatibility across all three channels') was reasonable but the agen... |
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | B | impl_wrong | neutral | The agent correctly implemented the required ValueError-on-wrong-length-interval behavior (S10 in the spec), but chose the message text 'please provide 1 or ... |
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | C | impl_wrong | neutral | The agent's own implementation raises ValueError('please provide 1 or 3 interval instances.') while its own recreated test asserts pytest.raises(ValueError, ... |
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | C0 | impl_wrong | neutral | 16/17 tests passed; the only failure is that the agent's ValueError message ('please provide 1 or 3 interval instances.') doesn't match the hidden ground-tru... |
| `astropy__astropy.b0db0daa.test_containers.6079987d.lv1` | A | impl_wrong | — | The original statement (with its detailed interface description) was a reasonably complete brief, but the agent's structured-dtype/stride-trick reimplementat... |
| `astropy__astropy.b0db0daa.test_lombscargle_multiband.78687278.lv1` | A | impl_wrong | — | Arm A had no spec, and the original problem statement (though broad) evidently included a detailed Interface Description for the LombScargleMultiband class; ... |
| `astropy__astropy.b0db0daa.test_lombscargle_multiband.78687278.lv1` | B | spec_wrong | harmed | The spec explicitly marks the lombscargle FFT/unit helpers (bitceil, extirpolate, trig_sum, get_unit/strip_units) and the deleted test_lombscargle_multiband.... |
| `astropy__astropy.b0db0daa.test_lombscargle_multiband.78687278.lv1` | C | spec_wrong | harmed | The graded FAIL_TO_PASS suite for this task is almost entirely astropy/timeseries/periodograms/lombscargle_multiband/tests/test_lombscargle_multiband.py (925... |
| `astropy__astropy.b0db0daa.test_lombscargle_multiband.78687278.lv1` | C0 | spec_wrong | harmed | The spec's Trade-offs section explicitly tells the agent that the FFT helpers (bitceil/extirpolate/trig_sum, get_unit/strip_units) in the lombscargle/lombsca... |
| `astropy__astropy.b0db0daa.test_table.48eef659.lv1` | A | impl_wrong | — | Arm A had only the original task statement, which is a valid (if broad) account of VOTable table operations; the agent's patch implements pieces (to_table, g... |
| `astropy__astropy.b0db0daa.test_vo.8fd473ce.lv1` | A | impl_wrong | — | The original problem statement (20K+ chars of interface descriptions) called for implementing a large surface of VOTable methods across tree.py, but the agen... |

## Totals

| class | count |
|---|---|
| env_or_flaky | 0 |
| impl_wrong | 8 |
| spec_wrong | 3 |
| unclear | 0 |
| **total cells** | **11** |

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

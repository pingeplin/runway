# Mutation-score overlay — agent-written tests

Per (task, arm): the arm's `model_patch` is applied inside the task's own
docker image, then **only the test files the agent itself wrote** are run
against strategic mutations of the agent's own source changes.
Kill rate = killed / applicable mutations. This is the test-quality
dimension FeatureBench's hidden fail-to-pass tests cannot see.

## Per-task kill rate

| task | arm A | arm B | arm C | arm C0 |
|---|---|---|---|---|
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | — (no_agent_tests) | 0.00 (0/2) | 0.33 (2/6) | 0.83 (5/6) |
| `astropy__astropy.b0db0daa.test_containers.6079987d.lv1` | — (no_agent_tests) | 0.83 (5/6) | 0.67 (4/6) | 0.50 (3/6) |
| `astropy__astropy.b0db0daa.test_lombscargle_multiband.78687278.lv1` | — (no_agent_tests) | — (baseline_red) | — (baseline_red) | — (baseline_red) |
| `astropy__astropy.b0db0daa.test_table.48eef659.lv1` | — (no_agent_tests) | 0.17 (1/6) | 0.50 (3/6) | 0.83 (5/6) |
| `astropy__astropy.b0db0daa.test_vo.8fd473ce.lv1` | — (no_agent_tests) | 0.00 (0/6) | 0.33 (2/6) | 0.20 (1/5) |

## Arm summary

| arm | cells | measured | no_agent_tests | baseline_red | patch_failed | other | mean kill rate (measured) | mean kill rate (no-tests = 0) |
|---|---|---|---|---|---|---|---|---|
| **A** | 5 | 0 | 5 | 0 | 0 | 0 | — | **0.0000** |
| **B** | 5 | 4 | 0 | 1 | 0 | 0 | **0.2500** | **0.2500** |
| **C** | 5 | 4 | 0 | 1 | 0 | 0 | **0.4583** | **0.4583** |
| **C0** | 5 | 4 | 0 | 1 | 0 | 0 | **0.5917** | **0.5917** |

Two denominators, deliberately:

- **measured** — mean over cells that produced a rate. Flatters an arm
  that wrote no tests at all, because those cells simply vanish.
- **no-tests = 0** — the same mean with every `no_agent_tests` cell
  scored 0.0. Shipping no tests is the worst possible test quality,
  not missing data. Read this column first.

Cells that failed for harness reasons (`patch_apply_failed`,
`baseline_unusable`, `no_mutations`, `timeout_abandoned`, `error`)
are excluded from both
means and shown in the census instead. `baseline_red` — the agent's own
tests fail against the agent's own code — is also excluded from the
means but is itself a quality signal worth reading.

## Agent tests on a fail-to-pass path

These cells wrote a test file at a path FeatureBench had deleted as
part of the hidden oracle. The test is still agent-authored — the
file was gone before the agent started — but the path coincidence
means the agent inferred the oracle's own layout.

- arm **B** · `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` — `astropy/visualization/tests/test_basic_rgb.py`
- arm **B** · `astropy__astropy.b0db0daa.test_containers.6079987d.lv1` — `astropy/uncertainty/tests/test_containers.py`
- arm **B** · `astropy__astropy.b0db0daa.test_table.48eef659.lv1` — `astropy/io/votable/tests/test_table.py`
- arm **B** · `astropy__astropy.b0db0daa.test_vo.8fd473ce.lv1` — `astropy/io/votable/tests/test_vo.py`
- arm **C** · `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` — `astropy/visualization/tests/test_basic_rgb.py`
- arm **C** · `astropy__astropy.b0db0daa.test_containers.6079987d.lv1` — `astropy/uncertainty/tests/test_containers.py`
- arm **C** · `astropy__astropy.b0db0daa.test_table.48eef659.lv1` — `astropy/io/votable/tests/test_table.py`
- arm **C** · `astropy__astropy.b0db0daa.test_vo.8fd473ce.lv1` — `astropy/io/votable/tests/test_vo.py`
- arm **C0** · `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` — `astropy/visualization/tests/test_basic_rgb.py`
- arm **C0** · `astropy__astropy.b0db0daa.test_containers.6079987d.lv1` — `astropy/uncertainty/tests/test_containers.py`
- arm **C0** · `astropy__astropy.b0db0daa.test_table.48eef659.lv1` — `astropy/io/votable/tests/test_table.py`
- arm **C0** · `astropy__astropy.b0db0daa.test_vo.8fd473ce.lv1` — `astropy/io/votable/tests/test_vo.py`

## Caveats

- **Small N.** 5 task(s) × 4 arm(s), one seed, ≤6 mutations per cell. Directional, not a verdict.
- **LLM-chosen mutations.** Sites are proposed by a model per cell, so
  the mutation panels differ between arms and between tasks. This
  measures 'did these tests catch plausible breakage', not a stable
  mutation-adequacy score comparable across runs.
- **Agent-tests-only scope.** Only test files the patch added or
  modified are run. Pre-existing repo tests and the hidden
  fail-to-pass tests are deliberately excluded — they are FeatureBench's
  job, not this overlay's.
- **Overlap with the oracle.** An agent test may land on the same path
  as a deleted fail-to-pass file. It is still agent-authored (the file
  was removed before the agent ran), but the path coincidence is worth
  knowing when reading a cell.
- **Survived ≠ untested.** A mutation can survive because it is
  semantically equivalent, not because the tests are vacuous. Read the
  per-cell JSON under `results/mutation/<arm>/<id>.json` before drawing
  a conclusion from a single survivor.

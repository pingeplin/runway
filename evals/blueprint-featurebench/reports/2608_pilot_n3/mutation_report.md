# Mutation-score overlay — agent-written tests

Per (task, arm): the arm's `model_patch` is applied inside the task's own
docker image, then **only the test files the agent itself wrote** are run
against strategic mutations of the agent's own source changes.
Kill rate = killed / applicable mutations. This is the test-quality
dimension FeatureBench's hidden fail-to-pass tests cannot see.

## Per-task kill rate

| task | arm A | arm B | arm C | arm C0 |
|---|---|---|---|---|
| `Netflix__metaflow.b390a8d4.test_stub_generator.7bf08c98.lv1` | — (no_agent_tests) | — (no_agent_tests) | 0.50 (3/6) | — (no_agent_tests) |
| `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` | — (no_agent_tests) | 0.83 (5/6) | 0.50 (3/6) | 0.80 (4/5) |
| `astropy__astropy.b0db0daa.test_comparison.445d81a3.lv1` | — (no_agent_tests) | — (baseline_red) | — (patch_apply_failed) | — (baseline_red) |

## Arm summary

| arm | cells | measured | no_agent_tests | baseline_red | patch_failed | other | mean kill rate (measured) | mean kill rate (no-tests = 0) |
|---|---|---|---|---|---|---|---|---|
| **A** | 3 | 0 | 3 | 0 | 0 | 0 | — | **0.0000** |
| **B** | 3 | 1 | 1 | 1 | 0 | 0 | **0.8333** | **0.4167** |
| **C** | 3 | 2 | 0 | 0 | 1 | 0 | **0.5000** | **0.5000** |
| **C0** | 3 | 1 | 1 | 1 | 0 | 0 | **0.8000** | **0.4000** |

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
- arm **B** · `astropy__astropy.b0db0daa.test_comparison.445d81a3.lv1` — `astropy/cosmology/_src/tests/funcs/test_comparison.py`
- arm **C** · `Netflix__metaflow.b390a8d4.test_stub_generator.7bf08c98.lv1` — `test/cmd/develop/test_stub_generator.py`
- arm **C** · `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` — `astropy/visualization/tests/test_basic_rgb.py`
- arm **C0** · `astropy__astropy.b0db0daa.test_basic_rgb.067e927c.lv1` — `astropy/visualization/tests/test_basic_rgb.py`
- arm **C0** · `astropy__astropy.b0db0daa.test_comparison.445d81a3.lv1` — `astropy/cosmology/_src/tests/funcs/test_comparison.py`

## Caveats

- **Small N.** 3 task(s) × 4 arm(s), one seed, ≤6 mutations per cell. Directional, not a verdict.
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

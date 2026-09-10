# Clean paired rerun 2609 — blueprint 4.0 vs 5.0 specs, astropy, N=5 (2026-09-10)

First run on the harness with **git-history masking** (`_common.reinit_git`,
commit `1910873`). The spec writer could no longer read the reference
implementation or the deleted FAIL_TO_PASS tests from `git show HEAD:`.
Both spec versions were rerun the same day, same panel
(`panel_task_ids.txt`), same implementing agent (`claude_code` /
`claude-sonnet-5`), one seed, Arm B only. Arm A is borrowed from
[`../2608_scale_astropy_n5/`](../2608_scale_astropy_n5/README.md) — it never
had history access, so it is valid as-is.

- `v4/` — specs from blueprint **4.0.0** (installed plugin; one in-place
  `spec-evaluator` pass)
- `v5/` — specs from blueprint **5.0** (`--plugin-dir` at commit `2063a62`;
  `/spec` runs the produce → judge → revise loop, ≤3 rounds)

Each side has `report.md` (paired vs Arm A), `mutation_report.md`,
`cost_report.md`, `specs/`, and the manifests.

## Headline

| | A — no spec | B — 4.0 spec | B — 5.0 spec ⟲ |
|---|---|---|---|
| Resolved | 0 / 5 | 1 / 5 | 1 / 5 |
| Mean pass rate | 0.42 | **0.84** | **0.37** |
| Tasks where the agent wrote any tests | 0 / 5 | 3 / 5 | 4 / 5 |
| Kill rate (no-tests = 0) | 0.00 | 0.22 | 0.39 |
| Spec cost / task | — | $15.88 | $15.36 |
| Spec wall / task | — | 33 min | 52 min |
| Spec length, lines (mean) | — | 634 | 647 |
| In-container inference / task | $5.28 | $3.84 | $3.96 |

Per task, pass rate:

| task | A | 4.0 B | 5.0 B |
|---|---|---|---|
| `test_basic_rgb` | 0.94 | 0.94 | **1.00** ✓ |
| `test_containers` | 0.67 | **1.00** ✓ | 0.52 |
| `test_lombscargle_multiband` | 0.03 | **0.96** | 0.03 |
| `test_table` | 0.44 | 0.35 | 0.30 |
| `test_vo` | 0.00 | **0.95** | 0.00 |

## What this run says

**1. The 4.0 spec still helps a lot without the oracle — on pass rate, not
on resolved.** 0.42 → 0.84, driven by three tasks that jump from near-zero
to near-complete (`lombscargle` 0.03 → 0.96, `vo` 0.00 → 0.95, `containers`
0.67 → 1.00). Only one of them fully resolves. The 2608 headline of "3/5
resolved" does not survive the leak fix; "the agent builds most of the
feature instead of little of it" does.

**2. The 5.0 loop makes the spec worse for the implementing agent.** 0.42
→ 0.37, below no-spec. `vo` and `lombscargle` go from 0.95 / 0.96 under
4.0 to 0.00 / 0.03 under 5.0; `containers` drops below Arm A.

**3. The mechanism is scope narrowing.** Read the two `vo` specs side by
side. The 4.0 spec has a section "Blocking prerequisites: other definitions
stripped from the same file — they are in scope; restore the prerequisites
first." The 5.0 spec scopes the task to the six members the problem
statement names. The 5.0 implementing agent's closing message: *"this
checkout has extensive unrelated breakage outside my assigned scope … I
left those files untouched since they're outside this task's stated
scope."* Same on `table`: *"all remaining failures trace to names
explicitly declared out-of-scope by the spec."* FeatureBench masks a whole
feature, which strips helpers and neighbours that the hidden tests exercise
too; a spec that fences the task to the literal problem statement fences
the agent away from what the oracle needs. The 5.0 evaluator's scope
discipline (Phase 6 "scope creep", the Coherence phase, and the fresh-judge
rewrite cycle) produces exactly that fence. 4.0's single in-place pass left
the writer's broader "restore everything stripped from this file"
instinct intact.

**4. Test writing is no longer the differentiator.** With history masked,
4.0 wrote tests on 3/5 and 5.0 on 4/5; kill rates 0.22 vs 0.39 (no-tests =
0). The leaky-run finding "5.0 stopped writing tests" was itself an artefact
of the leak: in 2608, "tests written" often meant the spec instructing the
agent to recreate the oracle test file from history.

**5. Spec cost is the same.** Without an oracle to transcribe, 4.0 costs
$15.88/task and 5.0 $15.36/task — the "6× loop cost" in the leaky rerun
was 4.0's cheap copying, not the loop. The loop still takes 1.6× the wall
time.

## What this does not show

- N=5, one repository, one seed, single-day. The pass-rate gap between
  4.0 and 5.0 (0.84 vs 0.37) is large and consistent in direction on 3/5
  tasks, but is not a significance claim.
- Nothing here measures the thing 5.0 was built to fix — contradictions
  and muddled ordering *inside* the spec. The harness does not persist the
  evaluator's ledger; the 5.0 specs may well be more coherent documents
  while being worse briefings for this benchmark's task shape.
- FeatureBench's "restore a stripped feature" shape rewards broad scope.
  A benchmark where over-reaching is penalised would grade the same
  narrowing differently.
- Self-run evaluation of our own plugin.

## Provenance

- Specs: `v4/specs/*.meta.json`, `v5/specs/*.meta.json` carry
  `mask_applied=true`, `f2p_deleted=1`, `git_reinit=true`.
- v4 stage 01 was interrupted once by user request after 4/5 and resumed
  for `vo` (the interrupted attempt's partial cost is not in the ledger).
- The first 5.0 inference attempt ran on a podman machine that had been
  restarted without Rosetta (the setting is read at machine start, not
  init); every cell failed at agent start-up at ~$0 and was discarded
  (`results/infer_arm_b/_failed_norosetta_*`). `~/.config/containers/
  containers.conf` now pins `provider = "applehv"`, `rosetta = true`.
- Every number is regenerable from each side's `runs.json` with the stage
  04/05/07/10 scripts; Arm A via `--report-a` pointing at the 2608 archive.

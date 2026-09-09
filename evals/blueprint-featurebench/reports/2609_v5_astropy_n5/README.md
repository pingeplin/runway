# Rerun 2609 — blueprint 5.0 specs, astropy, N=5, Arm B only (2026-09-10)

> **Validity caveat (added 2026-09-10).** The specs in this run were written
> in a workspace whose git history still held the upstream commit, so the
> spec writer could — and the 2608 specs demonstrably did — read the
> reference implementation and the deleted FAIL_TO_PASS tests via
> `git show HEAD:<path>`. Working-tree masking was in place; history masking
> was not (fixed in `_common.reinit_git`, see the harness README "Oracle
> masking"). The implementing agent never had history access (`fb infer`
> re-inits git in the container), so Arm A is unaffected, but every spec
> arm's numbers are upper bounds contaminated by however much of the oracle
> the spec transcribed. Do not cite the spec-arm deltas until the panel is
> rerun on the fixed harness.


Same panel as [`../2608_scale_astropy_n5/`](../2608_scale_astropy_n5/README.md)
(`panel_task_ids.txt`, FeatureBench `fast` split), same implementing agent
(`claude_code` / `claude-sonnet-5`), one seed. The only change is the
blueprint plugin that wrote the specs: **5.0** (commit `2063a62`, loaded via
`--plugin-dir`) instead of 4.0. Under 5.0, `/spec` runs the produce → judge →
revise loop (fresh report-only `evaluator`, whole-spec rewrite, up to 3
rounds) instead of one in-place evaluator pass.

Arm A is not rerun; the paired table borrows the 2608 Arm A cells. Arm C is
not rerun either: `referee.md` is byte-identical between 4.0 and 5.0 and the
headless `/verify` runs one round, so a C rerun would measure seed noise.

| file | contents |
|---|---|
| `report.md` | A (2608) vs B (5.0 spec) paired table — resolved 0/5 vs 2/5 |
| `mutation_report.md` | agent-written test quality — **3/5 cells wrote no tests** |
| `cost_report.md` | spec stage $69.98, in-container inference $14.08 |
| `specs/` | the five 5.0 specs and their `.meta.json` (cost, wall, turns) |
| `tasks.json`, `runs.json` | manifests |

## Headline — 5.0 vs 4.0 on the same five tasks

| | 4.0 Arm B | 5.0 Arm B |
|---|---|---|
| Resolved | 3 / 5 | 2 / 5 |
| Mean pass rate | 0.79 | 0.71 |
| Tasks where the agent wrote any tests | 5 / 5 | **2 / 5** |
| Kill rate (no-tests = 0) | 0.25 | 0.07 |
| Spec cost / task | $2.30 | **$14.00** |
| Spec wall / task | 13.8 min | 46.7 min |
| Spec `num_turns` (basic_rgb) | 13 | 48 |
| Spec length, lines (mean) | 542 | 714 |
| In-container inference / task | $5.94 | $2.82 |
| In-container output tokens (arm total) | 212 K | 171 K |

Per task: `basic_rgb` flipped to resolved under 5.0 (0.94 → 1.00);
`containers` resolved under both; `table` and `vo` flipped to unresolved
(1.00 → 0.53, 1.00 → 0.97); `lombscargle_multiband` failed under both (0.03).
One up, two down, two unchanged: at N=5 with one seed this is noise-level on
*resolved*, and the direction is not favourable.

## What the run says

- **The loop did not buy resolution.** Two of the three 4.0 resolves did
  not repeat. Nothing in this run separates "5.0 spec is worse" from
  "different seed"; a paired rerun of 4.0 on the same day would be needed.
- **The loop cost 6× on the spec stage** and took 3.4× the wall time.
  Every spec ran multiple evaluator rounds (48 turns vs 13 on the one task
  with a direct comparison). The in-container agent then spent *less* —
  fewer output tokens, half the cost — which reads as the agent doing less
  work, not the spec making the work easier.
- **The agent stopped writing tests.** 4.0 specs produced tests on 5/5
  tasks; 5.0 specs on 2/5. The 5.0 specs are longer and far more
  prescriptive: they enumerate 20–28 scenarios, cite existing test files as
  "your primary feedback loop", and list which scenarios "must" get new
  tests. On `containers` the spec said exactly that, and the agent shipped a
  2-file patch with no tests. The mechanism is not established here; the
  candidates are (a) the agent treating the named pre-existing suites as
  sufficient, (b) attention spread across a 1,000-line briefing, or (c)
  seed noise on a 5-task panel. (c) alone does not explain a 5/5 → 2/5 move.
- **This contradicts the design doc's success criterion in spirit.** The
  design's metric was "0 contradiction findings on round 2 of the next five
  specs" — a spec-quality metric the harness does not capture (the
  evaluator's ledger is not persisted by stage 01). What *is* captured says
  the downstream agent behaved worse on the one thing 4.0's spec reliably
  caused: writing tests.

## Limits

- N=5, one repository, one seed, Arm A borrowed from a run four weeks
  earlier. Not significant; directional at best.
- The podman machine was rebuilt mid-run. The first Arm B attempt ran on a
  libkrun VM without Rosetta, where the in-container Claude Code binary
  aborts on start (`qemu: uncaught target signal 6`); all five cells
  produced empty patches at ~$0 and were discarded
  (`results/infer_arm_b/_failed_libkrun_*`). The reported run is on an
  applehv + Rosetta machine, the same configuration as 2608.
- Spec stage `[spec].timeout_seconds` had to be raised from 1800 to 5400;
  the first probe timed out at 1800 s mid-loop (that partial run's cost is
  not recoverable and is not in the $69.98).
- Self-run evaluation of our own plugin.

## Provenance

- Specs regenerated under 5.0 with oracle masking (`mask_applied=true`,
  `f2p_deleted=1` per task). Stage 01 invoked `claude -p … --plugin-dir
  <worktree>/plugins/blueprint`, verified beforehand to expose `evaluator`
  and `referee` and no 4.0 agents.
- Every number is regenerable from `runs.json` with the unmodified stage
  04/05/07/10 scripts; Arm A via `--report-a` pointing at the 2608 archive.

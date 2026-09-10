# Clean paired rerun 2609 — blueprint 4.0 vs Ouroboros A vs Ouroboros B specs, astropy, N=5 (2026-09-10)

> **Naming.** The abandoned 5.x line is referred to as **Ouroboros** so that the
> version number stays free: Ouroboros A = the 5.0 build, Ouroboros B = 5.1,
> Ouroboros B′ = 5.1.1. Commit hashes in this document are unchanged.

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
- `ouroboros-a/` — specs from blueprint **Ouroboros A** (`--plugin-dir` at commit `2063a62`;
  `/spec` runs the produce → judge → revise loop, ≤3 rounds)
- `ouroboros-b/` — specs from blueprint **Ouroboros B** (`--plugin-dir` at commit `d5bc1bc`;
  same loop, findings typed `contradiction` / `uncovered` / `behavior-change`,
  scope rule "add, never remove", ledger persisted) — run the same day,
  ~5 h after `ouroboros-a/`

Each side has `report.md` (paired vs Arm A), `mutation_report.md`,
`cost_report.md`, `specs/`, and the manifests.

## Headline

| | A — no spec | B — 4.0 spec | B — Ouroboros A spec ⟲ | B — Ouroboros B spec ⟲ |
|---|---|---|---|---|
| Resolved | 0 / 5 | 1 / 5 | 1 / 5 | 1 / 5 |
| Mean pass rate | 0.42 | **0.84** | **0.37** | **0.70** |
| Tasks where the agent wrote any tests | 0 / 5 | 3 / 5 | 4 / 5 | 4 / 5 |
| Kill rate (no-tests = 0) | 0.00 | 0.22 | 0.39 | 0.29 |
| Spec cost / task | — | $15.88 | $15.36 | $18.69 |
| Spec wall / task | — | 33 min | 52 min | 56 min |
| Spec length, lines (mean) | — | 634 | 647 | 704 |
| In-container inference / task | $5.28 | $3.84 | $3.96 | $5.67 |

Per task, pass rate:

| task | A | 4.0 B | Ouroboros A B | Ouroboros B B |
|---|---|---|---|---|
| `test_basic_rgb` | 0.94 | 0.94 | **1.00** ✓ | 0.94 |
| `test_containers` | 0.67 | **1.00** ✓ | 0.52 | 0.67 |
| `test_lombscargle_multiband` | 0.03 | **0.96** | 0.03 | 0.03 |
| `test_table` | 0.44 | 0.35 | 0.30 | **0.88** |
| `test_vo` | 0.00 | **0.95** | 0.00 | **1.00** ✓ |

## What this run says

**1. The 4.0 spec still helps a lot without the oracle — on pass rate, not
on resolved.** 0.42 → 0.84, driven by three tasks that jump from near-zero
to near-complete (`lombscargle` 0.03 → 0.96, `vo` 0.00 → 0.95, `containers`
0.67 → 1.00). Only one of them fully resolves. The 2608 headline of "3/5
resolved" does not survive the leak fix; "the agent builds most of the
feature instead of little of it" does.

**2. The Ouroboros A loop makes the spec worse for the implementing agent.** 0.42
→ 0.37, below no-spec. `vo` and `lombscargle` go from 0.95 / 0.96 under
4.0 to 0.00 / 0.03 under Ouroboros A; `containers` drops below Arm A.

**3. The mechanism is scope narrowing.** Read the two `vo` specs side by
side. The 4.0 spec has a section "Blocking prerequisites: other definitions
stripped from the same file — they are in scope; restore the prerequisites
first." The Ouroboros A spec scopes the task to the six members the problem
statement names. The Ouroboros A implementing agent's closing message: *"this
checkout has extensive unrelated breakage outside my assigned scope … I
left those files untouched since they're outside this task's stated
scope."* Same on `table`: *"all remaining failures trace to names
explicitly declared out-of-scope by the spec."* FeatureBench masks a whole
feature, which strips helpers and neighbours that the hidden tests exercise
too; a spec that fences the task to the literal problem statement fences
the agent away from what the oracle needs. The Ouroboros A evaluator's scope
discipline (Phase 6 "scope creep", the Coherence phase, and the fresh-judge
rewrite cycle) produces exactly that fence. 4.0's single in-place pass left
the writer's broader "restore everything stripped from this file"
instinct intact.

**4. Test writing is no longer the differentiator.** With history masked,
4.0 wrote tests on 3/5 and Ouroboros A on 4/5; kill rates 0.22 vs 0.39 (no-tests =
0). The leaky-run finding "Ouroboros A stopped writing tests" was itself an artefact
of the leak: in 2608, "tests written" often meant the spec instructing the
agent to recreate the oracle test file from history.

**5. Spec cost is the same.** Without an oracle to transcribe, 4.0 costs
$15.88/task and Ouroboros A $15.36/task — the "6× loop cost" in the leaky rerun
was 4.0's cheap copying, not the loop. The loop still takes 1.6× the wall
time.

## Ouroboros B — the scope fix, measured

Ouroboros B (spec 2609.0002) types every finding and forbids the judge from
narrowing scope: anything the feature's code path or tests reach is
`uncovered` and gets added, marked `[INFERRED]`. Same panel, same day:

- **`vo` recovers completely** — 0.00 → **1.00**, and it is the one task
  Ouroboros B resolves. Its spec lists ten stripped `tree.py` neighbours as
  in-scope prerequisites, the exact section Ouroboros A had fenced off. `table`
  recovers most of the way (0.30 → 0.88).
- **`lombscargle` and `containers` do not move** (0.03, 0.67 — identical
  to no-spec). The `lombscargle` spec shows why: it carries a section
  titled "Known Environment Blockers" that says of `get_err_str`, an
  undefined symbol on the feature's own error path, *"do not attempt to
  fix `get_err_str`"*. The agent obeyed, marked the scenario `xfail`, and
  the hidden tests failed. 4.0's spec put the same symbol under
  "Companion gaps found during review — restore these" and scored 0.96.
  The Ouroboros B rule blocks the words "out of scope"; the producer reached for
  "environment blocker" instead. Same fence, new label.
- **Cost**: $18.69 per spec, 56 min — the loop ran to its 3-round cap
  on every task and was still raising items at the cap (ledger totals
  per task: 20–40 rows, roughly two `uncovered` per `contradiction`).
- Net: Ouroboros B recovers 0.37 → 0.70 of a 0.84 target. The remaining gap is
  one named fence pattern, not the loop's design.

## What this does not show

- N=5, one repository, one seed, single-day. The pass-rate gap between
  4.0 and Ouroboros A (0.84 vs 0.37) is large and consistent in direction on 3/5
  tasks, but is not a significance claim.
- Nothing here measures the thing Ouroboros A was built to fix — contradictions
  and muddled ordering *inside* the spec. The harness does not persist the
  evaluator's ledger; the Ouroboros A specs may well be more coherent documents
  while being worse briefings for this benchmark's task shape.
- FeatureBench's "restore a stripped feature" shape rewards broad scope.
  A benchmark where over-reaching is penalised would grade the same
  narrowing differently.
- Self-run evaluation of our own plugin.

## Provenance

- Specs: `v4/specs/*.meta.json`, `ouroboros-a/specs/*.meta.json`, `ouroboros-b/specs/*.meta.json`
  carry `mask_applied=true`, `f2p_deleted=1`, `git_reinit=true`. The Ouroboros B
  metas also carry `ledger_rounds` / `ledger_rows` (the `vo` meta predates
  the status-normalisation fix and shows zero-count rows; its ledger
  re-parses to 3/17/1, 4/7/0, 4/6/0).
- v4 stage 01 was interrupted once by user request after 4/5 and resumed
  for `vo` (the interrupted attempt's partial cost is not in the ledger).
- The first Ouroboros A inference attempt ran on a podman machine that had been
  restarted without Rosetta (the setting is read at machine start, not
  init); every cell failed at agent start-up at ~$0 and was discarded
  (`results/infer_arm_b/_failed_norosetta_*`). `~/.config/containers/
  containers.conf` now pins `provider = "applehv"`, `rosetta = true`.
- Every number is regenerable from each side's `runs.json` with the stage
  04/05/07/10 scripts; Arm A via `--report-a` pointing at the 2608 archive.

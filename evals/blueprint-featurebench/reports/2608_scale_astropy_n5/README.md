# Scale run 2608 — astropy, N=5, all four arms (2026-08-16)

First all-arms run under `claude-sonnet-5`. Panel: 5 astropy tasks from the
FeatureBench `fast` split (`panel_task_ids.txt`), one seed, implementing agent
`claude_code`/`claude-sonnet-5` identical in every arm.

Intended as the first batch of a 25-task, 5-repo panel; **stopped after batch 1**
by choice once per-batch cost came in at $128.96 (~$645 projected for the full
panel). Everything here is a single-repository result — see Limits.

| file | contents |
|---|---|
| `report.md` | A vs B paired table — resolved 0/5 vs 3/5, pass rate 0.42 vs 0.79 |
| `report_c.md` | B vs C vs C0 — all three 3/5, pass rates identical per task |
| `mutation_report.md` | agent-written test quality — Arm A shipped zero tests on 5/5 |
| `taxonomy_report.md` | failure classification, 11 unresolved cells |
| `cost_report.md` | full ledger incl. in-container inference — $128.96 |
| `panel_task_ids.txt` | the exact panel |
| `batches/astropy/` | per-stage logs and the per-batch copies of each report |

## Headline

- **Spec changes the outcome**: A 0/5 → B 3/5 resolved; 3 discordant pairs, all
  favouring B; exact McNemar **p = 0.25** (the floor at 3 pairs — *not*
  significant). Pass rate moved on exactly those 3 tasks and was identical on
  the 2 that did not move.
- **Spec is what causes tests to exist**: Arm A wrote **zero** test files on
  5/5 tasks; every spec arm wrote tests on 5/5. Replicates the N=3 sonnet-4-5
  pilot (`../2608_pilot_n3/`), where Arm A also wrote zero tests on 3/3.
- **Tests written ≠ tests good**: Arm B's kill rate is only **0.25**, and two
  of its four measurable cells killed nothing.
- **The referee loop did nothing here**: B = C = C0 = 3/5 with per-task
  identical pass rates. On test quality C0 (0.59) edged C (0.46) — at this N
  the referee is not separable from a plain second pass. This *contradicts* the
  pilot, where C lifted pass rates and C0 did not.
- **Cost**: Arm B all-in $41.16 vs Arm A $26.42 (+56%) → **$4.91 per extra
  task resolved**.

## Limits

- N=5, **one repository**, one seed. Not significant, not general.
- Self-run evaluation of the tool being evaluated.
- `test_lombscargle_multiband` was classified `spec_wrong` / **spec harmed**:
  the spec declared the graded test file and its helpers out of scope and told
  the agent not to restore them, but the hidden test set was composed entirely
  of that file. Arm A failed the same task, so the spec did not worsen the
  score — it entrenched a wrong scope boundary.
- Model contamination (the model may know astropy) biases both arms' levels
  equally under pairing, not the A/B delta.

## Provenance notes

- All 5 specs were regenerated under sonnet-5 (the pilot's sonnet-4-5 specs
  were not reused). Oracle masking verified per task: `mask_applied=true`,
  `f2p_deleted=1`.
- Arm A's low scores are not harness attrition — every cell in both arms
  terminated `success` with a substantive patch (A: 4.5–24 KB, 29–185 turns).
- Two bugs were found and fixed mid-run; both are described in the harness
  README. Verdicts, mutation cells and taxonomy cells are now fingerprinted
  against the patch they judge, so a cached artifact can never be reused for a
  different implementation.

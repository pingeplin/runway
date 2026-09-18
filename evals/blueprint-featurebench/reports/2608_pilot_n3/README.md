# Pilot 2608 — first clean run (N=3, 2026-08-15)

> **Validity caveat (added 2026-09-16).** "Clean" here means working-tree
> masking only. The workspaces the spec writer (stage 01) and the referee
> (stage 06) read still carried the upstream git history, so `git show HEAD:`
> returned the reference implementation and the deleted FAIL_TO_PASS tests —
> the leak fixed in `_common.reinit_git` and flagged in
> `../2608_scale_astropy_n5/`. Arm A is unaffected (`fb infer` re-inits git in
> the container). Every B, C and C0 number below is superseded by
> `../2609_clean_paired_astropy_n5/` (spec) and `../2609_armc_clean_astropy_n5/`
> (referee).

Archived output of the first oracle-masked pilot: FeatureBench fast split,
3 tasks (metaflow stub_generator, astropy basic_rgb, astropy comparison),
implementing agent claude_code/claude-sonnet-4-5 in every arm.

| file | contents |
|---|---|
| `report.md` | A vs B paired table — resolved 1/3 both, no discordant pairs |
| `report_c.md` | B vs C vs C0 — C lifts pass rates (0.65→0.77 mean), C0 doesn't |
| `mutation_report.md` | agent-written test quality — Arm A shipped zero tests on all 3 tasks |
| `taxonomy_report.md` | all 4 failures classified impl_wrong, spec contribution neutral |

Context: an earlier unmasked run (archived out-of-repo) showed a fake B
advantage caused by the oracle leak fixed in a5fe4c9. Headline reading and
caveats live inside each report; N=3 is hypothesis-generation only.

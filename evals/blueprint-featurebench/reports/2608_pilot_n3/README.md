# Pilot 2608 — first clean run (N=3, 2026-08-15)

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

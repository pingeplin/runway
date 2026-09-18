# Spec industry-practice pass — paired rerun, astropy, N=5 (2026-09-18)

## Question

Branch `feat/spec-quality-practices` changes what `/spec` produces:
- It adds an **Out of Scope** section with the guard "prerequisites of an
  in-scope scenario are never out of scope".
- It adds INCOSE wording rules and BRIEF scenario checks to the review.
- The `spec-evaluator` becomes report-only for scope and wording.

Out of Scope is the same kind of lever that regressed the abandoned 5.x
line: fencing scope. Does the change make the implementing agent build less
than the 4.x spec does?

## Design (fixed before inference)

| | B_4.1 | B_new |
|---|---|---|
| spec | archived 4.0 specs, [`../2609_clean_paired_astropy_n5/v4/specs/`](../2609_clean_paired_astropy_n5/README.md). `agents/spec-evaluator.md` and `references/` are byte-identical in 4.1.0. | written today by the branch plugin: `--plugin-dir plugins/blueprint`, installed `blueprint@runway` disabled. Plugin state = [`plugin.diff`](plugin.diff) on top of `main` `81b6d18`. |
| spec writer | `claude -p`, sonnet-5 (2026-09-10) | `claude -p` 2.1.276, sonnet-5, timeout 3600 s |
| implementing agent | `fb infer`, `claude_code`, `claude-sonnet-5`, in-container Claude Code pinned **2.1.272**, `n_concurrent` 1 | same |
| panel | [`panel_task_ids.txt`](panel_task_ids.txt), the 5 astropy tasks of every 2609 run | same |

- Both arms are inferred on the same day. Each arm has one run.
- Each arm runs in its own copy of the harness under
  `results/_spec_practices/{b41,bnew}/`, so neither can overwrite the other or
  `results/_armc_clean/`.
- Before any spend, a probe confirmed the plugin wiring. The init event lists
  exactly one `blueprint`: `blueprint@inline` at `plugins/blueprint`.
- B_4.1 has three earlier runs with the same specs: 0.84 on 09-10, 0.71 and
  0.73 on 09-16. Re-running the same spec swung `vo` by 0.55
  (`../2609_control_arms_astropy_n5/`).

## Reading rules (registered before inference)

Metrics:
- B pass_rate, per task and mean.
- fenced∩oracle: stage 12 heuristic, plus the stage 13 judge's hard fences as
  the reference.
- Tasks where the agent's patch adds or modifies a test file.

Rules:
1. **Guard failure on a task.** B_new hard-fences more oracle symbols than
   B_4.1 on a task **and** its pass rate on that task is lower by more than
   0.30 → the guard failed there → block release.
2. **The known mechanism.** On `lombscargle_multiband`, B_4.1 scored 0.96 on
   both earlier runs. If B_new fences `get_unit` or `strip_units` (judge
   listing), the guard failed, whatever the pass rate.
3. **Mean pass rate.** Take B_new − B_4.1:
   - within ±0.10 → no detectable change.
   - below −0.10 → regression; investigate before release.
   - above +0.10 → directional only, not claimable at N=5 with one run.
4. **Wiring.** Count B_new specs that contain an Out of Scope section;
   expected 5/5. The evaluator's *Wording Findings* output is not visible in
   stage 01's JSON result and is not checked.

## Known confounds

- One spec draw per arm. The effect of the plugin change cannot be separated
  from spec-sampling noise.
- The spec-writer Claude Code version differs between arms: B_4.1's specs
  were written on 09-10.
- N=5, one repository, one run per arm. Nothing here is significant.

## Result

**Rule 1 fired on `vo`, so release is blocked.** Three things are true on
that task:
- The symbol the judge matched is a name collision.
- The spec does fence two stripped oracle symbols, by line range, which
  neither fence metric sees.
- The pass-rate loss traces to a module neither spec names, which the agent
  treated as out of scope (see *Mechanism*).

| task | B_4.1 | B_new | Δ | test files touched (4.1 / new) | turns (4.1 / new) | infer $ (4.1 / new) |
|---|---|---|---|---|---|---|
| `test_basic_rgb` | 0.94 | **1.00** ✓ | +0.06 | 1 / 1 | 35 / 38 | 1.25 / 1.48 |
| `test_containers` | 0.65 | 0.65 | 0.00 | 0 / 1 | 48 / 119 | 3.14 / 10.49 |
| `test_lombscargle_multiband` | 0.96 | 0.98 | +0.02 | 0 / 0 | 72 / 97 | 1.95 / 2.75 |
| `test_table` | 0.35 | 0.37 | +0.02 | 0 / 4 | 103 / 158 | 4.08 / 6.28 |
| `test_vo` | 0.39 | **0.01** | **−0.38** | 0 / 0 | 167 / 118 | 6.13 / 3.71 |
| **mean / total** | **0.66** | **0.60** | −0.06 | 1 / 3 tasks | | 16.54 / 24.70 |

- Resolved: B_4.1 0/5, B_new 1/5.
- Every inference run ended `success`. None hit the 3600 s timeout;
  `containers` in B_new took 53 min.

### Fence judge

Stage 13, opus, 2 repeats. The fenced∩oracle count agrees across repeats
on every cell; the raw fence lists do not.

| task | B_4.1 hard fenced∩oracle | B_new |
|---|---|---|
| `test_basic_rgb` | 2 (`__call__`, `apply_mappings`) | 2 (same) |
| `test_containers` | 1 (`distribution`) | 0 |
| `test_lombscargle_multiband` | 2 (`get_err_str`, `ndim`) | **0** |
| `test_table` | 8 | 6 |
| `test_vo` | 0 | **1** (`FieldRef.get_ref`) |
| mean | 2.6 | 1.8 |

B_4.1's mean of 2.6 reproduces the 09-12 validation exactly
(`../2609_doc_quality_validation/`), so the judge is stable across days.

### Rules as registered

1. **Fired on `vo`.** Both conditions hold: B_new's hard fences on vo rose
   from 0 to 1, and its pass rate fell by 0.38 (> 0.30). **Block release.**
2. **Passed.** B_new fences nothing on `lombscargle_multiband`. It puts
   `strip_units`/`get_unit` in scope explicitly ("restored only because the
   class cannot run at all without them") and scores 0.98.
3. **No detectable change.** The mean difference is −0.06, inside ±0.10.
4. **Passed.** 5/5 B_new specs have an Out of Scope section.

### Mechanism on `vo`

- **The judged fence is a name collision.** The judge flagged
  `FieldRef.get_ref`. Stage 13 matches oracle symbols by bare name, and the
  mask stripped `ParamRef.get_ref`, while `FieldRef.get_ref` was intact. The
  new spec puts `ParamRef.get_ref` in scope (17 mentions). So rule 1's fence
  condition held on the letter of the registered metric, not in substance.
- **The loss is `astropy/utils/xml/check.py`.** The mask stripped `check_id`,
  `fix_id`, `check_token` and `check_anyuri` there. B_new's hidden-test
  output has 171 `E` lines of `AttributeError: module
  'astropy.utils.xml.check' has no attribute 'check_id'`.
  - Neither spec mentions `check.py`.
  - Every vo patch written against the 4.x spec restored it: 09-16 B, C and
    C0 (`results/_armc_clean/`) and today's B_4.1, 4 of 4.
  - B_new's patch did not.
- **The B_new agent found the gap and chose to leave it.** In its own words:
  - "monkeypatches the unrelated, out-of-scope `check.py` gaps (not part of
    my task)".
  - "those patches were never written to disk, only used in throwaway
    verification scripts".
  - "`check_id`, `fix_id` … are out of scope for this task's Interface
    Description and weren't touched".
- **Reading.** The two specs frame scope differently:
  - The 4.x vo spec has a section, "Blocking prerequisites: other definitions
    stripped from the same file … are in scope … restore the prerequisites
    first", and agents generalise it to other stripped modules.
  - The B_new spec's Out of Scope section lists stripped regions as "left
    untouched" (the `Values` and `MivotBlock` gaps, "not on the execution
    path of any scenario").
  - Those two gaps are the stripped oracle symbols `Values._parse_minmax`
    and `MivotBlock.__str__`. The spec fences them by line range, not by
    name, so neither stage 12 nor the stage 13 judge counts them. The real
    oracle fence on vo is at least 2, and both fence metrics missed it.
  - The agent generalised that to unnamed gaps elsewhere.
  - The guard sentence ("prerequisites of an in-scope scenario are never out
    of scope") cannot help here. The spec author never identified
    `check.py` as a prerequisite.
  - This is the Ouroboros mechanism one layer down: the section need not
    fence a named oracle symbol to narrow what the agent builds; its
    existence licenses "leave the other gaps".

### Against this reading

- `vo` is the noisiest task on the panel. The same 4.0 spec scored 0.95 on
  09-10 and 0.40 on 09-16, so −0.38 is inside that task's known swing.
- There is one spec draw and one inference run per arm.
- The check.py evidence (4/4 vs 0/1, with the agent's stated reason) points
  at the spec. Separating it from noise needs a second B_new run on `vo`.

### Stage 12's fence heuristic is broken by the new template

The phrase-based fenced∩oracle count goes from 10 (B_4.1) to 38 (B_new),
while the judge goes from 2.6 to 1.8 per spec
([`doc_quality_report.md`](doc_quality_report.md)). The new Out of Scope
section names in-scope *boundary* symbols ("everything else in X beyond the
two helpers `strip_units`/`get_unit`"), and the heuristic counts every
oracle symbol under an out-of-scope heading. Until the heuristic reads
sentence intent, the judge is the only usable fence metric for specs with
this section.

### Spend

$109.18 today:
- B_4.1 inference: $16.54.
- B_new specs: $56.91 ($6.44–17.63 per task).
- B_new inference: $24.70.
- Fence judge: $11.03.

`b41/cost_report.md` shows a panel total of $95.93. That total includes
$79.39 for the archived specs, which was paid on 09-10.

## Files

- `b41/`, `bnew/` — `report.json` (fb eval), `output.jsonl` (patches),
  `tasks.json`, `cost_report.md`.
- `bnew/specs/` holds the 5 new specs with their meta.
- `doc_judge/`, `doc_judge_report.md` — stage 13 cells and table.
- `doc_quality_report.md` — the stage 12 table.
- `plugin.diff` — the plugin state that wrote the B_new specs.
- `run.sh` — the driver. The per-arm harness copies lived under
  `results/_spec_practices/` (gitignored).

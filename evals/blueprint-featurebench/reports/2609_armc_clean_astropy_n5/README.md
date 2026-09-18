# Arm C / C0 clean rerun — does the `/verify` referee beat a generic self-review? astropy, N=5

> **Status: pre-registered 2026-09-16 before any paid cell ran.** The reading
> rules below were fixed first. Results are appended under "Results"; anything
> not derivable from these rules is labelled post-hoc.

## Question

`/verify` is half the product — blueprint 4.0 replaced TDD's fail-first
guarantee with a referee that proves non-vacuity **by inspection**
(`plugins/blueprint/skills/verify/SKILL.md:38`). That replacement has never
been measured on a clean panel.

Every Arm C number in this repo predates the git-history masking fix
(`b6db0b7`, 2026-09-12): `reports/2608_pilot_n3/` and
`reports/2608_scale_astropy_n5/` both ran 2026-08-15/16. They are unusable for
the same reason the two retracted benchmark headlines were.

The bar this run is measured against is the product's own, not FeatureBench's:
*an independent agent reviews the test cases; as long as they are reasonable and
steer the implementation to correct code, that is enough.* So the **primary
metric is test quality, not resolved count.**

## Arms

Same panel (`panel_task_ids.txt`), same implementing agent
(`claude_code` / `claude-sonnet-5`), in-container Claude Code pinned to
**2.1.272**, all inferred the same day.

| arm | round | problem statement |
|---|---|---|
| B | 1 | original + separator + the archived blueprint 4.0 spec |
| C | 2 | original + spec + B's patch + **the headless `/verify` verdict** + repair instruction |
| C0 | 2 | original + spec + B's patch + **a generic self-review instruction** + repair instruction |

C0 is the attribution control: it isolates "the referee's content" from "a
second pass happened at all".

**Specs are reused, not rewritten.** The five blueprint 4.0 specs archived at
`reports/2609_clean_paired_astropy_n5/v4/specs/` are restored verbatim; all five
carry `mask_applied: true` and `git_reinit: true`. Stage 01 therefore runs
cached at $0, and stage 01b (`scripts/01b_rebuild_workspaces.py`,
added for this run) rebuilds the masked workspaces stage 06 needs without any
model spend. B's round-1 patch is regenerated rather than reused — the
2026-09-10 artefacts were lost to temp-directory cleanup, and regenerating
puts B, C and C0 on the same day and the same agent version, which is required
anyway.

## Pre-registered reading

**Primary — kill rate (no-tests = 0), C − C0.** This is the only metric that
grades the agent's own tests, which is what the referee is supposed to improve.

The ruler is unstable and that is priced in: stage 07's mutation sites are
LLM-chosen per cell, so panels differ between arms, and the two existing
measurements disagree in direction — pilot C 0.50 vs C0 0.40
(`reports/2608_pilot_n3/mutation_report.md`), scale C 0.46 vs C0 0.59
(`reports/2608_scale_astropy_n5/mutation_report.md`). Both gaps are 0.10–0.13.

1. **C − C0 ≥ +0.15** → the referee's content beats a generic self-review on
   test quality. The v4.0 bet is supported on this panel.
2. **C − C0 ≤ −0.15** → the referee is worse than telling the agent to check
   its own work. The bet fails.
3. **|C − C0| < 0.15** → **indistinguishable, which is a negative result for
   the referee**, not a null one: a $1.8/task referee that does not beat one
   sentence of self-review has not earned its place.
4. **C − B and C0 − B** say whether a second pass helps at all, in either arm.
   Both are confounded by "a second attempt from scratch" (see Known defects);
   only C − C0 is clean.

**Secondary — mean pass rate**, same 0.15 band as
`reports/2609_control_arms_astropy_n5/`. **Reported only — resolved count.** At
N=5 with one seed it cannot decide anything.

Every conclusion is directional: N=5, one repository, one seed per arm.

## Known before running

Three defects in the stage-06 design were verified in the source before this run
and are **not** fixed here, because fixing them changes what the experiment
measures:

- **The referee never runs the test suite.** `prompts/verify_headless.md:21`:
  "Hard constraint: you cannot run the test suite" — deps live in docker and the
  referee runs on the host. `/verify`'s first gate is unexercised, so this
  measures a *weakened* referee, and a null result does not acquit the full skill.
- **Round 2 discards the patch.** `prompts/repair_instruction.md`: "Start from
  the pristine repository (the patch above is NOT applied)." C and C0 are fresh
  reimplementations informed by feedback text, not repairs. This confounds
  C − B; it does **not** confound C − C0, since both arms restart identically
  and only the feedback block differs.
- **FeatureBench rewards breadth and penalises scope-fencing**
  (`plugins/blueprint/README.md`, "What this does not show"). A referee that
  correctly tells the agent to narrow scope would be punished here.

One defect **was** fixed, because it made the control not a control:

- `prompts/repair_instruction.md` closed with "addressing **the verdict**" for
  both arms, so C0 was told to respond to a verdict it was never given. Changed
  to "addressing the feedback above", which is neutral and keeps the two prompts
  byte-identical outside the feedback block. **This run is therefore not
  directly comparable to the 2608 Arm C numbers** — which are leaky and
  unusable regardless.

**Not a defect, contrary to an earlier draft analysis:** stage 06 does *not*
still leak the oracle. `06_arm_c.py`'s `prepare_workspace` calls
`reinit_git(dest)`, and `_common.py:86–93` names the referee explicitly as an
actor that must not recover the oracle from history. The leak was real for the
2608 runs and is fixed in the code as it stands.

Estimated spend: B round 1 ~$19, verdicts ~$9, C + C0 inference ~$40–50,
mutation overlay unpriced. Self-run evaluation of our own plugin; not independent.

## Results (2026-09-16)

Every cell terminated `success` with a non-empty patch. All 15 in-container
transcripts report `claude_code_version` **2.1.272** and model
`claude-sonnet-5`. Verdicts were computed once (5/5 `ok`) and reused through the
`patch_sha256` cache.

**Two runs were killed by host memory pressure** (16 GB host, podman VM at
7630 MB): once at infer concurrency 2, once at concurrency 1 shortly after
restart. Both left orphaned `fb-infer-*` containers, as had a 2026-09-10 run
that was still `Up` five days later; all were removed. The completed run used
infer concurrency 1 with desktop apps closed. The killed partial Arm C cells are
not in `runs.json`.

**New spend ≈ $65.41**: B infer $14.79, verdicts $9.26, C infer $23.74, C0 infer
$16.16, killed partials ≥ $1.46 (a lower bound — a cell killed mid-flight emits
no cost event). The mutation overlay is unpriced. `cost_report.md`'s panel total
of $143.34 includes the $79.39 spec stage from 2026-09-10, which was reused here,
not re-spent.

### Primary — kill rate, C − C0

| arm | measured | no_agent_tests | baseline_red | kill rate (no-tests = 0) | kill rate (baseline_red = 0 too) |
|---|---|---|---|---|---|
| B | 1 | 4 | 0 | 0.067 | 0.067 |
| C | 1 | 1 | 3 | **0.167** | 0.067 |
| C0 | 1 | 3 | 1 | **0.042** | 0.033 |

C − C0 = **+0.125** on the pre-registered denominator, **+0.033** scoring
`baseline_red` as 0.

### Secondary — pass rate

| task | B | C | C0 |
|---|---|---|---|
| `basic_rgb` | 0.94 | 0.94 | 0.94 |
| `containers` | **1.00** ✓ | 0.90 | 0.98 |
| `lombscargle_multiband` | 0.96 | 0.96 | 0.96 |
| `table` | 0.35 | 0.35 | 0.35 |
| `vo` | 0.40 | **0.95** | 0.40 |
| **mean pass rate** | 0.73 | **0.82** | 0.73 |
| resolved | 1/5 | 0/5 | 0/5 |

C − C0 = +0.09. Resolved: every paired McNemar p = 1.0 (`report_c.md`).

### Against the pre-registered reading

**Rule 3. |C − C0| < 0.15 on kill rate under both denominators — indistinguishable,
which this run pre-registered as a negative result for the referee.** The
secondary metric agrees: C − C0 on pass rate is +0.09, inside the band.

### What the instrument actually graded (post-hoc, not pre-registered)

1. **Kill rate graded one cell per arm, and it was the same cell.** Every arm's
   only measured cell is `basic_rgb`, where all three wrote their tests to
   `astropy/visualization/tests/test_basic_rgb.py` — the path FeatureBench
   deleted as the oracle. Kills there: B 2/6, C 2/6, C0 1/6. The primary
   metric's entire between-arm difference is one killed mutation on one
   oracle-path file.

2. **`baseline_red` did not mean what the pre-registration assumed.** It was
   read as "the agent's own tests fail against the agent's own code". Stage 07
   actually runs *every test file the patch touched*. When an agent appends
   tests to a pre-existing file, that file's pre-existing tests run too — and on
   FeatureBench many of them exercise functionality the mask stripped. Splitting
   the failures captured in each pytest tail into agent-written and
   pre-existing:

   | cell | failed | visible in tail | written by the arm | pre-existing |
   |---|---|---|---|---|
   | C · `vo` | 7 | 7 | 0 | 7 |
   | C · `table` | 11 | 9 | 1 (`test_unit_format`) | 8 |
   | C · `lombscargle_multiband` | 19 | 8 | 0 | 8 |
   | C0 · `table` | 7 | 7 | 0 | 7 |

   The pattern is the same in both arms, so this is a property of the
   instrument, not a difference between them. But its effect is not neutral:
   the exclusion rule removed three of the referee arm's four test-writing
   cells from grading, for failures that were — in the captured tails — all but
   one not its own.

3. **Test writing changed; nothing graded it.** New test functions added to test
   files: B 15 on 1/5 tasks, C 68 on 4/5, C0 26 on 2/5. The referee verdict was
   followed by about 2.6× the test-writing of a self-review instruction. Whether
   those tests kill mutations is unmeasured. This is a behaviour difference, not
   a quality lift. *(Later measured: Referee audit, Layer 3.)*

4. **The pass-rate difference is one task, and it is not the referee's.** Three
   tasks score identically across all three arms despite different patches. C's
   +0.09 is entirely `vo` 0.40 → 0.95 — and that is a real code difference, not
   noise: C passes 101 FAIL_TO_PASS tests that B and C0 fail, all in
   `astropy/io/votable/tests/test_vo.py`, because C restored a stripped
   three-line `_splitter_lax` in `converters.py`, a file C0 never touched. The
   `vo` verdict never mentions `converters.py`, binary2 or `test_vo.py`. What the
   verdict *did* name — a real bug in B's `UCDWords.__init__`, which added every
   word to both the primary and secondary sets — C0 also fixed, from the
   self-review instruction alone. On the evidence, the one task that moved is not
   attributable to the referee's content.

5. **A published claim does not replicate.** `plugins/blueprint/README.md` states
   that with a spec the agent "wrote tests on three of five" (measured
   2026-09-10, flagged there as not re-measured). Same specs and panel, this run:
   **B wrote tests on 1/5.** Arm B pass rate across the three same-spec runs:
   0.84 (09-10), 0.71 (09-16 controls), 0.73 (this run).

### Reading

The pre-registered answer is negative: on this panel the headless referee did not
beat a one-sentence self-review on the primary metric, under either denominator.

The instrument behind that answer graded one task per arm, on the oracle's own
test path, and excluded three of the referee arm's four test-writing cells for
failures that were almost entirely pre-existing. This run therefore does not show
that the referee improves test quality, and it cannot show that it does not. The
question the pre-registration asked remains unmeasured. What the run does show is
a behaviour change — more tests, on more tasks — that nothing here grades.

> **Superseded the same day (post-hoc):** test quality was then measured directly
> with an oracle-anchored grader — see *Referee audit — measuring the referee
> directly*, Layer 3. The pre-registered verdict above is unchanged.

### Proposed next step (not run)

Scope stage 07 to agent-added tests: collect the test IDs the patch introduces,
run only those, and mark a cell `baseline_red` only when an agent-added test
fails. Then re-score the three patches archived in `runs.json`. That needs no
inference, verdict or spec spend — the mutation stage only.

> **Done, differently (post-hoc):** `referee_audit/layer3/grade.py` grades agent-added
> and agent-modified tests by exact node ID, but against one shared set of
> reference mutants filtered by the hidden tests rather than per-arm mutants, so
> arms are comparable. See *Referee audit*, Layer 3.

## Referee audit — measuring the referee directly (post-hoc, 2026-09-16)

Kill rate could not say whether the referee improves tests, so the question was
split into three, cheapest first: **(1)** are the verdict's claims right, and what
did it miss; **(2)** did the referee arm act on them where self-review did not;
**(3)** are the resulting tests correct against the reference implementation.
Everything is in `referee_audit/`.

**Ground truth** (`ground_truth.py`, deterministic): B's failing FAIL_TO_PASS
tests, clustered by the exception that failed them. Chained tracebacks print the
handled inner exception first, so the cluster key is the *last* `E` line of each
pytest section. Round-2 regressions (tests B passed that C or C0 fail) are listed
separately.

**Judge** (`judge.py`, `judge_prompt.md`): blind `claude-opus-5`, every tool
disabled, empty working directory, prompt on stdin. It sees the verdict, B's patch,
B's failure clusters *without* how many each arm fixed, the source of every test
the verdict names, and the C and C0 patches under X/Y labels alternated by panel
position (C is X on three tasks, Y on two). Spend **$7.54**.

**Judge validation, fixed before any call** (`judge_validation.md`): four facts
about `vo` verified by hand. The judge reproduced all four on **3/3 repeats**.
Self-agreement: claim count 4/3/4; one single-test cluster scored NO/PARTIAL/PARTIAL;
everything else identical. One further C-only attribution was checked by hand
after the run: the `vo` punch list asks for `test_empty_table` to assert
`len(table.to_table()) == 0` and `colnames == ["unsignedByte", "short"]`; C's patch
adds exactly those two assertions, and C0 does not touch the file.

### Layer 1 — are the referee's claims right?

| task | claims | TRUE | false positive | unverifiable | failure clusters caught | failing tests caught |
|---|---|---|---|---|---|---|
| `basic_rgb` | 4 | 4 | 0 | 0 | 0 / 1 | 0 / 1 |
| `containers` | 2 | 2 | 0 | 0 | — (B resolved) | — |
| `lombscargle_multiband` | 8 | 7 | 0 | 1 | 0 / 5 | 0 / 37 |
| `table` | 7 | 6 | 0 | 1 | 3 / 7 | 11 / 28 |
| `vo` | 4 | 3 | 0 | 1 | 0 / 3 | 0 / 110 |
| **all** | **25** | **22** | **0** | **3** | **3 / 16** | **11 / 176** |

By kind, every verifiable claim was true: `impl_defect` 6/6, `missing_tests` 12/12,
`vacuous_test` 2/2, `other` 2/2. **Precision 22/22; recall 11 of 176 failing tests.**

The two numbers do not rest on the same footing. **Precision is judge-assessed:**
3 of the 22 true claims — all on `vo` — were confirmed by hand; the other 19 rest on
one blind reading. **Recall's denominator is deterministic** (clusters come from
pytest output); only whether the verdict names each cluster is judged, and for
`vo`'s 107-test cluster that was confirmed by hand. The `vo` verdict did not just
miss that cluster; it closed by declaring the rest of the work sound: "Everything
else — `ParamRef.get_ref`, `TableElement.to_table`, … and the incidental
`check.py`/`iterparser.py`/`validate.py`/`exceptions.py`/`Values._parse_minmax`
restorations — reads as correct and does not need rework."

### Layer 2 — did the referee arm act on them?

Of the 22 true claims:

| | C only | both | C0 only | neither |
|---|---|---|---|---|
| `missing_tests` | 10 | 2 | 0 | 0 |
| `vacuous_test` | 2 | 0 | 0 | 0 |
| `impl_defect` | 1 | 3 | 1 | 1 |
| `other` | 1 | 0 | 0 | 1 |
| **all** | **14** | **5** | **1** | **2** |

On test claims the referee arm acted where self-review did not (12 C-only, 0
C0-only). On implementation defects the arms are level (4 addressed each).

That test signal is concentrated. **7 of the 10 C-only `missing_tests` claims are
on `lombscargle_multiband`**, where B, C and C0 all pass the same 923 of 960 hidden
tests and no arm fixed any of the 37 failures. By task, the 14 C-only claims are
`lombscargle_multiband` 7, `basic_rgb` 3, `table` 2, `vo` 2 — the same shape as the
spec's lift, which was also one task.

Against the hidden tests, exact passing sets:

| task | C and C0 identical? | passes only C has | passes only C0 has |
|---|---|---|---|
| `basic_rgb` | yes | 0 | 0 |
| `containers` | no | 1 | 5 |
| `lombscargle_multiband` | yes | 0 | 0 |
| `table` | yes | 0 | 0 |
| `vo` | no | **101** | 0 |

On `containers` C broke 5 tests B had passed and C0 broke 1. The 101 on `vo` are
the 107-test `E04: Invalid bit value` cluster — which the referee **did not catch**.
Nothing C gained over C0 on the hidden tests traces to a referee claim.

### Layer 3 — do the tests catch bugs? (`layer3/`)

**Grader** (`layer3/grade.py`, `layer3/l3_helper.py`, no model spend). Every arm is
graded against the same target — the unmasked reference — and the same mutants:
deterministic AST operators (comparison, boolean and arithmetic swaps, integer and
boolean constants, dropped `not`, `return None`) applied only to lines the dataset's
mask removes, sampled evenly to at most 200 per task, and **kept only if the hidden
FAIL_TO_PASS tests kill them**. An arm's tests are the test functions its patch added
*or modified* (so strengthening `test_empty_table` counts), applied after the oracle
test files are deleted and run by exact node ID; tests that fail on the reference are
excluded. A mutant is killed when those tests exit 1 or 2.

**Controls, every task:** identity (`ast.unparse` of each mutated file leaves the
hidden tests' results unchanged) dropped 0 files; negative (a suite that only imports
the masked modules) killed **0**; positive (half the hidden tests scored on the other
half's mutants) is in the table.

| task | mutants | killable (K) | negative | positive (half on half) | B | C | C0 |
|---|---|---|---|---|---|---|---|
| `basic_rgb` | 59 | 18 | 0 | 16/18, 16/16 | 16/18 | 16/18 | 16/18 |
| `containers` | — | — | — | — | no tests | no tests | no tests |
| `lombscargle_multiband` | 139 | 47 | 0 | 32/34, 32/45 | no tests | **15/47** | no tests |
| `table` | 200 of 203 | 106 | 0 | 61/93, 61/74 | no tests | **32/106** | 27/106 |
| `vo` | 130 | 54 | 0 | 51/51, 51/54 | no tests | **23/54** | no tests |

Mean kill rate, no-tests = 0, over five tasks: **B 0.18, C 0.39, C0 0.23**, so
C − C0 = +0.16. This is a post-hoc instrument, not the pre-registered one; the
pre-registered ±0.15 band does not transfer to it, and the pre-registered verdict
above stands.

**Where the gap comes from.** About 95% of it is `lombscargle_multiband` and `vo`,
where C wrote tests and C0 wrote none. Head to head, where both arms wrote tests:

- `basic_rgb`: the same 16 mutants killed by all three arms.
- `table`: C kills a strict superset of C0's — 27 shared, 5 C-only, 0 C0-only. All
  five are in `function_helpers.py`'s `_as_quantity`, `_quantities2arrays` and
  `_iterable_helper`, the helpers behind the layer-2 C-only claim "add direct
  `UnitConversionError` tests for concatenate/select/choose, and a nanmedian `out=`
  test". C's added tests in that file are `test_concatenate_incompatible_units_raises`,
  `test_select_…`, `test_choose_…`, `test_iterable_helper_out_not_quantity_raises` and
  `test_nanmedian_out_unit_is_overwritten`. Which test killed which mutant was not run.

**Strength against the ceiling.** Where the arms wrote their own tests, those tests
catch 25–43% of the mutants the hidden suite detects; half the hidden suite catches
66–100%. `basic_rgb` is the exception — every arm reaches 16/18, level with half the
hidden suite — and it is also the task where every arm wrote its tests to the
oracle's own path in a public repository, so those tests may reproduce upstream ones.

**Caveats.** One seed per arm, and test-writing is itself noisy: from the same specs,
B wrote tests on 3/5 tasks on 2026-09-10 and on 1/5 here, so "C0 wrote no tests on
`lombscargle_multiband` or `vo`" is a single draw. Mutants within a task are not
independent; no significance test is attempted.

### Layer 3 feasibility probe (`probe_layer3.py`, before the grader)

Restore `/testbed` from `/root/my_repo` (the unmasked reference), delete the
FAIL_TO_PASS test files as fb's `_initialize_level1` does, apply only the arm's
test-file hunks, and run only the test functions the arm added. The deletion is
required: every arm wrote `basic_rgb`'s tests to the oracle's own path, and on the
reference that file exists, so B's hunk failed with "already exists in working
directory" until it was removed. The source stays unmasked.

| cell | tests added | applied to reference | against the reference |
|---|---|---|---|
| B · `basic_rgb` | 15 | cleanly (after oracle-file deletion) | 14 pass, 2 fail |
| C · `vo` | 12 | cleanly | 11 pass, 1 fail |
| C · `table` | 21 | cleanly | all pass |
| C0 · `table` | 12 | cleanly | all 12 pass |

The failures are informative. C's `test_names_over_ids_collision` covers the
collision rule the `vo` verdict listed as untested, and asserts `["x", "x1"]` where
the reference produces `["x", "x2"]`. B's `test_apply_mappings_is_used_not_inlined`
tests an internal call path rather than behaviour, so it breaks on a correct
implementation built differently; B's second failure,
`test_uint8_quantization_uses_full_range` (`TypeError` at `image_rgb *= pixmax`),
was not read closely. C0's `table` tests — excluded by stage 07 as `baseline_red` —
all pass against the reference. Layer 3 is feasible for all three arms on the
probed cells.

Defects to avoid in a real grader: the probe pipes pytest into `tail`, which masks
its exit code; `-k` is a substring match (C · `table` selected 22 tests for 21
names, B · `basic_rgb` 16 for 15), so select exact node IDs; and delete the oracle
test files before applying an arm's tests.

### Reading

The product's own bar has two halves — *reasonable tests* that *steer the
implementation to correct code* — and on this panel the referee meets the first and
not the second.

**Reasonable tests: yes.** Every criticism the judge could verify was true. The
referee arm wrote the tests those criticisms asked for where self-review wrote none,
and the tests catch real bugs: 30–43% of the hidden suite's detectable mutants on the
three tasks other than `basic_rgb` where C wrote them, against 25% for C0 on the one
such task it had.
Where both arms wrote tests, the referee arm's were level (`basic_rgb`) or a strict
superset traceable to a named claim (`table`, +5 of 106).

**Steering to correct code: no.** The criticisms covered 11 of the 176 hidden tests
that failed; the only hidden-test gain C made over C0 came from a defect the verdict
never mentioned, in a verdict that called the rest of the work sound; and on three
tasks C and C0 pass identical hidden-test sets.

**Hypothesis, not tested:** the misses are runtime breakage — `NameError` on the
stripped `get_err_str` and `trig_sum`, `E04` from the missing `_splitter_lax` — which
a referee allowed to run the suite would see on its first check. The headless
referee is forbidden from running it (`prompts/verify_headless.md:21`).

N=5, one seed per arm, one judge model.

## Reproduce

Run in a clean copy of the harness: stage 01 short-circuits on any cached spec it
finds, whatever produced it.

```bash
cd evals/blueprint-featurebench
R=results/_armc_clean && mkdir -p $R/results/specs
cp -R scripts prompts samples fb_config.toml $R/
cp reports/2609_clean_paired_astropy_n5/v4/specs/* $R/results/specs/
cp reports/2609_armc_clean_astropy_n5/panel_task_ids.txt $R/panel.txt
# In $R: config.toml as in config.example.toml with [infer] n_concurrent = 1 and
# [eval] n_concurrent = 2 on a 16 GB host; fb_config.toml CLAUDE_CODE_VERSION = "2.1.272".
cd $R
uv run --with datasets python3 scripts/01_make_specs.py --task-ids-file panel.txt         # cached, $0
uv run --with datasets python3 scripts/01b_rebuild_workspaces.py --task-ids-file panel.txt # docker only
uv run --with datasets python3 scripts/02_make_dataset.py
uv run --with datasets python3 scripts/03_infer.py --arm B
uv run --with datasets python3 scripts/04_eval.py --arm B
uv run --with datasets python3 scripts/06_arm_c.py --arm both-c --stage all
uv run --with datasets python3 scripts/07_mutation.py --arm both --out results/mutation_report.md
uv run --with datasets python3 scripts/05b_report_c.py
uv run --with datasets python3 scripts/10_costs.py --task-ids-file panel.txt --out results/cost_report.md
```

The referee audit's scripts are archived under `referee_audit/` for reading; they
resolve paths relative to the run root, so to re-run them copy them back to
`$R/analysis/` (and `$R/analysis/layer3/`) and run from `$R`:

```bash
uv run python3 analysis/ground_truth.py
uv run python3 analysis/judge.py                  # blind opus judge, ~$7.5
uv run python3 analysis/layer3/grade.py --cap 200  # containers only, ~2 h on a 16 GB host
```

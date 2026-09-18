# blueprint × FeatureBench — paired spec ablation

The core question: **does handing an implementing agent a blueprint-produced
spec change what it builds on FeatureBench?** Mean pass rate is the primary
number; resolved is reported but cannot decide anything at N=5.

The core design is two arms over the same tasks, same agent, same model:

- **Arm A (control)** — `fb infer` on the official dataset. The agent sees the
  original `problem_statement`.
- **Arm B (treatment)** — a pre-stage runs blueprint's `/spec` headlessly
  against each task's codebase, then `fb infer` runs on a locally rewritten
  copy of the dataset whose `problem_statement` is *original + spec*.

Both arms are scored by the unmodified `fb eval` against the **official**
dataset. Predictions carry only `instance_id` and `model_patch`, so the
treatment cannot leak into scoring.

Arm C / C0 (the `/verify` referee), the control arms, the mutation overlay and
the doc-quality metrics are overlays on that design, each with its own stage
below. What the reports currently show is indexed in `../README.md`.

Design rationale: `docs/designs/2608.0001_blueprint_eval_featurebench_ablation.md`.

## Metrics

Every task ships hidden **FAIL_TO_PASS tests** — the official oracle. They all
fail until the feature is built correctly; the agent never sees them.

- **Resolved** — did ALL of the task's hidden tests pass? Binary, strictest,
  the leaderboard metric. One failing test = not resolved.
- **Pass rate** — the FRACTION of hidden tests that pass (13 of 20 → 0.65).
  The partial credit `resolved` throws away: two unresolved patches at 0.65
  vs 0.37 are very different, and on a small panel pass-rate deltas are often
  the only visible movement.
- **Kill rate** (mutation overlay) — grades a different artifact: the tests
  the AGENT ITSELF wrote. We plant deliberate bugs in the agent's own source
  changes (flip a boundary, break a constant) and run the agent's own tests.
  Test goes red → the bug is *killed* (the test works); stays green → the bug
  *survived* (the test is decoration). Kill rate = killed / planted. This is
  the only metric here that catches vacuous tests — 100% coverage with a ~4%
  mutation score is invisible to `resolved`/pass rate. Shipping no tests at
  all is scored 0.0, not skipped. **Known limit:** stage 07 runs every test
  *file* a patch touched, so tests appended to a pre-existing file drag in
  that file's mask-broken tests and the cell is excluded as `baseline_red`;
  and mutation sites are LLM-chosen per cell, so arms are not graded on the
  same mutants. On `reports/2609_armc_clean_astropy_n5/` this left one graded
  cell per arm. The oracle-anchored grader in that report's
  `referee_audit/layer3/` avoids both and is not yet a stage.

- **Doc quality** (stages 12–13) — grades the *spec itself*, not the agent.
  Deterministic against the oracle: **oracle recall** (share of the
  mask-removed `def`/`class` symbols the spec names — breadth), **fenced ∩
  oracle** (oracle symbols the spec forbids the agent to touch — the
  lombscargle failure as a count), **grounding precision** (share of named
  files/identifiers that exist in the masked workspace — it cannot tell a
  hallucinated name from a new helper the spec chose to design, so read it
  as diagnostic). Judged, report-only, blind opus: the **fence listing**
  (reference for the heuristic) and **scenario testability** (behavioral
  share). Coherence (contradiction counts) was judged once on the 15-spec
  corpus, showed no relation to pass_rate and ±1–4 judge self-disagreement,
  and was dropped (`reports/2609_doc_quality_validation/`). Both stages report each
  metric's direction against B pass_rate (pooled ρ and within-task
  concordance) so it can be checked before anything is optimised against it;
  a metric that points the wrong way is diagnostic only. Design docs have a
  rubric (`DESIGN_RUBRIC.md`) but no corpus yet.

Shorthand: resolved asks "is it done?", pass rate "how close?", kill rate
"is the agent's own QA real?".

## Prerequisites

| Requirement | Notes |
|---|---|
| `docker` CLI backed by podman | Every stage that extracts a testbed or runs a container needs it. Images are amd64-only and 18–22GB each. The podman machine must be `applehv` + Rosetta: on libkrun the in-container Claude Code aborts at start and every cell returns an empty patch at ~$0. On a 16GB host, run inference with `n_concurrent = 1` and close desktop apps. |
| `uv` | Every Python command runs as `uv run --with datasets python3 …`; scripts are stdlib-only otherwise. |
| `featurebench` | **Not on PyPI.** `uv tool install git+https://github.com/LiberCoders/FeatureBench.git`. Provides the `fb` CLI. Stage 00 installs it for you. |
| `CLAUDE_CODE_VERSION` pinned in `fb_config.toml` | `fb` installs `@latest` in the container otherwise, so arms run on different days run different agents. |
| `claude` CLI, authenticated | Stage 01 shells out to it. `claude --version` must work. |
| blueprint plugin installed | The `spec` skill must resolve inside a `claude -p` run started from an arbitrary directory. Install it from this marketplace (`/plugin` → `runway` → `blueprint`) so it is user-scoped, not repo-scoped — stage 01 runs inside extracted task codebases, not inside this repo. |
| `ANTHROPIC_API_KEY` | Used by stage 01 directly and by the in-container agent via `fb_config.toml`. |

## Run a panel

```bash
cd evals/blueprint-featurebench
cp config.example.toml config.toml
cp fb_config.example.toml fb_config.toml   # put your ANTHROPIC_API_KEY here
$EDITOR config.toml fb_config.toml
```

Start small. `[eval] limit = 3` for the first pass — stage 01 is the risky one
and you want to see it work before paying for more. A panel that will be
published takes an explicit `--task-ids-file` (`samples/`), and spans several
images: use `run_batch.sh` (see "Running a multi-image panel") rather than the
stage-by-stage walk below.

**0. Setup**

```bash
bash scripts/00_setup.sh
```

Installs `featurebench` if `fb` is missing, checks docker / `claude` /
`ANTHROPIC_API_KEY` / config files, then pre-pulls the split's images with
`fb pull --mode lite` — deliberately not the configured split (override with
`SPLIT=fast bash scripts/00_setup.sh`). Do not pre-pull the whole `fast` split on a capped podman VM: its 18 images
far exceed 93GB. `run_batch.sh` pulls and purges one image per batch.

**1. Specs (Arm B pre-stage)**

```bash
uv run --with datasets python3 scripts/01_make_specs.py
```

Per task: `docker create <image>` + `docker cp <cid>:/testbed` into
`results/workspaces/<id>/`, then `claude -p <rendered prompt> --output-format
json <claude_args> --model <spec.model>` with that workspace as cwd. The spec
is located via the `SPEC_PATH:` marker the prompt demands, falling back to the
newest `.md` under `<workspace>/.blueprint/specs/`.

Resumable — tasks with a successful `results/specs/<id>.meta.json` are skipped
unless you pass `--force`. Other flags: `--limit N`, `--task-ids-file <file>`.
The skip does not check how the cached spec was made: a spec written before
the history-masking fix is reused silently. Start a new panel in a clean
`results/`.

**1b. Rebuild workspaces for restored specs**

```bash
uv run --with datasets python3 scripts/01b_rebuild_workspaces.py --task-ids-file panel.txt
```

A cached spec skips extraction, but stage 06 needs the masked workspaces.
This does stage 01 minus the `claude -p` call, for $0 of model spend, and
refuses to write a workspace whose mask did not apply. Use it when a panel
reuses an archived spec set (`reports/2609_clean_paired_astropy_n5/v4/specs/`).

**2. Arm B dataset**

```bash
uv run --with datasets python3 scripts/02_make_dataset.py
```

Writes `results/dataset_arm_b/` (a JSONL data file plus a `README.md` whose
YAML front-matter declares the split) and immediately loads it back to assert
the row count and the mutated `problem_statement`. Only `spec_ok` tasks are
included — the paired design needs both cells, so a task that failed stage 01
is dropped from **both** arms.

**3. Inference (both arms)**

```bash
uv run --with datasets python3 scripts/03_infer.py --dry-run   # inspect the commands first
uv run --with datasets python3 scripts/03_infer.py
```

Two `fb infer` runs differing only in `--dataset` and `--output-dir`. This is
the long, expensive stage. Use `--arm A` / `--arm B` to run them separately.

**4. Scoring (both arms, official dataset)**

```bash
uv run --with datasets python3 scripts/04_eval.py --dry-run
uv run --with datasets python3 scripts/04_eval.py
```

**5. Report**

```bash
uv run --with datasets python3 scripts/05_report.py
```

**6. Arm C — the `/verify` referee loop (optional)**

```bash
uv run --with datasets python3 scripts/06_arm_c.py --stage all --arm both-c --dry-run
uv run --with datasets python3 scripts/06_arm_c.py --stage all --arm both-c
uv run --with datasets python3 scripts/05b_report_c.py
```

Takes Arm B's patch, referees it host-side with headless `/verify` (static
checks only — the referee cannot run the suite outside docker), then runs a
second `fb infer` round whose problem statement carries the previous patch
plus the verdict. **C0** is the attribution control: an identical second round
with a generic self-review instruction instead of the verdict, so
`report_c.md` can separate "the referee helped" from "a second iteration
helped".

Two design limits, both deliberate and both unfixed: the referee cannot run
the suite (`prompts/verify_headless.md`), so `/verify`'s first check is never
exercised; and round 2 starts from the pristine repository
(`prompts/repair_instruction.md`), so C − B measures a fresh attempt rather
than a repair. C − C0 is unaffected by either.

**7. Mutation overlay — agent-written test quality (optional)**

```bash
uv run --with datasets python3 scripts/07_mutation.py --arm both --dry-run
uv run --with datasets python3 scripts/07_mutation.py --arm both
```

FeatureBench scores hidden tests only; this measures the tests the
implementing agent itself wrote. Per (task, arm): rebuild the exact tree the
agent saw inside the task's container, apply its patch, run its own test
files, then apply LLM-chosen strategic source mutations and count kills.
Output: `results/mutation_report.md` (kill rates per cell and per arm, with a
census of cells that shipped no agent tests at all — itself signal).

**8. Failure taxonomy (optional)**

```bash
uv run --with datasets python3 scripts/08_taxonomy.py --dry-run
uv run --with datasets python3 scripts/08_taxonomy.py
```

Classifies every unresolved (task, arm) cell as `spec_wrong` / `impl_wrong` /
`env_or_flaky` / `unclear` (plus a helped/neutral/harmed spec-contribution
call for non-A arms) from the problem, spec, patch, and failing test log.
Output: `results/taxonomy_report.md`. Single-LLM-rater; directional.

**12. Doc quality — deterministic (optional, no docker, no LLM)**

```bash
uv run --with datasets python3 scripts/12_doc_quality.py --pristine-testbed /path/to/extracted/testbed
```

Scores every spec in `results/specs/` against the dataset mask: oracle
recall (code-context mentions only) and effective recall (minus fenced
symbols), fenced ∩ oracle (phrase heuristic), grounding precision. The
pristine testbed (one `docker cp <cid>:/testbed` of the task image) is
re-masked per task so grounding is checked against exactly what the spec
writer saw; omit the flag to skip grounding. Output:
`results/doc_quality_report.md`.

To validate metrics on several spec sets with known outcomes:

```bash
uv run --with datasets python3 scripts/12_doc_quality.py --pristine-testbed … \
  --corpus "v4=reports/<run>/v4/specs:reports/<run>/v4/report.md" \
  --corpus "other=reports/<run>/other/specs:reports/<run>/other/report.md"
```

The report then carries a per-label mean table, pooled Spearman ρ of each
metric against B pass_rate, and within-task concordance (do labels order the
same way on the metric as on pass_rate, inside each task?). Cells share
tasks, so pooled n is tasks × labels, not independent samples.

**13. Doc quality — LLM judge (optional)**

```bash
uv run --with datasets python3 scripts/13_doc_judge.py --dry-run --repeats 2
uv run --with datasets python3 scripts/13_doc_judge.py --repeats 2
```

Report-only opus prompts (`prompts/judge_{fence,testability}.md`),
`[doc_judge]` in config. The judge runs blind — `--tools ""`, empty cwd — so
its verdict is a function of the spec text alone. `--repeats N` reruns each
cell so the report shows judge self-agreement (max−min across repeats) next
to every mean. Accepts the same `--corpus` flags as stage 12. Cells cache
under `results/doc_judge/`, fingerprinted by spec and prompt sha256 (a
rewritten spec is re-judged). Output: `results/doc_judge_report.md`.

**14. Control arms — is Arm B's lift blueprint's? (optional)**

```bash
uv run --with datasets python3 scripts/14_control_arms.py --stage brief --parallel 3
uv run --with datasets python3 scripts/14_control_arms.py --stage dataset
uv run --with datasets python3 scripts/14_control_arms.py --stage infer --dry-run
uv run --with datasets python3 scripts/14_control_arms.py --stage all
uv run --with datasets python3 scripts/05c_report_controls.py
```

Two arms on the stage-01 panel, each testing a cheaper explanation for Arm
B's lift. **A_plan** appends a generic implementation brief
(`prompts/brief_headless.md`) written by the same model in the same masked
workspace with blueprint disabled. The stage parses the session's init event
and fails the task if any blueprint plugin, skill or agent loaded, so every
`results/briefs/<id>.meta.json` carries `plugins_loaded` as proof. **A_hint**
appends one fixed sentence (`prompts/breadth_hint.md`) naming the breadth
mechanism the 4.0 specs carried. Both use Arm B's separator, so only the
document differs. `[brief]` falls back to `[spec]`; its `max_budget_usd` is a
runaway ceiling, not a cost match — A_plan's cost is reported next to B's,
never forced.

`05c` reads A, A_hint, A_plan and B from `runs.json` (or `--report ARM=PATH`)
and reports B − A_plan as the attribution test, plus per-task up/down/tied
counts and exact McNemar for each pair. Output: `results/report_controls.md`.

`bash scripts/run_controls.sh <spec-archive> <report-dir>` runs the whole
panel on one resident image — A and B again (B reusing an archived spec set)
plus both controls — and refuses to start unless `CLAUDE_CODE_VERSION` is
pinned in `fb_config.toml`: `fb` installs `@latest` otherwise, so arms run on
different days run different agents. Resume past finished inference with
`START_AT` (see the script header).

## Expected outputs

```
results/
  tasks.json                     # id, image_name, status (spec_ok | spec_failed)
  specs/<id>.md                  # the spec handed to Arm B
  specs/<id>.meta.json           # cost_usd, duration_ms, wall_seconds, usage, ok/error
  workspaces/<id>/               # extracted /testbed (large; safe to delete after stage 02)
  dataset_arm_b/                 # local HF dataset dir for Arm B
    README.md  data/<split>.jsonl
  infer_arm_a/<timestamp>/output.jsonl     # predictions (instance_id, model_patch)
  infer_arm_b/<timestamp>/output.jsonl
  infer_arm_{a,b}/<timestamp>/report.json  # fb eval aggregate, written next to predictions
  infer_arm_{a,b}/<timestamp>/eval_outputs/<id>/attempt-1/report.json  # per-instance
  runs.json                      # the paths above, per arm
  report.md                      # the deliverable
  doc_quality_report.md          # stage 12: oracle recall / fence / grounding per spec
  doc_judge/<label>/<id>.<metric>.r<k>.json  # stage 13 judge cells
  doc_judge_report.md            # stage 13: fence listing / testability
  briefs/<id>.md                 # stage 14: A_plan's brief
  briefs/<id>.meta.json          # cost, plugins_loaded, blueprint_leaks (must be empty)
  dataset_arm_{a_plan,a_hint}/   # stage 14 datasets
  report_controls.md             # stage 05c: A / A_hint / A_plan / B
```

`results/` is gitignored in full.

`report.md` contains the per-task paired table (resolved A/B, pass rates, spec
cost and wall time), a totals row, the discordant-pair counts `b` (A-only
resolved) and `c` (B-only resolved), an exact two-sided McNemar p-value, the
total spec-stage cost, and a caveats block.

## Running a multi-image panel

A panel that spans several repositories cannot be run in one pass: FeatureBench
images are 18–22GB each and the podman VM is capped (93GB here). So the panel is
executed **one image at a time**, and the per-batch results are stitched back
together afterwards.

```bash
bash scripts/run_batch.sh astropy docker.io/libercoders/featurebench-specs_astropy-instance_493bb78b
bash scripts/11_finalize.sh 2608_scale_astropy_n5 samples/batch_astropy.txt
```

`run_batch.sh` runs one batch end to end — pull → 01 → **spec gate** → 02/03/04/05
→ 06/05b → 07 → 10 → 08 → archive to `results/batches/<name>/` → `docker rmi` →
`fstrim`. Then `09_merge.py` stitches the archives into `results/merged/`, shaped
so the *unmodified* report stages consume it, and `11_finalize.sh` writes the
published artifact to `reports/<name>/`.

Four things that are easy to get wrong:

- **Stage 03 is the expensive, non-idempotent stage** (~$56 per 5 tasks, two
  arms). A batch that dies later must be resumed past it:
  `START_AT=06 bash scripts/run_batch.sh …`. Never restart from 00.
- **The spec gate is not optional.** Stage 01 exits 0 on *partial* failure, but
  stage 02 drops non-`spec_ok` tasks from **both** arms — silently shrinking the
  panel, discoverable only at merge time once the image is gone. The gate fails
  the batch while the image is still resident, and on a `START_AT` resume it also
  asserts `tasks.json` holds *this* batch.
- **`docker rmi` does not return disk to the host.** The podman VM's `.raw` is
  sparse and never re-punches holes: it sat at 84GB allocated against 26GB live.
  `podman machine ssh <machine> "sudo fstrim -av"` reclaimed 60GB in seconds.
  `run_batch.sh` does this after every batch.
- **Don't `pgrep -f "run_batch.sh <arg>"` to wait on a batch.** A watcher whose
  own command line contains that string matches itself and reports "running"
  forever. Use `scripts/watch_pid.sh <pid>`.

### Stage 10 — cost ledger

```bash
uv run --with datasets python3 scripts/10_costs.py --task-ids-file samples/batch_astropy.txt
```

`fb infer` preserves the in-container agent's transcript at
`run_outputs/<id>/attempt-*/claude_code_stream_output.jsonl`, whose terminal
`result` event carries `total_cost_usd`. Joined against the `.meta.json` sidecars
from stages 01/06, that yields the all-in A-vs-B comparison and **cost per extra
task resolved**. Pass `--task-ids-file`: the `specs/` and `verdicts/` directories
accumulate across runs, and an earlier run's sidecars would otherwise be billed
to this panel. Arms with no transcript are reported as *unmeasured*, never $0.
Token usage (input, cache write, cache read, output) is read from the same
`usage` payload and reported alongside cost, with the same unmeasured-not-zero
handling.

## Cached artifacts are fingerprinted

Verdicts (06), mutation cells (07) and taxonomy cells (08) are all expensive
LLM artifacts cached by `(arm, instance_id)`. That key is **not sufficient** —
it does not say *which implementation* the artifact describes. Reusing a verdict
written against a previous run's patch silently feeds Arm C a referee report
about code that no longer exists, and nothing in any output looks wrong.

Each cached artifact therefore records `patch_sha256` of the patch it judged and
is invalidated when that changes; artifacts predating the fingerprint are treated
as stale by design. This was a real defect, not a hypothetical: a pilot verdict
(30419-char patch) was reused to referee a 20399-char one.

## Headless skills and background subagents

A skill that dispatches work to a **background subagent** does not survive
headless `claude -p`: the CLI waits a bounded time for background tasks and then
kills them, so no artifact is written — after the tokens are spent. This hit
`/verify` under sonnet-5 (which dispatches its referee; sonnet-4-5 ran it
inline), producing 1/5 verdicts. The tell is `num_turns` ~5 instead of ~56.

Both stages that shell out to `claude` set
`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` so the CLI waits indefinitely, bounded
instead by the harness's own `timeout_seconds`; and `prompts/verify_headless.md`
forbids background dispatch outright. The plugin has since been fixed as well
(PR #21): `/verify`'s "Running headless" section runs the referee inline when
no human is in the loop. The harness guards stay, for older plugin builds and
for any other skill that dispatches.

## Verifying the harness offline

```bash
bash scripts/smoke_all.sh    # all seven suites, correct deps per suite
```

Runs the whole pipeline in temp directories against fixtures — a fake
`claude`, a fake testbed, a JSONL dataset, mock docker, and synthetic eval
reports. Needs no real docker, no network, no `fb`, and no API key. Individual
suites: `smoke_test.sh` (stages 00–05), `smoke_arm_c.sh`, `smoke_taxonomy.sh`,
`smoke_mutation.sh`, `smoke_costs.sh`, `smoke_controls.sh`,
`smoke_doc_quality.sh`. Stage 01b has no suite. Set `KEEP_TMP=1` to keep a
fixture tree.

## Oracle masking (do not skip)

The task images' `/testbed` still **contains the reference solution**;
`fb infer` strips it (applies the dataset's mask `patch`, deletes the
`FAIL_TO_PASS` test files) before the agent sees the tree. Every stage here
that shows the codebase to a model reproduces that masking
(`_common.mask_reference_solution`): stage 01 before `/spec`, stage 06 before
`/verify`, stage 07 before applying a patch. A spec written against an
unmasked tree is written with oracle access and its results are invalid —
stage 01 hard-fails a task whose mask patch does not apply.

The working tree is only half of the oracle. An extracted `/testbed` carries
the upstream git history, so `git show HEAD:<path>` returns the reference
implementation and the deleted FAIL_TO_PASS tests even after masking — and
the 2608 specs demonstrably used it ("recoverable via `git show HEAD:…`").
`mask_reference_solution` therefore also re-initialises git to a single
commit of the masked tree (`_common.reinit_git`), exactly as `fb infer` does
in the container. Every result produced before this fix (both 2608 archives
and the 2609 Ouroboros A rerun) was written with history access and is flagged as
such in its README; `../README.md` lists every report's status.

## Troubleshooting

**Stage 01 produces no spec (`spec_failed`).** This is the known risk: the
`spec` skill was written for interactive use with approval gates and an
evaluator subagent, and a headless pass may stall on a gate, ask a question, or
never write a file. Look at `results/specs/<id>.meta.json` for the error, and
at the `result` text the run returned.

- Tighten `prompts/spec_headless.md` — it is the only lever that talks to the
  skill. It already forbids questions and approval gates and mandates the
  `SPEC_PATH:` final line; make the wording more specific to whatever the model
  actually did.
- Widen permissions through `[spec] claude_args` in `config.toml`. It is passed
  to the CLI verbatim; the default is `["--permission-mode",
  "bypassPermissions"]`. Adding `--allowedTools` or `--append-system-prompt` is
  fair game.
- If the skill never triggers, check the plugin is user-scoped, and consider
  naming it explicitly in the prompt (`/spec`).
- If headless `/spec` fundamentally cannot work, the fix belongs in the plugin
  (an explicit headless/eval mode), not here.

**`fb` not found after stage 00.** `pip install --user` may have put it outside
`PATH`; check `python3 -m site --user-base`/bin, or use `uv tool install`.

**Stage 02 fails to reload the dataset.** The layout depends on `datasets`
resolving the `configs:` block in the generated `README.md` (verified against
`datasets` 5.0.1). Bump `datasets` first. `datasets` caches by data-file
content, so a rerun after new specs does pick up the change.

**Stage 03 finds no `output.jsonl`.** `fb infer` creates
`<output-dir>/<timestamp>/output.jsonl` only once a task completes; if the run
died early the directory is empty. Check the `fb` console output — a bad
`ANTHROPIC_API_KEY` in `fb_config.toml` fails inside the container, not in the
harness.

**A task id is missing from `report.md`.** It either failed stage 01 (see
`tasks.json`) or `fb eval` wrote no per-instance report for it. `05_report.py`
renders `—` for an arm with no result rather than counting it as unresolved.

**Instance-id level suffix.** FeatureBench derives a task's level from the
`.lv1`/`.lv2` suffix on `instance_id` and raises on anything else — relevant
only if you hand-build a dataset JSONL for the `--mock-dataset` path.

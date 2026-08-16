# blueprint × FeatureBench — paired spec ablation

Measures one number: **does handing an implementing agent a blueprint-produced
spec improve its resolved rate on FeatureBench?**

Two arms over the same tasks, same agent, same model:

- **Arm A (control)** — `fb infer` on the official dataset. The agent sees the
  original `problem_statement`.
- **Arm B (treatment)** — a pre-stage runs blueprint's `/spec` headlessly
  against each task's codebase, then `fb infer` runs on a locally rewritten
  copy of the dataset whose `problem_statement` is *original + spec*.

Both arms are scored by the unmodified `fb eval` against the **official**
dataset. Predictions carry only `instance_id` and `model_patch`, so the
treatment cannot leak into scoring.

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
  all is scored 0.0, not skipped.

Shorthand: resolved asks "is it done?", pass rate "how close?", kill rate
"is the agent's own QA real?".

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker, daemon running | Every stage except 02/05 needs it. FeatureBench images are large — budget disk. |
| Python 3.11+ | Scripts are stdlib-only except `datasets`. |
| `datasets` | `pip install datasets` (used by stages 01 and 02). |
| `featurebench` | **Not on PyPI.** `pip install git+https://github.com/LiberCoders/FeatureBench.git` (or `uv tool install` the same URL). Provides the `fb` CLI. Stage 00 installs it for you. |
| `claude` CLI, authenticated | Stage 01 shells out to it. `claude --version` must work. |
| blueprint plugin installed | The `spec` skill must resolve inside a `claude -p` run started from an arbitrary directory. Install it from this marketplace (`/plugin` → `runway` → `blueprint`) so it is user-scoped, not repo-scoped — stage 01 runs inside extracted task codebases, not inside this repo. |
| `ANTHROPIC_API_KEY` | Used by stage 01 directly and by the in-container agent via `fb_config.toml`. |

## Run the pilot

```bash
cd evals/blueprint-featurebench
cp config.example.toml config.toml
cp fb_config.example.toml fb_config.toml   # put your ANTHROPIC_API_KEY here
$EDITOR config.toml fb_config.toml
```

Start small. `[eval] limit = 3` for the first pass — stage 01 is the risky one
and you want to see it work before paying for 30 tasks.

**0. Setup**

```bash
bash scripts/00_setup.sh
```

Installs `featurebench` if `fb` is missing, checks docker / `claude` /
`ANTHROPIC_API_KEY` / config files, then pre-pulls the split's images with
`fb pull --mode lite` (override with `SPLIT=fast bash scripts/00_setup.sh`).

**1. Specs (Arm B pre-stage)**

```bash
python3 scripts/01_make_specs.py
```

Per task: `docker create <image>` + `docker cp <cid>:/testbed` into
`results/workspaces/<id>/`, then `claude -p <rendered prompt> --output-format
json <claude_args> --model <spec.model>` with that workspace as cwd. The spec
is located via the `SPEC_PATH:` marker the prompt demands, falling back to the
newest `.md` under `<workspace>/.blueprint/specs/`.

Resumable — tasks with a successful `results/specs/<id>.meta.json` are skipped
unless you pass `--force`. Other flags: `--limit N`, `--task-ids-file <file>`.

**2. Arm B dataset**

```bash
python3 scripts/02_make_dataset.py
```

Writes `results/dataset_arm_b/` (a JSONL data file plus a `README.md` whose
YAML front-matter declares the split) and immediately loads it back to assert
the row count and the mutated `problem_statement`. Only `spec_ok` tasks are
included — the paired design needs both cells, so a task that failed stage 01
is dropped from **both** arms.

**3. Inference (both arms)**

```bash
python3 scripts/03_infer.py --dry-run   # inspect the commands first
python3 scripts/03_infer.py
```

Two `fb infer` runs differing only in `--dataset` and `--output-dir`. This is
the long, expensive stage. Use `--arm A` / `--arm B` to run them separately.

**4. Scoring (both arms, official dataset)**

```bash
python3 scripts/04_eval.py --dry-run
python3 scripts/04_eval.py
```

**5. Report**

```bash
python3 scripts/05_report.py
```

**6. Arm C — the `/verify` referee loop (optional)**

```bash
python3 scripts/06_arm_c.py --stage all --arm both-c --dry-run
python3 scripts/06_arm_c.py --stage all --arm both-c
python3 scripts/05b_report_c.py
```

Takes Arm B's patch, referees it host-side with headless `/verify` (static
checks only — the referee cannot run the suite outside docker), then runs a
second `fb infer` round whose problem statement carries the previous patch
plus the verdict. **C0** is the attribution control: an identical second round
with a generic self-review instruction instead of the verdict, so
`report_c.md` can separate "the referee helped" from "a second iteration
helped".

**7. Mutation overlay — agent-written test quality (optional)**

```bash
python3 scripts/07_mutation.py --arm both --dry-run
python3 scripts/07_mutation.py --arm both
```

FeatureBench scores hidden tests only; this measures the tests the
implementing agent itself wrote. Per (task, arm): rebuild the exact tree the
agent saw inside the task's container, apply its patch, run its own test
files, then apply LLM-chosen strategic source mutations and count kills.
Output: `results/mutation_report.md` (kill rates per cell and per arm, with a
census of cells that shipped no agent tests at all — itself signal).

**8. Failure taxonomy (optional)**

```bash
python3 scripts/08_taxonomy.py --dry-run
python3 scripts/08_taxonomy.py
```

Classifies every unresolved (task, arm) cell as `spec_wrong` / `impl_wrong` /
`env_or_flaky` / `unclear` (plus a helped/neutral/harmed spec-contribution
call for non-A arms) from the problem, spec, patch, and failing test log.
Output: `results/taxonomy_report.md`. Single-LLM-rater; directional.

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
forbids background dispatch outright. The underlying fix belongs in the plugin —
`/verify` is affected in any headless context, not just this harness.

## Verifying the harness offline

```bash
bash scripts/smoke_all.sh    # all four suites, correct deps per suite
```

Runs the whole pipeline in temp directories against fixtures — a fake
`claude`, a fake testbed, a JSONL dataset, mock docker, and synthetic eval
reports. Needs no real docker, no network, no `fb`, and no API key. Individual
suites: `smoke_test.sh` (stages 00–05), `smoke_arm_c.sh`, `smoke_mutation.sh`,
`smoke_taxonomy.sh`. Set `KEEP_TMP=1` to keep a fixture tree.

## Oracle masking (do not skip)

The task images' `/testbed` still **contains the reference solution**;
`fb infer` strips it (applies the dataset's mask `patch`, deletes the
`FAIL_TO_PASS` test files) before the agent sees the tree. Every stage here
that shows the codebase to a model reproduces that masking
(`_common.mask_reference_solution`): stage 01 before `/spec`, stage 06 before
`/verify`, stage 07 before applying a patch. A spec written against an
unmasked tree is written with oracle access and its results are invalid —
stage 01 hard-fails a task whose mask patch does not apply.

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

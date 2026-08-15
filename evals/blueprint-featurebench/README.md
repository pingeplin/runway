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

## Verifying the harness offline

```bash
bash scripts/smoke_test.sh
```

Runs the whole pipeline in a temp directory against fixtures — a fake `claude`,
a fake testbed, a JSONL dataset, and synthetic eval reports. Needs no docker,
no network, no `fb`, and no API key. Set `KEEP_TMP=1` to keep the fixture tree.

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

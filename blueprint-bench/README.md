# blueprint-bench

Pilot harness for evaluating the blueprint plugin's `/tdd` workflow against
hidden behavioral oracles. This is a **first cut** — step 1 of the build
order in `blueprint-eval-workspace/benchmark-proposal.html` (v2.2):

> Harness skeleton + 3 tasks (one per size bucket, all Python). Verify
> oracle-sandboxing in CI.

## What's in this cut

- **Harness skeleton** at `harness/` — sandboxed per-run working tree,
  oracle leak probes, mode invocation, artifact capture, manifest with
  plugin/harness git SHAs.
- **Correctness scorer** at `scorers/correctness.py` — runs each task's
  hidden oracle tests against the agent's output and returns
  `passed / total`.
- **3 pilot tasks** at `tasks/`:
  - `T01_pagination_bugfix` — bug-fix bucket (1–3 hidden tests, trap:
    visible suite passes on broken code).
  - `T02_password_validator` — single-feature bucket (8 hidden tests,
    trap: deliberately vague "reject gracefully" in description).
  - `T03_csv_normalizer` — multi-component bucket (12 hidden tests,
    trap: reader and writer streams both touch `columns.py`).
- **Two modes**: `full` (`claude -p "/tdd <desc>"`) and `naked`
  (`claude -p "<desc>"`).
- **Two default models**: `claude-sonnet-4-6` and `claude-haiku-4-5`,
  passed through `claude -p --model`. Opus is deliberately excluded —
  pilot tasks are sized for small/medium models, where the full-vs-naked
  delta is informative. Override with `--models <id1,id2,...>`.
- **Cost capture**: each cell parses the final `type=result` event from
  `claude -p`'s stream-json transcript and records `total_cost_usd`,
  input/output/cache tokens, `num_turns`, and `duration_api_ms` on the
  result row. `summary.json` carries the run-level `total_cost_usd`.
- **Sandboxing**: each run gets a fresh working tree containing **only**
  `starter/`. The task's `oracle/` directory is never copied in. Pre-run
  and post-run probes scan for any file named `oracle*`; post-run also
  scans the transcript for references to known leak paths.

## Pilot quarantine — important

Per proposal §Build-order item 5:

> Pilot tasks are quarantined into the private-20 split or retired
> entirely — they never enter the public-80 split, since plugin
> maintainers have inspected them in detail during harness tuning.
> **Do not draw plugin conclusions from the pilot.**

These 3 tasks were authored by the same person tuning the harness and
have **not** been pre-validated by an independent-implementer panel.
Treat any numbers they produce as harness-validation evidence only —
they are diagnostics for *the benchmark*, not for *the plugin*.

## What's deliberately out of scope

Everything outside step 1 of the build order. Specifically:

- **Other primary scorers**: mutation score, refactor robustness,
  `change_amplification`, `evolution`, EuTB / EuCB efficiency.
- **Other modes**: `naked-equalized`, `no-evaluators`, `sequential-only`,
  `plan-from-code`, `tdd-vs-joint`.
- **Independent-implementer 3-person panel** and pre-validation gate.
- **Public-80 / private-20 split**.
- **Pre-registered primary hypotheses** + Holm–Bonferroni correction.
- **Deliberate-trap detection** as a separately reported metric.
- **Unix-user / container filesystem isolation** for sandboxing (we use
  per-task chroot-like working trees + per-path probes; the stronger
  enforcement is deferred to a follow-up).
- **TypeScript/Go tasks**.

These land in subsequent passes.

## Setup

This project is uv-managed. Every Python command goes through `uv run`.

```bash
cd blueprint-bench
uv sync
```

## Running the harness

```bash
# Self-test: harness smoke suite.
uv run pytest tests/ -v

# Single-task naked-mode dry run on Haiku (cheap; pennies).
uv run python -m harness.runner \
    --tasks tasks/T01_pagination_bugfix \
    --modes naked \
    --models claude-haiku-4-5 \
    --seeds 1 \
    --workers 1

# Single-task full-mode dry run on Sonnet (expensive; ~$3–8 per /tdd invocation).
uv run python -m harness.runner \
    --tasks tasks/T01_pagination_bugfix \
    --modes full \
    --models claude-sonnet-4-6 \
    --seeds 1 \
    --workers 1

# Full pilot matrix (3 tasks × 2 modes × 2 models × 1 seed = 12 cells).
uv run python -m harness.runner \
    --tasks tasks/ \
    --modes full,naked \
    --models claude-sonnet-4-6,claude-haiku-4-5 \
    --seeds 1 \
    --workers 2
```

Results land under `results/<YYYYMMDD_HHMMSS>_<uuid>/`:

```
results/<run_id>/
├── manifest.json                 # plugin_sha, harness_sha, plugin_version, args (incl. models list)
├── runs/<task>__<mode>__<model-slug>__seed<n>/
│   ├── artifacts/
│   │   ├── transcript.jsonl      # stream-json from claude -p; final type=result has cost+usage
│   │   ├── stderr.log
│   │   ├── diff.patch            # agent's git diff vs starter baseline
│   │   ├── specs/                # if blueprint wrote any
│   │   └── plans/                # if blueprint wrote any
│   ├── probes.json               # pre/post/liveness probe results + compromised flag
│   ├── score.json                # correctness scorer output
│   ├── pytest_report.json        # raw scorer report
│   └── result.json               # per-cell row (score, runtime, model, usage{cost_usd,tokens,turns})
└── summary.json                  # all rows + manifest + total_cost_usd
```

Model slugs in cell ids strip the `claude-` prefix, so a cell looks like
`T01_pagination_bugfix__full__sonnet-4-6__seed0`.

## Known risks

- **`/tdd` headless gates** (resolved): `/tdd` originally had two
  approval gates ("Approve spec, or revise?", "Approve plan, or revise?")
  that stalled `claude -p` after the plan was written. We added a
  `--headless` token to `/tdd` (see
  `plugins/blueprint/commands/tdd.md`) and wired the harness's `full`
  mode to prepend it. Evaluator subagents still run and their reports
  are surfaced; only the human-input pauses are skipped.
- **Sandbox is "chroot-like", not chroot**: oracle paths aren't
  physically copied into the agent's CWD subtree, and the probes flag
  leaks if they happen — but a determined agent with shell access could
  still `find /` the disk. The stronger proposal-specified enforcement
  (unix user / container) is intentionally deferred to a follow-up.

## Repository layout

```
blueprint-bench/
├── README.md                     # you are here
├── pyproject.toml                # uv-managed
├── .python-version               # 3.11
├── uv.lock                       # committed
├── harness/                      # sandbox, probes, modes, artifacts, manifest, runner
├── scorers/                      # correctness only, for this cut
├── tasks/                        # T01 / T02 / T03
├── tests/                        # harness smoke tests
└── results/                      # gitignored
```

## See also

- `../blueprint-eval-workspace/benchmark-proposal.html` — the full v2.2 proposal.
- `../blueprint-eval-workspace/evidence-audit.html` — the literature
  review that grounds the proposal.
- `../blueprint-eval-workspace/run_trigger_eval.py` — the existing skill-trigger
  eval that this harness complements.

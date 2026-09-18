# runway

A Claude Code plugin marketplace. One plugin so far: `blueprint`.

## Repository structure

- `plugins/blueprint/` — the plugin: skills, agents, references, and its own
  eval suite under `evals/`.
- `.claude-plugin/marketplace.json` — exposes the repo as a marketplace;
  `pluginRoot` is `./plugins`.
- `evals/README.md` — index of every eval tier, what currently stands, and
  the status of each benchmark report. Update it when a run lands.
- `evals/blueprint-featurebench/` — the benchmark harness (FeatureBench
  spec-ablation). Expensive tier: containers, podman, ~$21/task/arm.
- `evals/transcript-analysis/` — measurements from local session
  transcripts. Free; raw output is private and stays uncommitted.
- `docs/designs/` — design docs and post-mortems.
- `.blueprint/specs/` — specs written with the plugin's own `/spec`.

## Validation

No CI runs in this repo, so these are the checks — run them before opening a
PR that touches the plugin.

```bash
# manifest (free, instant)
claude plugin validate --strict plugins/blueprint

# triggering tier — does the right skill fire? (~$2.75, ~5 min)
cd plugins/blueprint && claude plugin eval . --ablation none --no-publish
```

An eval run spawns real agents and outlives a 120s command timeout — run it
backgrounded, or it dies with exit 137.

The benchmark tier is **not** a pre-PR check. It costs real money per task
and needs podman (`applehv` + Rosetta); see
`evals/blueprint-featurebench/README.md`.

## Rules

- **Measurement claims are load-bearing.** Two published benchmark results
  have already been retracted for oracle leaks. Any number in
  `plugins/blueprint/README.md` names the report directory it came from. A
  README shows only the latest data; a retraction or correction stays in the
  source as an HTML comment rather than being edited away.
- **Keep `results/` out of git** (it is `*`-ignored by design); durable runs
  are archived under `evals/blueprint-featurebench/reports/<name>/` and
  committed.
- **Eval graders must fail when the thing they test breaks.** The trace
  embeds a listing of every available skill, so matching a bare skill name
  passes even when nothing fired. Match the invocation shape
  (`"skill":"blueprint:spec"`), and mutation-check new graders. See
  `plugins/blueprint/evals/README.md`.

# runway

A Claude Code plugin marketplace. One plugin so far: `blueprint`.

## Repository structure

- `plugins/blueprint/` — the plugin: skills, agents, references.
- `.claude-plugin/marketplace.json` — exposes the repo as a marketplace;
  `pluginRoot` is `./plugins`.
- `docs/designs/` — design docs and post-mortems.
- `.blueprint/specs/` — specs written with the plugin's own `/spec`.

There is no evaluation suite. The first one (FeatureBench benchmark,
transcript analysis, skill triggering) was retired on 2026-09-18. Its code
and reports are at git tag `archive/evals-v1`, and its lessons are in
`docs/designs/2609.0005_eval_v1_post_mortem.md`. Read that before designing
the next one.

## Validation

No CI runs in this repo. Before opening a PR that touches the plugin, run:

```bash
claude plugin validate --strict plugins/blueprint
```

## Rules

- **Measurement claims are load-bearing.** Two published benchmark results
  were retracted for oracle leaks. Any number in `plugins/blueprint/README.md`
  names the report it came from. A README shows only the latest data; a
  retraction or correction stays in the source as an HTML comment rather
  than being edited away.
- **Eval graders must fail when the thing they test breaks.** Mutation-check
  every new grader. For skill triggering: the trace embeds a listing of every
  available skill, so matching a bare skill name passes even when nothing
  fired. Match the invocation shape (`"skill":"blueprint:spec"`).

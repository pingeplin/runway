# Blueprint eval suite

The cheap tier. These cases ask one question — **does the right skill fire on
a prompt a real user would type?** — and answer it with free graders, no
containers, and no LLM judge.

```bash
# from plugins/blueprint/
claude plugin eval . --ablation none --no-publish -j 3
```

Last run (2026-09-18, Claude Code 2.1.276, 3 runs per case): all four cases
**12/12, $3.58**, but at the default `-j 1`, so **960s**. At `-j 3` the
earlier split runs took 289s (first three cases, 9/9, $2.75) and 52s
(`review-*`, 3/3, $0.78).

## Why this exists

Blueprint's quality evidence lives in `evals/blueprint-featurebench/`, which
grades a produced patch against hidden tests. That tier is honest and
expensive: ~$21 per task per arm, 20GB images, podman. It is the wrong
instrument for "did `/spec` trigger", and its cost means nothing gets checked
between benchmark runs.

Triggering is the plugin's most load-bearing untested property. A skill that
does not fire is worth exactly zero regardless of how good its body is, and
descriptions are edited far more often than they are measured.

## What is covered

| Case | Asserts | Why it is the hard case |
|---|---|---|
| `spec-triggers-on-feature-request` | `/spec` fires | The user never says "spec". The description claims this works; nothing checked it. |
| `unsettled-approach-routes-to-design` | `/design` fires, `/spec` does not | The `/design` ↔ `/spec` boundary is the plugin's subtlest routing call — approach in question vs approach settled. |
| `review-triggers-on-code-quality-ask` | `/review` fires, `/verify` does not | Both descriptions claim test- and code-quality territory; `/verify` needs a spec to referee against and there is none here. |
| `debugging-does-not-trigger-spec` | no blueprint skill fires | The negative control. Over-triggering is a real failure mode: on FeatureBench, a generic brief scored **below** handing over no document at all, because it fenced scope by default. |

The negative case matters as much as the positive ones. Measuring only that a
skill fires selects for descriptions that fire on everything.

## Grader types used

All free — they read the trace, so they cost nothing beyond the agent run
itself. `llm` and `baseline` graders are paid and deliberately absent.

- `type: regex` with `target: trace` — did a specific skill get invoked
- negative assertions use a lookahead (`^(?![\s\S]*…)`); the schema has no
  `negate` field

### Match the invocation, never the bare name

**`pattern: blueprint:spec` is vacuous and will pass without the skill ever
firing.** The trace includes the session's init event, which lists every
available skill by name — so `blueprint:spec`, `blueprint:design` and the
rest are all present in the trace of *any* run, including one where the
plugin did nothing.

Match the tool call instead:

```yaml
pattern: '"skill":"blueprint:spec"'      # an actual invocation
```

That shape appears only when the `Skill` tool is called. Verified: in a run
where only `/spec` fired, `"skill":"blueprint:spec"` matched once and
`"skill":"blueprint:design"` matched zero times, while the bare names each
appeared in the listing.

This is the vacuous-test failure `/verify`'s thought-mutation check exists to
catch, reproduced in our own eval suite. If you add a case, ask the question
that check asks: *if the skill silently stopped firing, would this grader go
red?*

Both negative graders here were checked that way — replayed against a trace
in which `/spec` *did* fire, `no-blueprint-skill-fires` and
`spec-skill-does-not-fire` both fail, as they must.

## What is not covered, and why

`/verify` and `/commit` have no case here, and not by oversight: neither can
be triggered by a bare prompt. `/verify` needs a spec plus an implementation
in the sandbox, and `/commit` needs a git repo with a diff — both mean
`scaffold_script`, `--scaffold` and Bash, which is the expensive tier wearing
a `case.yaml`. `/review` was the last skill whose trigger is testable for
free, which is why it is here and they are not.

## The max-turns exit is expected

Cases cap at `max_turns: 4`, so the positive cases usually end with
`Reached maximum number of turns (4)` in the NOTES column. **That is not a
failure.** The skill fires on the first turn; the remaining turns are the
skill body doing work this tier does not grade. The cap is a cost bound, not
an assertion, and the case still scores on whether the right skill fired.

Raising the cap would only buy a tidier NOTES column at a higher price per
run. Lowering it to 2 would risk a case where the agent orients before
invoking, turning a slow trigger into a false red — worse than a confusing
note.

## Ablation

`--ablation none` is the documented invocation. Under the default
`with-without`, the no-plugin baseline arm can never fire a plugin skill, so
it scores 0 on every case here — a correct but uninformative delta. Ablation
becomes useful once this suite grows graders that score *output quality*
rather than routing, which is where an `llm` grader would earn its cost.

## What this tier does not show

- **Nothing about output quality.** A skill firing is not a skill working.
  The spec's content is graded on FeatureBench, not here.
- **Triggering is stochastic.** Cases run 3× by default; a single pass is not
  evidence. Treat a case that moves between 2/3 and 3/3 as noise, not as a
  regression.
- **One phrasing per case.** Each case fixes one way of asking. It catches a
  description that stopped working, not the full space of phrasings a user
  might reach for.

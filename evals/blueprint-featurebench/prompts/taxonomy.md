You are running fully non-interactively as part of an automated benchmark
failure analysis. Nobody will read a question or approve anything — never ask
one, and never wait for confirmation.

Your task: classify **why** an AI coding agent failed a FeatureBench task,
using only the evidence bundle below. You are not being asked to fix
anything, run any tools, or read files outside this prompt — judge strictly
from the bundle.

## Task under analysis

- Task id: `{task_id}`
- Arm: `{arm}` (Arm A = control — the agent saw only the original problem
  statement. Arm B/other = treatment — the agent saw the original problem
  statement plus a blueprint-produced spec.)

## Scored outcome (from `fb eval`)

{outcome_header}

## Original problem statement (head, may be truncated)

{problem_statement}

## Spec handed to the agent

{spec_section}

## Agent's patch (model_patch — the diff it produced; head, may be truncated)

```diff
{model_patch}
```

## Failing test log ({test_log_source}; tail, may be truncated)

```
{test_log_tail}
```

## Classification

Decide **why this attempt failed**, choosing exactly one of:

- `spec_wrong` — the spec (Arm B/treatment only) misread, narrowed, or
  contradicted the original task, and that error is visible in what the
  agent built or in the gap between the spec and the original statement.
  Never choose this for Arm A — there is no spec to blame.
- `impl_wrong` — the brief the agent received (original statement alone, or
  original + spec) was an adequate and correct account of the task, but the
  agent's implementation still diverges from it, is buggy, incomplete, or
  fails requirements that were stated clearly.
- `env_or_flaky` — the failure looks like a harness/test-environment problem
  unrelated to whether the brief or the implementation was correct
  (collection errors from test/environment setup, timeouts, missing
  fixtures, nondeterminism, dependency issues) — not an authorship problem.
- `unclear` — the evidence does not let you tell with reasonable confidence.
  Prefer this over guessing.

Also decide `spec_contribution` — **only meaningful for Arm B/treatment**
(use JSON `null` for Arm A, never a string):

- `helped` — the spec's presence plausibly steered the agent toward a better
  or more correct solution than the original statement alone would have.
- `neutral` — the spec neither helped nor hurt in any way visible in this
  evidence.
- `harmed` — the spec plausibly misled, narrowed, or distracted the agent in
  a way that contributed to the failure.

## Output format

You may reason freely above this line. Your reply's **final line** must be,
and contain nothing else but, a single-line JSON object with exactly these
three keys:

```
{"class": "<spec_wrong|impl_wrong|env_or_flaky|unclear>", "spec_contribution": <"helped"|"neutral"|"harmed"|null>, "rationale": "<2-3 sentences citing specific evidence from the bundle above>"}
```

No trailing commentary after that line. No code fence around it.
`spec_contribution` must be the JSON literal `null` (not the string
`"null"`) for Arm A.

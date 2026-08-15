You are running fully non-interactively as part of an automated benchmark.
There is no human available. Nobody will read a question, answer it, or
approve anything.

Your task: use the **blueprint plugin's `verify` skill** to referee the
implementation currently in the working directory against the specification
at `.blueprint/specs/spec.md`.

The working tree already contains a candidate implementation produced by a
different coding agent for that spec. Treat it as code of unknown
provenance — judge it, do not defend it, do not assume it is right because it
is there.

The tree is exactly what that agent started from, plus its patch: the feature
was stripped out of the repository beforehand and the benchmark's own hidden
acceptance tests were deleted. So **every test you can see is either
pre-existing or written by the agent under review** — there is no reference
test file to compare against, and a missing test file is not a bug in the
checkout.

## Hard constraint: you cannot run the test suite

This checkout has **no installed dependencies and no test environment** — the
project's tests only run inside a docker image that is not available here.

- Do **not** try to install anything (`pip`, `uv`, `npm`, `apt`, …).
- Do **not** run `pytest` / `tox` / `make test` / the project's runner.
- Do **not** treat the missing test run as a blocker or as a failure verdict.

Record the test-suite check as **"not run — no test environment"** and perform
every other check **statically**, by reading the spec, the tests and the
source:

1. **Scenario coverage** — map each acceptance scenario in the spec to the
   test(s) and code path(s) that cover it, naming file + symbol. List
   scenarios with no test as uncovered.
2. **Anti-vacuity (thought-mutation)** — for each covered behaviour, state the
   smallest implementation change that would break it, then decide *by
   reading the test* whether any test would actually fail. Covered-but-vacuous
   scenarios are the headline finding.
3. **Test Desiderata** — score the tests against the skill's desiderata and
   anti-patterns references (deterministic, behaviour-focused, readable,
   isolated, …) and call out the specific offending tests.
4. **Implementation quality** — stubs, hard-coded returns, dead code, TODO
   placeholders, stale or restated-*what* comments and docstrings, and
   summary/markdown files standing in for real work.

## Operating rules for this run

1. **Never ask a question.** No clarification, no scope confirmation, no
   go/no-go. Decide yourself.
2. **Never wait at an approval gate.** Wherever the skill would pause for
   review or sign-off, proceed as if it had already been approved.
3. **Never fix anything.** Do not edit, create, move or delete any file other
   than the verdict file below. The referee assesses; it never edits. Do not
   run `git` commands that change the tree.
4. Write the verdict as **markdown** to a file under `.blueprint/verdicts/` in
   the current working directory (create the directory if needed).
5. The verdict must stand on its own: the implementing agent will receive it
   as its **only** feedback, with no access to you or to this conversation.
   Write it as an actionable punch list — what is missing, what is vacuous,
   what is wrong, and for each item what would make it pass. Include the
   coverage mapping, the thought-mutation table, the desiderata findings, the
   implementation-quality flags, and one explicit overall verdict line
   (meets / does not meet the spec's definition of done). Do not reference
   file paths that exist only in this scratch checkout.
6. **The final line of your reply must be exactly:**

   ```
   VERDICT_PATH: <path of the verdict file, relative to the current directory>
   ```

   Nothing after it. No trailing commentary, no code fence around it.

## Original feature request (for grounding only — the spec is the contract)

{problem_statement}

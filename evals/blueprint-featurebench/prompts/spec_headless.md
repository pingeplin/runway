You are running fully non-interactively as part of an automated benchmark.
There is no human available. Nobody will read a question, answer it, or
approve anything.

Your task: use the **blueprint plugin's `spec` skill** to write an
agent-executable specification for the feature request below, against the
codebase in the current working directory.

Read the codebase first so the spec names real files, real modules, and real
interfaces — not hypothetical ones.

## Operating rules for this run

1. **Never ask a question.** Do not request a feature name, clarification,
   scope confirmation, or anything else. Derive a short feature name from the
   request yourself.
2. **Never wait at an approval gate.** Wherever the skill would pause for
   review, sign-off, or a go/no-go, proceed as if it had already been
   approved and continue to the next step.
3. **Do not implement the feature.** Do not modify source files, do not write
   tests, do not run the test suite for the purpose of making it pass. The
   only file you create is the spec (plus its directory).
4. Write the spec to a file under `.blueprint/specs/` in the current working
   directory, following the skill's naming convention. Create the directory
   if it does not exist.
5. The spec must stand on its own: another coding agent will receive it as
   its entire briefing, with no access to you or to this conversation.
6. **The final line of your reply must be exactly:**

   ```
   SPEC_PATH: <path of the spec file, relative to the current directory>
   ```

   Nothing after it. No trailing commentary, no code fence around it.

## Feature request

{problem_statement}

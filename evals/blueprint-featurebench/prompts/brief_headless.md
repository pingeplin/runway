You are running fully non-interactively as part of an automated benchmark.
There is no human available. Nobody will read a question, answer it, or
approve anything.

Your task: write an implementation brief for the feature request below,
against the codebase in the current working directory. Another coding agent
will build the feature from your brief.

Read the codebase first so the brief names real files, real modules, and real
interfaces — not hypothetical ones.

## Operating rules for this run

1. **Never ask a question.** Do not request clarification, scope
   confirmation, or anything else. Decide for yourself.
2. **Never wait for approval.** Wherever you would pause for review or
   sign-off, proceed as if it had already been given.
3. **Do not implement the feature.** Do not modify source files, do not write
   tests, do not run the test suite for the purpose of making it pass. The
   only file you create is the brief.
4. Write the brief to `.handoff/brief.md` in the current working directory.
   Create the directory if it does not exist.
5. The brief must stand on its own: another coding agent will receive it as
   its entire briefing, with no access to you or to this conversation.
6. **The final line of your reply must be exactly:**

   ```
   BRIEF_PATH: .handoff/brief.md
   ```

   Nothing after it. No trailing commentary, no code fence around it.

## Feature request

{problem_statement}

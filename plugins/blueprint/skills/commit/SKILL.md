---
name: commit
description: Write a concise, descriptive git commit message in Conventional Commits format. ALWAYS use this skill when the user wants to commit changes, write a commit message, prepare a commit, or says "commit this", "commit my changes", "commit it", "let's commit", "write a commit message", or "help me commit". Also trigger when the user has just finished implementing something and says they want to save or commit the result.
argument-hint: [optional description of changes]
---

# Git Commit Message

Write a concise, descriptive Git commit message for the code changes.

Follow these guidelines:

1. Use Conventional Commits format: `<type>: <short summary>`
   - Types: `feat`, `fix`, `refactor`, `docs`, `style`, `test`, `chore`, `perf`
2. Keep the subject line under 50 characters and in imperative mood.
3. If needed, add a body (separated by a blank line) to explain the what and why (not how).

Generate only the commit message (no extra commentary).

## How to Use This Skill

**Dispatch the `commit-writer` subagent** via the `Agent` tool with
`subagent_type: commit-writer`. The subagent runs in a fresh context — it
has not seen the implementation conversation, which is the point: the
builder context is full of micro-decisions that don't belong in the commit
log. The subagent reads `git diff` and `git status` directly and drafts
the message from the diff alone.

Pass any relevant context in the prompt:
- A short hint about the feature or task (optional)
- Ticket/issue numbers or required trailers
- Whether the changes are already staged or need staging

When the subagent returns the draft:
1. Review the drafted message with the user (or proceed directly if the
   user has asked for autonomous commit).
2. Stage files if needed (`git add <paths>`).
3. Run `git commit` with the drafted message via a HEREDOC to preserve
   formatting.
4. Confirm with `git status`.

### Fallback (if the subagent is unavailable)

If the `commit-writer` subagent cannot be dispatched, fall back to writing
the message inline using the rules above:

1. **Read the actual changes** — `git diff --staged` (or `git diff`).
2. **Pick the right type** — `feat`, `fix`, `refactor`, `docs`, `style`,
   `test`, `chore`, or `perf`.
3. **Write the subject** — imperative mood, under 50 characters, no
   trailing period.
4. **Decide if a body is needed** — skip for trivial changes; add when
   context helps future readers.
5. **Write the body** — explain *what* and *why*, not *how*.

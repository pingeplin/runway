---
name: commit
description: Write a concise, descriptive git commit message in Conventional Commits format. ALWAYS use this skill when the user wants to commit changes, write a commit message, prepare a commit, or says "commit this", "commit my changes", "commit it", "let's commit", "write a commit message", or "help me commit". Also trigger when the user has just finished implementing something and says they want to save or commit the result.
argument-hint: [optional description of changes]
---

# Git Commit Message

Write a concise, descriptive Git commit message for the code changes.
Do it inline, in this session — nothing is dispatched for this.

**Write from the diff, not from the implementation conversation.** The
conversation that built the change is full of micro-decisions, dead
ends, and narration that do not belong in the commit log. Read what
`git` shows you and describe that.

## Procedure

1. **Read the actual changes** — `git status`, then `git diff --staged`
   (and `git diff` if nothing is staged yet). Do not consult `git log`
   to match a house style; the format below is the style.
2. **Pick the type** — `feat`, `fix`, `refactor`, `docs`, `style`,
   `test`, `chore`, or `perf`. If the change spans several, pick the
   dominant one.
3. **Write the subject** — `<type>: <summary>`, imperative mood ("Add
   X", not "Added X"), under 50 characters, no trailing period. It
   should complete *"If applied, this commit will ___"*.
4. **Decide whether a body is needed** — skip it for trivial changes
   (one-line fixes, dependency bumps). Add one when the *why* is
   non-obvious: a root cause, a trade-off, a user-facing consequence, a
   pointer to a follow-up. Separate it with a blank line, wrap at 72
   characters, and do not re-list files — `git show` does that.
5. **One concern per commit** — if the diff mixes unrelated changes,
   say so and suggest a split. Still provide a draft assuming they stay
   combined; the decision is the human's.

Output the message alone, in a fenced code block, with no commentary
unless you have a concrete concern to flag.

## Then

1. Review the drafted message with the user, or proceed directly if the
   user asked for an autonomous commit.
2. Stage files if needed (`git add <paths>`).
3. Run `git commit` with the message via a HEREDOC to preserve
   formatting.
4. Confirm with `git status`.

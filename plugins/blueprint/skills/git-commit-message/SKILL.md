---
name: git-commit-message
description: Write high-quality git commit messages following the 7 rules from Chris Beams' guide. Use when the user asks to write, generate, or improve a git commit message.
---

# Git Commit Message

Help the user write a well-crafted git commit message following the 7 rules from Chris Beams' *How to Write a Git Commit Message* (https://cbea.ms/git-commit/).

## The 7 Rules

1. **Separate subject from body** with a blank line
2. **Limit the subject line to 50 characters**
3. **Capitalize** the subject line
4. **Do not end** the subject line with a period
5. **Use imperative mood** — write as if giving a command ("Fix bug", not "Fixed bug" or "Fixes bug")
   - A good test: the subject should complete the sentence *"If applied, this commit will ___"*
6. **Wrap the body at 72 characters**
7. **Use the body to explain what and why**, not how (the diff already shows how)

## Commit Format

```
<type>: <Short summary under 50 chars>
<blank line>
<Optional body: explain what changed and why.>
<Wrap each line at 72 characters.>
<blank line>
<Optional footer: e.g., issue references, breaking changes>
```

### Conventional Commit Types

| Type       | When to use                                      |
|------------|--------------------------------------------------|
| `feat`     | A new feature                                    |
| `fix`      | A bug fix                                        |
| `refactor` | Code restructuring without behavior change       |
| `docs`     | Documentation changes only                       |
| `style`    | Formatting, whitespace — no logic change         |
| `test`     | Adding or fixing tests                           |
| `chore`    | Build process, dependency updates, tooling       |
| `perf`     | Performance improvements                         |

## How to Use This Skill

When asked to write or improve a commit message:

1. **Understand the change** — read the diff, ticket description, or user's explanation.
2. **Pick the right type** — from the table above.
3. **Write the subject** — imperative mood, capitalized, ≤50 chars, no trailing period.
4. **Decide if a body is needed** — skip it for trivial changes; add it when context helps future readers.
5. **Write the body if needed** — explain *what* changed and *why*, not *how*. Wrap at 72 chars.
6. **Add footer if relevant** — e.g., `Closes #123`, `BREAKING CHANGE: ...`.

## Examples

### Simple (no body needed)
```
feat: Add user avatar upload endpoint
```

### With body (non-obvious reason)
```
fix: Prevent race condition in token refresh

The previous implementation called refresh() and then immediately
used the token, but the refresh was async. Under high concurrency
this caused stale tokens to be sent.

Now we await the refresh before proceeding.

Closes #457
```

### Refactor with context
```
refactor: Extract payment logic into PaymentService

The checkout controller was handling too many responsibilities.
Moving payment processing to a dedicated service makes it easier
to unit test and swap out payment providers in the future.
```

## Anti-patterns to Avoid

| Bad                          | Why                        | Better                            |
|------------------------------|----------------------------|-----------------------------------|
| `fixed bug`                  | Past tense, lowercase      | `Fix null pointer in user login`  |
| `WIP`                        | Meaningless to future you  | `Add draft UI for settings page`  |
| `Update code`                | Zero context               | `refactor: Simplify auth flow`    |
| Subject line > 50 chars      | Gets truncated in git log  | Break details into body           |
| Explaining *how* in body     | The diff already shows how | Explain *why* the change was made |

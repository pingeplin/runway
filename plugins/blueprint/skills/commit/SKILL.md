---
name: commit
description: Write high-quality git commit messages following the 7 rules from Chris Beams' guide. Use when the user asks to write, generate, improve, or prepare a git commit message, or says "commit this", "commit my changes", or "/commit".
argument-hint: [optional description of changes]
---

# Git Commit Message

Help the user write a well-crafted git commit message. This skill combines Chris Beams' 7 rules (*How to Write a Git Commit Message* — https://cbea.ms/git-commit/) with Conventional Commits type prefixes. When both apply, repo conventions take precedence.

## The 7 Rules

1. **Separate subject from body** with a blank line
2. **Aim for 50 characters in the subject line** — treat 72 as the hard limit (type+scope prefixes eat into the budget)
3. **Capitalize** the first word after the type prefix colon (e.g., `feat: Add export button`, not `feat: add export button`). Note: some Conventional Commits conventions use lowercase — this is one of the most commonly varied rules, so defer to repo conventions when they exist.
4. **Do not end** the subject line with a period
5. **Use imperative mood** — write as if giving a command ("Fix bug", not "Fixed bug" or "Fixes bug")
   - A good test: the subject should complete the sentence *"If applied, this commit will ___"*
6. **Wrap the body at 72 characters**
7. **Use the body to explain what and why**, not how (the diff already shows how)

## Commit Format

```
<type>[optional scope]: <Short summary — aim for ~50 chars, 72 max>
<blank line>
<Optional body: explain what changed and why.>
<Wrap each line at 72 characters.>
<blank line>
<Optional footer: issue refs, breaking changes, Co-Authored-By, etc.>
```

### Scope (Optional)

Add scope in parentheses after the type to indicate the area of the codebase affected:

```
feat(auth): Add OAuth2 PKCE flow
fix(parser): Handle unterminated string literals
refactor(api): Consolidate error response format
```

Use scope when the type alone is ambiguous — skip it for changes that are obvious from the subject.

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

When asked to write, improve, or prepare a commit message:

### Before Writing

1. **Check repo conventions** — run `git log --oneline -10` to see how existing commits are formatted. Match the repo's style (casing, type prefixes, scope usage) even if it differs from these rules.
2. **Read the actual changes** — run `git diff --staged` (or `git diff` if nothing is staged) to understand what changed.

### Writing the Message

1. **Pick the right type** — from the table above.
2. **Write the subject** — imperative mood, capitalized after the colon, aim for ~50 chars (72 hard max), no trailing period.
3. **Decide if a body is needed** — skip it for trivial changes; add it when context helps future readers.
4. **Write the body if needed** — explain *what* changed and *why*, not *how*. Wrap at 72 chars.
5. **Add footer if relevant** — e.g., `Closes #123`, `BREAKING CHANGE: ...`, or `Co-Authored-By:` lines and any other team-mandated trailers.

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

### Breaking Changes

Use the `BREAKING CHANGE:` footer for backwards-incompatible changes. Optionally add `!` after the type/scope:

```
feat(api)!: Change pagination to cursor-based

The offset-based pagination on /users and /orders is replaced with
cursor-based pagination. Clients must update to use `cursor` and
`limit` parameters instead of `page` and `per_page`.

BREAKING CHANGE: Remove offset-based pagination from all list endpoints
```

## Anti-patterns to Avoid

| Bad                          | Why                        | Better                            |
|------------------------------|----------------------------|-----------------------------------|
| `fixed bug`                  | Past tense, lowercase      | `Fix null pointer in user login`  |
| `WIP`                        | Meaningless to future you  | `Add draft UI for settings page`  |
| `Update code`                | Zero context               | `refactor: Simplify auth flow`    |
| Subject line > 72 chars      | Gets truncated in git log  | Break details into body           |
| Explaining *how* in body     | The diff already shows how | Explain *why* the change was made |
| `fix: Fix bug`               | Redundant and vague        | `fix: Prevent NPE when user has no email` |
| `feat: Add stuff`            | "stuff" means nothing      | `feat: Add CSV export for reports` |

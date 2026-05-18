---
name: migrate-paths
description: Migrate an existing repo's blueprint artifacts from root-level specs/ and plans/ into blueprint/specs/ and blueprint/plans/. ALWAYS use this command when the user asks to migrate blueprint paths, move specs and plans under blueprint/, update to the new layout, or says "run the migration", "move my specs and plans", "migrate to v3.6 layout", or "move specs and plans into blueprint folder". Runs as a dry-run by default; use `--apply` to perform the move with `git mv` (history-preserving).
argument-hint: '[--apply]'
---

# Migrate Paths

Move blueprint workflow artifacts from root-level `specs/` and `plans/` directories into the namespaced `blueprint/` directory. Required after upgrading to v3.6+; pre-migration layouts still work via fallback paths in the skills and evaluators, but new artifacts will be written under `blueprint/`, so a mixed layout is messy.

```
specs/   ->  blueprint/specs/
plans/   ->  blueprint/plans/
```

Design docs in `docs/designs/` are **not moved** — they're human-facing and belong under `docs/`. The command does rewrite any `../../specs/` or `../../plans/` back-links inside existing design docs so they keep resolving after the move.

## What this command does

1. **Detects** existing `specs/` and `plans/` at the repo root.
2. **Refuses** to clobber existing `blueprint/specs/` or `blueprint/plans/` directories.
3. **Refuses** to apply if the working tree has uncommitted changes (so the migration becomes its own clean commit).
4. **Dry-runs by default** — prints exactly what it would do.
5. **With `--apply`:** uses `git mv` to preserve file history, then rewrites design-doc back-links via `sed`, then `git add`s the rewritten design docs.

## Usage

```bash
# Dry run — see what would happen
${CLAUDE_PLUGIN_ROOT}/scripts/migrate_paths.sh

# Apply the migration
${CLAUDE_PLUGIN_ROOT}/scripts/migrate_paths.sh --apply
```

If `$ARGUMENTS` contains `--apply`, run the second form; otherwise run the first. After a successful `--apply`, present the resulting `git status` to the user and propose a commit message:

```
chore(blueprint): migrate artifacts to blueprint/{specs,plans}/
```

Do not commit automatically — the user reviews and commits.

## When this command isn't needed

- The repo has no `specs/` or `plans/` at the root (fresh repo or already migrated).
- The repo isn't a git repo (the script will fail; `git mv` needs git).

## Safety notes

- Migration uses `git mv`, so file history is preserved.
- Cross-references between specs and plans use **sibling-relative paths** (`../specs/`, `../plans/`). These don't need rewriting because both `specs/` and `plans/` move together under `blueprint/` — the sibling relationship is preserved.
- Only design docs' **two-level-up** back-links (`../../specs/`, `../../plans/`) need rewriting, and the script handles that.
- If anything looks wrong after `--apply` but before committing, `git restore --staged .` and `git checkout .` will undo everything cleanly.

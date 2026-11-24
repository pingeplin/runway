# Implementation Review Methodology

Review implementation code against its spec for completeness, correctness,
and quality. Assume nothing about how the code was produced — which agent
wrote it, in what order, with what discipline. Judge the result, not the
process. Apply these phases in order.

**Determinism over judgment.** If a tool in the repo can decide a question,
run the tool and report its result. Use your own judgment only for the
design questions that no tool can decide.

## Phase 1 — Spec Cross-Check

If a spec is available (check `.blueprint/specs/` for a matching ID or ask
the user):

1. **Map acceptance scenarios to code** — For each scenario, by its title, identify the code path that implements it.
2. **Flag unimplemented scenarios** — Scenarios with no corresponding code path.
3. **Flag extra behaviors** — Code paths that don't correspond to any spec scenario (scope creep or a missing spec update).
4. **Check error handling** — Verify that error scenarios from the spec have corresponding error handling in the implementation.

Refer to each scenario by its title. If the spec still numbers its
scenarios (`S1`, `S2`, …), use the number and the first words of the
scenario together, and recommend the `migrate-scenario-titles` skill.

## Phase 2 — Deterministic Checks (the repo's tools)

Find the tools that the repo already uses. Look in the package manifest and
its scripts (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`,
`build.gradle`, …), `Makefile` / `justfile` / `Taskfile`,
`.pre-commit-config.yaml`, CI workflows (`.github/workflows/`, …), and tool
config files (`.eslintrc*`, `ruff.toml`, `.golangci.yml`, `mypy.ini`, …).
Prefer the exact command that CI or a script runs.

| Category | Examples | Decides |
|---|---|---|
| Formatter | prettier, black, ruff format, gofmt, rustfmt | layout |
| Linter | eslint, ruff, golangci-lint, clippy, rubocop | unused imports and variables, dead code, bare `except`, empty `catch`, commented-out code, TODO markers |
| Type checker | tsc, mypy, pyright | type contracts |
| Dependency / architecture rules | import-linter, dependency-cruiser, deptry, ArchUnit, madge | forbidden imports, layer breaks, unused or missing dependencies |
| Coverage | coverage.py, c8 / istanbul, `go test -cover` | public code with no test |
| Mutation | mutmut, cosmic-ray, Stryker, PIT, cargo-mutants, go-mutesting | whether the tests catch a break |

Rules:

- **Use only what the repo has.** Do not install a tool and do not add config.
- **Run in check mode.** Never pass `--fix`, `--write` or any flag that edits files.
- **Scope to the change** when the tool allows it (changed files, or the diff from the base ref). Mutation tools can be slow; always scope them.
- **The tool's result is the verdict.** Report its findings with `file:line`. Mark findings outside the change as `pre-existing, not blocking`. Do not judge again a question that a tool already answered, and do not repeat its findings in Phase 3.
- **No tool for a category** → write `not checked — no tool in repo` and name one tool that would cover it. Do not replace a missing linter or formatter with your own reading. A text search for stub markers (`NotImplementedError`, `TODO`, `FIXME`, `HACK`, `raise NotImplemented`) is deterministic, so run it with `grep` when no linter covers stubs.
- **A tool that fails to run** (missing dependency, broken config) → report the command and the error. Do not count it as a pass.

The referee uses the mutation category for its anti-vacuity check. In a
standalone `/review`, run a mutation tool only if the user asks.

## Phase 3 — Design Judgment

Only the questions that no tool can decide. Judge against these sources,
in this order:

1. **The repo's own design principles** — `CLAUDE.md`, `AGENTS.md`,
   `CONTRIBUTING.md`, `ARCHITECTURE.md`, ADRs and design docs (for example
   `docs/designs/`, `docs/adr/`), style guides, and
   `docs/testing/test-conventions.md`. Read the ones that exist before you
   judge.
2. **The design doc and the spec's Interface Contract** for this change.
3. **The plugin's principles** in this file — only where the repo is silent.

When the repo and the plugin disagree, the repo wins. Name the repo rule
you applied in each finding.

Flags:

- **Interface contract** — the signatures, errors and breaking-change rules differ from the spec's Interface Contract or the design doc.
- **Design principle** — the code breaks a principle that the repo states (for example SOLID, layering, error-handling policy, naming). Quote the rule.
- **Error semantics** — the error behavior is wrong for the domain even though it type-checks and lints clean: a swallowed failure, a wrong error kind, no check on external data.
- **Stale or low-value comments and docstrings** — a linter cannot read meaning, so you judge these:
  - **Stale docstring** — a function/method docstring whose described arguments, return type, raised errors, or behavior no longer match the current signature or implementation. Fix: update or delete.
  - **Restated *what*** — comments or docstrings that paraphrase what well-named code already shows (e.g. `# increment counter` above `counter += 1`, or a docstring that just re-narrates the function body). Fix: delete; if a real *why* is buried in there, keep only that line.
  - **Task-referential rot** — comments naming a ticket, fix, or caller ("added for the X migration", "used by handler Y"). Fix: delete; that context belongs in the commit message or PR description.

  Function and method docstrings explaining purpose, contracts, or non-obvious behavior are still encouraged — the issue is rot, not their presence.

## Phase 4 — Implementation Summary

Output: spec alignment (scenarios implemented/total, unimplemented
scenarios by title, extra behaviors); a table of the deterministic checks
with each tool's command and result, or `not checked — no tool in repo`;
the design findings, each with the repo rule or plugin principle it
applies; and an overall assessment. When this methodology is applied by
the `referee` agent, these results feed its checks; flag only, and leave
fixes to the human or the implementing agent.

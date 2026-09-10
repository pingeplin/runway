---
name: test-conventions
description: Generate a repo-specific test-writing conventions doc by mining the project's existing tests and projecting Kent Beck's Test Desiderata onto this codebase. Outputs to docs/testing/test-conventions.md and wires a pointer into AGENTS.md/CLAUDE.md. ALWAYS use this skill when the user wants to create, generate, regenerate, or update test guidelines, a test style guide, test-writing conventions, or coding standards for tests — anything that answers "what should our tests look like in this repo?". Also trigger on "codify our test conventions", "extract our test patterns", "give coding agents guidance on writing tests", "give PR reviewers a test checklist", "standardize how we write tests", or "what's our testing convention". This is the third intent producer alongside /design (what to build) and /spec (what done means) — it produces "what good tests look like" for THIS repo. Regenerable, not hand-maintained — re-run it whenever test conventions drift.
argument-hint: '[optional-scope-or-output-path]'
---

# Test Conventions

Generate a **repo-specific test-writing conventions doc**: the concrete answer
to *"how do we write a good test in this codebase?"* It is produced by mining
the project's existing tests for their de-facto conventions and **reconciling**
those conventions against Kent Beck's Test Desiderata and blueprint's
anti-patterns checklist — keeping what's good, flagging what isn't.

This is the **third intent producer**. Blueprint's portable interface to any
coding agent is intent, and intent has three legs:

| Producer | Intent leg | Artifact |
|---|---|---|
| `/design` | what to build (which approach) | `docs/designs/{id}.md` |
| `/spec` | what done means (this feature) | `.blueprint/specs/{id}.md` |
| **`/test-conventions`** | **what good tests look like (this repo)** | **`docs/testing/test-conventions.md`** |

`/design` and `/spec` are **per-feature**. `/test-conventions` is **per-repo and
regenerable** — you run it once to establish the conventions, and re-run it when
the test stack or conventions drift. It is not a hand-maintained document; the
header says so, and re-running it overwrites cleanly.

## Where this fits

The conventions doc sits *beside* the per-feature pipeline and feeds **both
ends** of it — the implementing agent (via an AGENTS.md/CLAUDE.md pointer it
auto-loads) and the referee (which loads the conventions when scoring tests):

```
        ┌──────────────────────────────────────────────────────────┐
        │  /test-conventions   (per-repo · regenerable)              │
        │  mine existing tests → reconcile vs Desiderata             │
        │  → docs/testing/test-conventions.md                        │
        └───────────────┬───────────────────────────┬──────────────┘
            AGENTS.md / CLAUDE.md pointer        /verify loads it
                        │                            │
                        ▼                            ▼
/design ─→ /spec ─→ ⟦ any coding agent implements ⟧ ─→ /verify ─→ /commit
```

The conventions never **contradict** the Desiderata the referee scores against —
they **concretize** them. The universal references
(`references/test-desiderata.md`, `references/anti-patterns.md`) stay the source
of truth; this doc is the repo's projection of them, regenerated from the repo,
not maintained by hand.

## Output

Write the conventions doc to:

```
docs/testing/test-conventions.md
```

(unless `$ARGUMENTS` names a different path). Create `docs/testing/` if it does
not exist. Then wire a one-line pointer into the repo's agent-instructions file
(see Step 4) so coding agents auto-load it.

## Workflow

### Step 1 — Mine the existing tests

Discover, don't assume. Investigate the repo:

1. **Test stack** — framework and runner command (`pyproject.toml`,
   `package.json` scripts, `Makefile`, CI config). Record the *exact* command a
   contributor runs (e.g. `uv run pytest`, `npm test`, `go test ./...`) — not a
   generic one.
2. **Layout** — where tests live, the file/dir naming pattern, how test files
   map to source (mirror tree? co-located? `_test` suffix?).
3. **De-facto conventions** — read a representative sample of real test files
   (aim for breadth: a few subsystems, both old and recent tests) and extract
   what the repo *actually does*:
   - Test naming pattern (and how consistent it is)
   - Setup/fixture style — inline vs shared `conftest`/`beforeEach`, factories,
     builders
   - **Mocking boundary** — what gets mocked/faked and what stays real; where
     the test doubles live (e.g. `tests/support/fakes/`)
   - **Determinism helpers** — clock injection, seeded randomness, frozen time
     (the real helper names and import paths)
   - Assertion style — bare asserts, custom matchers, snapshot usage
   - How behavior is asserted — through public interface vs. peeking at internals
4. **Where to point examples** — for every convention you'll state, find a real
   test in the repo that exemplifies it, so the doc cites `path::test_name`,
   never a hypothetical.

If the repo has **few or no tests**, say so explicitly in the header and fall
back to the test framework's idioms plus the universal Desiderata — and mark
those rules as *"baseline (no repo precedent yet)"* so the owner knows they
weren't observed.

### Step 2 — Reconcile against the Desiderata

Read `${CLAUDE_PLUGIN_ROOT}/references/test-desiderata.md` and
`${CLAUDE_PLUGIN_ROOT}/references/anti-patterns.md`. For each de-facto
convention you mined, classify it:

- **Endorse** — the repo's habit already satisfies a desideratum → write it as a
  convention, grounded in a real example.
- **Deviation** — the repo's habit *violates* a desideratum or hits an
  anti-pattern (e.g. pervasive `assert_called_with` → AP-1 structure-sensitive;
  direct `datetime.now()` → AP-3). **Do not codify it as a standard.** Record it
  under *Known Deviations* with the AP code and let the owner decide: fix the
  tests, or accept it and document the exception.
- **Gap** — a desideratum the repo's tests don't address at all (e.g. no
  determinism story) → state the convention from the universal principle and
  mark it *gap*.

**The reconcile pass is what makes this valuable.** A doc that just records
"what the tests do" launders existing bad habits into "the standard." A doc that
just restates Kent Beck with the repo's name pasted in is generic boilerplate.
The value is in the *intersection*: this repo's real idioms, filtered through
the Desiderata, with the mismatches surfaced.

### Step 3 — Write the conventions

Use the Template below. Every convention must be **grounded** — cite a real
file, helper, or `path::test_name`. Strip any rule you can't ground (or move it
to a clearly-labelled baseline section). Keep it scoped to *"how to write one
good test"* — naming, mocking boundary, determinism, fixtures, assertions. Do
**not** drift into test *strategy* (what level to test at, unit/integration
ratios, coverage targets) — that's a design-doc concern, not this doc's.

### Step 4 — Wire the pointer

So coding agents auto-load the conventions, add a short pointer to the repo's
agent-instructions file:

- If `AGENTS.md` exists, append a pointer there.
- Else if `CLAUDE.md` exists, append it there.
- Else create `AGENTS.md` with the pointer.

The pointer is one line, e.g.:

```markdown
- **Writing tests?** Follow [docs/testing/test-conventions.md](docs/testing/test-conventions.md) — this repo's test-writing conventions (naming, mocking boundary, determinism, fixtures).
```

Keep it a pointer, not a paste — the conventions doc is the long document; the
agent file stays terse.

## Template

```markdown
# Test Conventions — {repo name}

> Generated by `/test-conventions` on {YYYY-MM-DD} from {N} test files.
> **Regenerable, not hand-maintained** — re-run `/test-conventions` when the
> test stack or conventions drift; don't edit this file by hand.
> This is the repo-specific projection of the [Test Desiderata]; it concretizes
> those principles, it never overrides them.

## How to use this

- **Writing a test (human or coding agent):** follow the Conventions below. They
  are what `/verify` scores against, expressed in this repo's idioms.
- **Reviewing a PR:** the Conventions double as a review checklist; the Known
  Deviations section lists accepted exceptions so you don't re-flag them.

## Stack

- **Framework:** {e.g. pytest 8 / vitest / go test}
- **Run the suite:** `{exact command, e.g. uv run pytest}`
- **Layout:** {where tests live; file/dir naming; source↔test mapping}
- **Assertion style:** {bare assert / custom matchers / snapshots}

## Conventions

> Each convention: the principle → how THIS repo does it → a real example to copy.

### Naming
- **Rule:** {pattern in use, e.g. `test_<action>_<scenario>_<outcome>`}
- **Example:** `{path::test_name}`
- _(Desideratum: Specific · AP-8)_

### Mocking boundary
- **Mock / fake:** {what — e.g. HTTP gateway, Repository port; where the doubles live}
- **Keep real:** {what — domain objects, pure transforms, internal collaborators}
- **Example:** `{path::test_name}`
- _(Desideratum: Behavioral, Structure-insensitive · AP-1, AP-5)_

### Determinism
- **Rule:** {e.g. inject the clock via `FakeClock` (`tests/support/clock.py`); never `datetime.now()`}
- **Example:** `{path::test_name}`
- _(Desideratum: Deterministic · AP-3)_

### Fixtures & setup
- **Rule:** {inline vs shared; factories/builders in use; the readability bar}
- **Example:** `{path::test_name}`
- _(Desideratum: Readable · AP-6)_

### Asserting behavior
- **Rule:** {assert observable output/effects through the public interface; don't peek at internals or assert call order}
- **Example:** `{path::test_name}`
- _(Desideratum: Behavioral, Structure-insensitive · AP-1)_

## The bar /verify enforces

These conventions are this repo's wording of the rubric `/verify` scores
tests against — Behavioral and Structure-insensitive first, then
Deterministic, Specific, Readable, Isolated; no AP-1…AP-8 violations. A green
suite that wouldn't fail if the behavior broke does not pass, here or there.

## Known Deviations

> Existing tests that violate a convention above. Owner decides: fix, or accept
> and keep here as a documented exception. Re-running `/test-conventions`
> refreshes this list.

| Location | Violates | Note |
|---|---|---|
| `{path::test_name}` | {AP-1 / AP-3 / …} | {what's off; suggested fix or "accepted because …"} |

## Regenerating

Run `/test-conventions` again after the test stack changes, new conventions
land, or the Known Deviations are addressed. This file is output, not source.
```

## Principles

- **Ground every convention or cut it.** A rule with no `path::test_name` behind
  it is either generic boilerplate or a hallucination. If you can't point at a
  real test, move it to a labelled baseline section or drop it.
- **Reconcile, don't transcribe.** Mining without reconciling codifies the
  repo's bad habits as standards. The Known Deviations section is where the
  reconcile pass pays off — it's often the most useful part for the owner.
- **Concretize, never contradict.** This doc is downstream of the universal
  Desiderata, not a competing rulebook. If the repo's habit conflicts with a
  desideratum, that's a Deviation to flag — not a convention to enshrine.
- **Scope to one good test.** Naming, mocking boundary, determinism, fixtures,
  assertions. Leave test *strategy* (levels, ratios, coverage targets) to design.
- **Regenerable beats maintained.** Don't ask the user to keep this in sync by
  hand — that's the maintenance entropy v4.0 exists to avoid. The header tells
  readers it's output, and re-running it is the update path.

## Next Step

After writing the conventions doc and wiring the pointer, **dispatch the
`conventions-evaluator` subagent** via the `Agent` tool with
`subagent_type: conventions-evaluator`. Pass the file path in the prompt. The
evaluator runs in fresh context and is built to catch the one failure mode that
kills this artifact's value — **ungrounded, generic rules** — by spot-checking
that each convention's cited example actually exists in the repo and actually
demonstrates the rule. Surface its findings and address any "Needs Human Input"
items (usually: how to resolve a flagged Deviation).

Once approved, the conventions work without further action: coding agents pick
them up through the AGENTS.md/CLAUDE.md pointer, PR reviewers use them as a
checklist, and `/verify` loads them when scoring tests. Re-run
`/test-conventions` when conventions drift.

# The Loop — produce → judge → revise

One protocol for every artifact blueprint produces or gates: the design
doc, the spec, and the implementation. A producer makes the whole
artifact; a fresh judge reports on it; the producer revises the whole
artifact against the report. The human sees the result once, at loop
exit — never between rounds.

The loop has two jobs and only two: make the artifact **coherent** (no
internal contradictions) and **complete against its goal** (nothing
goal-related left uncovered). It routes to a human only what only a
human can decide. It never narrows scope.

## Protocol

```
ledger = []                       # owned by the calling skill, never by a judge
round  = 1
loop:
  producer  → artifact (the whole thing, regenerated — not a patch)
  judge     ← artifact + the ledger's open rows
  judge     → every open row re-stated as resolved | open, new rows (each with a Kind), verdict
  ledger    ← merge the judge's report (IDs are stable; nothing is renumbered)
  write     ← the merged ledger snapshot, appended to the artifact's .ledger.md sibling
  1. READY (no open rows, no questions, summary at passing value)   → exit: present the artifact
  2. round == 3                                                     → exit: ledger, artifact, open behavior-change rows as questions
  3. zero resolved and zero new this round                          → exit: same as 2, "stuck"
  4. no open contradiction/uncovered, ≥1 open behavior-change       → exit: NEEDS-HUMAN, present the questions
  5. otherwise                                                      → REVISE: producer ← full ledger; round += 1
```

**Stop rules, in this order:** `READY` → round cap 3 → stuck → `NEEDS-HUMAN`
→ `REVISE`. `NEEDS-HUMAN` fires only when no `contradiction` and no
`uncovered` row is open and at least one `behavior-change` row is; with
zero open rows it never fires — that is rule 1, or rule 5 when the
methodology's summary value is below passing. `REVISE` continues whenever
any `contradiction` or `uncovered` row is open, even if `behavior-change`
rows are open alongside. The cap and stuck exits still present every open
`behavior-change` row as a question.

**Fresh judge, whole-artifact revise.** Every round dispatches a new
judge subagent with no context from any earlier judge — only the
artifact and the ledger's open rows, which say what to look at again,
not what to conclude. The producer, who holds the intent, then
regenerates the entire artifact with the ledger in hand. Nobody patches
someone else's work in a context that has lost its freshness, and
someone owns whole-document coherence.

**Ledger ownership.** The calling skill — the session running `/design`,
`/spec`, or `/blueprint` — holds the ledger, passes it to every judge,
and writes it to disk after every round (see Ledger file). On exit it
presents the final ledger alongside the artifact, naming every
`[INFERRED]` addition so the human can strike any of them.

## What a finding may be

Every ledger row carries a `Kind`. There are exactly three:

| Kind | Meaning | Who resolves |
|---|---|---|
| `contradiction` | two parts of the artifact disagree, or one concept has two names | producer, autonomously |
| `uncovered` | goal-related scope the artifact does not cover — a prerequisite, a neighbour the feature's code path or tests reach, an edge the goal implies — where the goal, the code path, and the existing tests together determine what the behaviour must be, leaving the producer no choice to make | producer, autonomously: **add** it, marked `[INFERRED]` |
| `behavior-change` | resolving it requires a choice the goal leaves open — including whether to change behaviour that currently works and the goal did not mention — or it is an item a methodology's "Flag for human" line names: anything only the human can decide | human, via Needs human input |

One test, applied twice: **is a choice required?** Restoring something
that is absent is not a choice; altering something that already works
is. Worked example: definitions stripped from `astropy/io/votable/tree.py`
that the feature's code path and tests reach are `uncovered` — absent,
and the goal, the code path, and the tests determine what they must be;
the producer adds them as in-scope prerequisites. Deciding whether the
parser should *also* reject a malformed attribute the goal never
mentions, or rewriting a working function's return type, is
`behavior-change`.

**Scope rule.** A judge may add scope and may never remove goal-related
scope. An "Out of Scope" / "do not restore" / "leave as-is" entry is
valid only when it names a `behavior-change` decision a human declined;
any other such entry is itself a `contradiction` finding with
`Fix: remove the fence and cover it`. When in doubt between `uncovered`
and `behavior-change`, prefer `uncovered`: the `[INFERRED]` marker puts
the addition in front of the human at the gate, where striking it costs a
glance.

**`behavior-change` rows and questions are one set.** Every open
`behavior-change` row has exactly one matching question under the
judge's **Needs human input**, and nothing else appears there.

**Two markers, two authors.** `[ASSUMPTION: …]` is something the *writer*
guessed while drafting. `[INFERRED]` marks scope a *judge* raised as
`uncovered` and the producer added. Neither replaces the other.

## Ledger format

```markdown
## Ledger — round {n}

| ID | Kind | Phase | Finding | Location | Fix | Status |
|----|------|-------|---------|----------|-----|--------|
| F1 | contradiction | Coherence | "referee" and "verifier" used for the same agent | §Overview, §Data Flow | pick one term | resolved |
| F2 | uncovered | Scope | `check_string` is called by `to_table` but stripped from `tree.py` | §Key Components | add as in-scope prerequisite, marked [INFERRED] | open |
| F3 | behavior-change | Testability | spec is silent on whether malformed `arraysize` should raise | §S7 | ask: raise, or warn and skip? | open |
```

`Status` is exactly one word, `open` or `resolved` — never a phrase;
what was done goes in `Fix`. Every round's table keeps all seven columns.
IDs are stable across rounds; a judge never renumbers. Every row carries a `Kind`, a `Location`, and a concrete
`Fix` the producer can act on.

## Ledger file

The calling skill writes the ledger as a sibling of the artifact, with
`.ledger.md` replacing `.md`:

```
.blueprint/specs/{id}_{name}.ledger.md
docs/designs/{id}_{topic}.ledger.md
```

After every judge round it appends one `## Ledger — round {n}` section
holding the **merged snapshot** — every row raised so far, `open` or
`resolved` — and at exit appends an `## Exit` line naming the stop rule
that fired (`READY`, `round cap`, `stuck`, `NEEDS-HUMAN`). A later loop
over the same artifact (the implement loop over a spec) appends its own
round sections, numbered from 1 again, and its own `## Exit` after the
existing ones. Any "most recently modified `.md`" discovery over
`.blueprint/specs/` or `docs/designs/` must exclude `*.ledger.md`; the
ledger is always newer than its artifact.

## The three instantiations

| Stage | Producer | Judge | `READY` means |
|---|---|---|---|
| `/design` | this session, writing | `evaluator` + `references/review-design.md` | argument strength High, no open rows, no questions |
| `/spec` | this session, writing | `evaluator` + `references/review-spec.md` | testability High, no open rows, no questions |
| implement | any coding agent — default: this session | `referee` (via `/verify`) | the referee reports `Meets the spec's Definition of Done: Yes` |

The kinds apply to all three. Document rounds may raise every kind. The
implement loop raises no `behavior-change` row — the referee has no
human-input section and no gate sits between rounds — so its stop rules
are 1, 2, 3, and 5, with rule 4 not applicable. Human gates sit only at
loop exits: approve the design, approve the spec, review the verdict.

### Document rounds

Dispatch `evaluator` with `subagent_type: evaluator` and this prompt:

```
Artifact: {path}
Methodology: {reference path}
Ledger open items: {table rows with Status=open, or "none"}
```

It returns a ledger update, human-input items, and a verdict. On
`REVISE`, rewrite the whole document with the full ledger in hand: fix
every open `contradiction`, add every open `uncovered` item marked
`[INFERRED]`, and never move a goal-related item to Out of Scope.

### Implement rounds

`referee.md` is unchanged and knows nothing about ledgers, so the
calling skill carries the ledger in the dispatch prompt and derives the
rows itself. Each round invokes `/verify` with the spec, the base ref,
and the ledger; `/verify` dispatches the referee with:

```
Spec: {path}
Base git ref: {ref, or "none"}
Ledger open items: {table rows with Status=open, or "none"}
For each open item above, state in your report whether the condition it
describes is still present.
```

From the referee's report, the calling skill makes one row per
punch-list item, sets `Phase` to the referee check that raised it, sets
`Kind` (uncovered or vacuous scenario → `uncovered`; quality blocker →
`contradiction`), and marks a row `resolved` when the next round's report
no longer lists it. The rows go to the spec's `.ledger.md`, appended
after the spec loop's sections.

**Working-tree policy.** The next version is produced on the current
working tree; do not revert to a pristine checkout — the loop is
repairing, not measuring feedback quality. The handoff below shares its
shape with `evals/blueprint-featurebench/prompts/repair_instruction.md`
minus that prompt's previous-patch block and its pristine-repository
instruction. Hand the implementing agent (this session by default, or
any coding agent):

```
## Previous round
{referee verdict, verbatim}
{ledger}

## Instruction
Produce the next version on the current working tree, addressing every
open item. Do not revert to a clean checkout.
```

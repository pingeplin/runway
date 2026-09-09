# The Loop — produce → judge → revise

One protocol for every artifact blueprint produces or gates: the design
doc, the spec, and the implementation. A producer makes the whole
artifact; a fresh judge reports on it; the producer revises the whole
artifact against the report. The human sees the result once, at loop
exit — never between rounds.

## Protocol

```
ledger = []                       # owned by the calling skill, never by a judge
round  = 1
loop:
  producer  → artifact (the whole thing, regenerated — not a patch)
  judge     ← artifact + the ledger's open rows
  judge     → every open row re-stated as resolved | open, new rows, human-input items, verdict
  ledger    ← merge the judge's report (IDs are stable; nothing is renumbered)
  if verdict is READY              → exit: present the artifact to the human
  if verdict is NEEDS-HUMAN        → exit: present the questions to the human
  if round == 3                    → exit: present the ledger and the artifact
  if zero resolved and zero new    → exit: present as stuck
  producer  ← the full ledger; round += 1        # only REVISE reaches here
```

**Stop rules, in this order:** `READY` → `NEEDS-HUMAN` → round cap 3 →
stuck (a round whose ledger update resolves zero rows and adds zero
rows). Only `REVISE` continues the loop.

**Fresh judge, whole-artifact revise.** Every round dispatches a new
judge subagent with no context from any earlier judge — only the
artifact and the ledger's open rows, which say what to look at again,
not what to conclude. The producer, who holds the intent, then
regenerates the entire artifact with the ledger in hand. Nobody patches
someone else's work in a context that has lost its freshness, and
someone owns whole-document coherence.

**Ledger ownership.** The calling skill — the session running `/design`,
`/spec`, or `/blueprint` — holds the ledger and passes it to every
judge. On exit it presents the final ledger alongside the artifact, so
the human sees what was raised and what was resolved.

## Ledger format

```markdown
## Ledger — round {n}

| ID | Phase | Finding | Location | Fix | Status |
|----|-------|---------|----------|-----|--------|
| F1 | Testability | "handles errors gracefully" is untestable | §Proposed Solution ¶3 | state the status code and body | open |
| F2 | Coherence | "referee" and "verifier" used for the same agent | §Overview, §Data Flow | pick one term | resolved |
```

`Status` is `open` or `resolved`. IDs are stable across rounds; a judge
never renumbers. Every row carries a `Location` and a concrete `Fix`
the producer can act on.

## The three instantiations

| Stage | Producer | Judge | `READY` means |
|---|---|---|---|
| `/design` | this session, writing | `evaluator` + `references/review-design.md` | argument strength High, no open rows, no human-input items |
| `/spec` | this session, writing | `evaluator` + `references/review-spec.md` | testability High, no open rows, no human-input items |
| implement | any coding agent — default: this session | `referee` (via `/verify`) | the referee reports `Meets the spec's Definition of Done: Yes` |

Human gates sit only at loop exits: approve the design, approve the
spec, review the verdict.

### Document rounds

Dispatch `evaluator` with `subagent_type: evaluator` and this prompt:

```
Artifact: {path}
Methodology: {reference path}
Ledger open items: {table rows with Status=open, or "none"}
```

It returns a ledger update, human-input items, and a verdict. On
`REVISE`, rewrite the whole document with the full ledger in hand.

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
punch-list item (uncovered scenario, covered-but-vacuous scenario,
quality blocker), sets `Phase` to the referee check that raised it, and
marks a row `resolved` when the next round's report no longer lists it.

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

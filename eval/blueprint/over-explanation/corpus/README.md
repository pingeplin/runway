# Corpus authoring protocol

This directory holds the frozen task corpus for the over-explanation benchmark
(issue #10). Every arm receives the identical brief; the metric and guardrails
are scored against blindly-authored gold sets and hidden oracles. The validity
of the whole experiment rests on these assets being authored **blind** — before
and independent of any arm's output. This README is the protocol; `schema.md` is
the exact JSON shape; `example-brief/` is a complete worked example.

## Target: 9 briefs

The corpus comprises **9 briefs**, stratified by the pre-registered `regime`
(frozen *before* any treatment run, so the strata cannot be chosen to flatter
the result):

| Regime             | Count (target) | Character                                            |
| ------------------ | -------------- | ---------------------------------------------------- |
| `elicit_prone`     | 3              | Prompts that historically elicit over-explanation.   |
| `large_realistic`  | 3              | Full-size, realistic design/spec tasks. The primary effect must hold here, not just on the easy strata. |
| `neutral`          | 3              | Ordinary tasks with no particular elicitation pull.  |

A brief is **buildable** iff its deliverable is executable code with a hidden
oracle. Buildable briefs additionally carry `cases.json` + `oracle.py`. Briefs
whose deliverable is a design doc or spec are not buildable and omit those.

## Blind-authoring protocol

Author each brief in this strict order. **Do not** look at any arm's generated
output at any step — that is what makes the gold set and oracle blind.

1. **Write `brief.md`.** The full prose every arm receives. Self-contained.
2. **Write `brief.json`.** Set `id` (match the directory name), `title`,
   `regime` (assign from the held-out proxy — baseline length + a different
   model's coarse estimate — *not* from any A1 output), and `buildable`.
3. **Author `gold_propositions.json` from the brief alone.** Enumerate the
   atomic load-bearing claims. For each: assign a `tier`
   (`must` / `should` / `detail`) and `kind` from an ontology of your own
   wording. **Do not** reuse change ②'s six keep-categories (fact / decision /
   constraint / interface-detail / rejected-alternative / testable-behavior) —
   reusing them would make density rise by construction (fix #1). Record
   `mention_sentences` (>=1 per proposition) against the brief's own sentence
   indexing.
4. **If buildable, author the oracle blind.** Write `oracle.py` as a trusted
   reference implementation from the brief alone, then derive `cases.json`
   (label + args + expected) from it. Cover the happy path, the empty/boundary
   case, and any explicitly stated edge (e.g. negatives). The same frozen
   `cases.json` grades *every* arm identically.
5. **Freeze.** Once any A1 run has read a brief, its gold set and oracle are
   frozen. Changing them after the fact invalidates the pre-registration; the
   manifest `content_hash` is the tamper-evidence anchor.

## Tier discipline

* `must`   — dropping this claim is a hard ship block (substance guardrail).
* `should` — flagged for human review on loss; not blocking.
* `detail` — nice-to-have; reported only.

Tier the claim by the brief's intent, never by how any arm happened to treat it.

## Worked example

`example-brief/` is a genuine small buildable brief (`running_total`): a brief
body, metadata, a 5-proposition tiered gold set, an executable reference oracle,
and 5 oracle cases. Use it as the template for shape and tone.

You are running fully non-interactively as part of an automated benchmark.
There is no human available. Nobody will read a question or approve anything.

Your task: propose exactly {n_mutations} **strategic source mutations** for the
implementation diff below, so we can measure whether the tests that shipped
alongside it actually catch broken behaviour.

A good mutation is a **small, semantically load-bearing** edit to production
code that a competent test suite MUST catch:

- flip a boundary — `if x >= 3:` → `if x >= 2:`
- swap a comparison or boolean operator — `a > b` → `a < b`, `and` → `or`
- corrupt a lookup-table entry — `"M": 1000` → `"M": 999`
- change a default value — `def f(n=10)` → `def f(n=11)`
- drop or invert a guard — `if not ok: raise` → `if ok: raise`
- off-by-one a slice or index — `xs[1:]` → `xs[2:]`
- return the wrong branch of a conditional expression

A bad mutation is one that is uninteresting or unfalsifiable: whitespace,
comments, docstrings, logging text, renaming a local, an equivalent
expression, or anything that would crash on import regardless of behaviour.
Do not mutate test files, and do not propose edits to files outside the list
below.

## Hard requirements on your output

1. Reply with **a single JSON array and nothing else**. No prose before or
   after, no markdown fence.
2. Each element is an object with exactly these keys:
   - `file` — a path from the list below, verbatim.
   - `find` — a snippet copied **byte-for-byte** from the post-diff content of
     that file, which occurs **exactly once** in the whole file. Prefer a
     snippet long enough to be unique (include surrounding context on the same
     line, or two adjacent lines joined by `\n`), but keep it to a few lines.
   - `replace` — `find` with the mutation applied, same indentation.
   - `rationale` — one short sentence naming the semantics being broken.
3. `find` must be genuinely unique in the file. If a line like `return None`
   appears many times, widen the snippet until it is unique or pick a
   different site.
4. Spread the mutations across different behaviours (and across files, when
   several source files changed). Do not stack {n_mutations} variants of the
   same boundary.
5. Preserve indentation exactly — these strings are applied by literal string
   replacement, not by a patch tool.

## Task

Instance: {instance_id}

Source files you may mutate (non-test files touched by the diff):

{source_files}

## Implementation diff (source hunks only)

```diff
{source_diff}
```

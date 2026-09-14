You are running fully non-interactively as part of an automated benchmark.
Nobody will read a question or approve anything — never ask one.

Your task is a **listing** task, not a judgment: read the spec below and list
every code symbol (function, method, class, attribute, module) that the spec
tells the implementing agent **not to build, not to restore, not to fix, or
not to modify**.

What counts as fenced:

- A symbol named in a sentence that forbids building, restoring, fixing, or
  modifying it ("do not implement `x`", "`y` is out of scope", "leave `z`
  untouched", "must not be changed").
- A symbol listed as an item under a heading whose meaning is exclusion
  ("Out of scope", "Non-goals", "Do not attempt").

What does not count:

- A heading alone. A symbol under "Known blockers", "Companion gaps",
  "Environment notes" or similar is fenced only if the sentence about it
  forbids touching it; if the sentence says it is in scope, required, or to
  be added, it is not fenced.
- Symbols the spec asks the agent to implement, even when the same section
  also fences other symbols.
- Symbols mentioned only as existing context, callers, or examples.

For each fenced symbol also record how strongly the spec forbids it:

- `hard` — the agent is told not to touch it, no exception.
- `soft` — the spec says it is optional, unnecessary, or "not required", but
  does not forbid it.

Do not read files, do not run tools, do not propose changes. Judge strictly
from the spec text.

The final line of your reply must be exactly one JSON object on one line,
with no code fence, of the shape:

{"fenced": [{"symbol": "<identifier; for a method write Class.method; no module path, no parentheses>", "strength": "hard|soft", "quote": "<≤120 chars of the spec sentence that fences it>"}]}

## Spec

{spec}

# Corpus asset JSON shapes

Each brief is one immediate subdirectory of the corpus root. A directory is a
brief iff it contains a `brief.json`. `corpus.load_corpus(root)` loads every
such subdirectory (sorted by brief id); other subdirectories (docs, scaffolds)
are skipped.

Per-brief files:

| File                      | Required        | Loader                  | Model type        |
| ------------------------- | --------------- | ----------------------- | ----------------- |
| `brief.json`              | always          | `load_brief`            | `Brief` metadata  |
| `brief.md`                | recommended     | `load_brief`            | `Brief.text`      |
| `gold_propositions.json`  | always          | `load_gold`             | `PropositionSet`  |
| `cases.json`              | buildable only  | `load_oracle_cases`     | `tuple[OracleCase]` |
| `oracle.py`               | buildable only  | (audit aid; not loaded) | reference impl    |

All JSON is UTF-8. The model constructors enforce the domain invariants; the
loaders only shape-check and surface violations as `ValueError`.

---

## `brief.json`

```json
{
  "id": "example-brief",
  "title": "Running total",
  "regime": "neutral",
  "buildable": true
}
```

| Key         | Type   | Notes                                                        |
| ----------- | ------ | ------------------------------------------------------------ |
| `id`        | string | Non-empty. Should match the directory name.                  |
| `title`     | string | Human label.                                                 |
| `regime`    | string | One of `elicit_prone`, `large_realistic`, `neutral`. Frozen difficulty stratum; unknown value => `ValueError`. |
| `buildable` | bool   | `true` iff the brief has a hidden oracle (`cases.json`).      |

The brief body is read from the sibling `brief.md` into `Brief.text`. A missing
`brief.md` yields an empty body rather than an error.

---

## `gold_propositions.json`

The blind gold proposition set — the load-bearing claims a faithful build must
carry, authored from the brief alone (never from any arm's output).

```json
{
  "document_id": "example-brief-gold",
  "propositions": [
    {
      "id": "p1",
      "text": "running_total returns the cumulative sum ...",
      "kind": "testable-outcome",
      "tier": "must",
      "mention_sentences": [0, 4]
    }
  ]
}
```

| Key                 | Type        | Notes                                                       |
| ------------------- | ----------- | ----------------------------------------------------------- |
| `document_id`       | string      | Identifier for this gold set.                               |
| `propositions[].id` | string      | Non-empty, **unique** within the set.                       |
| `.text`             | string      | The atomic claim, one sentence.                             |
| `.kind`             | string      | The author's ontology label. MUST NOT reuse change ②'s six keep-categories. Descriptive only. |
| `.tier`             | string      | One of `must`, `should`, `detail`. Optional; defaults to `should`. |
| `.mention_sentences`| list[int]   | Sentence indices where the claim is asserted. **At least one** (a zero-mention proposition is not in the document). |

---

## `cases.json`

Hidden executed-oracle cases. Present only for buildable briefs. A **missing**
`cases.json` yields `()`; a **malformed** one raises.

```json
{
  "entrypoint": "running_total",
  "cases": [
    {"label": "simple", "args": [[1, 2, 3]], "expected": [1, 3, 6]},
    {"label": "empty",  "args": [[]],        "expected": []}
  ]
}
```

| Key              | Type   | Notes                                                         |
| ---------------- | ------ | ------------------------------------------------------------- |
| `entrypoint`     | string | (Optional metadata; the actual entrypoint is passed to `run_oracle`.) |
| `cases[].label`  | string | Human label for the case.                                     |
| `.args`          | list   | Positional arguments, materialised into a tuple and splatted as `entrypoint(*args)`. Each top-level element is one argument. |
| `.expected`      | any    | JSON value compared by `==` against the call result.          |

Note on `args`: it is the **argument list**, not a single argument. A function
of one list-valued argument is `"args": [[1, 2, 3]]` (outer list = arg list,
inner list = the single argument).

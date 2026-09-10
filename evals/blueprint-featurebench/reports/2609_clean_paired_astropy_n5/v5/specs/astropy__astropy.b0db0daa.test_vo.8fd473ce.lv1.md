# 2609.0001 VOTable Tree Navigation and Table Conversion Restore

**Date:** 2026-09-10
**Status:** draft
**Author:** FeatureBench

## Context

`astropy/io/votable/tree.py` implements the object model for parsed VOTable
XML documents (`VOTableFile` → `Resource` → `TableElement` → `Field`/`Param`,
plus cross-reference elements like `ParamRef`/`FieldRef` and `Values`
elements). Six members of this module are currently empty (either the
method body is missing entirely, or the method is absent from the class)
while their surrounding code, docstrings, and call sites are intact:

1. `ParamRef.get_ref` (class starts at `tree.py:2256`) — body is missing.
   The gap is between the `ref` property's deleter and the end of the
   class, roughly `tree.py:2310-2320`.
2. `TableElement.to_table` (class starts at `tree.py:2478`) — the entire
   method is missing. The gap is between `TableElement._write_binary` and
   the existing `TableElement.from_table` classmethod (`@classmethod` at
   `tree.py:3546`, `def` at `tree.py:3547`), roughly `tree.py:3498-3545`.
   `from_table` is the inverse conversion and documents the metadata keys
   (`ID`, `name`, `ref`, `ucd`, `utype`, `description`) that round-trip
   through `Table.meta`.
3. `TableElement.is_empty` — the method does not exist anywhere in the
   class. `TableElement.__init__` already sets `self._empty = False`
   (`tree.py:2518`), and `TableElement.parse` already flips it to `True`
   in two branches (around `tree.py:2822-2834`): when a caller requested a
   specific `table_number` and this table isn't it, or when a caller
   requested a specific `table_id` and this table's `ID` doesn't match.
   Only the accessor method is missing. The gap is immediately after the
   `infos` property (`tree.py:2698-2704`) and before `create_arrays`,
   roughly `tree.py:2706-2713`.

   **This is not the same thing as "has zero rows."** A table with
   `FIELD`s but no `DATA` (zero-length `array`) that was *not*
   parser-skipped must still report `is_empty() == False`. This is
   pinned down by `astropy/io/votable/tests/test_table.py:445-448
   (test_empty_table)`, which parses
   `astropy/io/votable/tests/data/empty_table.xml` — a `TABLE` with two
   `FIELD`s and no `DATA` element at all, never touched by `table_number`
   or `table_id` — and asserts `votable.get_first_table()` returns that
   table (item 5 below) and that `.to_table()` succeeds on it. An
   implementation of `is_empty` written as `len(self.array) == 0` would
   pass most other scenarios in this spec but fail `test_empty_table`,
   because it would cause `get_first_table` to skip this table and raise
   `IndexError` instead.
4. `VOTableFile.__repr__` (class starts at `tree.py:4138`) — missing
   entirely. The gap is immediately after `__init__` and before the
   `config` property, roughly `tree.py:4169-4171`. **No existing test
   asserts this method's output**, so the exact string below is this
   spec's contract, not a value independently pinned by the test suite.
   It is required to be
   `f"<VOTABLE>... {n_tables} tables ...</VOTABLE>"` where
   `n_tables = len(list(self.iter_tables()))`. The nearest in-file
   precedent for a summarizing (non-XML) `__repr__` is `Group.__repr__`
   (`tree.py:2373-2374`): `f"<GROUP>... {len(self._entries)} entries
   ...</GROUP>"` — the same `<TAG>... {n} noun ...</TAG>` shape. Other
   `__repr__` implementations in this file (`SimpleElement.__repr__`,
   `tree.py:582`; `Values.__repr__`, `tree.py:991`; `Resource.__repr__`,
   `tree.py:3858`) instead serialize to XML; `Group` is the one sibling
   that summarizes a count instead, which is why `VOTableFile` — itself
   a container of many elements, like `Group` — follows `Group`'s shape
   rather than the XML-serializing pattern.
5. `VOTableFile.get_first_table` — missing entirely. The gap is between
   `VOTableFile.iter_tables` (`tree.py:4490`) and the
   `get_table_by_id = _lookup_by_attr_factory(...)` assignment
   (`tree.py:4508`), roughly `tree.py:4498-4507`. This method is called
   directly throughout `astropy/io/votable/tests/test_table.py`, and by
   `parse_single_table` (`astropy/io/votable/table.py:167-180`, which
   defaults `table_number` to `0` and returns
   `votable.get_first_table()` — used at
   `astropy/io/votable/tests/test_converter.py:328`).
6. `VOTableFile.iter_values` — missing entirely. The gap is between the
   `get_field_by_id_or_name = _lookup_by_id_or_name_factory(...)`
   assignment (`tree.py:4569`) and the
   `get_values_by_id = _lookup_by_attr_factory(...)` assignment
   (`tree.py:4585`), roughly `tree.py:4577-4584`. This is not merely a
   convenience walker: `get_values_by_id` (built by
   `_lookup_by_attr_factory`, `tree.py:141-206`) drives `iter_values` and
   is called from `Values.ref`'s setter (`tree.py:1057`, `other =
   self._votable.get_values_by_id(ref, before=self)`) whenever a
   `<VALUES ref="...">` element resolves its shared min/max/null/options
   from an earlier `VALUES` element. The lookup walks `iter_values()` in
   document order and compares elements with `is` (identity) against
   `before`, to reject forward references (`tree.py:172-191`).
   `iter_values` must therefore yield the *same* `Values` object instances
   that are attached to each field/param (`field.values`), in document
   order — not copies, and not a re-sorted or de-duplicated set.

Item 3 (`is_empty`) and the callers listed under items 2 and 5 are not
named in the original task's interface description, but they are
verified, load-bearing dependencies of the five named members — confirmed
by reading `TableElement.__init__`/`parse`, `Values.ref`,
`_lookup_by_attr_factory`, and the actual call sites directly in this
codebase, not assumed from documentation.

**Scope boundary on lookups.** `VOTableFile.iter_fields_and_params`
(`tree.py:4539-4545`) — which both `ParamRef.get_ref` (via
`self._table._votable.iter_fields_and_params()`) and `iter_values` build
on — only walks `self.resources` (recursively through `Resource`,
`TableElement`, and `Group`). `PARAM` elements declared directly under
`<VOTABLE>` (stored in `self._params`, `tree.py:4163`, populated by
`VOTableFile._add_param`) are **not** reachable through it. All scenarios
below involving `PARAM`/`Param` lookups therefore place the relevant
`PARAM` under a `RESOURCE`, `TABLE`, or `GROUP`, never directly under
`VOTABLE`.

All six gaps sit in one file, `astropy/io/votable/tree.py`. Most are
exercised today by an existing test suite under `astropy/io/votable/tests/`
that currently fails or cannot exercise these code paths — nearly every
test in `astropy/io/votable/tests/test_table.py` calls `get_first_table()`
and/or `to_table()`. Three of the six members (`ParamRef.get_ref`,
`VOTableFile.__repr__`, `VOTableFile.iter_values`) have **no existing test
anywhere in the repository** — confirmed by grepping
`astropy/io/votable/tests/*.py` for `get_ref`, `iter_values`, and the
literal string `<VOTABLE>`, all with zero matches. `PARAMref` appears only
inside XML fixture data (e.g.
`astropy/io/votable/tests/data/regression.xml`), never exercised via
`.get_ref()` in a test. New tests for these three, and for a few edge
cases of the other three, are required — see "For the Implementing Agent"
for exactly which scenarios already have coverage and which do not.

## Motivation

`astropy.io.votable` is a public, documented API
(`astropy.io.votable.tree.TableElement.to_table`,
`VOTableFile.get_first_table`, etc.). With these six members empty:

- Any `GROUP`-scoped `PARAMref` cannot resolve its target `PARAM`
  (`ParamRef.get_ref` unusable).
- VOTable data cannot be converted to `astropy.table.Table` at all
  (`TableElement.to_table` unusable) — this breaks the single most common
  entry point into the package (`parse(...).get_first_table().to_table()`),
  the `Table.read(..., format="votable")` connector
  (`astropy/io/votable/connect.py:128`, which calls
  `table.to_table(use_names_over_ids=use_names_over_ids)`, exercised by
  `astropy/io/votable/tests/test_table.py:126,133,147,156`), and
  `TableElement.__repr__`/`__str__`/`__bytes__` (`tree.py:2550-2560`),
  which are themselves implemented in terms of `self.to_table()`.
- `VOTableFile` cannot report a first usable table (`get_first_table`),
  cannot resolve `<VALUES ref="...">` cross-references during parsing
  (`iter_values`, via `Values.ref`), and cannot produce a summary `repr`.
- `astropy/io/votable/tests/test_table.py` fails on essentially every
  test, since nearly all of them call `get_first_table()` and/or
  `to_table()`.

Restoring these six members to their documented, verified behavior, without
touching any other logic in the module, unblocks the VOTable test suite
and the package's primary read path (parse → get first table → convert to
`Table`).

## Proposed Solution

### Overview

Fill in the six gaps in `astropy/io/votable/tree.py` exactly at the
locations identified in Context, using only APIs and attributes that
already exist elsewhere in the same file (`vo_raise`, `Param`,
`iter_fields_and_params`, `self._empty`, `self.array`,
`Field.to_table_column`, etc.). No new files, no new module-level imports
beyond what a local `from astropy.table import Table` inside `to_table`
requires (the same pattern already used inside
`TableElement._parse_parquet`, `tree.py:3283`).

**Non-goal, stated once:** do not modify `_version_namespace_map`,
`_attr_list_11`/`_attr_list_12`, `_utype_in_v1_2`/`_ucd_in_v1_2`,
`VOTableFile.version`, or `VOTableFile.to_xml` — all already correct.
Scenarios S12–S13 exist solely to confirm this file's other changes did
not disturb them; the Definition of Done's corresponding checklist item
is that check's pass/fail restatement, not a separate constraint.

### Key Components

- **`ParamRef.get_ref(self)`** (`tree.py`, inside `ParamRef`, ~line 2310) —
  Scans `self._table._votable.iter_fields_and_params()`, returns the first
  item that is an instance of `Param` whose `.ID` equals `self.ref`.
  Mirrors the existing sibling `FieldRef.get_ref` (`tree.py:2245-2253`),
  which does the identical lookup for `Field` against `self.ref`. Because
  `Param` is a subclass of `Field` (`class Param(Field):`, `tree.py:1784`),
  an `isinstance(x, Field)` check would also accept a plain `Field` that
  is not a `Param` — the check must be `isinstance(x, Param)` specifically,
  and this must be verified by a test where a `FIELD` (not a `PARAM`)
  shares the same `ID` as the `PARAMref`'s `ref` (see S13). If no `Param`
  match is found, calls `vo_raise(KeyError, f"No params named
  '{self.ref}'", self._config, self._pos)` — matching `FieldRef.get_ref`'s
  error message shape (`f"No field named '{self.ref}'"`) but for params.
  Give the method a short docstring, following the style of
  `FieldRef.get_ref`'s docstring.

- **`TableElement.is_empty(self)`** (`tree.py`, inside `TableElement`,
  ~line 2706) — Returns `self._empty` (the parser-skip flag described in
  Context item 3). No parameters, no side effects, no reference to
  `self.array` or row count. Give it a one-line docstring stating that it
  reflects parser-skip status, not row count.

- **`TableElement.to_table(self, use_names_over_ids=False)`**
  (`tree.py`, inside `TableElement`, ~line 3498) — Converts this table to
  `astropy.table.Table`:
  - Builds a `meta` dict from `self.ID`, `self.name`, `self.ref`,
    `self.ucd`, `self.utype`, `self.description`, including a key only
    when the corresponding attribute is not `None`. (Whether an explicit
    empty string `""` is included or omitted is not pinned by any
    existing test or docstring — see Open Questions; either behavior is
    acceptable unless a scenario below says otherwise, and none does.)
  - Chooses column names: `field.ID` for each `field` in `self.fields`
    by default; when `use_names_over_ids=True`, uses `field.name` instead,
    de-duplicating any repeated name by appending an incrementing integer
    suffix starting at `2` (e.g. `flux`, `flux2`, `flux3`, ...) so that
    `Table` construction never fails on duplicate column names. This is
    required behavior, not optional hardening: `Field.uniqify_names`
    (`tree.py:1439-1471`, called during parsing) already guarantees every
    `field.ID` in `self.fields` is unique by the time `to_table` runs — it
    rewrites colliding `field.ID`s with an `_2`/`_3`/... suffix — but it
    deliberately leaves `field.name` untouched (it only records a
    collision-free alias in the private `field._unique_name`, which
    `to_table` does not consult). So the default `use_names_over_ids=False`
    path never needs its own dedup (names are already unique), while
    `use_names_over_ids=True` reads the still-duplicate `field.name`
    values directly and must dedup them itself. The general mechanism
    ("may cause some columns to be renamed by appending numbers to the
    end") is documented at `astropy/io/votable/connect.py:69-73`, in
    `read_table_votable`'s `use_names_over_ids` parameter docs (that
    function forwards to this one, `connect.py:128`). The exact scheme —
    start the suffix at `2`, concatenate with no separator (`flux`,
    `flux2`, `flux3`) — is this spec's contract for `to_table` (see S10);
    it is not independently pinned by an existing test today.
  - Constructs `Table(self.array, names=names, meta=meta)`. This must
    work when `self.array` has zero rows (see Context item 3).
  - For each `(name, field)` pair, fetches `table[name]` and calls
    `field.to_table_column(column)` (existing, unmodified method,
    `tree.py:1719`) to transfer unit/description/ucd/utype/format metadata
    onto the column.
  - Returns the resulting `Table`.
  - Does not copy table-level `INFO`/`LINK` elements into `table.meta`
    (only field-level metadata is transferred, via `to_table_column`).

- **`VOTableFile.__repr__(self)`** (`tree.py`, inside `VOTableFile`,
  ~line 4169) — Returns
  `f"<VOTABLE>... {n_tables} tables ...</VOTABLE>"` where
  `n_tables = len(list(self.iter_tables()))`, following the
  `Group.__repr__` convention cited in Context item 4. Counts every
  table from every resource, including zero-row ones (row count is
  irrelevant here — `iter_tables()` does not filter on `is_empty()`).

- **`VOTableFile.get_first_table(self)`** (`tree.py`, inside
  `VOTableFile`, ~line 4498) — Iterates `self.iter_tables()` in document
  order and returns the first `table` for which `not table.is_empty()`
  (parser-skip flag, per Context item 3 — a zero-row, non-skipped table
  qualifies and is returned). If the iteration completes with no
  qualifying table, raises `IndexError("No table found in VOTABLE file.")`.

- **`VOTableFile.iter_values(self)`** (`tree.py`, inside `VOTableFile`,
  ~line 4577) — A generator: `for field in self.iter_fields_and_params():
  yield field.values`. Every `FIELD`/`PARAM` element (per
  `iter_fields_and_params`, subject to the Scope boundary above) has a
  `.values` attribute (a `Values` instance) regardless of whether it
  carries real constraints (`Values.is_defaults()` may be `True`); all are
  yielded, in the same document order as `iter_fields_and_params`, as the
  exact object instances attached to each field/param (required for the
  identity comparison inside `_lookup_by_attr_factory`'s `before` check —
  see Context item 6).

### Data Flow

1. A VOTable XML document is parsed into a `VOTableFile` tree. During
   parsing, any `<VALUES ref="other-id">` element calls
   `self._votable.get_values_by_id("other-id", before=self)`, which walks
   `iter_values()` — so `iter_values` must already work correctly by the
   time parsing of a document containing `VALUES ref=` completes.
2. Caller runs `votable.get_first_table()` to obtain the first table in
   document order for which `is_empty()` is `False` (i.e., not
   parser-skipped via `table_number`/`table_id`); a table with zero rows
   but no skip flag still qualifies.
3. Caller runs `table.to_table(use_names_over_ids=...)` to obtain an
   `astropy.table.Table` whose columns carry the same data
   (`table.array`) and per-column metadata (unit, description, ucd,
   utype, format) as the original `FIELD` elements, and whose `.meta`
   carries the table-level `ID`/`name`/`ref`/`ucd`/`utype`/`description`.
   This also makes `repr(table_element)`, `str(table_element)`,
   `bytes(table_element)`, and `Table.read(fh, format="votable")` work,
   since all four delegate to `to_table()`.
4. Independently, caller runs `votable.iter_values()` to walk every
   `Values` element reachable via `iter_fields_and_params()`, e.g. to
   inspect declared min/max/null/enumeration constraints.
5. Independently, inside a `GROUP`, a `PARAMref.get_ref()` call resolves
   back to the referenced `PARAM` element anywhere reachable via
   `iter_fields_and_params()` (not restricted to elements textually
   preceding the reference — unlike `Values.ref`, `ParamRef.get_ref` has
   no `before` restriction).
6. `repr(votable)` gives a one-line table-count summary for
   interactive/debugging use, unaffected by anything else above.

### Interface Contract

```python
class ParamRef(SimpleElement, _UtypeProperty, _UcdProperty):
    def get_ref(self) -> "Param": ...
    # Raises KeyError (via vo_raise) if no PARAM with ID == self.ref is
    # reachable via self._table._votable.iter_fields_and_params() (a FIELD
    # with a matching ID does not count).

class TableElement(Element, _IDProperty, _NameProperty, _UcdProperty, _DescriptionProperty):
    def is_empty(self) -> bool: ...   # parser-skip flag, NOT "len(array) == 0"
    def to_table(self, use_names_over_ids: bool = False) -> "astropy.table.Table": ...

class VOTableFile(Element, _IDProperty, _DescriptionProperty):
    def __repr__(self) -> str: ...          # "<VOTABLE>... N tables ...</VOTABLE>"
    def get_first_table(self) -> "TableElement": ...   # raises IndexError if none
    def iter_values(self): ...              # generator of Values instances, document order, same objects as field.values
```

No other public signature in `tree.py` changes.

## Alternatives Considered

### Reimplement `to_table` via a fresh column-by-column loop instead of `Table(self.array, ...)`

Rejected: `self.array` is already a structured/masked NumPy array laid out
one column per `FIELD`, in `FIELD` order, matching `self.fields`. Passing
it directly to `Table(...)` with `names=` is the same approach the
existing, unmodified `TableElement.from_table` classmethod uses in
reverse (`np.asarray(table)` → masked array), keeping the two conversions
symmetric and consistent with the rest of the module's conventions.

### Define `is_empty` as `len(self.array) == 0`

Rejected: disproven by `astropy/io/votable/tests/test_table.py:445-448
(test_empty_table)` — see Context item 3. `is_empty` must report the
parser-skip flag (`self._empty`), not row count.

### Have `get_first_table` return the first table regardless of `is_empty()`

Rejected: `get_table_by_index` already exists as the position-based
accessor that does not filter on `is_empty()`. `get_first_table`'s
distinguishing behavior — and the reason it needs `is_empty()` at all —
is skipping parser-skipped tables so that a `table_number`/`table_id`
selective parse still returns the intended table via `get_first_table()`.

## Acceptance Scenarios

Coverage key, verified against the current test tree: **existing** = a
currently-present test already exercises this exact behavior and will
fail today (before this change) and pass after it — cited precisely by
file and line. **new** = no current test covers this; one must be added
(see "For the Implementing Agent" for placement).

### Happy Path
- **S1 — new.** Given a parsed `VOTableFile` containing a `GROUP` with a
  `PARAMref` whose `ref` matches the `ID` of a `PARAM` element defined
  under a different `RESOURCE`, appearing later in document order than
  the `PARAMref`, when `paramref.get_ref()` is called, then it returns
  that exact `Param` instance (lookup is not restricted to elements
  preceding the reference).
- **S2a — existing** (`test_table.py::test_table`, `data/regression.xml`,
  mask assertion at `test_table.py:69-70`). Given a parsed VOTable with
  one non-empty `TABLE`, when `votable.get_first_table().to_table()` is
  called, then the result is an `astropy.table.Table` whose `colnames`
  equal the fields' `ID` values (in field order) and whose mask matches
  `table_element.array.mask` column-for-column.
- **S2b — existing** (`test_table.py::test_pass_kwargs_through_table_interface`,
  `data/nonstandard_units.xml`, assertion at `test_table.py:165`:
  `t["Flux1"].unit == u.Unit("erg / (Angstrom cm2 s)")`). Given a `FIELD`
  with a `unit` attribute, when converted via `to_table()`, then the
  resulting column's `.unit` matches.
- **S2c — new.** Given a `FIELD` with `ucd` and `description` set, when
  converted via `to_table()`, then the resulting column's `.meta["ucd"]`
  and `.description` match the source `FIELD` attributes (this is the
  part of `Field.to_table_column`'s contract that S2a/S2b do not
  exercise).
- **S3 — existing** (`test_table.py::test_names_over_ids` and
  `::test_explicit_ids`, `data/names.xml`). Given the same class of
  VOTable as S2a, when `to_table(use_names_over_ids=True)` is called,
  then `colnames` equal the fields' `name` values; when called with the
  default `use_names_over_ids=False` (or explicitly `False`), `colnames`
  equal the fields' auto-generated `ID` values instead.
- **S4 — new.** `data/regression.xml` has three `TABLE`s in document
  order, none parser-skipped by a plain `parse()` call: `ID="main_table"`
  (5 data rows, at `tree.py`-parsed line ~30), an unnamed table with
  `ref="main_table"` (1 data row, ~line 270), and `ID="last_table"` with
  `ref="main_table"` (0 data rows, ~line 310). All three share the same
  field schema (a table with `ref` set inherits its FIELD descriptors
  from the referenced table, per `TableElement.parse`'s `self.ref is not
  None` branch), so field names/types cannot distinguish them — only
  `ID` and row count can. Given `votable = parse(get_pkg_data_filename("data/regression.xml"))`,
  when `votable.get_first_table()` is called, then it returns the table
  with `ID == "main_table"` and `len(table.array) == 5` — not the 1-row
  or 0-row table that follow it in document order. (`test_table.py::test_table`
  already parses this file and calls `get_first_table()`, but never
  asserts `.ID` or row count on the result, so it cannot by itself prove
  which of the three tables came back — hence this is new coverage, not
  existing.)
- **S5 — new.** Given a parsed `VOTableFile` with `N` total `TABLE`
  elements across all resources (e.g. `data/regression.xml`, which has
  more than one), when `repr(votable)` is evaluated, then it equals
  `f"<VOTABLE>... {N} tables ...</VOTABLE>"`, matching the
  `Group.__repr__` format convention (`tree.py:2373-2374`).
- **S6 — new.** Given a parsed `VOTableFile` in which one `FIELD`'s
  `VALUES` declares `min`/`max`/`null`, and a second `FIELD`'s `VALUES`
  uses `ref="<first VALUES' ID>"` to inherit those constraints, when
  `list(votable.iter_values())` is collected, then: (a) it contains one
  `Values` instance per `FIELD`/`PARAM` reachable via
  `votable.iter_fields_and_params()`, in that same order; (b) each entry
  is the identical object (`is`) referenced by its owning field's
  `.values` attribute; and (c) the second field's resolved
  `Values.min`/`max`/`null` equal the first's (proving `Values.ref`'s
  call to `get_values_by_id`, which depends on `iter_values`, resolved
  correctly during parsing).
- **S7 — new** (round-trip mechanics exist at `test_table.py:72-73`, but
  that test never inspects `table.meta` — only field `datatype`/
  `arraysize` after round-trip — so the `meta` behavior itself is
  unverified today). Given a `TableElement` with `ID`, `name`, `ucd`,
  `utype`, and `description` all set to non-empty, non-`None` values,
  when `to_table()` is called, then `table.meta` contains exactly those
  five keys with matching values (no key for the unset `ref`), and
  passing that `Table` to `VOTableFile.from_table(table)` and then
  `.get_first_table()` yields a `TableElement` whose corresponding
  attributes match the originals.

### Edge Cases
- **S8 — existing** (`test_table.py::test_empty_table`,
  `data/empty_table.xml`; the "zero-row `Table` with correct columns"
  half of the assertion is new — the existing test only calls
  `.to_table()` without inspecting the result). Given a `VOTableFile`
  whose only `TABLE` has `FIELD`s but no `DATA` element (zero-length
  `array`) and was never targeted by a `table_number`/`table_id` skip,
  when `votable.get_first_table()` is called, then it returns that table
  (does **not** raise `IndexError`), and `.to_table()` on it succeeds and
  returns a zero-row `Table` with the correct columns.
- **S9 — new.** `table_number` counts every `<TABLE>` in document order
  across all resources (the shared `config["_current_table_number"]`
  counter is incremented once per `TableElement.parse()` call,
  `tree.py:2821-2828`, regardless of resource nesting), so
  `table_number=2` against `data/regression.xml` (the three tables from
  S4's Given) marks the first two (`main_table`, the unnamed 1-row table)
  as parser-skipped and leaves only the third, `ID="last_table"`, as
  non-empty. Given
  `votable = parse(get_pkg_data_filename("data/regression.xml"), table_number=2)`,
  when `votable.get_first_table()` is called, then it returns the table
  with `ID == "last_table"` — not `main_table`, which appears first in
  document order but was parser-skipped.
- **S10 — new.** Given a VOTable whose `FIELD` elements have `name`
  values that collide (e.g., two fields both named `"flux"`), when
  `to_table(use_names_over_ids=True)` is called, then the resulting
  `Table` has as many columns as there were fields, with no
  `ValueError`/duplicate-name failure, and the second and later
  colliding columns are renamed by appending an incrementing suffix
  (e.g. `flux`, `flux2`).
- **S11 — new.** Given a `PARAMref` whose `ref` matches the `ID` of both
  a `FIELD` and a distinct `PARAM`, with the `FIELD` placed so it is
  yielded by `iter_fields_and_params()` *before* the `PARAM` — e.g. the
  `FIELD` in a `TABLE` under one `RESOURCE`, and the `PARAM` in a
  `GROUP`/`TABLE` under a second `RESOURCE` that appears later (recall
  `TableElement.iter_fields_and_params`, `tree.py:3572-3578`, yields
  `self.params` before `self.all_fields` within one table, and
  `Resource.iter_fields_and_params`, `tree.py:4097-4106`, yields a
  resource's own `params` before its `tables`, so a same-container
  placement risks the `PARAM` being seen first regardless of the bug this
  scenario targets) — when `paramref.get_ref()` is called, then it
  returns the `Param`, not the `Field`. This is the scenario that
  specifically guards against an `isinstance(x, Field)` mutation (which
  would wrongly accept the earlier-seen `Field`, since `Param` subclasses
  `Field`) in place of the required `isinstance(x, Param)`; ordering the
  `FIELD` first is what makes the mutation observable.
- **S12 — existing, non-regression** (`test_tree.py::test_votable_tag`,
  lines 296-318). Given `VOTableFile` instances constructed with
  `version` set to each of `"1.1"`, `"1.2"`, `"1.3"`, `"1.4"`, `"1.5"`,
  when `to_xml(...)` is called, then the emitted `VOTABLE` tag's `xmlns`
  and `xsi:schemaLocation`/`xsi:noNamespaceSchemaLocation` attributes
  match `VOTableFile._version_namespace_map[version]` exactly as before
  this change. Adding `__repr__`/`get_first_table`/`iter_values` must not
  change this.
- **S13 — new.** `ParamRef.__init__` (`tree.py:2274-2294`) branches on
  `config.get("version_1_2_or_later")`, a key set by
  `VOTableFile._get_version_checks()` (`tree.py:4281-4289`) — it is not
  derived automatically from a `VOTableFile` instance just being nearby,
  so the test must pass the votable's own `config` (e.g.
  `ParamRef(table, ref="x", ucd="meta.code", config=votable.config)`),
  not an empty/default `config`. Given a `VOTableFile(version="1.1")`
  versus a `VOTableFile(version="1.2")`, and a `ParamRef` constructed
  with `ucd`/`utype` keyword arguments and `config=` set to that
  votable's `.config`, when constructed, then (per the pre-existing,
  unmodified `_attr_list_11`/`_attr_list_12`/`_utype_in_v1_2`/`_ucd_in_v1_2`
  logic already present in `ParamRef.__init__`) the version-1.1 votable's
  config produces an "unknown attribute" warning for `ucd`/`utype` while
  the version-1.2 votable's config accepts them silently. Adding
  `get_ref` must not change this — no test in the repository currently
  constructs a `ParamRef` directly, so this is new coverage, not a
  regression check against an existing test.

### Error Scenarios
- **S14 — new.** Given a `ParamRef` whose `ref` does not match the `ID`
  of any `Param` reachable via `iter_fields_and_params()` (including when
  it matches only a `Field`'s `ID` — see S11 for the positive case),
  when `paramref.get_ref()` is called, then it raises `KeyError`.
- **S15a — new.** Given a `VOTableFile` with zero `RESOURCE`/`TABLE`
  elements at all, when `votable.get_first_table()` is called, then it
  raises `IndexError`. (This alone does not exercise the `is_empty()`
  filter — an implementation that ignored `is_empty()` entirely would
  also raise `IndexError` here, since `iter_tables()` yields nothing.
  S15b is what actually exercises the filter.)
- **S15b — new.** Given a `VOTableFile` with at least one `TABLE`, parsed
  such that every `TABLE` present has `is_empty() == True` (e.g.
  `parse(get_pkg_data_filename("data/regression.xml"), table_id="does-not-exist")`,
  which marks every table skipped since none match the requested `ID`),
  when `votable.get_first_table()` is called, then it raises
  `IndexError`. Both S15a and S15b are required; an implementation must
  not satisfy only the non-discriminating S15a case.

## Open Questions

- [ ] Does `TableElement.to_table()`'s `meta` dict include a key whose
      source attribute (`ID`/`name`/`ref`/`ucd`/`utype`/`description`) is
      an explicit empty string `""`, or only keys whose value is
      genuinely non-`None`-and-non-empty? No existing test or docstring
      in the repository pins this. `TableElement.from_table` accepts `""`
      on the way back (`tree.py:3553-3559`) without objection, so neither
      choice breaks the inverse conversion. Resolve by implementer
      judgment (the "not None" reading in Key Components is the
      lower-risk default, matching `from_table`'s own `if val is not
      None` checks); no acceptance scenario in this spec depends on the
      answer.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*. A green suite that passes for
> the wrong reason does not satisfy this contract — `/verify` will hunt
> for vacuous tests by asking, of each behavior, "what is the smallest
> change that breaks this, and would any test catch it?"

Fill in the six gaps in `astropy/io/votable/tree.py` (see
Context/Key Components for exact locations and signatures).

Scenarios marked **existing** above are already present in the repository
and will start passing once the gaps are filled — do not duplicate them.
Scenarios marked **new** (S1, S2c, S4, S5, S6, S7, S9, S10, S11, S13, S14,
S15a, S15b, and the unverified half of S8) have no current test that
covers them. Add a minimal, focused test for each, placed by convention:

- S1, S11, S14 (`ParamRef.get_ref`) and S13 (`ParamRef` version behavior)
  → `astropy/io/votable/tests/test_tree.py`. Construct the `VOTableFile`/
  `Resource`/`TableElement`/`Group`/`Param`/`Field`/`ParamRef` tree
  directly in Python (as `test_tree.py`'s existing tests such as
  `test_make_Fields` do), rather than adding new XML fixtures.
- S2c (ucd/description transfer) → `astropy/io/votable/tests/test_table.py`,
  alongside `test_table` or `test_pass_kwargs_through_table_interface`.
- S4 (`get_first_table` returns the first table in document order among
  several non-skipped tables) and S9 (`table_number` skip) →
  `astropy/io/votable/tests/test_table.py`, both against
  `data/regression.xml` (see S4/S9 for the exact `ID`/row-count
  discriminators; that fixture's later tables share the first table's
  field schema, so field names cannot be used to tell them apart).
- S5 (`__repr__`) → `astropy/io/votable/tests/test_tree.py`, parsing
  `data/regression.xml` and asserting the exact string against
  `len(list(votable.iter_tables()))`.
- S6 (`iter_values`) → `astropy/io/votable/tests/test_tree.py`, near the
  existing `VALUES`-related tests (e.g. `test_votable_values_empty_min_max`,
  `test_min_max_with_arrays`) — reuse their fixture style for a
  `<VALUES ref="...">` document.
- S7 (`to_table` meta + round-trip) → `astropy/io/votable/tests/test_table.py`,
  alongside `test_table`'s existing round-trip block (`test_table.py:72-73`).
- S10 (duplicate names) → `astropy/io/votable/tests/test_table.py`,
  alongside `test_names_over_ids`. Building the fixture by parsing XML
  with two same-named `FIELD`s will trigger `W33` ("Column name '{}'
  renamed to '{}' to ensure uniqueness", raised by `Field.uniqify_names`,
  `tree.py:1471`) during parsing itself — this is expected and unrelated
  to the bug this scenario targets (`uniqify_names` renames the internal
  `field._unique_name`, not `field.name`, so `to_table`'s `field.name`
  values are still duplicated when `use_names_over_ids=True` reads them);
  wrap the parse in `pytest.warns(W33)` or an equivalent filter rather
  than treating the warning as a test failure.
- S15a and S15b (`IndexError`) → `astropy/io/votable/tests/test_table.py`;
  S15a needs no fixture (construct an empty `VOTableFile()` directly),
  S15b uses `parse(get_pkg_data_filename("data/regression.xml"), table_id="does-not-exist")`.
- S8's zero-row-`Table` assertion → extend
  `astropy/io/votable/tests/test_table.py::test_empty_table` in place
  (it already parses the right fixture and calls the right method; it
  just doesn't check the result yet).

After filling the gaps and adding the tests above, run
`pytest astropy/io/votable/` — it must be fully green. (Note: this spec
does not add a second, out-of-package acceptance gate. `complex_table()`
in `astropy/table/table_helpers.py:86-100` looks like an out-of-package
caller of `get_first_table()`/`to_table()`, but it has zero callers
anywhere in the repository and calls `parse(..., pedantic=False)` —
`parse()`'s signature, `astropy/io/votable/table.py:31-42`, has no
`pedantic` parameter and no `**kwargs`, so this function raises
`TypeError` if ever invoked, independent of this spec's changes. It is
dead code; do not fix it and do not gate on it — that would be a change
outside `astropy/io/votable/tree.py` and outside this spec's scope.)

Do not modify any code outside `astropy/io/votable/tree.py` (test files
under `astropy/io/votable/tests/` are the one exception, for the new
tests listed above). Do not change any method signature, default value,
or behavior other than filling in the six identified gaps.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] `pytest astropy/io/votable/` is green.
- [ ] Every acceptance scenario (S1–S14, S15a, S15b) maps to at least one
      test — pre-existing (per the Coverage key above) or newly added.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
      the smallest break of its behavior. In particular: swapping
      `is_empty()` for `len(self.array) == 0` must fail S8; an
      implementation of `get_first_table` that ignores `is_empty()`
      entirely must fail S15b (S15a alone would not catch it, since it
      has no tables to filter — both are required); using `field.name`
      unconditionally in `to_table` must fail S3; matching `Field`
      instead of `Param` in `ParamRef.get_ref` must fail S11 (not
      necessarily S1, since `Param` is itself a `Field` — S11 is the
      scenario that specifically orders a `Field` before the `Param` to
      distinguish the two); yielding copies instead of the original
      `Values` objects from `iter_values` must fail S6(b).
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
      first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, missing or
      stale docstrings) remain in the six restored members.
- [ ] `_version_namespace_map`, `_attr_list_11`/`_attr_list_12`,
      `_utype_in_v1_2`/`_ucd_in_v1_2`, and `VOTableFile.to_xml`'s
      namespace/schema output are unchanged from before this change
      (S12, S13 still pass).

## Trade-offs and Limitations

- Variable-length array `FIELD`s may not round-trip identically through
  `to_table()` → `Table` → `TableElement.from_table()` due to differences
  in how `astropy.table` and VOTable represent variable-length arrays.
  This is a pre-existing, documented limitation of the conversion, not a
  regression introduced here, and is not in scope to fix.
- `to_table()` does not copy table-level `INFO`/`LINK` elements into
  `table.meta`; only field-level metadata (via `Field.to_table_column`)
  is transferred. This matches the documented contract and is not a gap.
- `PARAM` elements declared directly under `<VOTABLE>` are outside the
  reach of `iter_fields_and_params()`, and therefore outside the reach of
  `ParamRef.get_ref` and `iter_values` as well. This is existing,
  unmodified behavior (see Scope boundary in Context) and is not changed
  or fixed by this spec.

## References

- `astropy/io/votable/tree.py` — the file under change.
- `astropy/io/votable/tests/test_table.py`,
  `astropy/io/votable/tests/test_tree.py` — existing acceptance tests
  (see Coverage key in Acceptance Scenarios for exact test names and
  lines).
- `astropy/io/votable/tests/data/empty_table.xml` — fixture proving
  `is_empty()` ≠ "zero rows" (Context item 3, S8).
- `astropy/io/votable/connect.py:128` — out-of-package caller of
  `to_table()` via `Table.read(..., format="votable")`, exercised by
  `test_table.py:126,133,147,156`.
- `TableElement.from_table` (`tree.py:3546-3547`) and
  `Field.to_table_column` (`tree.py:1719`) — existing, unmodified sibling
  implementations that define the metadata-key and column-transfer
  conventions `to_table` must follow.
- `FieldRef.get_ref` (`tree.py:2245`) — existing, unmodified sibling
  implementation that defines the lookup/error pattern `ParamRef.get_ref`
  must follow.
- `Group.__repr__` (`tree.py:2373-2374`) and `_lookup_by_attr_factory`
  (`tree.py:141-206`) / `Values.ref` (`tree.py:1057`) — existing,
  unmodified implementations that establish, respectively, the `__repr__`
  string format and the document-order/identity contract `iter_values`
  must satisfy.

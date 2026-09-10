# 2609.0001 VOTable Tree Navigation and Table Conversion

**Date:** 2026-09-10
**Status:** draft
**Author:** EP Lin

## Context

`astropy/io/votable/tree.py` models a parsed VOTable document as a tree of
elements (`VOTableFile` → `Resource` → `TableElement` → `Field`/`Param`/
`Group`/`ParamRef`/`FieldRef`/`Values`, etc.). Six methods on this tree are
currently deleted entirely — five are the public navigation/conversion
interface this spec restores, the sixth (`TableElement.is_empty`) is a
private helper one of the five calls (see Motivation) — `def`
line, docstring, and body all gone, leaving only blank lines where each
method used to be (not `pass`, not `NotImplementedError`: nothing):

- `ParamRef.get_ref` — deleted, leaving blank lines at `tree.py:2311-2320`
  (class starts `tree.py:2256`). `grep -n "def get_ref"` on the working
  tree returns **only** the intact `FieldRef.get_ref` at `tree.py:2245` —
  `ParamRef`'s own `get_ref` produces no grep hit at all, since the `def`
  line itself is gone.
- `TableElement.is_empty` — deleted, blank at `tree.py:2705-2713` (class
  starts `tree.py:2478`).
- `TableElement.to_table` — deleted, blank at `tree.py:3498-3545`.
- `VOTableFile.__repr__` — deleted, blank at `tree.py:4167-4171` (class
  starts `tree.py:4138`; line 4172 is the next member, `@property` for
  `config`).
- `VOTableFile.get_first_table` — deleted, blank at `tree.py:4498-4507`.
- `VOTableFile.iter_values` — deleted, blank at `tree.py:4576-4584`.

The working tree also has other blank method bodies in this same file that
are **not** individually targeted by this spec but sit inside the same
class or the same file: `Values._parse_minmax` (blank at `tree.py:1191-1219`,
between `Values.parse` and `Values.is_defaults`), `CooSys.reference_frames`
(blank at `tree.py:1946-1970`, between the `system` deleter and the
`equinox` property), and `MivotBlock.__str__` (blank right after
`MivotBlock.__init__` at `tree.py:3663`). None of the six target methods or
their prerequisites call these three, so no acceptance scenario below
exercises them — but see §Proposed Solution → Alternatives for why
restoring them anyway, as a side effect of the recommended restoration
mechanism, is accepted rather than treated as scope creep.

The working tree additionally has uncommitted deletions, relative to
`git HEAD`, in files `tree.py` depends on transitively: `astropy/utils/xml/
check.py`, `astropy/utils/xml/iterparser.py`, `astropy/io/votable/
exceptions.py`, `astropy/io/votable/ucd.py`, `astropy/table/table.py`, and
`astropy/utils/data_info.py`. `git HEAD` in this repository holds a
complete, working reference implementation of all of these files — this is
not a hypothetical upstream project, it is the commit this working tree is
checked out from. Run `git diff HEAD -- <path>` or `git show HEAD:<path>`
to see the exact removed code for any file mentioned in this spec.

**Grading scope, decided here because no one is available to ask:** this
spec targets exactly the interface documented below (`ParamRef.get_ref`,
`TableElement.is_empty`, `TableElement.to_table`, `VOTableFile.__repr__`,
`VOTableFile.get_first_table`, `VOTableFile.iter_values`), matching the
five-method public interface plus the one private-dependency method
(`is_empty`) needed to implement it correctly. `astropy/io/votable/tests/
test_vo.py` is deleted in this working tree (`git status` shows `D`); this
spec does not assume it will be restored or graded against, and does not
size its prerequisite list to it. If it turns out grading does restore and
run that file, treat this spec's prerequisite list as a floor, not a
ceiling — extend it using the same "trace the call graph, don't guess"
method demonstrated in §Proposed Solution, rather than reopening this
question.

## Motivation

The six target methods must be restored so that:

1. `ParamRef` (used inside `GROUP` elements) can resolve to the `PARAM` it
   refers to.
2. A parsed `TableElement` can be converted into an `astropy.table.Table`
   for downstream analysis — this is the primary VOTable → astropy.table
   bridge and is exercised anywhere a caller does `table_element.to_table()`
   or `repr(table_element)` / `str(table_element)` / `bytes(table_element)`
   (all three call `to_table()` — see `tree.py:2550-2557`, itself intact).
3. `VOTableFile` callers can get a one-line summary (`repr`), grab "the"
   table when there's conceptually only one, and walk every `VALUES`
   element in the document (used for domain/range introspection).

`TableElement.is_empty()` is in scope even though it isn't one of the five
originally-named methods because `VOTableFile.get_first_table()` calls
`table.is_empty()` on every candidate table to decide whether to skip it —
confirmed by reading `TableElement.__init__` (sets `self._empty = False`)
and the parser's two call sites that set `self._empty = True` inside
`TableElement.parse` (guarding on the `table_number`/`table_id` filters
used by `astropy.io.votable.parse(..., table_number=N)`). Without
`is_empty`, `get_first_table` cannot be implemented as specified.

Restoring only the six tree.py methods is not sufficient to make them
*testable*: nearly every constructor in `tree.py` that this spec touches
sets a `ucd`, `utype`, `xtype`, `ID`, `ref`, or `name` attribute, and those
setters unconditionally call helper functions that are **also deleted**,
in other files. If those helpers are not restored first, constructing a
`Field`, `Param`, `ParamRef`, or `TableElement` at all raises `NameError`/
`AttributeError` before any of the six target methods can run — see
"Required Prerequisites" below. Every dependency listed there was
confirmed by tracing the actual call graph (`git diff` + `grep` against
this working tree), not inferred from the file names.

## Proposed Solution

### Overview

Restore the six listed methods on `ParamRef`, `TableElement`, and
`VOTableFile` in `astropy/io/votable/tree.py` to match the documented
interface (below) exactly, and — as a strict prerequisite — restore the
helper functions elsewhere in the dependency graph that these methods (and
the object construction they depend on) call at runtime. Every restored
symbol must match the reference implementation at `git HEAD` for that
file; this is a restoration task, not a redesign, so no behavior should be
"improved" relative to `HEAD` (e.g. do not change `get_ref`'s lookup scope,
do not add a singular/plural branch to `__repr__`'s table count).

### Key Components

- **`ParamRef.get_ref`** — searches `self._table._votable.iter_fields_and_params()`
  for a `Param` whose `ID` equals `self.ref`; raises `KeyError` (via
  `vo_raise`) if none matches. `self._table` is whatever object
  constructed this `ParamRef` — a `TableElement` if the owning `GROUP` is
  declared inside a `TABLE`, or a `Resource`/`VOTableFile` if the `GROUP`
  is declared at the resource or file level (`Group.__init__` just stores
  whatever `table` argument its caller passed — see `Group._add_paramref`
  at `tree.py:2406-2408`, and the four call sites that construct `Group`:
  `TableElement._add_group`, `Resource._add_group`,
  `VOTableFile._add_group`, and `Group._add_group` itself for nested
  `GROUP`s, which passes through its own `self._table` — so a `PARAMref`
  inside a nested `GROUP` inherits whatever scope the outermost enclosing
  `GROUP` was declared in). `._votable` is an attribute only `TableElement`
  defines (set in `__init__`, pointing at the owning `VOTableFile`); neither
  `Resource` nor `VOTableFile` itself has a `._votable` attribute at the
  time `get_ref()` runs on a fully-parsed tree, so `get_ref()` only works
  when the `PARAMref`'s `GROUP` is nested inside a `TABLE`. This is an
  existing constraint of the method being restored, not something to fix.
- **`TableElement.to_table`** — builds an `astropy.table.Table` from
  `self.array` and `self.fields`, carrying over table-level metadata and
  per-column metadata via `Field.to_table_column` (already implemented,
  intact, at `tree.py:1719-1749`).
- **`TableElement.is_empty`** — trivial accessor for `self._empty`,
  required by `get_first_table`.
- **`VOTableFile.__repr__`** — one-line summary reporting the total number
  of tables in the file.
- **`VOTableFile.get_first_table`** — returns the first table in document
  order for which `is_empty()` is `False`.
- **`VOTableFile.iter_values`** — recursively yields the `Values` element
  attached to every `FIELD`/`PARAM` element reachable from
  `self.iter_fields_and_params()`. For `VOTableFile`, that iterator walks
  `self.resources` only (`tree.py:4539-4545`, intact) — file-level
  `self.params`/`self.groups` and any `GROUP`s declared directly under a
  `RESOURCE` (as opposed to under a `TABLE`) are **not** visited, because
  `Resource.iter_fields_and_params` (`tree.py:4097-4106`, intact) yields
  `self.params` and each table's fields/params but does not recurse into
  `self.groups`; only `TableElement.iter_fields_and_params`
  (`tree.py:3572-3580`, intact) recurses into `Group.iter_fields_and_params`.
  So `iter_values()` only sees `VALUES` belonging to: (a) fields/params
  directly on a `TABLE`, and (b) params inside `GROUP`s that are themselves
  inside a `TABLE`.
- **Required Prerequisites** (table below) — helper functions in other
  files that the setters/constructors exercised by the six methods above
  call unconditionally.

### Data Flow

1. A `VOTableFile` is either parsed from an XML source
   (`astropy.io.votable.parse(source)`, where `source` is a path, file
   object, or readable stream) or built up programmatically; either path
   constructs `Resource`, `TableElement`, `Field`, `Param`, `Group`,
   `ParamRef`, `FieldRef`, and `Values` objects, whose attribute setters
   call into `xmlutil` (`check_id`, `fix_id`, `check_token`),
   `tree.check_string` / `tree.check_astroyear`, and `ucd.check_ucd`.
2. `ParamRef.get_ref()` walks up to the owning `VOTableFile` via
   `self._table._votable` and calls `iter_fields_and_params()` to find the
   matching `Param` (only reachable when `self._table` is a `TableElement`
   — see Key Components above).
3. `TableElement.to_table()` reads `self.array` (a masked `numpy` array
   populated during parsing or construction) and `self.fields`, constructs
   an `astropy.table.Table` (which itself goes through `Table.__init__` →
   `_init_from_ndarray` and column `.info` assignment), and layers on
   metadata via `Field.to_table_column`.
4. `VOTableFile.get_first_table()` calls `self.iter_tables()` (intact) and
   filters with the newly restored `is_empty()`.
5. `VOTableFile.iter_values()` composes with the already-intact
   `iter_fields_and_params()`.

### Interface Contract

Signatures are exact — do not rename, reorder parameters, or change
return/raise types. The docstrings below are **this spec's paraphrase of
required observable behavior**, not a transcription of `HEAD`'s wording —
`HEAD`'s actual docstrings differ (e.g. `HEAD`'s `to_table` docstring uses
a `.. warning::` directive and has no `Returns`/`Warns` sections; `HEAD`'s
`get_first_table` docstring is one sentence; `HEAD`'s `VOTableFile.__repr__`
has no docstring at all). Either is acceptable: restore `HEAD`'s docstring
text verbatim (e.g. via the whole-file `git checkout` in §Alternatives), or
write new docstring text, as long as it is accurate to the implementation
and does not contradict it — DoD item 5's "no stale docstrings" means "no
docstring that describes behavior the code doesn't have," not "must match
this spec's wording." Of the behavioral content below, the `meta` key
enumeration is part of the tested contract (S2, S3c); the variable-length
array clause is a documented limitation only — no scenario tests it (see
Trade-offs) — so do not add a docstring assertion for it:

```python
class ParamRef(SimpleElement, _UtypeProperty, _UcdProperty):
    def get_ref(self):
        """
        Lookup the :class:`Param` instance that this :class:`ParamRef`
        references. ...

        Returns
        -------
        param : :class:`Param`

        Raises
        ------
        KeyError
            If no PARAM element with the specified ID is found in the VOTable.
        """

class TableElement(Element, _IDProperty, _NameProperty, _UcdProperty, _DescriptionProperty):
    def is_empty(self):
        """Returns True if this table doesn't contain any real data."""

    def to_table(self, use_names_over_ids=False):
        """
        Convert this VO Table to an `astropy.table.Table` instance.

        Parameters
        ----------
        use_names_over_ids : bool, optional
            When `True` use the ``name`` attributes of columns as the names
            of columns in the `astropy.table.Table` instance. Since names
            are not guaranteed to be unique, this may cause some columns to
            be renamed by appending numbers to the end. Otherwise (default),
            use the ID attributes as the column names.

        Returns
        -------
        table : `astropy.table.Table`
            `table.meta` contains only the following keys from this
            `TableElement`, each present only when the corresponding
            attribute is not `None`: `ID`, `name`, `ref`, `ucd`, `utype`,
            `description`. Table-level `INFO`/`LINK` elements are never
            copied into `table.meta` — only field-level `LINK`/unit/
            description/ucd metadata, transferred per-column by
            `Field.to_table_column`.

        Warns
        -----
        Variable-length array fields may not be restored identically when
        round-tripping through the `astropy.table.Table` instance, due to
        differences in how `astropy.table` and VOTable represent such data.
        """

class VOTableFile(Element, _IDProperty, _DescriptionProperty):
    def __repr__(self):
        """Returns '<VOTABLE>... N tables ...</VOTABLE>', N = total table count."""

    def get_first_table(self):
        """
        Returns
        -------
        table : `~astropy.io.votable.tree.TableElement`
            The first table, in document order, for which `is_empty()` is
            `False`.

        Raises
        ------
        IndexError
            If no non-empty table is found in the VOTable file.
        """

    def iter_values(self):
        """Recursively iterate over all VALUES_ elements in the VOTABLE_ file."""
```

**Required Prerequisites** — verified by reading the setter/constructor
call graph the six methods (and the object construction they sit on top
of) go through. Restore each to match `git show HEAD:<path>` exactly
before implementing the six methods above; without them, none of the six
can be exercised by any test that constructs or parses a VOTable object:

| File | Symbol(s) | Why it blocks this feature |
|---|---|---|
| `astropy/io/votable/tree.py` | `check_astroyear`, `check_string` (module-level, blank at `tree.py:295-343`, under the `# ATTRIBUTE CHECKERS` comment) | `_UtypeProperty.utype` and `_XtypeProperty.xtype` setters call `check_string` unconditionally (`tree.py:429,459`); `CooSys.equinox`/`.epoch` setters call `check_astroyear`. Every `Field`/`Param`/`ParamRef`/`FieldRef`/`Group`/`TableElement` construction sets `utype`, so none of them can be built without this. |
| `astropy/utils/xml/check.py` | `check_id`, `fix_id`, `check_token`, `check_anyuri` | Wrapped by `astropy/io/votable/xmlutil.py` (`xmlutil.check_id`, `xmlutil.fix_id`, `xmlutil.check_token`); called by `ID`/`ref`/`name` setters on nearly every tree.py element, including `ParamRef.ref` and `TableElement.ID`/`.name`. |
| `astropy/utils/xml/iterparser.py` | `_convert_to_fd_or_read_function` | Referenced unconditionally at `iterparser.py:156` inside `get_xml_iterator`; every `astropy.io.votable.parse(source)` call — file path, file object, or in-memory XML — raises `NameError` without it. Needed for any test that builds its fixture by parsing XML text/files rather than constructing objects in memory (this spec's S5 requires it — see below). |
| `astropy/io/votable/exceptions.py` | `_format_message` (module-level), `_suppressed_warning` (module-level) | `VOWarning.__init__` (`exceptions.py:231`) calls `_format_message` for every `W*`/`E*` warning/exception instantiation; `vo_warn` (`exceptions.py:156`) calls `_suppressed_warning`. Both fire during ordinary element construction through `warn_or_raise`/`warn_unknown_attrs`, which nearly every setter and `parse()` call path in `tree.py` uses — including paths exercised while building the acceptance-scenario fixtures (§Acceptance Scenarios). (`vo_raise`, used for the `KeyError` in `ParamRef.get_ref` and the bare `IndexError` in `VOTableFile.get_first_table`, does not itself call either symbol — but construction of the surrounding tree does.) |
| `astropy/io/votable/ucd.py` | `UCDWords.__init__`, `UCDWords.is_primary`, `UCDWords.is_secondary`, `UCDWords.normalize_capitalization` | `check_ucd()` (intact) instantiates `UCDWords()` and calls these methods; `_UcdProperty.ucd` setter calls `check_ucd()`. `ParamRef`, `TableElement`, and every `Field`/`Param` mix in `_UcdProperty`. |
| `astropy/table/table.py` | `Table._init_from_ndarray`, `Table._base_repr_` | `TableElement.to_table()` constructs `Table(self.array, names=names, meta=meta)` from a masked ndarray, which routes through `_init_from_ndarray`; `TableElement.__repr__`/`__str__`/`__bytes__` (intact, `tree.py:2550-2557`) format the `to_table()` result via `Table.__repr__`/`__str__`, which call `_base_repr_` (exercised by S13 below). |
| `astropy/utils/data_info.py` | `BaseColumnInfo.__set__` | Column `.info` assignment during `Table` construction from an ndarray goes through this descriptor's `__set__`. |

Before restoring, confirm each symbol is still absent
(`grep -n "def <symbol>" <file>`) and confirm the reference body via
`git show HEAD:<path>`; do not guess at a body.

**Conditional Prerequisites** — plausibly on some path through `tree.py`,
but not required by any scenario below. Verify reachability before
restoring; do not restore speculatively:

- `astropy/units/format/base.py: _did_you_mean_units, _validate_unit, _invalid_unit_error_message, _decompose_to_known_units` and `astropy/utils/misc.py: did_you_mean, strip_accents` — `astropy/units/format/vounit.py`'s `_get_unit` (`vounit.py:113-126`) routes *any* unit string not already in the VOUnit registry through `_invalid_unit_error_message` → `_did_you_mean_units`, which are deleted. This is why every fixture in this spec that sets a `unit` uses a standard, VOUnit-registry string (e.g. `"m"`, per S2) — using a non-standard or misspelled unit string in any fixture turns this row from Conditional into Required. Keep it that way; do not restore this row speculatively.
- `astropy/utils/xml/validate.py: validate_schema` and `astropy/io/votable/converters.py: BitArray._splitter_lax` — used by `votable.validate()` and lax-mode "bit"-arraysize parsing respectively. No scenario below exercises either.
- `tree.py`'s `Values._parse_minmax`, `CooSys.reference_frames`, `MivotBlock.__str__` (see §Context) — not on the call graph of any scenario below, **provided** no fixture's `<VALUES>` element declares `<MIN>`/`<MAX>` (both setters call the deleted `_parse_minmax`, at `tree.py:1084` and `tree.py:1117`). Several files under `astropy/io/votable/tests/data/` (e.g. `regression.xml`, `gemini.xml`, `mivot_annotated_table.xml`) do declare `<MIN>`/`<MAX>` — prefer a small hand-written XML string or in-memory construction for S5/S12's fixtures rather than pointing at those files directly, unless `tree.py` is restored whole-file (§Alternatives), which brings `_parse_minmax` back too.

Recall from §Alternatives: because each Required Prerequisite file's *only* difference from `HEAD` is blanked bodies, whole-file `git checkout HEAD -- <path>` is an equally valid restoration mechanism to hand-restoring individual symbols — it simply restores a superset. The Conditional list above exists to say which symbols are *not confirmed necessary*, not to forbid restoring the file they live in if you choose the whole-file mechanism for that file.

## Alternatives Considered

### Reimplement `to_table` with a different metadata mapping

Considered carrying over additional metadata (e.g. table-level `INFO`/
`LINK` elements) into `table.meta`. Rejected: `to_table`'s contract (see
Interface Contract, and S2/S3c below) is explicit that table-level `INFO`/
`LINK` are *not* copied, only field-level `LINK` metadata via
`Field.to_table_column`. Matching `HEAD` exactly avoids introducing
behavior the contract doesn't describe.

### Restore `tree.py` via whole-file `git checkout HEAD -- <path>`

`tree.py`'s only difference from `HEAD` is blanked-out function bodies —
confirmed via `git diff HEAD -- astropy/io/votable/tree.py` (every hunk is
a deletion replaced by an equal number of blank lines, no additions, no
edits to surrounding code). `git checkout HEAD -- astropy/io/votable/
tree.py` is therefore equivalent to, and less error-prone than,
hand-transcribing each of the six target methods, and it also restores the
three untargeted blank bodies noted in §Context (`Values._parse_minmax`,
`CooSys.reference_frames`, `MivotBlock.__str__`) as an accepted side
effect — restoring the whole target file, rather than six hand-picked
methods within it, is in scope.

Apply the same reasoning **per file** to the Required Prerequisites table
above (each of those files, too, differs from `HEAD` only by blanked
bodies) — but do **not** run `git checkout HEAD --` against
`astropy/units/format/base.py`, `astropy/utils/misc.py`, `astropy/utils/
xml/validate.py`, or `astropy/io/votable/converters.py` unless a concrete
failing test demands it: those files' deletions are on the Conditional
Prerequisites list, not confirmed necessary, and are out of this spec's
scope until demonstrated otherwise.

## Acceptance Scenarios

Full scenario ID set (15 total, referenced below as a group by this exact
list — `S1–S13` is not a contiguous range): **S1, S2, S3a, S3b, S3c, S4,
S5, S6, S13, S7, S8, S9, S10, S11, S12**. `S13` is numbered out of document
order — it was appended after the rest were drafted — but is grouped under
Happy Path, next to `S6`, because that is where it logically belongs
(`repr(TableElement)`, a happy-path check).

### Happy Path

- **S1:** Given a `VOTableFile` → `RESOURCE` → `TABLE` (`TableElement`)
  containing a `GROUP` with a `PARAMref` whose `ref` equals the `ID` of a
  `PARAM` element declared directly on that same `TABLE` (a sibling `PARAM`
  outside the `GROUP`), when `paramref.get_ref()` is called, then it
  returns that exact `Param` instance (`is` identity, not just equal
  attributes).
- **S2:** Given a `TableElement` (with `ID="t1"`, no `ref`, no `utype`, a
  `ucd`, and a `description`) with two `FIELD`s — one with `unit="m"`
  (a standard VOUnit-registry unit; do not use a non-standard string here,
  see the Conditional Prerequisites note on unit validation) and a `ucd`,
  one with neither — and populated `array` data, when
  `table_element.to_table()` is called, then the result is an
  `astropy.table.Table` with: the same number of rows/columns; column
  values equal to `table_element.array`'s data; column names equal to the
  fields' `ID`s; `table.meta == {"ID": "t1", "ucd": <that ucd>, "description": <that description>}`
  exactly (no `name`/`ref`/`utype` keys, since those attributes are
  `None`/unset on this table); and the unit/ucd-bearing column carrying
  `.unit` and `.meta["ucd"]` as set by `Field.to_table_column`.
- **S3a:** Given the same `TableElement` as S2, when
  `table_element.to_table(use_names_over_ids=True)` is called, then column
  names equal the fields' `name` attributes instead of their `ID`s.
- **S3b (de-duplication):** Given a `TableElement` whose two `FIELD`s have
  distinct `ID`s but share `name="x"`, when
  `to_table(use_names_over_ids=True)` is called, then the resulting column
  names are exactly `["x", "x2"]`, in field order.
- **S3c (INFO/LINK exclusion):** Given a `TableElement` with one `INFO`
  child and one table-level `LINK` child (in addition to its `FIELD`s),
  when `to_table()` is called, then `table.meta` contains none of that
  `INFO`/`LINK` data — only the keys enumerated in the Interface Contract.
- **S4:** Given a `VOTableFile` with two `RESOURCE`s containing 1 and 2
  tables respectively (3 tables total, all non-empty), when
  `repr(votable_file)` is called, then it returns exactly
  `"<VOTABLE>... 3 tables ...</VOTABLE>"`.
- **S5:** Given a two-table XML fixture parsed with
  `astropy.io.votable.parse(source, table_number=1)` (which causes the
  parser to mark every table except index 1 as empty, per
  `TableElement.parse`'s `table_number`/`table_id` filtering — do not set
  `table._empty` directly in the test), when
  `votable_file.get_first_table()` is called, then it returns the table at
  index 1, and `votable_file.get_table_by_index(1).is_empty()` is `False`
  while `votable_file.get_table_by_index(0).is_empty()` is `True`.
- **S6:** Given a `VOTableFile` → `RESOURCE` → `TABLE` with exactly two
  `FIELD`s (`f1`, `f2`, each getting a default `Values` in `__init__` since
  neither declares an explicit `<VALUES>` child) and no `PARAM`s or
  `GROUP`s anywhere in the file, when `list(votable_file.iter_values())`
  is called, then it returns a list of exactly 2 items, and that list
  equals `[f1.values, f2.values]` by identity, in that order (field
  declaration order, per `TableElement.iter_fields_and_params`'s
  `self.params` then `self.all_fields` then per-group order).
- **S13:** Given the S2 `TableElement`, when `repr(table_element)` is
  called, then the result is a string starting with `"<VOTable"` (per
  `tree.py:2550-2554`, which computes `repr(self.to_table())` and replaces
  the leading `<Table` with `<VOTable`) and containing both fields' column
  names.

### Edge Cases

- **S7:** Given a `TableElement` with zero `FIELD`s and `array =
  ma.array([])`, when `to_table()` is called, then it returns an
  `astropy.table.Table` with 0 columns and 0 rows, without raising.
- **S8:** Given a `VOTableFile` → `RESOURCE` → `TABLE` A containing a
  `GROUP` with a `PARAM` whose `ID="shared"`, and a *different* `TABLE` B
  in the same file (same or a different `RESOURCE`) containing a `GROUP`
  with a `PARAMref` whose `ref="shared"`, when
  `paramref.get_ref()` is called on the `ParamRef` in table B, then it
  still returns table A's `Param` — the lookup is not restricted to table
  B's own subtree, to elements textually preceding the reference, or to
  elements outside `GROUP`s, provided the `GROUP` is table-scoped (see
  Key Components; a `PARAM` inside a `RESOURCE`-level or file-level
  `GROUP` is **not** reachable this way, and no scenario relies on that
  path).
- **S9:** Given a `VOTableFile` with zero `RESOURCE`s (hence zero tables),
  when `repr(votable_file)` is called, then it returns
  `"<VOTABLE>... 0 tables ...</VOTABLE>"` (no special-casing of the count).
- **S10:** Given a `VOTableFile` → `RESOURCE` → `TABLE` with two `FIELD`s,
  `f1` declaring an explicit `<VALUES ID="v1"/>` child (no `min`/`max`/
  `null`, so `f1.values.is_defaults()` is still `True` despite being
  explicit — do not give it `<MIN>`/`<MAX>`, which routes through the
  deleted `Values._parse_minmax`, see the Conditional Prerequisites note
  below) and `f2` declaring none (so `f2.values` is the implicit default
  created by `Field.__init__`), when `list(votable_file.iter_values())` is
  called, then it returns `[f1.values, f2.values]` — both the explicit and
  the implicit default `Values` are yielded; neither "is a default" nor
  "was never written in the XML" filters either one out. (This is a
  distinct check from S6: S6 establishes count/order/identity across two
  *implicit* defaults; S10 establishes that an *explicit but default-valued*
  `VALUES` is treated the same as an implicit one.)

### Error Scenarios

- **S11:** Given a `ParamRef` (in a table-scoped `GROUP`, per Key
  Components) whose `ref` does not match any `Param`'s `ID` anywhere in
  the owning `VOTableFile`, when `get_ref()` is called, then it raises
  `KeyError`.
- **S12:** Given a `VOTableFile` where every table is empty (via
  `table_number` parsing as in S5, applied so no table survives, or zero
  `RESOURCE`s), when `get_first_table()` is called, then it raises
  `IndexError`.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*. A green suite that passes for
> the wrong reason does not satisfy this contract — `/verify` will hunt for
> vacuous tests by asking, of each behavior, "what is the smallest change
> that breaks this, and would any test catch it?"

Start by restoring the Required Prerequisites table's symbols (verify
absence first, then match `git show HEAD:<path>` exactly, preferably via
per-file `git checkout HEAD -- <path>` as justified in §Alternatives) —
none of the six target methods can be exercised end-to-end until basic
`Field`/`Param`/`TableElement` construction and `astropy.io.votable.parse()`
work. Then implement the six methods to the exact interface contract
above. Only touch the Conditional Prerequisites' files if a specific test
in your suite fails because of them, and note in your commit message which
ones you had to restore and why.

Implement however you work best — blueprint does not prescribe order,
cadence, or commit structure. Only the result is checked. Write tests to
the project's conventions (this codebase uses `pytest`; `astropy/io/
votable/tests/data/` holds existing VOTable XML fixtures usable as a
starting point for S5's file-based scenario) and to these principles (the
same ones `/verify` scores against — see `references/test-desiderata.md`
and `references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects (the
  returned `Table`'s columns/meta, the `repr()` string, the raised
  exception type), not internals; the suite must survive refactoring. In
  particular, S5's precondition must come from parsing with
  `table_number=`, never from assigning `table._empty` directly.
- **Every test can fail** — no copy-pasted expected values, no asserting a
  constant, no tautologies (AP-2, AP-4). S4/S9's expected literal
  (`"...3 tables..."`, `"...0 tables..."`) encodes the fixture's *designed*
  table count — chosen when you build the fixture, before calling
  `repr()` — not a value computed by calling `iter_tables()`, `repr()`, or
  any other production code path and asserting the result equals itself.
- **Deterministic, isolated, readable** — build VOTable fixtures
  in-memory or from small XML strings/files local to the test; no
  cross-test state, AAA structure with inline setup.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] `pytest` is green for the new tests covering all 15 scenario IDs
  listed at the top of §Acceptance Scenarios, and for
  `astropy/io/votable/tests/test_table.py` and
  `astropy/io/votable/tests/test_converter.py` — both already call
  `to_table()`/`get_first_table()`/`is_empty()` today and currently fail
  for exactly the reasons this spec addresses. Failures caused by the
  Conditional Prerequisites' files (left untouched per this spec's scope
  decision) do not block this checkbox.
- [ ] Every one of the 15 acceptance-scenario IDs maps to at least one test.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
  the smallest break of its behavior (thought-mutation), e.g. removing the
  `is_empty()` filter in `get_first_table`, or swapping `ID`s for `name`s
  in `to_table`'s default column-naming, must break its corresponding
  test.
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
  first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale
  docstrings) in `tree.py` or any Required Prerequisite file touched.
- [ ] Constructing/parsing a representative VOTable (with at least one
  `Field` carrying `utype`, `ucd`, and `unit`) succeeds without
  `NameError`/`AttributeError` originating from a prerequisite helper.

## Trade-offs and Limitations

- This spec deliberately does not attempt to restore every deletion found
  in the working tree — only what the six target methods' call graph
  requires (Required Prerequisites), plus an explicit, verify-before-use
  list of what might also be required (Conditional Prerequisites).
  Unrelated deleted functions elsewhere in the repository are out of
  scope; restoring them is neither required nor forbidden by this spec,
  but should be justified by a failing test, not done speculatively.
- Variable-length array fields are documented (per the Interface Contract's
  `Warns` clause) as not necessarily round-tripping identically through
  `to_table()` — this is an accepted, pre-existing limitation of the
  original implementation, not a defect to fix here, and deliberately has
  no acceptance scenario: "may not be restored identically" isn't a
  precise enough claim to write a non-vacuous test against.
- `iter_values()`'s scope is bounded by `iter_fields_and_params()`'s scope
  (table-level fields/params and table-scoped group params only, per Key
  Components); this spec preserves that limitation rather than widening
  it, per the restoration-not-redesign principle.
- `ParamRef.get_ref()`'s reachability is similarly bounded to
  table-scoped `GROUP`s (see Key Components and S8); a `PARAMref` inside a
  `RESOURCE`- or file-level `GROUP` will raise `AttributeError` when
  `get_ref()` is called, because `Resource`/`VOTableFile` have no
  `._votable` attribute. This is the restored `HEAD` behavior, not a new
  bug — no scenario here exercises that path, and none should be added
  that asserts it "should" work differently.

## References

- Reference implementation for every restored symbol: `git show HEAD:<path>`
  in this repository (e.g. `git show HEAD:astropy/io/votable/tree.py`).
- `astropy/io/votable/tree.py` — `Field.to_table_column` (`tree.py:1719-1749`,
  intact) and `TableElement.from_table` (`tree.py:3547-3570`, intact) as
  already-working examples of the Field↔Column and Table↔TableElement
  metadata-mapping conventions this spec's `to_table` must follow.

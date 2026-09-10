# 2609.0001 VOTable Tree Navigation and Table Conversion

**Date:** 2026-09-10
**Status:** draft
**Author:** FeatureBench

## Context

`astropy/io/votable/tree.py` implements the object tree that
`astropy.io.votable.parse()` builds from a VOTable XML document
(`VOTableFile` → `Resource` → `TableElement` → `Field`/`Param`/`Group`/
`Values`, etc.). Five navigation and conversion methods that the rest of
the module already depends on have been removed **in their entirety** —
the `def` line, the docstring, and the body are all gone, leaving runs of
blank lines at each site. All line numbers below were verified against
the working tree on 2026-09-10:

| Missing definition | Blank slot in `tree.py` | Anchors immediately around it |
| --- | --- | --- |
| `ParamRef.get_ref` | 2309-2320 | `ParamRef.ref` deleter ends 2308; `class Group` starts 2321 |
| `TableElement.to_table` | 3496-3545 | `TableElement._write_binary` (3452-3495); `from_table` at 3546 |
| `VOTableFile.__repr__` | 4167-4171 | `VOTableFile.__init__` (4149-4166); `config` property at 4173 |
| `VOTableFile.get_first_table` | 4497-4507 | `iter_tables` (4490-4496); `get_table_by_id` at 4508 |
| `VOTableFile.iter_values` | 4576-4584 | `get_field_by_id_or_name` (4569-4575); `get_values_by_id` at 4585 |

Because the docstrings were removed along with the bodies, **this spec —
not the source file — is the only surviving statement of what these
methods must do.** The implementing agent must write fresh docstrings
that match the behavior specified here.

Every line number in this spec is a *pre-implementation* position. Filling
the blank slots in place keeps the surrounding anchors stable; if the
implementation shifts them anyway, that is not a spec staleness defect —
the named symbols, not the offsets, are the contract.

Supporting facts, all verified in the current file:

- `ParamRef` (class at `tree.py:2256`) has no `get_ref`. Its sibling
  `FieldRef.get_ref` (`tree.py:2245-2253`) is fully implemented and
  resolves a `FIELDref`'s `ref` XML ID to a `Field` by scanning
  `self._table._votable.iter_fields_and_params()` (`FieldRef` is only ever
  constructed with a `TableElement` as `self._table` — see
  `Group._add_fieldref` at `tree.py:2402` — so `self._table._votable`
  reaches the owning `VOTableFile`). `ParamRef` is constructed identically
  (`Group._add_paramref` at `tree.py:2406` passes `self._table` straight
  through).
- `TableElement.__repr__`, `__bytes__`, and `__str__`
  (`tree.py:2550-2560`) already call `self.to_table()`; `__repr__`
  additionally rewrites a leading `"<Table"` into `"<VOTable"`. So
  `repr()`, `str()`, and `bytes()` on any `TableElement` raise
  `AttributeError` until `to_table` exists.
- The inverse conversion, `TableElement.from_table` (classmethod
  `tree.py:3546-3570`, immediately before `iter_fields_and_params` at
  `tree.py:3572`), already exists and defines the round-trip attribute
  names (`ID`, `name`, `ref`, `ucd`, `utype` read from `table.meta` at
  3553-3556, `description` at 3558-3559; one `Field` per column via
  `Field.from_table_column`).
- `VOTableFile.get_values_by_id` (`tree.py:4585-4594`) is built by
  `_lookup_by_attr_factory("ID", True, "iter_values", "VALUES", ...)`,
  which calls `self.iter_values()` by name — so `get_values_by_id`
  raises `AttributeError: 'VOTableFile' object has no attribute
  'iter_values'` whenever it is called, on every VOTable, regardless of
  content.
- `astropy/io/votable/connect.py:128` (`read_table_votable`) calls
  `table.to_table(use_names_over_ids=use_names_over_ids)`, so the whole
  `Table.read(..., format="votable")` entry point is dead as well.
- `astropy/io/votable/tests/test_table.py` exercises the to-be-restored
  surface extensively: `test_table` (line 61, `get_first_table()` +
  `to_table()` + mask comparison + `from_table` round trip),
  `test_read_from_tilde_path` (line 120), `test_names_over_ids`
  (lines 168-192, pins exact `colnames` for `use_names_over_ids=True`),
  `test_explicit_ids` (lines 195-219, pins exact `colnames` for
  `use_names_over_ids=False`), `test_empty_table` (line 445),
  `test_binary2_masked_strings` (line 466).

### Blocking prerequisites: other definitions stripped from the same file

Three more definitions were stripped from `tree.py` and *are referenced by
live code*, so **no scenario in this spec can pass until they are
restored**. They are in scope for this work (they live in `tree.py`, like
everything else here):

1. **`check_astroyear` and `check_string`** — module-level functions in
   the "ATTRIBUTE CHECKERS" section (blank slot 295-341, between
   `_attach_default_config` ending at 290 and `resolve_id` at 342).
   Neither is defined nor imported (the import block at lines 1-97 does
   not name them), yet both are called by live code: `check_string` at
   `tree.py:434` (`_XtypeProperty.xtype` setter), `:460`
   (`_UtypeProperty.utype` setter), `:636`, `:857`, `:867` (`Info`), and
   `check_astroyear` at `:1981`/`:1998` (`CooSys.equinox`/`epoch`
   setters). `Field` inherits both `_XtypeProperty` and `_UtypeProperty`
   (class declaration `tree.py:1299-1306`), so constructing any `Field`
   — and therefore parsing any document containing a `FIELD` — currently
   raises `NameError: name 'check_string' is not defined`. `test_tree.py`
   calls both functions directly (`test_check_astroyear_fail` line 27,
   `test_string_fail` line 34).
2. **`CooSys.reference_frames`** — blank slot 1948-1969, between the
   `system` deleter (1945-1947) and the `equinox` property (1970). The
   `system` setter reads `self.reference_frames` (`tree.py:1941`) and the
   `system` docstring points at it (`:1935`); only the cache attribute
   `_reference_frames = None` survives (`:1875`). Until it is restored,
   every `CooSys(...)` construction — including `parse()` of any file
   containing a `COOSYS` element, e.g. `tests/data/regression.xml:10` —
   raises `AttributeError`.

The practical consequence: the current failure mode of `parse()` is
`NameError`/`AttributeError` from these prerequisites, *before* any of
the five methods above is ever reached. Restore the prerequisites first,
then the five methods.

## Motivation

`astropy.io.votable` is currently unusable end to end. Parsing itself
dies in the stripped attribute checkers (`NameError` on `check_string`
for any `FIELD`, `AttributeError` on `CooSys.reference_frames` for any
`COOSYS`), and even with parsing repaired the module cannot serve its two
primary purposes: converting a parsed VOTable into an
`astropy.table.Table` (the documented entry point — `docs/io/votable/
table_element.rst:27-29,90` and `docs/io/votable/index.rst:238-245` both
show `votable.get_first_table().to_table(...)`, and
`connect.py:128` routes `Table.read(format="votable")` through it), and
navigating `PARAMref`/`VALUES` structures inside `GROUP` elements. Any
caller that parses a VOTable file and calls `get_first_table()`,
`to_table()`, `repr()`/`str()` on a table, or `get_values_by_id()` hits an
`AttributeError`. Restoring these definitions — modelled on the surviving
sibling implementations (`FieldRef.get_ref`, `TableElement.from_table`,
`Resource`/`TableElement.iter_fields_and_params`, `Field.to_table_column`)
and on the behavior specified below — unblocks the existing test suites in
`astropy/io/votable/tests/test_table.py`, `test_tree.py`, and
`test_coosys.py` without changing any other public behavior.

## Proposed Solution

### Overview

Restore, directly in `astropy/io/votable/tree.py`, the two blocking
module-level checkers plus `CooSys.reference_frames`, and then the five
missing methods (`ParamRef.get_ref`, `TableElement.to_table`,
`VOTableFile.__repr__`, `VOTableFile.get_first_table`,
`VOTableFile.iter_values`), using the already-present sibling
implementations in the same file as the pattern to follow for style,
error handling, and traversal. Each restored definition gets a fresh
docstring describing the behavior specified here (the original docstrings
were deleted with the bodies). No new files, no new public classes, no
new public names beyond the eight listed here, and no changes to the
parsing (`parse`) or serialization (`to_xml`) method bodies.
Do not modify `ParamRef._attr_list_11`, `_attr_list_12`,
`_utype_in_v1_2`, `_ucd_in_v1_2` (`tree.py:2268-2272`) or
`VOTableFile._version_namespace_map` (`tree.py:4292-4340`) — these
version-dependent attribute/namespace tables already exist and are
exercised by `astropy/io/votable/tests/test_tree.py::test_namespace_warning`
and `astropy/io/votable/tests/test_schema_versions.py`; leave them
byte-for-byte intact.

### Key Components

#### Blocking prerequisites

- **`check_string(string, attr_name, config=None, pos=None)`** (module
  level, in the blank "ATTRIBUTE CHECKERS" slot at `tree.py:295-341`) —
  accepts `None` and any `str` silently; for a non-text value (e.g. an
  `int`) it reports `W08` through `warn_or_raise(W08, W08, attr_name,
  config, pos)`, so that a `{"verify": "exception"}` config raises `W08`
  (message template `"'{}' must be a str or bytes object"`,
  `exceptions.py:458-467`) and the default config only warns. Call sites
  pass the attribute label as the second argument (`tree.py:434`, `:460`,
  `:636`, `:857`, `:867`); `test_tree.py:34-37` calls
  `tree.check_string(42, "foo", config)` and expects `W08` to be raised.
  Whether `bytes` is accepted is deliberately left unconstrained — the
  `W08` message names both `str` and `bytes`, and no caller or test in
  the repository passes `bytes`.
- **`check_astroyear(year, field, config=None, pos=None)`** (same slot) —
  accepts `None` and any string matching the astroYear pattern
  `^[JB]?[0-9]+([.][0-9]*)?$` (`exceptions.py:437-455`) silently; a
  string that fails the pattern reports `W07` through
  `warn_or_raise(W07, W07, (field, year), config, pos)`, so a
  `{"verify": "exception"}` config raises `W07`. Call sites pass the
  attribute label as `field` (`tree.py:1981`, `:1998`); `test_tree.py:27-31`
  calls `tree.check_astroyear("X2100", field, config)` and expects `W07`.
  Behavior for non-`None`, non-string arguments is unconstrained (no
  caller passes them).
- **`CooSys.reference_frames`** (inside `CooSys`, blank slot
  `tree.py:1948-1969`) — an attribute readable off both the class and an
  instance (`self.reference_frames` is read by the `system` setter at
  `tree.py:1941`, and the `system` docstring cross-references
  `CooSys.reference_frames` at `:1935`) that yields the accepted `COOSYS`
  `system` values. It must contain every term key of the bundled IVOA
  refframe vocabulary `astropy/io/votable/data/ivoa-vocalubary_refframe-
  v20220222.json` — `EQUATORIAL`, `geo_app`, `ICRS`, `FK4`, `FK5`,
  `eq_FK4`, `eq_FK5`, `ECLIPTIC`, `ecl_FK4`, `ecl_FK5`,
  `GENERIC_GALACTIC`, `GALACTIC_I`, `GALACTIC`, `galactic`,
  `SUPER_GALACTIC`, `supergalactic`, `AZ_EL`, `BODY`, `UNKNOWN`, `xy`,
  `barycentric` (this superset also covers the legacy DTD list in
  `exceptions.py:1446-1459` and `data/VOTable.dtd:156-157`) — and must
  not contain arbitrary strings such as `"InvalidSystem"`. The bar is set
  by the live tests, which run under `filterwarnings = ["error", ...]`
  (`pyproject.toml:243-247`), so an `E16` for any accepted term fails a
  test: `test_coosys.py::test_coosys_to_astropy_frame_and_time` constructs
  `CooSys(system=...)` for `ICRS`, `FK4`, `FK5`, `eq_FK4`, `eq_FK5`,
  `GALACTIC`, `galactic`, `SUPER_GALACTIC`, `supergalactic`, `AZ_EL`, and
  `test_coosys_to_astropy_frame_error` constructs `CooSys(system="BODY")`.
  How the values are obtained and cached (the surviving
  `_reference_frames = None` slot at `tree.py:1875` suggests lazy loading
  from that JSON file) is not constrained by this spec.

#### The five missing methods

- **`ParamRef.get_ref`** (`tree.py`, inside the `ParamRef` class starting
  at line 2256, in the blank slot 2309-2320) — a zero-argument instance
  method. Iterates
  `self._table._votable.iter_fields_and_params()` (mirroring
  `FieldRef.get_ref` at `tree.py:2245`) and returns the first element that
  is both an instance of `Param` and whose `ID` attribute equals
  `self.ref`. If no such element exists, raises `KeyError` via
  `vo_raise(KeyError, f"No PARAM named '{self.ref}'", self._config,
  self._pos)` — the same `vo_raise`/message-shape convention
  `FieldRef.get_ref` uses for its own not-found case.

- **`TableElement.to_table`** (`tree.py`, inside the `TableElement` class
  starting at line 2478, in the blank slot 3496-3545 immediately before
  `from_table` at 3546) — instance method
  `to_table(self, use_names_over_ids=False)` returning a masked
  `astropy.table.Table` (masked so that `astropy_table.mask[colname]` is
  usable, as `test_table.py:69-70` requires). The table has exactly one
  column per entry in `self.fields`, in that order (not
  `self.all_fields` — `fields` is the selected/active column list whose
  members are the ones represented in `self.array`'s structured dtype;
  see `create_arrays`, `tree.py:2732-2759`). Each column's values and
  mask are those of the corresponding `self.array` field. `create_arrays`
  builds each dtype entry as `(x._unique_name, x.ID)` when the two differ
  (`tree.py:2755-2759`), and numpy reads a 2-tuple field spec as
  `(title, name)` — so `self.array.dtype.names` are the field `ID`s and
  `_unique_name` is the title. Both `self.array[field.ID]` and positional
  construction from `self.array` therefore read the right column.
  Column naming:
  - `use_names_over_ids=False` (default): the column name is `field.ID`.
    `test_explicit_ids` (test_table.py:195-219) pins this for
    `data/names.xml` (`col1` … `col17`).
  - `use_names_over_ids=True`: the column name is `field.name`
    (`Field.__init__` guarantees `name` is non-`None`, defaulting it to
    `field.ID` at `tree.py:1390-1397`). `test_names_over_ids`
    (test_table.py:168-192) pins this for `data/names.xml`.
    Names are not unique in VOTable, so collisions are resolved by
    appending numbers to the end, per `docs/io/votable/index.rst:241-245`:
    processing fields in order, the first field to claim a given name
    keeps it unchanged, and each subsequent field whose name is already
    taken receives that name with the smallest positive integer appended
    directly (`name1`, then `name2`, …) that is not yet in use. The
    resulting name list must be collision-free so `Table` construction
    never raises on duplicate column names.

  For each column, call `field.to_table_column(column)`
  (`tree.py:1719`, already implemented) to transfer unit, description,
  ucd, width/precision/utype/xtype, and VALUES-derived metadata. After
  building the `Table`, populate `table.meta` with `self.ID`, `self.name`,
  `self.ref`, `self.ucd`, `self.utype`, and `self.description`, each only
  when the corresponding attribute is not `None` — mirror the *inverse*
  of `from_table`'s `for key in ["ID", "name", "ref", "ucd", "utype"]:
  ...; if "description" in table.meta: ...` block (`tree.py:3552-3559`)
  so `to_table` followed by `from_table` followed by `to_table` again
  round-trips these six attributes. Do not copy table-level `INFO` or
  `LINK` elements into `table.meta` (only field-level link metadata,
  which `Field.to_table_column` already handles, is transferred).

- **`VOTableFile.__repr__`** (`tree.py`, inside the `VOTableFile` class
  starting at line 4138, in the blank slot 4167-4171) — returns
  `f"<VOTABLE>... {n} tables ...</VOTABLE>"` where `n = len(list(self.iter_tables()))`
  (`iter_tables` already exists at `tree.py:4490` and recursively flattens
  every table across every nested `Resource`). Mirrors the existing
  `Group.__repr__` (`tree.py:2373`, `f"<GROUP>... {len(self._entries)}
  entries ...</GROUP>"`) and `Resource`/`TableElement` `__repr__` patterns
  already in the file.

- **`VOTableFile.get_first_table`** (`tree.py`, in the blank slot
  4497-4507, between `iter_tables` and `get_table_by_id`) — iterates
  `self.iter_tables()` in document order and returns the first
  `TableElement` for which `table._empty` is falsy. `TableElement._empty`
  is initialised to `False` in `TableElement.__init__` (`tree.py:2518`)
  and set to `True` during `TableElement.parse` (`tree.py:2828` for the
  `table_number` filter, `:2834` for the `table_id` filter — the latter
  is currently unreachable via `parse()`, which does not put `table_id`
  into `config`; see `table.py:144-153`); that flag is the only
  surviving signal for "skipped during parsing", because the public
  accessor `TableElement.is_empty()` was stripped from this file too and
  is referenced by nothing in the package (see Open Questions). If
  `iter_tables()` yields no non-empty table,
  raises `IndexError` — mirror the message style of
  `get_table_by_index`'s `raise IndexError(f"No table at index {idx:d}
  found in VOTABLE file.")` (`tree.py:4537`), e.g. `raise
  IndexError("No table found in VOTABLE file.")`.

- **`VOTableFile.iter_values`** (`tree.py`, in the blank slot 4576-4584,
  immediately before `get_values_by_id` at `tree.py:4585`, which already
  depends on it by name) — a generator that iterates
  `self.iter_fields_and_params()` (`tree.py:4539`, already implemented
  and recursive over resources -> tables/params -> groups) and, for each
  yielded `Field`/`Param`, yields its `.values` attribute (a `Values`
  instance — every `Field`/`Param` always has a non-`None` `.values` per
  `Field.__init__`, which constructs a default `Values` when none is
  parsed from XML). `Values` instances for which `is_defaults()`
  (`tree.py:1220`) returns `True` must **not** be filtered out: the
  generator yields exactly one `Values` per element yielded by
  `iter_fields_and_params()`, in the same order, so that the two
  iterations stay positionally aligned and no `VALUES` element can be
  hidden from `get_values_by_id`.

### Data Flow

1. `parse()` builds a `VOTableFile` tree — unchanged in structure, but it
   only runs at all once `check_string`, `check_astroyear`, and
   `CooSys.reference_frames` are restored (today it raises `NameError` on
   the first `FIELD` and `AttributeError` on the first `COOSYS`).
2. A caller does one of:
   - `repr(table)` / `str(table)` / `bytes(table)` on a `TableElement` →
     now succeeds because `TableElement.to_table()` exists.
   - `repr(votable)` on a `VOTableFile` → counts `iter_tables()` and
     returns the `<VOTABLE>... N tables ...</VOTABLE>` summary.
   - `votable.get_first_table().to_table()` → walks `iter_tables()` to
     find the first non-`_empty` `TableElement`, then converts it to an
     `astropy.table.Table` field-by-field.
   - `votable.get_values_by_id("some_id")` → now succeeds because the
     `iter_values` generator it depends on exists.
   - `paramref_instance.get_ref()` inside a `GROUP` → resolves back to
     the referenced `Param`.
3. No data is written back to the XML tree by any of these five methods;
   they are all pure read/derive operations.

### Interface Contract

```python
# tree.py — module level, "ATTRIBUTE CHECKERS" section (blank slot 295-341)
def check_astroyear(year, field, config=None, pos=None):
    """Report W07 unless `year` is None or a string matching
    ^[JB]?[0-9]+([.][0-9]*)?$.  `field` is the attribute label used in
    the message."""

def check_string(string, attr_name, config=None, pos=None):
    """Report W08 unless `string` is None or a str.
    `attr_name` is the attribute label used in the message."""

# tree.py — CooSys (class starts at line 1865; blank slot 1948-1969)
class CooSys(SimpleElement):
    reference_frames  # readable on class and instance; membership test
                      # used by the `system` setter (tree.py:1941)

# tree.py — ParamRef (class starts at line 2256)
class ParamRef(SimpleElement, _UtypeProperty, _UcdProperty):
    def get_ref(self) -> "Param":
        """Return the Param whose ID equals self.ref.
        Raises KeyError (via vo_raise) if none is found among
        self._table._votable.iter_fields_and_params()."""

# tree.py — TableElement (class starts at line 2478)
class TableElement(Element, _IDProperty, _NameProperty, _UcdProperty, _DescriptionProperty):
    def to_table(self, use_names_over_ids: bool = False) -> "astropy.table.Table":
        """Convert this TABLE element to an astropy.table.Table,
        transferring column data/mask, units, descriptions, ucd, and
        ID/name/ref/ucd/utype/description into table.meta."""

# tree.py — VOTableFile (class starts at line 4138)
class VOTableFile(Element, _IDProperty, _DescriptionProperty):
    def __repr__(self) -> str:
        """f"<VOTABLE>... {n} tables ...</VOTABLE>" with n = total tables."""

    def get_first_table(self) -> "TableElement":
        """First non-empty TableElement in document order.
        Raises IndexError if none exists."""

    def iter_values(self):
        """Generator yielding every Values instance reachable from
        every FIELD_/PARAM_ element in the file, including
        VALUES that are_defaults()."""
```

The docstrings that once declared these signatures were deleted along
with the bodies, so the signatures above are pinned instead by the
surviving call sites, which must all work unmodified once the definitions
are added:

- `check_string(...)` — `tree.py:434`, `:460`, `:636`, `:857`, `:867`;
  `test_tree.py:37`.
- `check_astroyear(...)` — `tree.py:1981`, `:1998`; `test_tree.py:31`.
- `CooSys.reference_frames` — `tree.py:1941`.
- `TableElement.to_table(use_names_over_ids=...)` —
  `TableElement.__repr__`/`__str__`/`__bytes__` (`tree.py:2550-2560`),
  `connect.py:128`, `test_table.py` (many).
- `VOTableFile.iter_values` — `_lookup_by_attr_factory("ID", True,
  "iter_values", "VALUES", ...)` in `get_values_by_id`
  (`tree.py:4585-4594`).
- `VOTableFile.get_first_table()` — `test_table.py` (many),
  `docs/io/votable/table_element.rst:29`.

## Acceptance Scenarios

### Happy Path

- **S1:** Given a `VOTableFile` produced by `parse(get_pkg_data_filename("data/regression.xml"))` (used already in `astropy/io/votable/tests/test_table.py::test_table`), when `votable.get_first_table().to_table()` is called, then it returns an `astropy.table.Table` whose `colnames` equal `list(table.array.dtype.names)` (the fields' `ID`s, in `table.fields` order), and for every one of those names, `astropy_table[name]` equals `table.array[name]` value-for-value and `astropy_table.mask[name]` equals `table.array.mask[name]` element-for-element.
- **S2:** Given `parse(get_pkg_data_filename("data/names.xml"))`, when `get_first_table().to_table(use_names_over_ids=True)` is called, then the returned `Table`'s `colnames` are the fields' `name` attributes (`["Name", "GLON", "GLAT", "RAdeg", "DEdeg", "Jmag", "Hmag", "Kmag", "G3.6mag", "G4.5mag", "G5.8mag", "G8.0mag", "4.5mag", "8.0mag", "Emag", "24mag", "f_Name"]`), whereas the same call with `use_names_over_ids=False` yields the fields' `ID`s (`["col1", ..., "col17"]`) — i.e. the flag selects between the two naming sources, and the two results differ.
- **S3:** Given the `astropy.table.Table` produced by `TableElement.to_table()` for a `TableElement` with non-`None` `ID`/`name`/`ref`/`ucd`/`utype`/`description`, when it is round-tripped via `tree.VOTableFile.from_table(astropy_table).get_first_table().to_table()`, then the second `Table`'s `meta` contains the same values for each of those keys as the first `Table`'s `meta` (and `meta` omits keys whose source attribute was `None`).
- **S4:** Given a `GROUP` element containing a `PARAMref` whose `ref` matches the `ID` of a `PARAM` element elsewhere in the same `VOTableFile` (constructed directly via the `tree` API or parsed from XML containing `<PARAMref ref="...">`), when `paramref.get_ref()` is called, then it returns that exact `Param` instance.
- **S5:** Given a `VOTableFile` containing both a `FIELD` with an explicit `<VALUES>` block and a `FIELD`/`PARAM` without one (so its `Values.is_defaults()` is `True`), when `list(votable.iter_values())` is called, then the result is `[f.values for f in votable.iter_fields_and_params()]` — same length, same order, same object identities — with the defaulted `Values` included, not filtered out.
- **S6:** Given a `VOTableFile` built in-test with two `TableElement`s in one `Resource` plus a third in a nested `Resource` (the shape used by `test_tree.py::test_mivot_order`), when `repr(votable)` is called, then the returned string is exactly `"<VOTABLE>... 3 tables ...</VOTABLE>"`; and given a `VOTableFile()` with no resources, `repr(votable)` is exactly `"<VOTABLE>... 0 tables ...</VOTABLE>"` — i.e. the count is the total across nested resources, taken from `iter_tables()`, not the number of top-level resources.
- **S7:** Given a `VOTableFile` with a `VALUES` element with a known `ID` (e.g. from `data/binary2_masked_strings.xml` or an inline-constructed table), when `votable.get_values_by_id(that_id)` is called, then it returns the matching `Values` instance without raising `AttributeError`.
- **S13:** Given any parsed `TableElement`, when `repr(table)`, `str(table)`, and `bytes(table)` are called, then none of them raises, `repr(table)` starts with `"<VOTable"` (`tree.py:2550-2554` rewrites the leading `"<Table"` produced by `repr(Table)`), and `str(table)` equals `str(table.to_table())`.
- **S14:** Given a `FIELD` carrying `unit`, `<DESCRIPTION>`, and `ucd` attributes (e.g. `data/regression.xml`, or a small inline VOTable), when the enclosing table is converted with `to_table()`, then the corresponding column's `unit` and `description` equal the `FIELD`'s values and `column.meta["ucd"]` equals the `FIELD`'s `ucd` — i.e. `Field.to_table_column` was applied to every column.

### Edge Cases

- **S8:** Given `parse(get_pkg_data_filename("data/regression.xml"), table_number=1)` — that file holds three `TABLE`s (`main_table` at index 0, a `ref="main_table"` table at index 1, `last_table` at index 2) — so that tables 0 and 2 are marked `_empty` and table 1 is not (`VOTableFile.parse` seeds `config["_current_table_number"] = 0` at `tree.py:4343`; `TableElement.parse` sets `_empty` at `:2828`), when `votable.get_first_table()` is called, then it returns the table at index 1 — the first table whose `_empty` is falsy — and not `votable.get_table_by_index(0)`. (Use `table_number`, not `table_id`: `table.py:144-153` does not propagate `table_id` into `config`, so the `_empty` branch at `tree.py:2830-2834` is unreachable through `parse()`.)
- **S9:** Given `parse(get_pkg_data_filename("data/empty_table.xml"))` — a `TABLE` that declares two `FIELD`s (`unsignedByte`, `short`) but carries no `DATA`, so `table.array` has zero rows (exercised today by `test_table.py::test_empty_table`, line 445) — when `get_first_table().to_table()` is called, then it returns without raising an `astropy.table.Table` with `len(result) == 0` and `colnames == ["unsignedByte", "short"]`.
- **S10:** Given a table with two `FIELD`s that share the same `name` (e.g. `name="x"`) but have distinct `ID`s (e.g. `a` and `b`), when `to_table(use_names_over_ids=True)` is called, then the returned `Table` is constructed successfully with `colnames == ["x", "x1"]` — the first field keeps the unmodified name and the colliding one gets the smallest unused positive integer appended — and no `ValueError` about duplicate column names is raised. (Building this fixture may emit `W32`/`W33` uniquification warnings from `Field.uniqify_names`; those are pre-existing behavior and not part of this scenario's assertion.)

### Error Scenarios

- **S11:** Given a `VOTableFile` with zero tables across all resources (e.g. `VOTableFile()` with a single childless `Resource`), and separately given a file parsed with a `table_number` beyond the last table so that every table is marked `_empty`, when `votable.get_first_table()` is called, then each case raises `IndexError`.
- **S12:** Given a `ParamRef` whose `ref` does not match the `ID` of any `Param` reachable via `self._table._votable.iter_fields_and_params()` (even if it matches a `Field`'s `ID` instead), when `paramref.get_ref()` is called, then it raises `KeyError`.

### Blocking Prerequisites

- **S15:** Given `config = {"verify": "exception"}`, when `tree.check_string(42, "foo", config)` is called, then `W08` is raised (`test_tree.py::test_string_fail`); when `tree.check_string(None, "foo", config)` or `tree.check_string("abc", "foo", config)` is called, then nothing is raised.
- **S16:** Given `config = {"verify": "exception"}` and a `tree.Field`, when `tree.check_astroyear("X2100", field, config)` is called, then `W07` is raised (`test_tree.py::test_check_astroyear_fail`); when called with `"J2000"`, `"B1950.0"`, `"2000"`, or `None`, then nothing is raised.
- **S17:** Given `config = {"verify": "exception"}`, when `tree.CooSys(system=s, config=config)` is constructed for each of `"ICRS"`, `"FK4"`, `"FK5"`, `"eq_FK4"`, `"eq_FK5"`, `"GALACTIC"`, `"galactic"`, `"SUPER_GALACTIC"`, `"supergalactic"`, `"AZ_EL"`, `"BODY"`, `"geo_app"`, `"ecl_FK4"`, `"ecl_FK5"`, `"xy"`, `"barycentric"`, then no `E16` is raised; when it is constructed with `system="InvalidSystem"`, then `E16` is raised. (The `verify="exception"` config is what makes this discriminating: the `system` setter stores the value either way — `tree.py:1939-1943` — so a test that only asserts `coosys.system == "FK4"` after a default parse passes even with an empty `reference_frames`.) Parsing-level counterpart: `test_coosys.py::test_coosys_system` expects `E16` only for `system="InvalidSystem"`, and `test_coosys_to_astropy_frame_and_time`/`test_coosys_to_astropy_frame_error` construct `CooSys` for the accepted terms under `filterwarnings = ["error"]`.
- **S18:** Given `data/regression.xml` (which contains `FIELD`, `COOSYS`, and `INFO` elements), when `parse()` is called on it, then it completes without raising `NameError` or `AttributeError` — i.e. the stripped attribute checkers and `CooSys.reference_frames` are back in place and every later scenario is reachable.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that would *fail if the behavior were wrong*. A green suite that passes for the wrong reason does not satisfy this contract — `/verify` will hunt for vacuous tests by asking, of each behavior, "what is the smallest change that breaks this, and would any test catch it?"

Concretely:

- Restore the blocking prerequisites first — `check_string` and
  `check_astroyear` (module level) and `CooSys.reference_frames` — then
  implement `ParamRef.get_ref`, `TableElement.to_table`,
  `VOTableFile.__repr__`, `VOTableFile.get_first_table`, and
  `VOTableFile.iter_values`. All eight live in
  `astropy/io/votable/tree.py`; change no other source file. Do not
  touch parsing (`parse`) or serialization (`to_xml`) method bodies, and
  do not alter `ParamRef._attr_list_11`/`_attr_list_12`/`_utype_in_v1_2`/
  `_ucd_in_v1_2` or `VOTableFile._version_namespace_map`.
- Write a docstring for each restored definition (the originals were
  deleted); the docstrings must describe the behavior specified here, not
  the mechanism.
- Sanity-check the prerequisites before anything else: `parse()` on any
  file containing a `FIELD` currently dies with `NameError`, so a red run
  of `test_table.py` proves nothing until S15-S18 pass.
- `astropy/io/votable/tests/test_table.py` already contains extensive
  `to_table()`/`get_first_table()`/round-trip tests (`test_table` line 61,
  `test_names_over_ids` lines 168-192, `test_explicit_ids` lines 195-219,
  `test_empty_table` line 445, `test_binary2_masked_strings` line 466,
  and the many other `votable.get_first_table()` call sites) — run this
  file first once the prerequisites are in; it is the fastest signal for
  `to_table`/`get_first_table` correctness. Do not delete or weaken any
  existing assertions in it to make it pass.
- Add new, focused tests (in `astropy/io/votable/tests/test_tree.py` or
  `test_table.py`, matching existing style in those files) specifically
  for `ParamRef.get_ref`, `VOTableFile.iter_values`/`__repr__`,
  `TableElement.__repr__`/`__str__`/`__bytes__`, the `_empty`-skipping
  behavior of `get_first_table`, and the `use_names_over_ids` collision
  rule — the existing suite does not cover these directly.
- **Behavioral over structural** — assert on `Table.colnames`,
  `Table[...].data`/`.mask`, `Table.meta`, returned objects' identity, and
  raised exception types — not on internal private attributes beyond
  `_empty` (which S8 specifically requires exercising, since it is the
  only observable signal for "skipped during parsing").
- **Every test can fail** — do not hardcode an expected `Table` and skip
  checking it; do not assert `True` or a tautology; each of S1-S18 needs
  at least one test where flipping the target behavior (e.g. returning
  the first table instead of the first non-empty one, or returning a
  `Field` instead of only `Param` from `get_ref`) makes that test fail.
- **Deterministic, isolated** — use the existing fixture data files under
  `astropy/io/votable/tests/data/` (e.g. `regression.xml`,
  `binary2_masked_strings.xml`) or construct small `tree.VOTableFile`
  trees directly in-test; do not depend on network access or file-system
  state outside `get_pkg_data_filename`.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Test suite is green (`astropy/io/votable/tests/test_table.py`,
      `test_tree.py`, `test_coosys.py`, and any new tests added for this
      spec).
- [ ] Every acceptance scenario (S1-S18) maps to at least one test.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
      the smallest break of its behavior (thought-mutation), e.g.
      swapping `_empty` filtering off in `get_first_table`, having
      `iter_values` skip `is_defaults()` values, or making `check_string`
      accept every type, must break a test.
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
      first); no AP-1...AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings) — each of the eight restored definitions carries a
      docstring that accurately describes its final behavior.

## Alternatives Considered

- **Keep the scope to the five methods and treat the stripped attribute
  checkers as someone else's problem.** Rejected: `check_string` is
  called from the `utype`/`xtype` setters that every `Field` construction
  runs (`tree.py:434`, `:460`), so `parse()` raises `NameError` before any
  of the five methods is reachable and *no* acceptance scenario here could
  be demonstrated. The prerequisites are therefore in scope.
- **Restore every stripped definition in the file, including the ones
  nothing references.** Rejected as the default: `TableElement.is_empty`,
  `MivotBlock.__repr__`, and the unidentified `Values` block have no
  caller and no test, so requiring them would add unverifiable surface.
  They are recorded in Open Questions and permitted but not required.

## Trade-offs and Limitations

- Variable-length array fields (`arraysize` ending in `*`) may not
  round-trip identically through `astropy.table.Table` — an accepted,
  pre-existing limitation of the VOTable/Table type systems, not a defect
  to fix under this spec. The restored `to_table` docstring should say so
  (`Field.to_table_column`, `tree.py:1744-1749`, already stashes
  `_votable_arraysize` in the column meta for these cases).
- Table-level `INFO` and `LINK` elements are intentionally not copied
  into `table.meta` by `to_table` (only field-level link metadata is,
  via `Field.to_table_column`) — not in scope to change.
- `CooSys.reference_frames` is specified by membership only (which
  systems are accepted/rejected), not by source or caching strategy, so
  an implementation that hard-codes the union of the DTD list and the
  vocabulary terms is acceptable under this spec even though the bundled
  `ivoa-vocalubary_refframe-v20220222.json` suggests the values were once
  loaded from that file.

## Open Questions

These were resolved by inspection rather than by asking a human; they are
recorded here so the decisions are visible and revisable.

- **Three more definitions were stripped from `tree.py` but are
  referenced by nothing in the package or its tests** (verified by
  grepping `astropy/**/*.py`): `TableElement.is_empty` (blank slot
  2705-2712, between the `infos` property and `create_arrays`),
  `MivotBlock.__repr__` (blank slot 3671-3674), and an unidentified
  ~30-line block in `Values` between `parse` and `is_defaults` (blank
  slot 1190-1219; no missing `Values` member is referenced anywhere, so
  it is not load-bearing). **Decision:** out of scope. No acceptance
  scenario depends on them, and `get_first_table` reads `table._empty`
  directly. If the implementing agent prefers to reintroduce
  `TableElement.is_empty()` as a thin public accessor for `_empty` and
  have `get_first_table` call it, that is permitted — the observable
  behavior in S8/S11 is unchanged either way.
- **De-duplication suffix format for `use_names_over_ids=True`:** no test
  or doctest in the repository pins it; `docs/io/votable/index.rst:241-245`
  only says names "may be renamed by appending numbers to the end".
  **Decision:** committed in S10 to `name`, `name1`, `name2`, … so the
  scenario is checkable. If a future upstream test demands a different
  suffix, only S10 and the `to_table` bullet need to change.

## References

All line numbers verified against the working tree on 2026-09-10.

- `astropy/io/votable/tree.py` — surviving anchors: `Field` class
  declaration (1299-1306), `Field.uniqify_names` (1440),
  `Field.to_table_column` (1719), `Values.is_defaults` (1220), `CooSys`
  (1865) with `_reference_frames` (1875) and the `system` setter (1939-
  1943), `FieldRef.get_ref` (2245-2253), `ParamRef` (2256),
  `Group._add_paramref` (2406), `TableElement` (2478),
  `TableElement.__repr__`/`__bytes__`/`__str__` (2550-2560),
  `TableElement.create_arrays` (2714-2771), `TableElement.parse`
  `_empty` assignments (2828, 2834), `TableElement.from_table`
  (3546-3570), `TableElement.iter_fields_and_params` (3572),
  `VOTableFile` (4138), `VOTableFile.iter_tables` (4490),
  `VOTableFile.get_table_by_index` (4530-4537),
  `VOTableFile.iter_fields_and_params` (4539),
  `VOTableFile.get_values_by_id` (4585-4594).
  Blank (stripped) slots: 295-341, 1190-1219, 1948-1969, 2309-2320,
  2705-2712, 3496-3545, 3671-3674, 4167-4171, 4497-4507, 4576-4584.
- `astropy/io/votable/connect.py:49-128` — `read_table_votable`, the
  `Table.read(format="votable")` path into `to_table`.
- `astropy/io/votable/tests/test_table.py` — existing `to_table`/
  `get_first_table` coverage (lines 61, 120, 168, 195, 445, 466).
- `astropy/io/votable/tests/test_tree.py` — `test_check_astroyear_fail`
  (27), `test_string_fail` (34), `test_namespace_warning` (73).
- `astropy/io/votable/tests/test_coosys.py` — `test_coosys_system` (59),
  `_coosys_tests` (77).
- `astropy/io/votable/exceptions.py` — `W07` (437-455), `W08` (458-467),
  `E16` (1446-1459), and the `vo_raise`/`warn_or_raise` conventions used
  by `FieldRef.get_ref` and to be mirrored by `ParamRef.get_ref` and the
  restored checkers.
- `docs/io/votable/table_element.rst` (27-29, 82-90) and
  `docs/io/votable/index.rst` (236-245) — documented `to_table`/
  `get_first_table` behavior, including the name-collision note.

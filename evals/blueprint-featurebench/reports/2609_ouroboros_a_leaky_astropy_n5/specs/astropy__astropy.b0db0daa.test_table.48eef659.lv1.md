# 2609.0001 Quantity Concatenation and Selected Table/VOTable Operations

**Date:** 2026-09-10
**Status:** draft
**Author:** EP Lin

## Context

Four areas of the `astropy` codebase currently have specific functions
emptied out — **the entire `def` (signature, docstring, and body) has been
deleted**, leaving only call sites in the surrounding, still-intact code —
while the rest of each module, including callers and downstream tests, is
intact:

1. `astropy/units/quantity_helper/function_helpers.py` — the machinery
   that lets `numpy.concatenate` (and, transitively, `numpy.stack`,
   `numpy.hstack`, `numpy.vstack`, `numpy.dstack`, `numpy.block`) work on
   `Quantity` arrays.
2. `astropy/io/votable/tree.py` — `TableElement.to_table` (VOTable → Table
   conversion) and `VOTableFile.get_first_table` (first non-empty table
   lookup).
3. `astropy/table/table.py` — `Table._init_from_ndarray` (ndarray-based
   `Table` construction) and `Table.add_column` (single-column insertion).
4. `astropy/io/votable/converters.py` — `UnicodeChar._binoutput_var` /
   `UnicodeChar._binparse_var` (variable-length UTF-16-BE VOTable BINARY
   serialization).

`astropy/io/votable/tests/test_table.py`, the test module that historically
exercised most of this behavior, has been deleted from the working tree
(`git status` shows it as `D`) and will be replaced by an external test
suite at evaluation time. This spec is the contract that suite is written
against.

**Every fact below about "what the original code did" is recovered
directly from this repository's own git history** — the pre-strip bodies of
every function named in this spec are still retrievable with
`git show HEAD:<path>` (the strip is an uncommitted working-tree edit) —
and from the installed environment (`python -c "import numpy;
print(numpy.__version__)"` reports **2.5.3** in this environment, which is
load-bearing for the `concatenate` interface, see below). Nothing in this
spec is guessed.

Several *other* functions in the same four files, plus in
`astropy/table/row.py` and `astropy/utils/xml/writer.py`, have also had
their bodies removed and are direct or transitive dependencies of the four
primary interfaces. "Required Supporting Restorations" enumerates the ones
needed for every Acceptance Scenario below to be reachable at all; without
them the primary interfaces raise `AttributeError`/`NameError` on first
call, not the errors their own docstrings describe.

## Motivation

Without these methods, `Quantity` cannot participate in `np.concatenate`
(and everything built on it), VOTable files cannot be converted to or from
`astropy.table.Table`, `Table` cannot be constructed from a plain
`numpy.ndarray`, and `Table.add_column` — one of the most commonly used
public `Table` APIs — is unavailable. The BINARY2 VOTable serialization
path (compact binary transmission of VOTable data, including
variable-length Unicode fields) cannot round-trip at all without the
`UnicodeChar` binary codec and its supporting restorations.

## Proposed Solution

### Overview

Restore each named method to the documented, observable contract given in
"Interface Contract" below, and restore the functions identified in
"Required Supporting Restorations" to the behavior implied by their own
recoverable pre-strip bodies. Do not change any public signature — the
hidden grading tests call these functions with the exact signatures given
below.

### Key Components

- **`_iterable_helper`** (`astropy/units/quantity_helper/function_helpers.py`)
  — normalizes `*args` into value arrays sharing one common unit, and
  converts a `Quantity` `out=` argument into a plain `ndarray` view (or
  raises if `out` is given and is not a `Quantity`).
- **`concatenate`** (same file) — **two call sites currently exist for this
  name**, guarded by `if NUMPY_LT_2_4: ... else: ...`. With NumPy 2.5.3
  installed, `NUMPY_LT_2_4` is `False`, so the `else` branch is the one
  that actually runs; it is currently `pass` (no function defined at all,
  so `np.concatenate` on `Quantity` currently raises `TypeError` with no
  helper in `FUNCTION_HELPERS`). The `if NUMPY_LT_2_4:` branch already
  contains a complete, correct `concatenate` body that calls
  `_iterable_helper` — **do not modify it**; it is simply dead code in
  this environment. Implement the `else` branch as
  `concatenate(arrays, /, axis=0, out=None, **kwargs)` (positional-only
  `arrays`, per NumPy ≥ 2.4's calling convention) using the same
  `_iterable_helper`-based approach as the intact branch.
- **`TableElement.to_table`** (`astropy/io/votable/tree.py`) — converts a
  parsed VOTable `TABLE` element's masked-array data into an
  `astropy.table.Table`, carrying over column naming (ID vs. name),
  table-level metadata, and per-column units/format/description/meta.
- **`VOTableFile.get_first_table`** (`astropy/io/votable/tree.py`) —
  returns the first table in the file for which `is_empty()` is `False`.
- **`Table._init_from_ndarray`** (`astropy/table/table.py`) — private
  initializer invoked by `Table.__init__` when `data` is a `numpy.ndarray`;
  splits it into per-column data for structured or homogeneous arrays and
  delegates to `self._init_from_list`.
- **`Table.add_column`** (`astropy/table/table.py`) — public API to insert
  or append a single column, with broadcasting, length validation, and
  duplicate-name handling.
- **`UnicodeChar._binoutput_var` / `UnicodeChar._binparse_var`**
  (`astropy/io/votable/converters.py`) — BINARY-format serialize/deserialize
  for variable-length `unicodeChar` VOTable fields (UTF-16-BE), each
  delegating the 4-byte length prefix to `Converter._parse_length` /
  `Converter._write_length`.

### Data Flow

1. **Quantity concatenation:** `np.concatenate(seq_of_quantities, ...)` →
   NumPy's `__array_function__` protocol dispatches to the `concatenate`
   entry in `FUNCTION_HELPERS` (the `else`-branch implementation, in this
   environment) → it calls `_iterable_helper(*arrays, out=out, axis=axis,
   **kwargs)` → `_iterable_helper` converts `out` (if any) to a bare
   `ndarray` view via `_quantity_out_as_array` (already intact) and calls
   `_quantities2arrays(*args)` (see Required Supporting Restorations) to
   get plain-value arrays sharing one unit → returns `(arrays, kwargs,
   unit, out)` → `concatenate` wraps that into `((arrays,), kwargs, unit,
   out)` → numpy's override machinery calls the real
   `numpy.concatenate(arrays, **kwargs)` on the plain arrays and reattaches
   `unit`.
2. **VOTable → Table:** `votable.parse(...)` builds a `VOTableFile` tree,
   populating each `TableElement.array` (a masked `numpy.recarray`) during
   XML/BINARY/BINARY2 parsing → `VOTableFile.get_first_table()` walks
   `self.iter_tables()` and returns the first element where
   `table.is_empty()` is `False`, else raises `IndexError` →
   `TableElement.to_table(use_names_over_ids)` builds a `Table` from
   `self.array` with column names chosen per `use_names_over_ids`, sets
   `table.meta` from `ID`/`name`/`ref`/`ucd`/`utype`/`description`, then
   calls `field.to_table_column(column)` per field to copy over
   units/format/description/meta onto each `Table` column.
3. **ndarray → Table:** `Table(data=some_ndarray, ...)` → `Table.__init__`
   (already intact) detects `data` is a `numpy.ndarray`; for a 1-D array it
   reshapes to `data[np.newaxis, :]` first (turning a length-N 1-D array
   into a single row of N columns), raises `ValueError` up front for a
   0-D/scalar array, then calls
   `self._init_from_ndarray(data, names, dtype, n_cols, copy)` → the method
   derives per-column names/data (from `dtype.names` for structured arrays,
   or by slicing `data[:, i]` for the now-guaranteed-2-D array) and
   delegates to `self._init_from_list(cols, names, dtype, n_cols, copy)`.
4. **`add_column`:** converts `col` to a table-compatible column via
   `self._convert_data_to_col`, broadcasts scalars/length-1 columns to the
   table's length, validates the resulting length against the table's
   existing length, applies `rename_duplicate` uniquification (only when
   `rename_duplicate=True`), registers the column's parent table/mask,
   inserts it via `self.columns[name] = col` — which raises `ValueError` if
   `name` already exists and was not uniquified — and, if `index` is given,
   reorders `self.columns` so the new column sits before position `index`.
5. **VOTable BINARY unicodeChar round-trip:** writing a table in `format=
   "binary"` or `"binary2"` calls each field's converter's `binoutput`
   (`UnicodeChar._binoutput_var` when `arraysize` ends in `*`), which emits
   a 4-byte big-endian UTF-16-code-unit count followed by UTF-16-BE bytes
   (or 4 zero bytes if masked/`None`/empty); reading it back calls
   `binparse` (`UnicodeChar._binparse_var`), which reads that 4-byte count,
   reads `count * 2` bytes, and decodes them as UTF-16-BE, warning `W46`
   (message args exactly `("unicodeChar", self.arraysize)`) if the field
   has a bounded `arraysize` (not `"*"`) and the decoded length exceeds the
   bound — on both the read and the write side.

### Interface Contract

Exact signatures — do not deviate, hidden tests call these directly:

```python
# astropy/units/quantity_helper/function_helpers.py
def _iterable_helper(*args, out=None, **kwargs):
    """Returns (arrays, kwargs, unit, out).
    Raises NotImplementedError if `out` is given and is not a Quantity."""

if NUMPY_LT_2_4:
    @function_helper
    def concatenate(arrays, axis=0, out=None, **kwargs):
        ...  # already implemented — do not change
else:
    @function_helper
    def concatenate(arrays, /, axis=0, out=None, **kwargs):
        """Returns ((arrays,), kwargs, unit, out) for the
        FUNCTION_HELPERS protocol. This is the branch that executes with
        the installed NumPy (2.5.3)."""

# astropy/io/votable/tree.py
class TableElement:
    def to_table(self, use_names_over_ids=False):
        """Returns an astropy.table.Table."""

class VOTableFile:
    def get_first_table(self):
        """Returns the first TableElement with is_empty() False.
        Raises IndexError if none exists."""

# astropy/table/table.py
class Table:
    def _init_from_ndarray(self, data, names, dtype, n_cols, copy):
        """Returns None. After the call, self.colnames and each
        self[name] reflect data's fields (structured array) or
        data[:, i] (homogeneous 2-D array), in `names` order."""

    def add_column(
        self, col, index=None, name=None, rename_duplicate=False,
        copy=True, default_name=None,
    ):
        """Returns None; mutates self.columns in place."""

# astropy/io/votable/converters.py
class UnicodeChar(Converter):
    def _binoutput_var(self, value, mask):
        """Returns bytes: 4-byte big-endian length prefix (count of
        UTF-16 code units) + UTF-16-BE payload, or 4 zero bytes if
        mask is True, value is None, or value == "". Warns W46
        (args=("unicodeChar", self.arraysize)) if arraysize is bounded
        (not "*") and len(value) exceeds it — value is still encoded
        and returned in full, never truncated."""

    def _binparse_var(self, read):
        """Returns (value: str, mask: bool); mask is always False.
        Warns W46 (args=("unicodeChar", self.arraysize)) if arraysize
        is bounded (not "*") and the decoded length exceeds it — the
        full decoded string is still returned, never truncated."""
```

## Required Supporting Restorations

These functions in the same files, plus `astropy/table/row.py`,
`astropy/utils/xml/writer.py`, and `astropy/utils/xml/check.py`, are also
empty in the working tree and are direct or transitive dependencies of the
interfaces above — prerequisites for those interfaces to be reachable at
all, whether or not a scenario directly asserts on the dependency's own
output. They **must** be restored (DoD checks this list); each function's
signature, docstring, and body were deleted along with everything else
named in this spec, so `git show HEAD:<path>` — not the current working
tree — is the only source of ground truth for its exact behavior.

- **`astropy/units/quantity_helper/function_helpers.py`** — `_as_quantity(a)`
  (convert one argument to `Quantity`, raising `NotImplementedError` on
  failure) and `_quantities2arrays(*args, unit_from_first=False)` (convert
  multiple arguments to plain-value arrays sharing one common unit — the
  first argument's unit, unless it is an inferred/default dimensionless
  unit and a later argument has an explicit non-dimensionless-equivalent
  unit, per S14). Both are called directly by `_iterable_helper`.
- **`astropy/io/votable/tree.py`** — `TableElement.is_empty()` (`True` iff
  `self._empty`; called directly by `get_first_table`, S5/S17/S26);
  `TableElement._resize_strategy(size)`, `TableElement._get_binary_data_stream`
  (and its nested `careful_read`), `TableElement._parse_binary`,
  `TableElement._write_binary` (the BINARY/BINARY2 `<STREAM>` read/write
  pipeline, row by row, via each field's converter `binparse`/`binoutput`
  — required for the write→parse round-trip in S13 to exercise real XML
  I/O rather than calling the converter methods in isolation).
- **`astropy/io/votable/converters.py`** — `Converter._parse_length(read)` /
  `Converter._write_length(length)` (4-byte big-endian length prefix;
  called directly by `UnicodeChar._binparse_var`/`_binoutput_var`);
  `_make_masked_array(data, mask)`, `bitarray_to_bool(data, length)`,
  `bool_to_bitarray(value)` (used by `_parse_binary`/`_write_binary` for
  BINARY2 row-mask bits and by `create_arrays`);
  `UnicodeChar._binparse_fixed(self, read)` / `UnicodeChar._binoutput_fixed(self,
  value, mask)` (the fixed-`arraysize` siblings of the two primary
  interfaces, on the same class — leaving them empty means the class is
  only half-restored and any fixed-length `unicodeChar` field raises
  `AttributeError`; not separately scenario-tested here, but restore them
  from `git show HEAD:astropy/io/votable/converters.py` alongside the var
  ones).
- **`astropy/table/row.py`** — `Row.__init__(self, table, index)`
  (validates `index` via `operator_index`, bounds-checks against
  `len(table)`, normalizes negative indices via `index % n`); required for
  `Table`'s row-access API (`table[0]`) to work at all, even though no
  scenario below directly indexes a row (all `Table` assertions above go
  through `colnames`/`t["name"]`).
- **`astropy/utils/xml/writer.py`** — `XMLWriter.data(self, text)`
  (`self._data.append(text)`); used throughout VOTable XML serialization,
  exercised by the `votable.to_xml(...)` write step in S13.
- **`astropy/utils/xml/check.py`** — `check_anyuri(uri)` (RFC 2396 URI
  syntax check). This is a **hard prerequisite for parsing `names.xml`**,
  not merely a nice-to-have: that fixture's `<LINK href="https://doi.org/
  10.1088/0004-6256/136/6/2413"/>` element goes through `Link.href`'s
  setter → `astropy/io/votable/xmlutil.py::check_anyuri` →
  `astropy/utils/xml/check.py::check_anyuri`, so parsing `names.xml`
  currently raises `AttributeError` before `get_first_table`/`to_table`
  ever run. S3, S4, S5, and S11 (all of which parse `names.xml`) are
  unreachable without restoring it.

The following functions are *also* empty but are **not** exercised by any
scenario in this spec (no VOTable fixture used here has a `<GROUP>`
element or an unparseable `unit` string, and no scenario calls
`from_table`/`Table.write(format="votable")`). Restore them only if you add
a scenario that needs them; they are excluded from the "no stubs left"
Definition-of-Done check: `Group.entries` / `Group._add_fieldref` /
`Group._add_paramref`, the nested `yes_no` in `Values.to_xml`, and
`VOTableFile.iter_values()` (`astropy/io/votable/tree.py`);
`Numeric._is_null`, `BitArray._splitter_lax`, `Boolean.binparse`,
`_all_matching_dtype`, `numpy_to_votable_dtype`
(`astropy/io/votable/converters.py`);
`_ParsingFormatMixin._invalid_unit_error_message`
(`astropy/units/format/base.py`).

## Alternatives Considered

### Re-deriving `_iterable_helper`'s contract from `concatenate`'s needs alone

Rejected: `_iterable_helper` is also called by `numpy.choose`, `numpy.select`,
`numpy.quantile`/`numpy.percentile`/`nanquantile`/`nanpercentile`, and
`numpy.piecewise` helpers elsewhere in the same file (already-intact code,
not blanked). Its contract must satisfy all of those call sites, not just
`concatenate`, so it is specified generically rather than narrowed.

### Leaving the NumPy ≥ 2.4 `concatenate` branch as `pass`

Rejected: the installed environment runs NumPy 2.5.3 (`NUMPY_LT_2_4 ==
False`), so this is the branch that actually executes when a hidden test
calls `np.concatenate` on `Quantity` arrays. Leaving it as `pass` would
make S1, S2, S14, S24 (every scenario that calls `np.concatenate`) fail
with `TypeError: no implementation found`, regardless of how correct
`_iterable_helper` is.

## Acceptance Scenarios

### Happy Path

- **S1:** Given two `Quantity` arrays with compatible units — `q1 =
  np.arange(6.0).reshape(2, 3) * u.m` and `q2 = q1.to(u.cm)` — when
  `np.concatenate([q1, q2])` is called, then the result is a `Quantity` in
  `u.m` whose values equal `np.concatenate([q1.value, q2.to_value(u.m)])`.
- **S2:** Given `q1`/`q2` as above and `out = np.empty((4, 3)) *
  u.dimensionless_unscaled`, when `np.concatenate([q1, q2], out=out)` is
  called, then the function returns `out` itself, `out.unit == u.m`, and
  `out`'s values equal the same concatenation as S1.
- **S3:** Given a `VOTableFile` parsed from
  `astropy/io/votable/tests/data/names.xml` (17 distinct `FIELD` elements),
  when `votable.get_first_table().to_table(use_names_over_ids=True)` is
  called, then `table.colnames == ["Name", "GLON", "GLAT", "RAdeg",
  "DEdeg", "Jmag", "Hmag", "Kmag", "G3.6mag", "G4.5mag", "G5.8mag",
  "G8.0mag", "4.5mag", "8.0mag", "Emag", "24mag", "f_Name"]` (the literal
  `name` attributes, in field order).
- **S4:** Given the same file, when `.to_table(use_names_over_ids=False)`
  (the default) is called, then `table.colnames == ["col1", "col2", ...,
  "col17"]` (the literal `ID` attributes declared on each `FIELD` in
  `names.xml`, in field order).
- **S5:** Given a `VOTableFile` parsed from `names.xml` (a single `TABLE`,
  parsed with no `table_number`/`table_id` filter, so nothing marks it
  `_empty`), when `get_first_table()` is called, then it returns that
  `TableElement` without raising.
- **S6:** Given a homogeneous 2-D `numpy.ndarray` `arr` of shape `(2, 3)`,
  when `Table(arr, names=["a", "b", "c"])` is constructed, then the
  resulting table has 3 columns named `a`, `b`, `c` and `t["a"]` equals
  `arr[:, 0]`, `t["b"]` equals `arr[:, 1]`, `t["c"]` equals `arr[:, 2]`.
- **S7:** Given a structured `numpy.ndarray` with named fields (e.g.
  `dtype=[("x", "i4"), ("y", "f8")]`), when `Table(arr)` is constructed
  with no explicit `names`, then `table.colnames == ["x", "y"]` and each
  column's data equals `arr["x"]` / `arr["y"]`.
- **S8:** Given `t = Table([[1, 2], [0.1, 0.2]], names=("a", "b"))`, when
  `t.add_column(Column(name="c", data=["x", "y"]))` is called, then
  `t.colnames == ["a", "b", "c"]` and `list(t["c"]) == ["x", "y"]`.
- **S9:** Given the same `t`, when `t.add_column(["p", "q"], name="d",
  index=1)` is called, then `t.colnames == ["a", "d", "b"]` (`"d"` is
  inserted before position 1, i.e. between `"a"` and `"b"`).
- **S10:** Given `t = Table([[1, 2], [0.1, 0.2]], names=("a", "b"))` (2
  existing columns), when `t.add_column([3, 4])` is called with no `name`
  and a plain list (which has no `.info.name`), then the new column is
  named `"col2"` (`default_name = f"col{len(self.columns)}"`, computed
  from the column count *before* insertion) and `t.colnames == ["a", "b",
  "col2"]`.
- **S11:** Given a `VOTableFile` parsed from `names.xml`, when
  `.to_table(use_names_over_ids=True)` is called, then
  `table["GLON"].unit == u.deg` (the `FIELD unit="deg"` attribute on the
  `GLON` field is carried onto the resulting column via
  `field.to_table_column`).
- **S12:** Given `field = tree.Field(votable, name="f", datatype=
  "unicodeChar", arraysize="*", ID="f")` and `converter =
  get_converter(field)`, when `converter._binoutput_var("héllo", mask=
  False)` is called and the resulting `bytes` object is fed byte-by-byte to
  `converter._binparse_var(read)` (via a `read(n)` callable that consumes
  those bytes in order), then the round-tripped value equals `"héllo"` and
  `mask is False`.
- **S13:** Given a `tree.VOTableFile()`/`tree.Resource()`/`tree.TableElement`
  built programmatically with one field `tree.Field(votable, name="u",
  datatype="unicodeChar", arraysize="128*", ID="u")`, two rows `"Short
  string"` and a 49-character string that still fits in 128 characters
  (the same shape of setup as the recovered
  `test_binary2_bounded_variable_length_char`, which used `datatype=
  "char"` — this scenario deliberately uses `datatype="unicodeChar"` so the
  `UnicodeChar` variable-length codec, not `Char`'s, is the code under
  test), when the table is serialized with `votable.version = "1.3"`,
  `table.format = "binary2"`, `table._config["version_1_3_or_later"] =
  True`, then written via `votable.to_xml(bio)` and re-parsed with
  `parse(bio)`, then `table2.fields[0].arraysize == "128*"` and both rows'
  decoded string values equal exactly what was written.

### Edge Cases

- **S14:** Given a plain (unit-less) array `np.zeros(q1.shape)` placed
  *first* in the list passed to `np.concatenate`, with `q1 = [1.0, 2.0] *
  u.m` placed later in the same list, when `np.concatenate([np.zeros(2),
  q1])` is called, then the result's unit is `u.m` (a later explicit
  non-dimensionless-equivalent unit establishes the common unit even
  though the first argument had none).
- **S15:** Given `astropy/io/votable/tests/data/no_field_not_empty_table.xml`
  (0 `FIELD` elements, 3 empty `<TR>` rows, 1 `<INFO>`), when the file is
  parsed, then `len(table.fields) == 0` and `len(table.infos) == 1` (the
  parser accepts and stores rows even when there are no fields to
  interpret them; `to_table()` is not asserted here, since a 0-field
  `TableElement`'s `array` is a 1-D object array rather than a 2-D one,
  which `Table.__init__` handles differently than the 2-D case S6 covers —
  out of scope for this scenario).
- **S16:** Given `astropy/io/votable/tests/data/empty_table.xml` (2
  `FIELD` elements — `unsignedByte`, `short` — and no `<DATA>` block), when
  `.to_table()` is called on its first table, then it returns a zero-row
  `Table` with `colnames == ["unsignedByte", "short"]`, without raising.
- **S17:** Given two `tree.TableElement` objects built programmatically and
  appended to the same `Resource.tables`, where the first has
  `._empty = True` set directly (simulating what the parser sets when a
  `table_number`/`table_id` filter skips a table — `is_empty()` returns
  exactly `self._empty`) and the second does not, when
  `VOTableFile.get_first_table()` is called, then it returns the second
  table, not the first.
- **S18:** Given `t = Table([[1, 2], [0.1, 0.2]], names=("a", "b"))`, when
  `t.add_column(1.1, name="c")` (a bare scalar) is called, then `t["c"]`
  has length 2 and both elements equal `1.1` (broadcast to the table's
  existing length).
- **S19:** Given the same `t`, when `t.add_column(1.1, name="b",
  rename_duplicate=True)` is called, then `t.colnames == ["a", "b", "b_1"]`
  and `t["b_1"]` equals `[1.1, 1.1]` (the new column is inserted as
  `"b_1"`, the existing `"b"` column is untouched).
- **S20:** Given a `TableElement` with two `FIELD`s that have distinct
  `ID`s (`ID="f1"`, `ID="f2"`, avoiding the `W32` ID-collision warning), an
  explicit `datatype="float"` on both (a `FIELD` with no `datatype` raises
  `E10` on setup), and the identical `name="flux"`, built programmatically,
  when
  `table.create_arrays(1)` is called (wrapped in `pytest.warns(W33)` — this
  is where `Field.uniqify_names` runs and warns, under this project's
  `filterwarnings = ["error", ...]` pytest config) and then
  `.to_table(use_names_over_ids=True)` is called, then `table.colnames ==
  ["flux", "flux2"]` (the second duplicate gets the literal suffix `2`, per
  the recovered `to_table` algorithm: `new_name = f"{name}{i}"` starting at
  `i=2`).
- **S21:** Given a `unicodeChar` field with bounded, variable-length
  `arraysize="5*"` — e.g. `field = tree.Field(votable, name="f", datatype=
  "unicodeChar", arraysize="5*", ID="f")`, `converter = get_converter(
  field)` (the trailing `*` makes `converter.arraysize` the int `5` while
  still selecting `_binparse_var`/`_binoutput_var`, unlike a bare
  `arraysize="5"`, which selects the fixed-width codec instead) — and a
  `read` callable that reports a length of 10 UTF-16 code units followed by
  10 code units of data, when `converter.binparse(read)` is called (which
  is `_binparse_var` for this field), then, wrapped in `pytest.warns(W46)`,
  it issues a warning whose message **contains**
  `"unicodeChar value is too long for specified length of 5"` (the full
  formatted warning is prefixed with a `file:line:col: W46:` location tag,
  so assert with `in`/`match=`, not `==`), and still returns the full
  10-code-unit decoded string with `mask is False` (no truncation, no
  exception).
- **S22:** Given the same bounded (`arraysize="5*"`) field and a string
  value 10 characters long, when `converter._binoutput_var(value, mask=
  False)` is called, then, wrapped in `pytest.warns(W46)`, it issues a
  warning whose message **contains** the same text as S21's, but still
  returns the full UTF-16-BE-encoded bytes for all 10 characters (no
  truncation).
- **S23:** Given `mask=True`, or `value=None`, or `value=""`, when
  `UnicodeChar._binoutput_var(value, mask)` is called (any of the three
  combinations), then it returns exactly `b"\x00\x00\x00\x00"` (4 zero
  bytes, no payload).

### Error Scenarios

- **S24:** Given two `Quantity` inputs with mutually inconvertible units
  (e.g. `[1.0] * u.m` and `[1.0] * u.s`), when `np.concatenate([q1, q2])`
  is called, then `astropy.units.UnitConversionError` is raised directly
  (from `Quantity._to_own_unit`'s `.to_value(unit)` call inside
  `_quantities2arrays`, which is not a `TypeError` and therefore is not
  converted to `NotImplementedError`).
- **S25:** Given `_iterable_helper` called directly with `out` set to a
  plain `numpy.ndarray` (not a `Quantity`) — e.g. `_iterable_helper(q1,
  out=np.empty_like(q1.value))` — when the call is made, then
  `NotImplementedError` is raised before any numpy computation happens
  (per the documented contract: `_quantity_out_as_array` raises when its
  argument is not a `Quantity`).
- **S26:** Given `votable = tree.VOTableFile()` with no `Resource`/`TABLE`
  appended to it, when `votable.get_first_table()` is called, then
  `IndexError` is raised with the message `"No table found in VOTABLE
  file."`.
- **S27:** Given `t = Table([[1, 2], [3, 4]])` (2 rows, columns `col0`,
  `col1`), when `t.add_column([9, 9, 9], name="x")` (length 3) is called,
  then `ValueError` is raised (message contains `"Inconsistent data column
  lengths"`), and `t.colnames` is unchanged (does not include `"x"`)
  afterward.
- **S28:** Given `t = Table([[1, 2]], names=["a"])`, when `t.add_column([3,
  4], name="a")` is called (default `rename_duplicate=False`, name already
  exists), then `ValueError` is raised with a message containing `"Cannot
  replace column 'a'"`, and `t.colnames` still equals `["a"]` with its
  original data afterward.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that would *fail if the behavior were wrong*. A green suite that passes for the wrong reason does not satisfy this contract — `/verify` will hunt for vacuous tests by asking, of each behavior, "what is the smallest change that breaks this, and would any test catch it?"

Implement however you work best — blueprint does not prescribe order,
cadence, or commit structure. Only the result is checked. Write tests to
the project's conventions (this repo uses `pytest`; the existing, intact
`astropy/units/tests/test_quantity_non_ufuncs.py::TestConcatenate` and the
git-recoverable `astropy/io/votable/tests/test_table.py`
(`git show HEAD:astropy/io/votable/tests/test_table.py`) are both worth
reading for fixture and assertion style) and to these principles (the same
ones `/verify` scores against — see `references/test-desiderata.md` and
`references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects (table
  contents, column names, returned bytes/strings, raised exception types
  and messages, warning categories), not internals; the suite must survive
  refactoring.
- **Every test can fail** — no copy-pasted expected values, no asserting a
  constant, no tautologies (AP-2, AP-4). For the binary codec scenarios,
  assert round-tripped values, not just "no exception raised."
- **Deterministic, isolated, readable** — use the named fixture files under
  `astropy/io/votable/tests/data/` where a scenario names one; build
  `tree.VOTableFile`/`tree.TableElement`/`tree.Field` objects
  programmatically where a scenario says so (S12, S13, S17, S20–S23, S26); AAA
  structure with inline setup.
- **Warnings are errors in this project's pytest config** —
  `pyproject.toml` sets `filterwarnings = ["error", ...]`, so any scenario
  whose Then includes a VOTable warning (`W33` in S20, `W46` in S21/S22)
  must wrap the warning-producing call in `pytest.warns(...)`, or the test
  will fail with the warning turned into an exception rather than
  asserting on it.

Do not change the public signatures given in "Interface Contract." Restore
every function listed as required in "Required Supporting Restorations" —
they are prerequisites, not optional cleanup — using
`git show HEAD:<path>` as the source of truth for behavior. You may modify
other files if it helps satisfy the scenarios above, but avoid unrelated
refactors: changes outside the files already identified as touched in this
spec are unlikely to be necessary and increase the risk of breaking
unrelated, currently-passing tests elsewhere in `astropy`.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Test suite is green.
- [ ] Every acceptance scenario (S1…S28) maps to at least one test.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under the smallest break of its behavior (thought-mutation).
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale docstrings).
- [ ] Every function listed as required in "Required Supporting Restorations" (and both `concatenate` branches, per "Key Components") exists and is fully implemented — none left undefined, left as `pass`, or raising `NotImplementedError` unconditionally.

## Trade-offs and Limitations

- `to_table`'s docstring explicitly disclaims exact round-trip fidelity for
  variable-length array fields; do not treat imperfect round-tripping of
  those specifically (beyond what S13 asserts) as a defect to fix.
- `add_column`'s `copy` parameter (semantics per its own docstring:
  `copy=True` makes an independent copy, `copy=False` shares the
  underlying data) has no dedicated scenario above; it is exercised
  indirectly by the existing, intact `Column`/mixin copy-semantics tests
  elsewhere in `astropy/table/tests/`, which this spec does not duplicate.
- The functions listed at the end of "Required Supporting Restorations" as
  not-exercised-by-any-scenario are real gaps in the file (they will raise
  if called) but are out of scope for this spec's grading; do not spend
  effort on them beyond what's needed to keep the modules importable.

## References

- `git show HEAD:astropy/units/quantity_helper/function_helpers.py`,
  `git show HEAD:astropy/io/votable/tree.py`,
  `git show HEAD:astropy/io/votable/converters.py`,
  `git show HEAD:astropy/table/table.py`,
  `git show HEAD:astropy/table/row.py`,
  `git show HEAD:astropy/utils/xml/writer.py` — recover the original
  (pre-strip) implementation of every function named in this spec.
- `git show HEAD:astropy/io/votable/tests/test_table.py` — the deleted test
  module; its content is the primary source for the concrete Acceptance
  Scenarios above (`test_names_over_ids`, `test_explicit_ids`,
  `test_empty_table`, `test_no_field_not_empty_table`,
  `test_binary2_bounded_variable_length_char`,
  `test_unicodechar_binparse_var_exceeds_arraysize`, etc.).
- `astropy/units/tests/test_quantity_non_ufuncs.py::TestConcatenate` —
  existing, intact test class exercising `np.concatenate` and related
  functions on `Quantity`.
- `astropy/io/votable/tests/data/names.xml`,
  `astropy/io/votable/tests/data/empty_table.xml`,
  `astropy/io/votable/tests/data/no_field_not_empty_table.xml` — existing
  fixture files referenced by name above.

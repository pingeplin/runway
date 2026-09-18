# 2609.0001 Quantity Concatenation and Selected Table/VOTable Operations

**Date:** 2026-09-18
**Status:** draft
**Author:** FeatureBench

## Context

Four gaps exist in this `astropy` checkout, each removing one or more
callables from the middle of a surrounding implementation that is otherwise intact and
still references them by name. The itemisation below was checked against the files as
they stand; where the callers imply a dependency that is also absent, that dependency is
named here and carried into the Interface Contract, because a scenario's prerequisites
cannot be assumed present:

1. `astropy/units/quantity_helper/function_helpers.py` defines
   `FUNCTION_HELPERS[np.concatenate]` (the `concatenate` helper at line 484, guarded by
   `if NUMPY_LT_2_4:`) whose body already calls `_iterable_helper(*arrays, out=out,
   axis=axis, **kwargs)` — but `_iterable_helper` itself is not defined anywhere in the
   module. Other callers of `_iterable_helper` that are equally broken today: `np.choose`
   (line 729), `np.select` (line 735), `np.quantile`/`np.nanquantile` and therefore
   `np.percentile`/`np.nanpercentile` (line 853), and `np.nanmedian` (line 867).
   `np.stack` is in `SUBCLASS_SAFE_FUNCTIONS` (line 100) and reaches `_iterable_helper`
   indirectly, because `ndarray`'s `stack` implementation re-dispatches through
   `np.concatenate`. The module also references two other undefined names,
   `_as_quantity` (singular; the surviving `_as_quantities`, plural, is a different
   function) and `_quantities2arrays`, from many unrelated numpy overrides (`average`,
   `median`, `sort`, etc.) that are outside this spec's four named interfaces — see Out
   of Scope.
2. `astropy/io/votable/tree.py` has no `TableElement.to_table` method (class starts at
   line 2478; the blank run at lines 3460–3545 is where it belongs, immediately before
   `from_table`) and no `VOTableFile.get_first_table` method (class's `iter_tables` is at
   line 4490; the gap for a new method sits between `iter_tables` and the
   `get_table_by_id`/`get_table_by_index` lookups at lines 4508–4537). The inverse
   conversion, `TableElement.from_table` (line 3547), already exists and is the
   authoritative reference for which `Table.meta` keys round-trip (`ID`, `name`, `ref`,
   `ucd`, `utype`, `description`). `TableElement.__repr__`/`__bytes__`/`__str__` (lines
   2551–2560) already call `self.to_table()`, so they raise `AttributeError` today.
   `TableElement._empty` is set at lines 2518, 2828 and 2834 and is readable directly;
   the public `is_empty()` accessor is also absent, but nothing in the package calls it.
3. `astropy/table/table.py`'s `Table.__init__` (line 711) already dispatches ndarray
   input to `self._init_from_ndarray` for both structured arrays (line 822) and
   homogeneous 2-D arrays (line 826), and the ordinary list path
   `_init_from_list`/`_init_from_cols` (lines 1263, 1500) is the working sibling
   implementation to model column-building on — but `_init_from_ndarray` itself does not
   exist. `Table.add_column` (singular) does not exist either (blank run at lines
   2380–2480). The dependency runs the *opposite* way from what the method names
   suggest: `Table.add_columns` (plural, line 2481) is present but its body (lines
   2580–2588) is a loop over `self.add_column(...)`, so `add_columns` is broken today and
   `add_column` is the primitive that must carry the conversion, broadcasting,
   length-checking, renaming and insertion logic. `add_column` must not delegate to
   `add_columns`; that would recurse infinitely. The blast radius is wider than the two
   method names suggest: `Table.__setitem__` routes every new string key to
   `self.add_column(value, name=item, copy=True)` (line 2140), so `t['new'] = data`,
   `Table.setdefault` (line 3505) and `Table.update` are all broken today as well.
4. `astropy/io/votable/converters.py`'s `UnicodeChar` class (line 423) wires
   `self.binparse = self._binparse_var` / `self.binoutput = self._binoutput_var` for
   `arraysize == "*"` or a bounded-variable arraysize (e.g. `"20*"`), but neither method
   is defined on `UnicodeChar`. The sibling `Char` class (line 299) spells out the
   protocol to mirror in `Char._binparse_var` (line 382) and `Char._binoutput_var` (line
   398): a 4-byte big-endian length prefix followed by 1-byte-per-character ASCII data —
   which `UnicodeChar` must mirror with UTF-16-BE's 2 bytes per code unit. (`Char`'s own
   methods additionally call `self._parse_length`/`self._write_length`, which are not
   defined on `Converter`; this spec does not require adding them — see Out of Scope —
   `UnicodeChar._binoutput_var`/`_binparse_var` can implement the 4-byte prefix inline,
   exactly as their own docstrings in the Interface Description specify.)

## Motivation

Each gap currently breaks a working call path: `np.concatenate`/`np.stack`/`np.choose`/
`np.select`/`np.quantile`/`np.percentile`/`np.nanmedian` on `Quantity` raise `NameError`
inside `astropy`; VOTable files cannot be converted to `astropy.table.Table` or have
their first data table selected; `Table(ndarray)`, `Table.add_column(...)`,
`Table.add_columns(...)` and plain `t['new'] = data` assignment — all documented,
commonly used entry points — do not work; and
BINARY-format VOTable files containing variable-length `char` or `unicodeChar` fields
cannot be read or written.

The four items are *not* fully independent, despite being in four different files:
`TableElement.to_table` (item 2) builds its result with `Table(self.array, names=...,
meta=...)`, and `self.array` is a structured `numpy.ma.MaskedArray`, so
`Table.__init__` routes it straight to `_init_from_ndarray` (item 3, table.py:820-824).
Item 3 must land before any of item 2's scenarios can pass. Items 1 and 4 are
independent of everything else.

## Proposed Solution

### Overview

Implement the missing callables exactly as named and located in the Interface
Contract below, each by following the pattern already established by a working sibling
in the same file (`Char` for `UnicodeChar`, `_init_from_list`/`_convert_data_to_col` for
`_init_from_ndarray`, `from_table` for `to_table`, `get_table_by_index` for
`get_first_table`). No other public behavior changes, and no existing definition is
edited — every callable below fills a hole its existing callers already reference by
name. Internal decomposition (e.g. whether `_iterable_helper` is written as one function
or factored into smaller private helpers) is the implementing agent's choice; only the
Interface Contract's four named callables and their observable behavior are the
contract.

### Key Components

- **`_iterable_helper`** — `astropy/units/quantity_helper/function_helpers.py`. Converts
  a tuple of array-like arguments to plain arrays in a common unit, and handles an
  optional `out=`: if `out` is a `Quantity`, it puts the bare `ndarray` view into the
  returned `kwargs` (`kwargs["out"] = out.view(np.ndarray)`) while returning the
  **original `Quantity`** as the fourth element, because callers rely on `result is out`
  after the numpy call runs in-place. Unit selection across the input arguments: the unit
  comes from the first argument that carries an explicit (non-dimensionless-by-default)
  unit; a bare `ndarray` argument with no unit does not by itself force the common unit to
  dimensionless if a later argument has an explicit unit. Returns the 4-tuple
  `(tuple_of_arrays, kwargs, unit, out)` — `nanmedian` (line 867) returns that tuple
  verbatim and `quantile` (line 853) unpacks it as `(a,), kwargs, unit, out`, so the
  shape is fixed. Used by `concatenate`, `stack` (via `concatenate`'s machinery),
  `choose`, `select`, `quantile` and `nanmedian`.
- **`TableElement.to_table`** — `astropy/io/votable/tree.py`. Builds an
  `astropy.table.Table` from `self.array`, `self.fields`, and table-level ID/name/ref/
  ucd/utype/description, mirroring `from_table`'s meta-key set in reverse. Column names
  come from each `Field`'s `ID` by default and from its `name` (uniquified) when
  `use_names_over_ids=True`; per-column attributes are then applied by calling
  `field.to_table_column(column)` for each field. Note the cross-item dependency:
  `self.array` is a structured `numpy.ma.MaskedArray`, so `Table(self.array, ...)`
  dispatches to `_init_from_ndarray` below.
- **`VOTableFile.get_first_table`** — `astropy/io/votable/tree.py`. Returns the first
  `TableElement` from `self.iter_tables()` whose `_empty` attribute is `False`.
- **`Table._init_from_ndarray`** — `astropy/table/table.py`. Splits a structured or
  homogeneous ndarray into per-column data (`data[field]` for each dtype field name;
  `data[:, i]` for each of the `n_cols` columns of a 2-D array), resolves each column's
  name as the caller-supplied `names[i]` when it is not `None` and otherwise the dtype
  field name (structured) or the `_auto_names` default `col{i}` (homogeneous), and then
  builds the table through the same `_init_from_list`/`_convert_data_to_col`/
  `_init_from_cols` path the list branch uses. `copy=True` copies the data; `copy=False`
  produces columns that share memory with the input array, matching `copy=False`
  elsewhere in `Table.__init__`. It must accept a structured `numpy.ma.MaskedArray` and
  keep each field's mask: indexing a masked structured array per field yields a
  `MaskedArray`, which `_convert_data_to_col` already turns into a `MaskedColumn`, so an
  implementation that first flattens the input through `np.asarray` or a plain `.view`
  silently drops every mask. This is the path `TableElement.to_table` depends on, and S2
  is its end-to-end check.
- **`Table.add_column`** — `astropy/table/table.py`. The primitive that `add_columns`
  already loops over (table.py:2580-2588), so it must do the work itself rather than
  delegate: default `default_name` to `f"col{len(self.columns)}"`, convert `col` via
  `self._convert_data_to_col(col, name=name, copy=copy, default_name=default_name)`,
  broadcast a scalar or length-1 column to `len(self)`, raise
  `ValueError("Inconsistent data column lengths")` — that exact string, with nothing
  appended — on a length mismatch against an existing table, uniquify the
  name as `f"{name}_{i}"` for `i = 1, 2, …` when
  `rename_duplicate` is set and the name is taken, call
  `self._set_col_parent_table_and_mask(col)` (table.py:1595), append to `self.columns`,
  and — when `index` is not `None` — move the columns from `index` onward back to the end
  so the new column lands *before* the original column at `index`.
- **`UnicodeChar._binoutput_var`** / **`UnicodeChar._binparse_var`** —
  `astropy/io/votable/converters.py`. UTF-16-BE analogs of `Char._binoutput_var` /
  `Char._binparse_var`: a 4-byte big-endian length prefix (count of UTF-16 code units,
  not bytes or code points) followed by that many code units encoded/decoded as
  UTF-16-BE — i.e. `_write_length(len(encoded) // 2) + encoded` on output and
  `read(length * 2).decode("utf_16_be")` on input.

### Interface Contract

```python
# astropy/units/quantity_helper/function_helpers.py
def _iterable_helper(*args, out=None, **kwargs):
    """Convert args to Quantity in a common unit; return (arrays, kwargs, unit, out)."""

# astropy/io/votable/tree.py
class TableElement:
    def to_table(self, use_names_over_ids=False) -> "astropy.table.Table": ...

class VOTableFile:
    def get_first_table(self) -> "TableElement": ...  # raises IndexError if none

# astropy/table/table.py
class Table:
    def _init_from_ndarray(self, data, names, dtype, n_cols, copy) -> None: ...

    def add_column(
        self, col, index=None, name=None, rename_duplicate=False,
        copy=True, default_name=None,
    ) -> None: ...

# astropy/io/votable/converters.py
class UnicodeChar:
    def _binoutput_var(self, value: str | None, mask: bool) -> bytes: ...
    def _binparse_var(self, read) -> tuple[str, bool]: ...
```

- `_iterable_helper` raises `NotImplementedError` if `out` is supplied and is not a
  `Quantity`. Reached through `np.concatenate`, that `NotImplementedError` is caught by
  `Quantity.__array_function__` (quantity.py:1885) and re-surfaced by
  `_not_implemented_or_raise` (quantity.py:1937-1951) as a **`TypeError`**, because the
  plain `ndarray` passed as `out` is among the dispatch `types`. Both levels are part of
  the contract.
- When `out` is a `Quantity`, `np.concatenate(..., out=out)` returns that same object
  (`result is out`) carrying the common unit, not a new `Quantity`.
- `_iterable_helper` propagates `UnitConversionError` (from the underlying `Quantity`
  unit-conversion machinery) when input units are mutually incompatible, and raises
  `NotImplementedError` (never `TypeError` directly) when an argument cannot be made into
  a `Quantity`; through a public `numpy` entry point such as `np.concatenate` this
  surfaces as `TypeError` via the `__array_function__` mechanism (see the `TypeError`
  bullet below).
- `to_table` preserves per-column `unit`, `description`, and VOTable-specific
  metadata (`ucd`, `utype`, `width`, `precision`, `xtype`) exactly as
  `Field.to_table_column` (line 1719) sets them, and preserves masked values from
  `self.array`'s mask.
- `get_first_table` raises `IndexError` when every table in `self.iter_tables()` has
  `_empty is True` (including the empty-file case).
- `_init_from_ndarray` and `add_column` leave the signature and behavior of every
  currently-working `Table` code path (`_init_from_list`, `_init_from_dict`,
  `add_columns`, etc.) as they are: after this change those paths produce the same
  columns, names, dtypes and errors for the same inputs as before.
- `add_column` uniquifies a duplicate name as `f"{name}_{i}"` starting at `i = 1` only
  when `rename_duplicate=True` (`add_columns`'s documented example, table.py:2544-2553).
  With `rename_duplicate=False` a duplicate name raises `ValueError` — `add_column`
  inserts through `TableColumns.__setitem__`, which refuses to replace an existing
  column (table.py:283-298). The existing test `TestAddColumns.test_add_duplicate_column`
  (test_table.py:668-703) already pins both halves, including the `a`, `a_1`, `a_2`,
  `a_3` progression across repeated calls.
- `UnicodeChar._binoutput_var` returns 4 zero bytes (no data) when `mask` is `True`, or
  `value` is `None` or `""`.
- For a bounded-variable `arraysize` (e.g. `"5*"`), `UnicodeChar._binoutput_var` and
  `UnicodeChar._binparse_var` emit `W46` when the value's length **in characters**
  exceeds that bound (not its length in bytes), mirroring `Char._binoutput_var`
  (converters.py:407-408) and `Char._binparse_var` (converters.py:385-386); neither
  method truncates.
- `UnicodeChar._binparse_var` returns `mask=False` for every input (unicodeChar has no
  null encoding in BINARY format, matching the existing `Char._binparse_var` and the
  class docstring "Missing values are not handled for string or unicode types").

## Out of Scope

- The `NUMPY_LT_2_4` branch of `concatenate` at
  `astropy/units/quantity_helper/function_helpers.py:492` (`else: pass`, the NumPy ≥ 2.4
  positional-only `concatenate(arrays, /, ...)` form) — the existing `if NUMPY_LT_2_4:`
  branch already calls `_iterable_helper` correctly, so supplying `_iterable_helper`
  alone makes that branch functional without touching the `else` branch. Consequence to
  plan tests around: on a NumPy ≥ 2.4
  interpreter nothing registers a `concatenate` helper, so `np.concatenate` on `Quantity`
  is never intercepted and the scenarios below that reach `_iterable_helper` *through*
  `np.concatenate` (S1, S14, S15, S16, S17) are only exercisable under NumPy < 2.4 and
  must be skipped otherwise. S18 and S19 reach `_iterable_helper` through
  `np.choose`/`np.select`, which are ungated, so the helper stays covered on any NumPy.
- `UnicodeChar._binparse_fixed` / `UnicodeChar._binoutput_fixed` (the bounded,
  non-variable `arraysize` BINARY path referenced at
  `astropy/io/votable/converters.py:459-460`) — these methods do not exist anywhere in
  the class today, and `UnicodeChar.__init__` *binds* `self.binparse =
  self._binparse_fixed` at construction time for a plain numeric `arraysize` (e.g.
  `"10"`), so building such a converter raises `AttributeError` before any data is read.
  **Decision:** stays out of scope. The Interface Description this spec implements names
  only `_binoutput_var`/`_binparse_var` (the `"*"` / bounded-variable-`"N*"` path); the
  fixed-length case is a separate, pre-existing gap on a code path this spec's four
  interfaces do not touch. Consequence for test authors: do not reuse
  `tests/data/regression.xml` (`fixed_unicode_test` at line 44, `arraysize="10"`) or
  `tests/data/parquet_binary.xml` (line 7, `arraysize="10"`) as fixtures for this spec's
  scenarios, and do not extend
  `test_converter.py::test_oversize_unicode`/`::test_unicode_mask` (both `arraysize="1"`,
  the fixed path) — build minimal fixtures with `arraysize="*"` or `"N*"` instead, as S7,
  S12, and S13 already do.
- `Converter._parse_length` / `Converter._write_length` and `_as_quantity` /
  `_quantities2arrays` — real, currently-undefined names referenced elsewhere in
  `converters.py` and `function_helpers.py` respectively (e.g. `Char._binparse_var` at
  converters.py:383 calls `self._parse_length`, which does not exist, so `Char`'s own
  variable-length path is separately broken today). None of the four interfaces in this
  spec require them: `UnicodeChar._binoutput_var`/`_binparse_var` can inline the 4-byte
  length prefix directly (their own docstrings specify the exact byte layout), and
  `_iterable_helper` can perform its unit/array conversion without a separate
  `_quantities2arrays` function. Leaving these undefined does not block any scenario
  below.
- `bitarray_to_bool`, `bool_to_bitarray`, and `_make_masked_array` in
  `astropy/io/votable/converters.py` — undefined module-level helpers used by `bit`-type
  and other variable-length *array* converters (not `UnicodeChar`), reached by e.g.
  `tests/data/regression.xml`'s `bit` fields (lines 71-74, 92). Outside this spec's four
  named interfaces; do not use fixtures containing `bit` fields for scenarios in this
  spec.
- `Table.add_columns` (plural) — its full body is already present at
  `astropy/table/table.py:2481` and its loop (lines 2580-2588) already calls
  `self.add_column(...)`, so implementing `add_column` is what makes `add_columns` work;
  `add_columns` itself needs no edit.
- `TableElement.from_table` and `Field.to_table_column` — already implemented; `to_table`
  reuses them as-is.
- Any VOTable format other than BINARY (TABLEDATA/XML text encoding, BINARY2) for the
  `unicodeChar` variable-length case — `parse`/`output` (text-format methods, already
  implemented at converters.py:464-472) are unaffected by this spec.

## Acceptance Scenarios

### Happy Path

- **S1:** Given `q1 = [[0., 1., 2.]] * u.m` and `q2 = [[0., 100., 200.]] * u.cm`, when
  `np.concatenate([q1, q2])` is called, then the result is a `Quantity` with unit `m` and
  values `[[0., 1., 2.], [0., 1., 2.]]`. (NumPy < 2.4 only; see Out of Scope.)
- **S2:** Given a parsed VOTable with one non-empty `TABLE` element holding a single
  `double` `FIELD` with `ID="flux"`, `unit="Jy"`, a `DESCRIPTION` of `"source flux"`, and
  three rows whose middle value is missing, when `table_element.to_table()` is called,
  then the returned `astropy.table.Table` has a column `"flux"` with
  `unit == u.Jy`, `description == "source flux"`, and `mask == [False, True, False]`.
- **S3:** Given a `VOTableFile` with two `RESOURCE`/`TABLE` elements, when parsed with
  `table_number=1` (skipping the first table) and `votable.get_first_table()` is called,
  then it returns the `TableElement` corresponding to the second (`table_number=1`)
  table, not the skipped first one.
- **S4:** Given a 2-column, 2-row homogeneous `numpy.ndarray` (e.g.
  `np.array([[1, 2], [3, 4]])`), when `Table(data, names=['a', 'b'])` is called, then the
  resulting table has columns `'a'` and `'b'` with values `[1, 3]` and `[2, 4]`
  respectively.
- **S5:** Given a structured `numpy.ndarray` with dtype `[('x', 'i4'), ('y', 'f8')]`,
  when `Table(data)` is called with no `names` argument, then the resulting table's
  column names are `'x'` and `'y'`, taken from the dtype field names.
- **S6:** Given `t = Table([[1, 2], [0.1, 0.2]], names=('a', 'b'))`, when
  `t.add_column(Column(name='c', data=['x', 'y']))` is called with no `index`, then
  `t.colnames == ['a', 'b', 'c']` and `t['c']` holds `['x', 'y']`.
- **S7:** Given a `unicodeChar` `FIELD` with `arraysize="*"`, when a `UnicodeChar`
  converter's `_binoutput_var("héllo", mask=False)` output is fed byte-for-byte into
  `_binparse_var(read)` (where `read` consumes from that byte string), then the
  round-tripped value equals `"héllo"`.
- **S17:** Given `q1 = [[0., 1., 2.]] * u.m`, `q2 = [[0., 100., 200.]] * u.cm` and
  `out = np.empty((2, 3)) * u.dimensionless_unscaled`, when
  `np.concatenate([q1, q2], out=out)` is called, then the returned object *is* `out`
  (same object), `out.unit == u.m`, and `out` holds `[[0., 1., 2.], [0., 1., 2.]]`.
  (NumPy < 2.4 only.)
- **S18:** Given `a = np.array([0, 1]).reshape(2, 1)`, `q1 = [1., 2.] * u.cm` and
  `q2 = [-1., -2.] * u.m`, when `np.choose(a, (q1, q2))` is called, then the result is a
  `Quantity` in `cm` whose second row is `[-100., -200.]`. This path is not gated by
  `NUMPY_LT_2_4`, so it proves `_iterable_helper` on any supported NumPy.
- **S27:** Given `t = Table([[1, 2]], names=('a',))`, when `t['b'] = [3, 4]` is assigned,
  then `t.colnames == ['a', 'b']` and `t['b']` holds `[3, 4]` — `Table.__setitem__`
  reaches `add_column` for every new string key (table.py:2139-2140), so this is the
  entry point most of the existing table suite depends on.

### Edge Cases

- **S8:** Given `t = Table([[1, 2], [0.1, 0.2]], names=('a', 'b'))`, when
  `t.add_column(['x', 'y'], name='c', index=1)` is called, then the column order is
  `['a', 'c', 'b']` — the new column lands *before* the column that was at position 1
  (matching the `index` semantics documented on `add_columns`, table.py:2532-2542).
- **S9:** Given `t = Table([[1, 2], [0.1, 0.2]], names=('a', 'b'))`, when
  `t.add_column(1.1, name='b', rename_duplicate=True)` is called, then `t.colnames ==
  ['a', 'b', 'b_1']`, the new `'b_1'` column holds the scalar broadcast to `[1.1, 1.1]`,
  and the original `'b'` still holds `[0.1, 0.2]` (the `b_1` name is the format
  `add_columns`'s own documented example produces, table.py:2544-2553).
- **S10:** Given a `VOTableFile` where every `TABLE` element was skipped during parsing
  (e.g. `table_number` selected an index beyond the last table, so `_empty` is `True` for
  every table, or the file has zero `TABLE` elements), when `get_first_table()` is
  called, then it raises `IndexError`.
- **S11:** Given a `TableElement` whose two `FIELD` elements both have
  `name="flux"` but different `ID`s, when `to_table(use_names_over_ids=True)` is called,
  then the resulting `Table` has two distinct column names, the first of which is
  `"flux"` and the second of which starts with `"flux"` and has a number appended
  (`docs/io/votable/index.rst:241-245`: "the names may be renamed by appending numbers to
  the end"). The exact suffix format is not part of this contract; a test must assert
  distinctness and the `"flux"` prefix, not a literal second name.
- **S24:** Given the same `TableElement` as S11 (two `FIELD`s with `name="flux"` and
  `ID`s `"col1"` and `"col2"`), when `to_table()` is called with the default
  `use_names_over_ids=False`, then the column names are `['col1', 'col2']` — the `ID`
  attribute, not the `name` attribute.
- **S25:** Given a `TableElement` built by `TableElement.from_table(votable, t)` from a
  `Table` whose `meta` is `{'ID': 'tab1', 'name': 'mytable', 'ucd': 'meta.main',
  'utype': 'stc:x', 'description': 'a test table'}`, when `to_table()` is called on it,
  then the returned `Table`'s `meta` contains those same five keys with those same
  values — the round trip is closed over the key set `from_table` reads
  (tree.py:3553-3559).
- **S12:** Given a `unicodeChar` converter with `arraysize="*"`, when `_binoutput_var` is
  called as `("héllo", mask=True)`, as `(None, mask=False)`, or as `("", mask=False)`,
  then each of the three calls returns exactly `b"\x00\x00\x00\x00"` — a zero length
  prefix and no data, even in the first case where a non-empty value was supplied.
- **S13:** Given a bounded variable-length `unicodeChar` field (`arraysize="5*"`), when
  `_binoutput_var("abcdefgh", mask=False)` is called, then it emits a `W46` warning and
  returns a length prefix of 8 followed by all 8 code units (16 data bytes) — the value
  is not truncated to 5. The bound is compared against the value's length in characters,
  so a 5-character value such as `"abcde"` emits no warning even though it encodes to 10
  bytes.
- **S19:** Given `condlist = [[True, False], [False, True]]` and
  `choicelist = [np.zeros(2), [3., 4.] * u.km]` — the first choice is a plain
  `ndarray` carrying no unit — when `np.select(condlist, choicelist)` is called, then the
  result is a `Quantity` in `km` equal to `[0., 4.] * u.km`: a leading unitless array
  does not force the common unit to dimensionless. This path is not gated by
  `NUMPY_LT_2_4`.
- **S20:** Given `data = np.array([(1, 2.0), (3, 4.0)], dtype=[('x', 'i4'), ('y', 'f8')])`,
  when `t = Table(data, copy=False)` is created and `t['x'][0]` is set to `99`, then
  `data['x'][0]` is also `99` — `copy=False` columns share memory with the input array.
  With `copy=True` (the default), `data['x'][0]` stays `1`.
- **S21:** Given the same structured `data` as S20, when `Table(data, names=['a', 'b'])`
  is created, then the column names are `['a', 'b']` — an explicit `names` argument wins
  over the dtype field names, and the column values still come from the matching dtype
  fields in order (`t['a']` holds `[1, 3]`).
- **S23:** Given an empty `t = Table()`, when `t.add_column(0, name='a')` is called with
  a scalar, then it succeeds: `len(t) == 0`, `t['a']` is a zero-length `Column` with
  `dtype == int`. Adding a length-1 value afterwards (`t['c'] = [1.0]`) still succeeds by
  broadcasting to length 0, while a length-2 value (`t['d'] = [1.0, 2.0]`) raises
  `ValueError` matching `"data column length"`. `add_column` raises **no** `TypeError`
  for a scalar on an empty table — `TestEmptyData.test_scalar` (test_table.py:264-283)
  spells this out ("we used to have setting empty tables succeed, but raise on access.
  Then, we ensured they raised on setting. But now we let setting and accessing
  succeed"), and `Table.setdefault`'s docstring claim of a `TypeError`
  (table.py:3458-3461) is stale in this checkout.
- **S28:** Given a structured `numpy.ma.MaskedArray` with dtype
  `[('x', 'i4'), ('y', 'f8')]`, two rows, and `x` masked in the second row, when
  `Table(data)` is created, then `t['x']` is a `MaskedColumn` whose mask is
  `[False, True]`, and `t['y']`'s mask is all `False` — `_init_from_ndarray` preserves
  per-field masks rather than flattening them away. Assert `t['y']` via
  `not np.any(t['y'].mask)`, not via its column type: indexing a structured
  `MaskedArray` yields a `MaskedArray` for every field, so `t['y']` is legitimately a
  `MaskedColumn` too.

### Error Scenarios

- **S14:** Given `q1 = [1., 2.] * u.m` and `q2 = [3., 4.] * u.s`, when
  `np.concatenate([q1, q2])` is called, then `UnitConversionError` is raised and no
  array is returned. (NumPy < 2.4 only.)
- **S15:** Given `q = [1., 2.] * u.m` and `buf = np.empty(4)` (a plain `numpy.ndarray`,
  not a `Quantity`), when `_iterable_helper(q, q, out=buf)` is called directly, then
  `NotImplementedError` is raised; and when the same call is made through
  `np.concatenate([q, q], out=buf)`, then `TypeError` is raised, because
  `Quantity.__array_function__` converts the helper's `NotImplementedError` into a
  `TypeError` whenever a plain `ndarray` is among the dispatch types
  (quantity.py:1885, 1937-1951). (The `np.concatenate` half is NumPy < 2.4 only.)
- **S16:** Given `np.concatenate([q, object()])` where `object()` cannot be converted to
  a `Quantity`, when called, then a `TypeError` is raised. (NumPy < 2.4 only.)
- **S22:** Given `t = Table([[1, 2], [0.1, 0.2]], names=('a', 'b'))` (2 rows), when
  `t.add_column([1, 2, 3], name='c')` is called, then `ValueError` matching
  `"Inconsistent data column lengths"` is raised and `'c'` is absent from `t.columns` —
  the same contract the existing `test_table_setdefault_wrong_shape`
  (test_table.py:2361-2365) asserts through `setdefault`.
- **S26:** Given `t = Table([[1, 2], [0.1, 0.2]], names=('a', 'b'))`, when
  `t.add_column(Column(name='a', data=[9, 9]))` is called with the default
  `rename_duplicate=False`, then `ValueError` is raised and `t['a']` still holds
  `[1, 2]`.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that would *fail if
> the behavior were wrong*. A green suite that passes for the wrong reason does not
> satisfy this contract — `/verify` will hunt for vacuous tests by asking, of each
> behavior, "what is the smallest change that breaks this, and would any test catch it?"

Implement however you work best — blueprint does not prescribe order, cadence, or commit
structure. Only the result is checked. Write tests to the project's conventions (pytest,
colocated in each module's `tests/` directory, e.g.
`astropy/units/tests/test_quantity_non_ufuncs.py`,
`astropy/io/votable/tests/test_converter.py`, `astropy/io/votable/tests/test_vo.py`,
`astropy/table/tests/test_table.py`) and to these principles (the same ones `/verify`
scores against — see `references/test-desiderata.md` and `references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects (values, units,
  masks, column names, raised exception types), not internals; the suite must survive
  refactoring.
- **Every test can fail** — no copy-pasted expected values, no asserting a constant, no
  tautologies (AP-2, AP-4).
- **Deterministic, isolated, readable** — no cross-test state, AAA structure with inline
  setup.
- Match the exact function/method names, locations, and signatures given in the
  Interface Contract above — the test harness imports these symbols directly.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Test suite is green.
- [ ] Every acceptance scenario (S1…S28) maps to at least one test. Scenarios marked
      "NumPy < 2.4 only" are guarded with `pytest.mark.skipif(not NUMPY_LT_2_4)`; the
      ungated `_iterable_helper` scenarios (S15's direct half, S18, S19) run
      unconditionally.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under the smallest
      break of its behavior (thought-mutation).
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive first); no
      AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale docstrings).

## Trade-offs and Limitations

- Fixed-length (non-variable) `unicodeChar` BINARY encoding remains unimplemented (see
  Out of Scope) — this spec only restores the variable-length path. Note the failure
  mode: `UnicodeChar.__init__` *binds* `self.binparse = self._binparse_fixed`
  (converters.py:459-460) for any non-variable bounded arraysize, so merely constructing
  a converter for a `unicodeChar` field with `arraysize="10"` raises `AttributeError`,
  independent of format. Every VOTable fixture in this spec's scenarios therefore uses
  `arraysize="*"` or the bounded-variable form `"5*"` for `unicodeChar` columns. Existing
  tests and fixtures that do not (test_converter.py `test_oversize_unicode`,
  `test_unicode_mask`; `regression.xml:44`; `parquet_binary.xml:7`) stay red under the
  current fence — see the Out of Scope entry for the evidence.
- The `NUMPY_LT_2_4`-gated `concatenate` behavior for NumPy ≥ 2.4 is untouched; on a
  NumPy ≥ 2.4 interpreter the `else: pass` branch means `np.concatenate` on `Quantity`
  will not be intercepted by this helper at all. This spec targets the `NUMPY_LT_2_4`
  code path per the Interface Description. Because the interpreter's NumPy version is not
  pinned in this checkout (`pyproject.toml` allows `numpy>=2.0.0, <3`), S18 and S19 are
  the scenarios that keep `_iterable_helper` covered either way.
- Several other symbols referenced elsewhere in these two files remain undefined
  (`_as_quantity`, `_quantities2arrays`, `Converter._parse_length`/`_write_length`,
  `bitarray_to_bool`, `bool_to_bitarray`, `_make_masked_array`) — see Out of Scope for
  why none of them block this spec's four interfaces or its scenarios.

## References

- `astropy/units/quantity_helper/function_helpers.py` (module docstring, lines 1–35) —
  describes the `FUNCTION_HELPERS` contract that `concatenate`/`_iterable_helper` must
  satisfy.
- `astropy/io/votable/tree.py:3547` (`TableElement.from_table`) — authoritative source
  for the `Table.meta` key set `to_table` must produce in reverse.
- `astropy/io/votable/converters.py:299-420` (`Char` class) — reference implementation
  of the length-prefixed variable-length BINARY protocol `UnicodeChar` must mirror.
- `astropy/units/tests/test_quantity_non_ufuncs.py:696-734` (`TestConcatenate`) —
  existing, currently-failing tests that pin `_iterable_helper`'s contract: `out is
  result` and `out.unit == q1.unit` for a `Quantity` `out` (lines 723-731), a leading
  plain `ndarray` not overriding the unit (lines 717-721), and `TypeError` for an
  unconvertible argument (lines 733-734).
- `astropy/table/table.py:2568-2588` (`add_columns` body) — proof that `add_columns`
  delegates to `add_column`, not the reverse.
- `docs/io/votable/index.rst:236-245` — the documented (format-unspecified) renaming rule
  for duplicate `name` attributes under `use_names_over_ids=True`.

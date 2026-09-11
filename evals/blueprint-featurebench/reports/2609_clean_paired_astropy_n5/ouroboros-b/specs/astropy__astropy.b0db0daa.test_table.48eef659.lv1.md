# 2609.0001 Unit-Aware Concatenation and Selected Table/VOTable Operations

**Date:** 2026-09-10
**Status:** draft
**Author:** FeatureBench

## Context

The working copy of `astropy` in this repository has had a large number of
code paths intentionally removed (left as blank lines or `pass` stubs)
across four otherwise-complete files. This spec's primary contract is the
eight callables named in the originating task, but investigation (including
an evaluator pass over the actual file contents and call graphs) found that
several of those eight cannot function without other, equally-missing
helpers in the same files — helpers that are called from the eight primary
targets, or from their existing, unmodified callers, or from both. Per this
project's scope rule, goal-adjacent gaps are pulled into scope rather than
fenced off; every such addition below is marked `[INFERRED]`.

**1. `astropy/units/quantity_helper/function_helpers.py`** (the
`Quantity.__array_function__` override machinery):

- `_iterable_helper` is called from `concatenate` (line 488), `choose`
  (line 729), `select` (line 735), `quantile`/`percentile` (line 853), and
  `nanmedian` (line 867) — but is not defined anywhere in the file.
- `concatenate` itself is guarded by `if NUMPY_LT_2_4: ... else: pass`
  (lines 482–493). The installed numpy in this environment is **2.5.3**
  (`NUMPY_LT_2_4` is `False`), so today the `else` branch is a no-op and
  `np.concatenate` is **not registered as a function helper at all** for
  `Quantity` inputs.
- `[INFERRED]` `_quantities2arrays` is called from 15 sites (including
  `_iterable_helper`'s own call chain once restored, `append` at line 792,
  `insert` at 803, `digitize` at 974, `close`/`array_equal`/`array_equiv`
  at 881/891/900) but is not defined anywhere — blank run at lines
  435–481. This, not `_as_quantities`, is the function that derives the
  common output unit; `_as_quantities` (already implemented, lines
  421–432) only converts arguments to `Quantity` objects.
- `[INFERRED]` `_as_quantity` (singular) is called from 21 sites elsewhere
  in the same file (e.g. `invariant_a_helper`, `full_impl`, `close`) but
  is not defined anywhere — blank run adjacent to `_as_quantities`. It is
  not on `concatenate`'s call chain, but leaving it undefined breaks
  numerous already-implemented functions in this file that this spec's
  Definition of Done (a green test suite) depends on.

**2. `astropy/io/votable/tree.py`:**

- `TableElement.to_table` has no definition; the gap sits directly before
  the already-implemented `TableElement.from_table` classmethod (line
  ~3547), which is its mirror image.
- `VOTableFile.get_first_table` has no definition; the gap sits directly
  after `VOTableFile.iter_tables` (line ~4489) and before
  `get_table_by_id`/`get_table_by_index`.
- `[INFERRED]` `TableElement.is_empty` has no definition anywhere in the
  package, yet `self._empty` — the flag it must expose — is written at
  lines 2518 (`False`, on construction), 2828 and 2834 (`True`, when the
  parser skips this table because `table_number`/`table_id` selected a
  different one). `get_first_table` must consult this flag: it is **not**
  a row-count check. A legitimately parsed table with zero rows still has
  `_empty == False` and must still be returned.
- `[INFERRED]` `TableElement._parse_binary` (the BINARY/BINARY2 **read**
  path) is called at lines 2931 and 2937, `self._parse_binary(1, ...)` /
  `self._parse_binary(2, ...)`, but has no definition. Any VOTable fixture
  serialized in BINARY or BINARY2 format fails to parse at all without it,
  which blocks `to_table()`/`get_first_table()` for those fixtures.
- `[INFERRED]` `TableElement._write_binary` (the BINARY/BINARY2 **write**
  path) is called at lines 3383/3385, `self._write_binary(1, w, ...)` /
  `self._write_binary(2, w, ...)`, but has no definition.
- Both `to_table`/`get_first_table` and `_parse_binary`/`_write_binary`
  are exercised pervasively by the existing test suite (e.g.
  `astropy/io/votable/tests/test_vo.py` calls `get_first_table()` at more
  than a dozen call sites and writes/reads BINARY at lines 126, 130, 753,
  798, 828; `astropy/io/votable/connect.py:128` calls
  `table.to_table(use_names_over_ids=...)` from the unified I/O `read()`
  path) — all four are load-bearing, not optional.
- `[INFERRED]` `TableElement._resize_strategy` is called from inside
  `_parse_tabledata` (line 3074) but has no definition — blank run at
  lines 2773–2784. Every TABLEDATA parse whose row count exceeds the
  pre-allocated array size (the common case, since the parser
  pre-allocates and grows) hits this and fails with `AttributeError`
  before `to_table()`/`get_first_table()` are ever reached. The module
  constant `RESIZE_AMOUNT = 1.5` (line 122) and the comment at line 2984
  ("allocation is by factors of 1.5") are the only remaining trace of what
  this method must do; it is on the same growth path `_parse_binary`
  (above) needs to follow for BINARY parsing.
- `[INFERRED]` `Group.entries` (a property), `Group._add_fieldref`, and
  `Group._add_paramref` are referenced at lines 2416, 2421, 2426–2427,
  2453, 2461, 2472 but have no definition — blank run at lines 2393–2409.
  `astropy/io/votable/tests/data/regression.xml`, the fixture behind
  several of this spec's own VOTable scenarios (S2/S3/S12/S15/S28), has
  `GROUP` elements containing `FIELDref`/`PARAMref` children, so parsing
  that fixture — and therefore reaching `get_first_table()` at all — fails
  without these.
- `[INFERRED]` `VOTableFile.iter_values` has no definition (blank run
  adjacent to `iter_tables`), yet `get_values_by_id` (already implemented,
  line ~4585) dispatches through it, and `Values.ref`'s setter (line
  ~1052) already calls `get_values_by_id`. `regression.xml` has a
  `<VALUES ref="...">` element, so parsing that fixture fails without
  this method too.

**3. `astropy/table/table.py`:**

- `Table._init_from_ndarray` is referenced from `Table.__init__` (lines
  822 and 826, for structured and homogeneous ndarrays respectively) but
  not defined anywhere.
- `Table.add_column` is referenced from `Table.add_columns` (line 2581)
  but not defined anywhere either — `add_columns`, and therefore any
  table-construction path that appends/inserts columns one at a time, is
  currently broken.

**4. `astropy/io/votable/converters.py`:**

- `UnicodeChar._binoutput_var` and `UnicodeChar._binparse_var` (BINARY
  serialization for variable-length `unicodeChar` fields, UTF-16-BE
  encoded) are referenced from `UnicodeChar.__init__` (lines 441–442,
  456–457) but not defined. The sibling `Char` converter (7-bit `char`
  datatype) already has fully-written `_binoutput_var`/`_binparse_var`
  (lines ~383–411 of the same file) — the closest in-repo reference for
  the wire format (4-byte big-endian length prefix + payload), adjusted
  for UTF-16 code units instead of raw ASCII bytes. **Do not modify
  `Char`'s methods** — they are already implemented and verified working
  by the existing test suite; integrate with them (e.g. via the shared
  length-prefix helpers below), do not change their behavior.
- `[INFERRED]` `Converter._parse_length` / `Converter._write_length` are
  called by `Char._binparse_var` (383), `Char._binoutput_var` (410), and
  `Array.binparse`/`Array.binoutput` (554, 571) but have no definition —
  blank run at lines 178–186 of the base `Converter` class. `Char`'s own
  variable-length BINARY round trip is currently broken without them, and
  every variable-length array field of every datatype is affected, not
  just `unicodeChar`. Note: `Converter.__init__` itself (line 176, body
  `pass`) is **not** part of this gap — `Char.__init__` and
  `UnicodeChar.__init__` each set their own needed state directly and do
  not rely on base-class initialization; leave `Converter.__init__` as is
  unless investigation before coding proves otherwise.
- `[INFERRED]` `UnicodeChar._binparse_fixed` / `UnicodeChar._binoutput_fixed`
  are bound in `UnicodeChar.__init__` (lines 459–460, the non-variable
  branch) but never defined. Because `field.arraysize is None` is rewritten
  to `"1"` before the branch is chosen (lines 435–437), **any**
  `unicodeChar` FIELD with no explicit `arraysize` takes this fixed path,
  so without these two methods, constructing such a converter succeeds but
  using it for BINARY I/O fails.
- `[INFERRED]` `_make_masked_array`, `bitarray_to_bool`, and
  `bool_to_bitarray` (module-level functions in this file, used by array-
  and bit-valued converters at lines 564, 600, 622, 992, 1015, 1146, 1155)
  have no definition — blank run at lines 73–155. `regression.xml` (the
  fixture backing several scenarios below) has `array`, `bitarray`,
  `bitvararray`, and `booleanArray` columns that exercise these, and the
  BINARY2 per-row NULL bit-mask that `_parse_binary`/`_write_binary`
  (above) must read/write **is** a bit array in this same encoding —
  `bitarray_to_bool`/`bool_to_bitarray` are therefore also a direct
  dependency of this spec's own `_parse_binary`/`_write_binary`, not just
  an adjacent gap.
- `[INFERRED]` `_all_matching_dtype` and `numpy_to_votable_dtype` (used by
  `table_column_to_votable_datatype`, reached via `Field.from_table_column`
  → `TableElement.from_table` → `Table.write(format="votable")`) have no
  definition — blank run at lines 1394–1443. Without them, writing a
  `Table` back out as a VOTable raises `NameError`, which blocks
  `Table.write(..., format="votable")`.
- `[INFERRED]` `BitArray._splitter_lax` has no definition (blank run
  between `BitArray._splitter_pedantic` and `BitArray.output`), yet
  `Array.__init__` binds `self._splitter = self._splitter_lax` whenever
  `config.get("verify", "ignore") != "exception"` — the default parsing
  mode. `regression.xml` defines `bit`/`bitarray`/`bitvararray` FIELDs, so
  every default-mode TABLEDATA parse of that fixture needs this method.

## Motivation

These callables are prerequisites for large, pre-existing swaths of the
astropy test suite (`astropy/units/tests/test_quantity_non_ufuncs.py`,
`astropy/io/votable/tests/test_vo.py`, `astropy/io/votable/tests/test_converter.py`,
`astropy/table/tests/test_init.py`, `astropy/table/tests/test_table.py`) to
even run past setup, since fixtures and other tests in those files call
`get_first_table()`, `to_table()`, `add_column()`, table construction from
ndarrays, and `np.concatenate` on `Quantity` objects. Leaving any one of
them broken cascades into unrelated-looking failures elsewhere in the
suite.

## Proposed Solution

### Overview

Restore each missing callable to behave exactly as the rest of its module
already assumes, using already-implemented sibling code in the same file
as the behavioral template: `_as_quantities` for `_as_quantity` and
`_quantities2arrays`; `TableElement.from_table` for `to_table`;
`VOTableFile.get_table_by_index` for `get_first_table`; `_parse_tabledata`/
`_write_tabledata` for `_parse_binary`/`_write_binary`; `Table.add_columns`
and `Table._convert_data_to_col` for `add_column`; and `Char`'s
`_binoutput_var`/`_binparse_var`/`_binoutput_fixed` (referenced via its
already-defined `_struct_format` pattern) for `UnicodeChar`'s equivalents.
No new files, no public API renames, no changes to any method signature
beyond what the Interface Contract specifies.

### Key Components

**Units:**

- **`_as_quantity(a)`** `[INFERRED]` — converts a single argument to
  `Quantity` (`Quantity(a, copy=COPY_IF_NEEDED, subok=True)`), raising
  `NotImplementedError` on failure, mirroring the already-present
  `_as_quantities` (plural) at line 421.
- **`_quantities2arrays(*args, unit_from_first=False)`** `[INFERRED]` —
  determines a common output unit from `*args`: the first argument's unit
  when `unit_from_first=True`; otherwise the unit of the first argument
  that carries an explicit, non-dimensionless unit, falling back to the
  first argument's unit if none do. Converts each argument's value to that
  common unit and returns `(arrays, unit)`. Observable contract (see
  `array_equal`'s existing `except UnitConversionError` at line 892, and
  `test_concatenate` in `test_quantity_non_ufuncs.py`, which this
  function's behavior must satisfy): a plain array/scalar argument (not a
  `Quantity`), or the values `0`/`inf`/`nan`, are accepted as already
  being in the common unit rather than rejected as dimensionless (S10);
  a `Quantity` argument with a genuinely incompatible unit raises
  `UnitConversionError` (S20); an argument that cannot be interpreted as
  array-like at all raises `NotImplementedError`, which the
  `__array_function__` dispatch machinery surfaces to the caller as
  `TypeError` (S22). How the common-unit and per-argument conversion is
  implemented internally (e.g. via `Quantity._to_own_unit` against the
  chosen reference unit, or via `_as_quantities` plus explicit
  `to_value` calls) is an implementation choice — match the three
  observable behaviors above, not a specific internal call sequence.
- **`_iterable_helper(*args, out=None, **kwargs)`** — pops and validates
  `out`: if `out` is a `Quantity`, `kwargs['out']` becomes
  `out.view(np.ndarray)`; if `out` is given and is not a `Quantity`, raises
  `NotImplementedError`. Calls `_quantities2arrays(*args)` to get
  `(arrays, unit)`. Returns `(arrays, kwargs, unit, out)` (the original
  `out` Quantity, not the view).
- **`concatenate(arrays, axis=0, out=None, **kwargs)`** — already
  decorated with `@function_helper` and already calls `_iterable_helper`
  for the `NUMPY_LT_2_4` branch; only `_iterable_helper` and
  `_quantities2arrays` were missing for that branch to work. For
  **NumPy ≥ 2.4** (the version installed here), add the missing `else`
  branch: a `@function_helper`-decorated `concatenate` matching NumPy's
  own ≥2.4 signature, with `arrays` **positional-only**
  (`concatenate(arrays, /, axis=0, out=None, **kwargs)`), delegating to
  the same `_iterable_helper` call and returning the same four-tuple
  shape.

**VOTable:**

- **`TableElement.is_empty(self)`** `[INFERRED]` — returns `self._empty`.
- **`TableElement.to_table(self, use_names_over_ids=False)`** — builds an
  `astropy.table.Table` from `self.array` (a masked structured array) and
  `self.fields`. Per field: column name is `field.ID` by default (when
  `use_names_over_ids=False`), or `field.name` when
  `use_names_over_ids=True`, de-duplicated by appending sequential numbers
  on collision (e.g. `name`, `name_1`, `name_2`). Each `Field`'s
  `to_table_column` (already implemented, line ~1719) is the mechanism
  used to carry unit/description/ucd/utype/meta onto the resulting
  `Column`. Table-level `meta` is populated from `self.ID`, `self.name`,
  `self.ref`, `self.ucd`, `self.utype`, `self.description` — only for
  keys whose underlying attribute is not `None`. Masking on `self.array`
  is preserved on the output table.
- **`VOTableFile.get_first_table(self)`** — returns the first element
  yielded by `self.iter_tables()` for which `table.is_empty()` is
  `False`; raises `IndexError` if every table is empty (including the
  case of zero tables).
- **`TableElement._parse_binary(self, mode, iterator, colnumbers, config, pos)`** `[INFERRED]` —
  reads a BINARY (`mode=1`) or BINARY2 (`mode=2`) `<STREAM>` payload and
  returns the resulting masked structured array, following the structural
  pattern already used by the sibling `_parse_tabledata(self, iterator,
  colnumbers, config)` (line 2980) but reading fixed-width binary records
  via each field's `converter.binparse`/`converter.arraysize` instead of
  TABLEDATA XML text; for `mode=2`, a leading per-row NULL bit-mask (one
  bit per field, big-endian byte order) precedes each record and marks
  masked cells directly instead of relying on each converter's own mask
  return value.
- **`TableElement._write_binary(self, mode, w, **kwargs)`** `[INFERRED]` —
  the write-side mirror of `_parse_binary`, following the structural
  pattern of the sibling `_write_tabledata(self, w, **kwargs)` (line
  3391) but emitting a `<STREAM>` of fixed-width binary records via each
  field's `converter.binoutput`; for `mode=2`, emitting the per-row NULL
  bit-mask ahead of each record's field values.
- **`TableElement._resize_strategy(self, size)`** `[INFERRED]` — returns
  the next row-allocation size for the array `_parse_tabledata`/
  `_parse_binary` are growing, following the "factors of 1.5" growth
  policy already named in a comment beside its call site (line 2984) and
  using the module constant `RESIZE_AMOUNT = 1.5` (line 122) as the
  growth-rate intent, not as a literal formula: the returned value must be
  **strictly greater than** `size` for every `size >= 0`, including
  `size == 0` (a naive `int(size * RESIZE_AMOUNT)` does not grow from 0
  and would infinite-loop the caller at line 3073, since no TABLE in the
  reference fixture carries an explicit `nrows` and the allocation starts
  at 0 for those).
- **`VOTableFile.iter_values(self)`** `[INFERRED]` — recursively yields
  `field.values` for every element of `self.iter_fields_and_params()`, in
  document order. Needed so that `get_values_by_id` (already implemented
  via `_lookup_by_attr_factory(..., "iter_values", ...)`, line ~4585)
  works, which `Values.ref`'s setter (line ~1052) already calls to
  resolve a VALUES element's `ref` attribute to another VALUES element
  earlier in the document.
- **`Group.entries`** `[INFERRED]` (property) — returns `self._entries`,
  the `HomogeneousList` already constructed in `Group.__init__` (line
  2369) to hold `FieldRef`/`ParamRef`/`Group`/`Param` children.
  **`Group._add_fieldref`/`Group._add_paramref`** `[INFERRED]` — construct
  a `FieldRef`/`ParamRef` from `self._table` and the parsed element
  attributes and append it to `self.entries`, mirroring the
  already-implemented `Group._add_param` (lines 2410–2417).

**Table:**

- **`Table._init_from_ndarray(self, data, names, dtype, n_cols, copy)`** —
  for a structured array (`data.dtype.names` is not `None`): one column
  per field, name precedence `names[i]` (if given) else
  `data.dtype.names[i]`; per-column `dtype` from `dtype[i]` if given else
  inferred from the field. For a homogeneous 2-D array: one column per
  index along `axis=1` (`data[:, i]`); `names`/`dtype` are **not**
  guaranteed to be populated for this branch — `Table.__init__` only
  builds `default_names` from dtype field names for the structured case
  (line 824), so `names` can arrive as a list of `None` (one per column).
  When a given column's name is `None`, the resulting column falls back
  to the same auto-naming (`col0`, `col1`, ...) that
  `self._init_from_list`/`_auto_names` already produce for unnamed
  columns elsewhere in the class. Delegates to `self._init_from_list` /
  `self._convert_data_to_col` / `self._init_from_cols` for column
  construction and honors `copy` exactly as those already do.
- **`Table.add_column(self, col, index=None, name=None, rename_duplicate=False, copy=True, default_name=None)`** —
  converts `col` via `self._convert_data_to_col(col, copy, default_name or
  f"col{len(self.columns)}", None, name)`, broadcasting scalars/length-1
  objects to the table's row length when the table is non-empty. If
  `rename_duplicate` and the resulting name already exists in
  `self.colnames`, uniquifies it by appending `_1`, `_2`, ... . If `index`
  is `None`, appends the column to the end; otherwise inserts it before
  the current column at position `index`. If `rename_duplicate` is
  `False` (the default) and the resulting name already exists in
  `self.colnames`, raises `ValueError` and leaves the table unchanged. If
  `col`'s length does not match the table's current row count (for a
  non-empty table and a non-scalar `col`), raises `ValueError`. Must
  satisfy `Table.add_columns`, which already calls
  `self.add_column(...)` once per column (line 2581).

**VOTable converters:**

- **`Converter._parse_length(self, read)`** `[INFERRED]` — reads 4 bytes
  via `read(4)` and returns `struct.unpack(">I", ...)[0]` (the big-endian
  unsigned 32-bit length prefix shared by every variable-length BINARY
  encoding).
- **`Converter._write_length(self, length)`** `[INFERRED]` — returns
  `struct.pack(">I", int(length))`, the write-side mirror.
- **`UnicodeChar._binoutput_var(self, value, mask)`** — returns 4 zero
  bytes (`b"\0\0\0\0"`, the module's `_zero_int` constant) when `mask` is
  `True`, or `value` is `None` or `""`. Otherwise: encode `value` as
  UTF-16-BE, compute the number of UTF-16 **code units**
  (`len(encoded) // 2` — a non-BMP character occupies a surrogate pair,
  i.e. 2 code units, not 1), write that count as a 4-byte big-endian
  unsigned integer prefix, and concatenate with the encoded bytes. When
  `self.arraysize` is bounded (a numeric prefix before a trailing `*`,
  not bare `*`) and the code-unit count exceeds `self.arraysize`, emit
  warning `W46` (`vo_warn(W46, ("unicodeChar", self.arraysize), None,
  None)`, matching `Char._binoutput_var`'s call shape) but still write
  the full string, not a truncated one.
- **`UnicodeChar._binparse_var(self, read)`** — reads 4 bytes, unpacks as
  big-endian unsigned 32-bit to get a UTF-16 code-unit count `n`, reads
  `n * 2` bytes, decodes as UTF-16-BE, and returns `(decoded_string,
  False)` — `unicodeChar` never reports a masked value from this path.
  When `self.arraysize` is bounded and `n` exceeds it, emit `W46` the
  same way.
- **`UnicodeChar._binparse_fixed(self, read)` / `UnicodeChar._binoutput_fixed(self, value, mask)`** `[INFERRED]` —
  the fixed-width mirror, keyed off `self._struct_format` (already set in
  `__init__` as `f">{self.arraysize * 2:d}s"`, line 462) and UTF-16-BE
  encode/decode, adapted from `Char._binoutput_fixed`/`_binparse_fixed`
  (lines ~412–420, ~390–396): on parse, unpack the fixed-size byte string,
  strip trailing NUL padding, decode as UTF-16-BE; on output, encode as
  UTF-16-BE (empty bytes when masked), pad/pack to `self._struct_format`.
- **`_make_masked_array(data, mask)`** `[INFERRED]` (module-level) —
  builds and returns the `numpy.ma` masked array that array-valued
  converters' `parse`/`binparse` methods return, given a plain data array
  and a boolean mask array of the same shape. The returned array's dtype
  follows `data`'s dtype (no coercion); a zero-length `data` (the case
  `VarArray.binparse` produces for an empty variable-length cell) returns
  a valid zero-length masked array, not an error.
- **`bitarray_to_bool(data, length)` / `bool_to_bitarray(value)`**
  `[INFERRED]` (module-level) — convert between a big-endian packed-bit
  byte string (the VOTable `bit`/`bitarray` wire encoding) and a boolean
  array of `length` elements; this is the same bit-packing the BINARY2
  per-row NULL mask in `_parse_binary`/`_write_binary` (above) uses.
- **`_all_matching_dtype(column)` / `numpy_to_votable_dtype(dtype, shape)`**
  `[INFERRED]` (module-level) — used by the already-implemented
  `table_column_to_votable_datatype`, whose own docstring (already present
  at lines ~1450–1467) documents the heuristic these two helpers
  implement; that function is reached from `Field.from_table_column` →
  `TableElement.from_table`, i.e. `Table.write(..., format="votable")`.
  `numpy_to_votable_dtype` maps a numpy dtype/shape to a VOTable
  `{"datatype", "arraysize"}` pair via the existing
  `numpy_dtype_to_field_mapping` table (line ~1380). `_all_matching_dtype`
  returns `(dtype, shape)` when every element of an object-dtype column is
  an `ndarray` of one consistent dtype and trailing shape, else
  `(False, ())`.
- **`BitArray._splitter_lax(value, config=None, pos=None)`** `[INFERRED]`
  (staticmethod) — the default-mode (non-`"exception"`-verify) TABLEDATA
  splitter for `bit`/`bitarray` cells: splits `value` into one token per
  bit character (same effective result as the sibling
  `_splitter_pedantic`, i.e. `list(re.sub(r"\s", "", value))`), additionally
  stripping commas and emitting warning `W01` (via `vo_warn(W01, (), config,
  pos)`) when `value` contains a comma — mirroring how the lax/pedantic
  split distinction is already handled for other array-valued converters
  in this file.

### Data Flow

1. `np.concatenate([q1, q2, ...])` on `Quantity` inputs dispatches through
   `Quantity.__array_function__` into the `concatenate` function helper,
   which calls `_iterable_helper` → `_quantities2arrays` to get plain-array
   args/kwargs plus the result unit, calls the real `np.concatenate` on
   the plain arrays, then the existing dispatch machinery — already
   implemented and unchanged by this spec — re-wraps the plain result as
   a `Quantity` in that unit.
2. `votable.parse("file.xml")` → `VOTableFile` → `.get_first_table()` →
   `TableElement` (parsed via `_parse_tabledata` or `_parse_binary`
   depending on format) → `.to_table()` → `astropy.table.Table`. This is
   also the path `Table.read(..., format="votable")` takes via
   `astropy/io/votable/connect.py`.
3. `Table(ndarray_data, names=..., dtype=...)` → `Table.__init__` picks
   `_init_from_ndarray` as `init_func` → columns land in `self.columns`
   via `_init_from_cols`.
4. `table.add_column(col)` / `table.add_columns([...])` → per-column
   conversion via `_convert_data_to_col` → insertion into `self.columns`
   at the requested position.
5. Writing a VOTable stream with format `"binary"`/`"binary2"` calls
   `TableElement._write_binary`, which calls each field's
   `converter.binoutput(value, mask)` — bound to `_binoutput_var` or
   `_binoutput_fixed` for `unicodeChar` fields depending on `arraysize`.
   Reading calls `TableElement._parse_binary`, which calls each field's
   `converter.binparse(read)` — bound to `_binparse_var` or
   `_binparse_fixed` correspondingly.

### Interface Contract

```python
# astropy/units/quantity_helper/function_helpers.py
def _as_quantity(a): ...                                    # [INFERRED]
def _quantities2arrays(*args, unit_from_first=False): ...   # [INFERRED]
def _iterable_helper(*args, out=None, **kwargs):
    """Returns (arrays, kwargs, unit, out); raises NotImplementedError
    if `out` is given and is not a Quantity."""

@function_helper
def concatenate(arrays, axis=0, out=None, **kwargs):
    """NumPy < 2.4 branch (arrays not positional-only)."""

# NumPy >= 2.4 branch to add in the `else:` of `if NUMPY_LT_2_4:` (currently `pass`):
@function_helper
def concatenate(arrays, /, axis=0, out=None, **kwargs):
    """arrays is positional-only, matching numpy>=2.4's own signature."""


# astropy/io/votable/tree.py
class TableElement:
    def is_empty(self) -> bool: ...                          # [INFERRED]
    def to_table(self, use_names_over_ids=False) -> "astropy.table.Table": ...
    def _parse_binary(self, mode, iterator, colnumbers, config, pos): ...  # [INFERRED]
    def _write_binary(self, mode, w, **kwargs): ...           # [INFERRED]
    def _resize_strategy(self, size): ...                     # [INFERRED]

class Group:
    @property
    def entries(self): ...                                    # [INFERRED]
    def _add_fieldref(self, iterator, tag, data, config, pos): ...  # [INFERRED]
    def _add_paramref(self, iterator, tag, data, config, pos): ...  # [INFERRED]

class VOTableFile:
    def get_first_table(self) -> "TableElement":
        """Raises IndexError if no non-empty table exists."""
    def iter_values(self): ...                                 # [INFERRED]


# astropy/table/table.py
class Table:
    def _init_from_ndarray(self, data, names, dtype, n_cols, copy): ...

    def add_column(
        self, col, index=None, name=None, rename_duplicate=False,
        copy=True, default_name=None,
    ): ...


# astropy/io/votable/converters.py
class Converter:
    def _parse_length(self, read): ...                       # [INFERRED]
    def _write_length(self, length): ...                     # [INFERRED]

def _make_masked_array(data, mask): ...                       # [INFERRED]
def bitarray_to_bool(data, length): ...                       # [INFERRED]
def bool_to_bitarray(value): ...                              # [INFERRED]
def _all_matching_dtype(column): ...                          # [INFERRED]
def numpy_to_votable_dtype(dtype, shape): ...                 # [INFERRED]

class BitArray(Array):
    def _splitter_lax(value, config=None, pos=None): ...       # [INFERRED]

class UnicodeChar(Converter):
    def _binoutput_var(self, value, mask) -> bytes: ...
    def _binparse_var(self, read) -> tuple[str, bool]: ...
    def _binoutput_fixed(self, value, mask) -> bytes: ...     # [INFERRED]
    def _binparse_fixed(self, read) -> tuple[str, bool]: ...  # [INFERRED]
```

## Alternatives Considered

### Rewrite `concatenate` without `_iterable_helper`/`_quantities2arrays`

`choose`, `select`, `quantile`/`percentile`, and `nanmedian` all call
`_iterable_helper` too; inlining unit-conversion logic directly into
`concatenate` instead of restoring the shared helpers would require
duplicating the same logic several times, or leaving those other call
sites broken (they are exercised by the same test file this spec's
Definition of Done requires green). Rejected — restore the shared helpers.

### Have `to_table`/`get_first_table` share more code with `from_table`/`get_table_by_index`

Considered making `to_table` a thin wrapper reusing more of `from_table`'s
field-iteration machinery, but `from_table` builds a VOTable *from* a
`Table` (the opposite direction) and shares only the FIELD metadata mapping
(`to_table_column`), not the array/masking assembly. Rejected — the two
methods are each other's inverse, not delegatable to one another.

### Skip `_parse_binary`/`_write_binary` as out of scope

Considered leaving BINARY/BINARY2 support broken since it was not in the
original eight interfaces. Rejected: `to_table()` and `get_first_table()`
cannot be exercised end-to-end against any BINARY-format fixture without
them, and the pre-existing test suite already round-trips tables through
both formats — leaving them out would make the Definition of Done
unreachable for reasons unrelated to the eight named interfaces.

## Acceptance Scenarios

### Happy Path

- **S1:** Given `Quantity([1, 2], u.km)` and `Quantity([3, 4], u.m)`, when
  `np.concatenate([a, b])` is called, then the result is a `Quantity` in
  `u.km` with values `[1, 2, 0.003, 0.004]`.
- **S2:** Given a VOTable file with one non-empty `TABLE` element containing
  a `FIELD` with a `unit` attribute and some masked cells, when
  `votable.get_first_table().to_table()` is called, then the resulting
  `astropy.table.Table` has a column whose `.unit` matches the FIELD's
  unit, whose masked cells are masked in the output, and whose column
  name equals that FIELD's `ID` (not its `name`).
- **S3:** Given a VOTable with two `FIELD`s that have the same `name` but
  different `ID`s, when `to_table(use_names_over_ids=True)` is called,
  then the resulting table has two distinct column names (the second
  suffixed, e.g. `foo` and `foo_1`), and the table's `meta` contains the
  TABLE element's `ID`/`name`/`description` for whichever of those
  attributes are present on the source TABLE.
- **S4:** Given a structured `numpy.ndarray` with named fields (e.g.
  `dtype=[('x', 'i4'), ('y', 'f8')]`), when `Table(data)` is constructed
  with no explicit `names`, then the resulting table's column names equal
  the structured dtype's field names, in order.
- **S5:** Given a homogeneous 2-D `numpy.ndarray` of shape `(n_rows, n_cols)`
  and an explicit `names` list of length `n_cols`, when `Table(data,
  names=names)` is constructed, then column `i` of the table equals
  `data[:, i]` for every `i`.
- **S6:** Given `Table([[1, 2], [0.1, 0.2]], names=('a', 'b'))`, when
  `t.add_column(Column(name='c', data=['x', 'y']))` is called, then `t`
  gains a third column named `c` appended after `b`, with `t['c']` equal
  to `['x', 'y']`.
- **S7:** Given the same table from S6, when `t.add_column(['a', 'b'],
  name='d', index=1)` is called, then column `d` appears immediately
  before the original column `b` (column order becomes `a, d, b`).
- **S8:** Given a `unicodeChar` `FIELD` with unbounded `arraysize="*"` and
  the string `"café"`, when the value is written via `_binoutput_var` and
  then read back via `_binparse_var` from the same byte stream, then the
  round-tripped string equals `"café"` exactly.
- **S9:** Given the same field, when the string contains a non-BMP
  character (e.g. `"\U0001F600"`, one code point but a UTF-16 surrogate
  pair), when written and read back, then the round-tripped string is
  unchanged and the 4-byte length prefix decodes to `2` (two code units),
  not `1`.
- **S10 `[INFERRED]`:** Given a plain (non-`Quantity`) list or
  `numpy.ndarray` as the first argument and `Quantity([3, 4], u.m)` as the
  second, when `np.concatenate([plain_list, q])` is called, then the
  common output unit is `u.m` (established by the second argument, since
  the first has no explicit non-dimensionless unit), matching the pattern
  already pinned by `test_concatenate` in
  `astropy/units/tests/test_quantity_non_ufuncs.py` (`q_list=[np.zeros(...),
  self.q1, self.q2]`).
- **S11 `[INFERRED]`:** Given `Quantity([1, 2], u.m)` and
  `Quantity([3, 4], u.cm)`, when `np.concatenate([q1, q2], out=out)` is
  called with `out = np.empty((4,)) * u.dimensionless_unscaled`, then the
  call returns `out` itself (`out is result`), `out.unit == u.m`, and
  `out`'s values equal the concatenation of `q1.value` and
  `q2.to_value(u.m)` — matching the pattern pinned by `test_concatenate`.
- **S12 `[INFERRED]`:** Given a VOTable fixture whose table is parsed with
  `table_number=1` and has multiple candidate tables (e.g.
  `astropy/io/votable/tests/data/regression.xml`, which has more than one
  `TABLE`), when `votable.get_first_table()` is called, then it returns
  the table at index 1 (not index 0), matching
  `test_parse_single_table2` in `astropy/io/votable/tests/test_vo.py`.
- **S13 `[INFERRED]`:** Given the table parsed from
  `astropy/io/votable/tests/data/regression.xml` (which includes `bit`,
  `bitarray`, and variable-length `unicodeChar` columns among others),
  when it is written and then re-parsed in BINARY format
  (`format="binary"`) and separately in BINARY2 format
  (`format="binary2"`), then each round trip's re-parsed
  `TableElement.array` (and, via `to_table()`, the resulting `Table`)
  equals the original data for every column, including which cells are
  masked — exercising the bit-packing (`bitarray_to_bool`/
  `bool_to_bitarray`) and variable-length masked-array
  (`_make_masked_array`) helpers in both directions.
- **S29 `[INFERRED]`:** Given a `bit`-typed TABLEDATA cell parsed in the
  default verification mode (`config` without `verify="exception"`) with
  `arraysize="2x3"` and a value of six bit characters (e.g. `"101010"`),
  when the field is parsed, then the result is a 2×3 boolean array of the
  six individual bit values, not a single-token parse failure — exercising
  `BitArray._splitter_lax`, the default-mode splitter.
- **S30 `[INFERRED]`:** Given a VOTable with two `VALUES` elements where
  the second has `ref="..."` pointing at the first's `ID` (the pattern
  used by `regression.xml`'s `int_nulls` VALUES), when the file is parsed,
  then the second `VALUES` element inherits the referenced attributes
  (e.g. `null`) from the first — exercising `VOTableFile.iter_values`,
  which `Values.ref`'s setter uses via `get_values_by_id` to resolve the
  reference.
- **S31 `[INFERRED]`:** Given a VOTable `GROUP` element containing a
  `FIELDref`, a nested `GROUP`, and a `PARAMref` child (the pattern in
  `regression.xml`'s GROUP), when the file is parsed, then the `GROUP`'s
  `entries` property yields those three children in document order, and
  writing the parsed `VOTableFile` back out via `to_xml` re-emits the same
  `FIELDref`/`PARAMref` elements — exercising `Group.entries`,
  `Group._add_fieldref`, and `Group._add_paramref`.
- **S32 `[INFERRED]`:** Given `Quantity([1, 2, 4], u.m)` and
  `Quantity([0], u.cm)`, when `np.diff(a, prepend=b)` is called, then the
  result is a `Quantity` in `u.m` with `b`'s value converted to `u.m`
  before differencing — exercising `_as_quantity` (a call site outside
  `_iterable_helper`'s chain), matching the `diff` helper's existing call
  to it at line ~1134.
- **S33 `[INFERRED]`:** Given an `astropy.table.Table` with an
  object-dtype column whose every element is an `ndarray` of the same
  dtype and trailing shape, when the table is written via
  `Table.write(..., format="votable")` and re-parsed, then the emitted
  FIELD's `datatype`/`arraysize` match what `numpy_dtype_to_field_mapping`
  prescribes for that dtype/shape, and the round-tripped column values are
  unchanged — exercising `_all_matching_dtype`/`numpy_to_votable_dtype`.
- **S23 `[INFERRED]`:** Given `Quantity`-valued `choices` sharing a
  compatible unit (e.g. `[Quantity([1, 2], u.m), Quantity([300, 400],
  u.cm)]`) and an integer `a` selecting between them, when
  `np.choose(a, choices)` is called, then the result is a `Quantity` in
  the first choice's unit with the selected values converted accordingly
  — exercising `_iterable_helper`'s other call site (line 729) with the
  same restored helper chain S1 exercises for `concatenate`.
- **S24 `[INFERRED]`:** Given `Quantity([1, 2, 3], u.m)` and
  `out = Quantity(np.empty(()), u.dimensionless_unscaled)`, when
  `np.nanmedian(q, out=out)` is called, then it returns `out` itself with
  `out.unit == u.m`, exercising `_iterable_helper`'s single-argument +
  `out=` call site (line 867), matching `test_nanmedian_out` in
  `astropy/units/tests/test_quantity_non_ufuncs.py`.
- **S27 `[INFERRED]`:** Given a homogeneous 2-D `numpy.ndarray` of shape
  `(3, 2)` and **no** `names` argument, when `Table(data)` is constructed,
  then the resulting table's column names are the auto-generated
  `['col0', 'col1']`, not `[None, None]` — this is the case where
  `Table.__init__` passes an all-`None` `names` list into
  `_init_from_ndarray`.

### Edge Cases

- **S14:** Given `np.concatenate([a, b])` where the first argument has no
  explicit non-dimensionless unit and the second argument has an explicit
  unit, then the common output unit comes from the second argument (see
  S10 for the concrete case).
- **S15:** Given a VOTable file with three tables (indices 0, 1, 2), when
  `parse_single_table(filename, table_number=3)` is called (an index past
  the end, so the parser marks every table `_empty=True` since none
  matches `table_number`), then `get_first_table()` — which
  `parse_single_table` calls internally — raises `IndexError`, matching
  `test_parse_single_table3` in `astropy/io/votable/tests/test_vo.py`.
- **S28 `[INFERRED]`:** Given a VOTable table that parses successfully
  with zero data rows (e.g. `astropy/io/votable/tests/data/regression.xml`'s
  third `TABLE`, an empty `<TABLEDATA/>`, parsed via
  `parse_single_table(filename, table_number=2)`), when
  `get_first_table()` is called, then it **returns** that table
  (`len(table.array) == 0`) instead of raising `IndexError` — this is the
  case that distinguishes `is_empty()` (must be `False` here, since the
  parser did not skip this table) from a row-count check (which would
  wrongly treat a zero-row table the same as a skipped one, contradicting
  S15).
- **S16:** Given `Table([[1, 2], [0.1, 0.2]], names=('a', 'b'))`, when
  `t.add_column(1.1, name='b', rename_duplicate=True)` is called (a scalar
  broadcast to the table's 2 rows, with a name colliding with the existing
  `b`), then the table gains a column named `b_1` with values `[1.1,
  1.1]`, and the original `b` column is unchanged.
- **S17:** Given a `unicodeChar` field with a bounded variable-length
  `arraysize` (e.g. `"5*"`), when `_binoutput_var` is called with a string
  longer than 5 UTF-16 code units, then a `W46` warning is emitted but the
  returned bytes still encode the full string (not truncated to 5).
- **S18:** Given `_binoutput_var` called with `mask=True`, or with
  `value=None`, or with `value=""`, then the return value is exactly the
  4-byte sequence `b"\x00\x00\x00\x00"` in all three cases.
- **S19 `[INFERRED]`:** Given a `unicodeChar` `FIELD` with no explicit
  `arraysize` attribute at all (so it is rewritten to `"1"` and takes the
  fixed-width path), when a converter is constructed for it via
  `get_converter`, then constructing the converter succeeds (a `W47`
  warning is emitted by `UnicodeChar.__init__`, matching the existing
  `test_oversize_char`/`test_oversize_unicode` pattern in
  `astropy/io/votable/tests/test_converter.py`, but no `AttributeError`
  is raised), and a subsequent `_binoutput_fixed`/`_binparse_fixed` round
  trip of a 1-character string preserves that character.

### Error Scenarios

- **S20:** Given `Quantity([1, 2], u.km)` and `Quantity([3, 4], u.s)`
  (incompatible units), when `np.concatenate([a, b])` is called, then
  `astropy.units.UnitConversionError` is raised (the concrete class the
  incompatible-unit conversion path raises via `Quantity.to_value`), and
  no partial result is returned.
- **S21:** Given `np.concatenate([a, b], out=some_plain_ndarray)` where
  `a`, `b` are `Quantity` and `some_plain_ndarray` is a plain
  `numpy.ndarray` (not a `Quantity`), when the call is made, then
  `NotImplementedError` is raised.
- **S22 `[INFERRED]`:** Given `np.concatenate([Quantity([1, 2], u.m),
  object()])` (a non-array-like element mixed into the list), when the
  call is made, then `TypeError` is raised, matching `test_concatenate` in
  `astropy/units/tests/test_quantity_non_ufuncs.py`.
- **S25 `[INFERRED]`:** Given `Table([[1, 2], [0.1, 0.2]], names=('a',
  'b'))`, when `t.add_column(Column(name='a', data=[9, 9]))` is called
  (a name colliding with the existing `a`, with `rename_duplicate=False`,
  the default), then `ValueError` is raised and `t`'s columns are
  unchanged, matching the duplicate-name behavior pinned in
  `astropy/table/tests/test_table.py`.
- **S26 `[INFERRED]`:** Given the same table (2 rows), when
  `t.add_column(Column(name='c', data=[1, 2, 3, 4]))` is called (a
  4-element column against a 2-row table), then `ValueError` is raised,
  matching the length-mismatch behavior pinned in
  `astropy/table/tests/test_table.py`.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*. A green suite that passes for
> the wrong reason does not satisfy this contract.

Implement every callable named in the Interface Contract — both the eight
originally-named interfaces and the `[INFERRED]` prerequisites — in the
files and at the approximate locations described in Context (each sits in
a contiguous run of blank lines directly adjacent to a named,
already-implemented neighbor; use that neighbor as your structural
anchor). Do not rename, relocate, or change the signature of any of them
beyond what this spec specifies (e.g. `concatenate`'s NumPy ≥2.4 signature
must make `arrays` positional-only; nothing else about its call sites
should change).

Before writing any code, re-read `astropy/units/quantity_helper/function_helpers.py`,
`astropy/io/votable/tree.py`, `astropy/io/votable/converters.py`, and
`astropy/table/table.py` in full and confirm the current state of every
callable named above — this spec's Context reflects the state found during
investigation, not a guarantee about what you will find. Do not build on
any claim in this spec (including which functions are "already
implemented") without re-verifying it against the current file contents
first. Do not modify `Char`'s methods, `Field.to_table_column`,
`TableElement.from_table`, `TableElement._parse_tabledata`,
`TableElement._write_tabledata`, `VOTableFile.get_table_by_index`,
`Group._add_param`, `Table.add_columns`, or `Table._convert_data_to_col`
— they are working, already-implemented code that this spec's
restorations must integrate with, not replace.

Write tests to the project's existing conventions (see
`astropy/units/tests/test_quantity_non_ufuncs.py`,
`astropy/io/votable/tests/test_vo.py`,
`astropy/io/votable/tests/test_converter.py`,
`astropy/table/tests/test_init.py`) and to these principles:

- **Behavioral over structural** — assert observable output (values, units,
  masks, column order/names, raised exception types), not internals.
- **Every test can fail** — no copy-pasted expected values, no asserting a
  constant, no tautologies.
- **Deterministic, isolated, readable** — no dependence on test execution
  order; each test builds its own minimal fixture inline.

## Definition of Done

- [ ] Test suite is green, including the pre-existing astropy tests listed
      under Motivation that depend on these callables.
- [ ] Every acceptance scenario (S1–S33) maps to at least one test.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
      the smallest break of its behavior (e.g. flipping which unit wins in
      S1/S10/S14, off-by-one in the S9 surrogate-pair code-unit count,
      wrong insertion side in S7, missing the `W46` warning in S17, using
      a row-count check instead of `is_empty()` in S15/S28, skipping the
      `ValueError` checks in S25/S26, a `_resize_strategy` that fails to
      grow from `size == 0` (breaking the `regression.xml` parse behind
      S2/S3/S12/S13/S15/S28/S30/S31), a `_splitter_lax` that returns one
      token instead of six in S29, wrong document order in S31).
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
      first); no vacuous-test anti-patterns.
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings) left in any of the four touched files.

## Trade-offs and Limitations

- `_parse_binary`/`_write_binary` (S13) are specified at the level of
  "round trip preserves data and masking," not a byte-for-byte wire-format
  description, because the exact BINARY/BINARY2 layout (NULL bit-mask
  placement, per-datatype fixed-vs-variable dispatch) is fully determined
  by the VOTable BINARY specification and by the already-implemented
  `_parse_tabledata`/`_write_tabledata` structural pattern in the same
  class; re-deriving it byte-by-byte here would duplicate that
  specification rather than constrain behavior.
- This spec pulls in every `[INFERRED]` prerequisite found to be on a
  necessary call path for the eight originally-named interfaces to work
  end-to-end against the existing test suite, including two rounds of
  additional prerequisites found by re-reading the call graphs of the
  first round's additions (`_resize_strategy`, `Group.entries`/
  `_add_fieldref`/`_add_paramref`, `_make_masked_array`,
  `bitarray_to_bool`/`bool_to_bitarray`, `_all_matching_dtype`/
  `numpy_to_votable_dtype`). It does not claim to be an exhaustive audit
  of every blank region in these four files — if implementation
  surfaces another missing prerequisite on the path to a listed
  scenario, it is in scope by the same rule that added the ones above,
  even though this document does not name it in advance.

## Open Questions

- [ ] None — all four originating areas, and their discovered prerequisite
      gaps, were resolved against the current state of the repository and
      its existing test suite during investigation.

## References

- `astropy/units/quantity_helper/function_helpers.py` — `_as_quantities`,
  `choose`, `select`, `quantile`, `nanmedian`, `append`, `insert`,
  `digitize` (existing call sites of `_iterable_helper`/`_quantities2arrays`).
- `astropy/units/tests/test_quantity_non_ufuncs.py` — `test_concatenate`
  (pins the `out=` success path, the plain-first-argument unit-selection
  case, and the `TypeError` case for non-array-like elements).
- `astropy/io/votable/tree.py` — `TableElement.from_table`,
  `VOTableFile.get_table_by_index`, `Field.to_table_column`,
  `TableElement._parse_tabledata`, `TableElement._write_tabledata`.
- `astropy/io/votable/tests/test_vo.py` — `test_parse_single_table`,
  `test_parse_single_table2`, `test_parse_single_table3` (pin
  `get_first_table`'s selection and `IndexError` behavior).
- `astropy/io/votable/table.py` — `parse_single_table` (calls
  `get_first_table()` unconditionally after setting `table_number`).
- `astropy/io/votable/connect.py` — unified I/O `read()`, the primary
  caller of `to_table(use_names_over_ids=...)`.
- `astropy/table/table.py` — `Table.add_columns`, `Table._convert_data_to_col`,
  `Table._init_from_cols`.
- `astropy/io/votable/converters.py` — `Char._binoutput_var`,
  `Char._binparse_var`, `Char._binoutput_fixed`, `Char._binparse_fixed`
  (the ASCII sibling implementations used as the behavioral template for
  `UnicodeChar`).
- `astropy/units/tests/test_quantity_non_ufuncs.py` — `test_nanmedian_out`,
  `test_select` (pin the single-argument + `out=` and multi-choice-list
  call sites of `_iterable_helper`/`_quantities2arrays`).
- `astropy/table/tests/test_table.py` — existing `add_column`/`add_columns`
  duplicate-name and length-mismatch tests (pin `ValueError` behavior for
  S25/S26).
- `astropy/io/votable/tests/data/regression.xml` — the fixture behind
  S2/S3/S12/S13/S15/S28/S29/S30/S31, containing GROUP/FIELDref/PARAMref,
  VALUES/ref, and bit/bitarray/unicodeChar FIELDs that exercise the
  round-2 and round-3 `[INFERRED]` prerequisites together.

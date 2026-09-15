# Implementation Brief: Quantity concatenation, VOTable table conversion, ndarray Table init, UnicodeChar binary I/O

Repo root for this task is the current working directory (equivalent to `/testbed`
in the task statement); the astropy package lives at `./astropy/...`, e.g.
`./astropy/units/quantity_helper/function_helpers.py`. All paths below are given
relative to the repo root. The package already imports cleanly
(`python -c "import astropy.units"` succeeds), so none of the gaps described
here break module import — they only fail when the specific missing code paths
are exercised.

There are 4 numbered interfaces plus **one required, unlisted prerequisite**
(`_quantities2arrays`) that interface 1 transitively depends on. Implement all
of them. Do not otherwise refactor these files.

---

## 0. IMPORTANT prerequisite: `_quantities2arrays` (not separately numbered, but required)

File: `astropy/units/quantity_helper/function_helpers.py`

`_iterable_helper` (interface 1) must delegate unit-resolution to a helper
called `_quantities2arrays`. That helper is **called in ~15 places already
in this file** (`append`, `insert`, `close`/`isclose`/`allclose`,
`array_equal`, `array_equiv`, `piecewise`, `where`, `histogram`-family,
`searchsorted`, `in1d`/`isin`, `interp`, `arange_impl`, etc.) but it is
**not defined anywhere in the codebase** (confirmed via AST scan — 0
definitions, 15 call sites). Those call sites are already-correct,
already-tested code; they are simply missing this one piece of shared
plumbing. You must add `_quantities2arrays` for `_iterable_helper` (and by
extension all those other functions) to work.

Evidence for its exact contract, from call sites already in the file:

```python
what, unit = _quantities2arrays(*what)                                   # piecewise
arrays, unit = _quantities2arrays(arr, values, unit_from_first=True)     # append
(arr, values), unit = _quantities2arrays(arr, values, unit_from_first=True)  # insert
(a, b), unit = _quantities2arrays(a, b, unit_from_first=True)            # close/isclose/allclose
args, unit = _quantities2arrays(a1, a2)                                  # array_equal, array_equiv
args, unit = _quantities2arrays(*args)                                   # where
```

So the signature is `_quantities2arrays(*args, unit_from_first=False)`,
returning `(arrays, unit)` where `arrays` is a tuple of plain values (same
length/order as `args`) all expressed in the common `unit` (an astropy
`Unit`).

**Ground truth for the default (`unit_from_first=False`) unit-selection
behavior** is in
`astropy/units/tests/test_quantity_non_ufuncs.py::TestConcatenate.check`
(around line 696-720):

```python
def check(self, func, *args, **kwargs):
    q_list = kwargs.pop("q_list", [self.q1, self.q2])
    q_ref = kwargs.pop("q_ref", q_list[0])
    o = func(q_list, *args, **kwargs)
    v_list = [q_ref._to_own_unit(q) for q in q_list]
    expected = func(v_list, *args, **kwargs) * q_ref.unit
    ...

def test_concatenate(self):
    ...
    self.check(
        np.concatenate,
        q_list=[np.zeros(self.q1.shape), self.q1, self.q2],
        q_ref=self.q1,
    )
```

`self.q1` is in `u.m`, `self.q2 = self.q1.to(u.cm)`. When the first element
of the list is a *plain* `np.zeros(...)` array (no unit → converts to
`dimensionless_unscaled`) and the second element has an explicit unit
(`u.m`), the reference/output unit must be the **second** element's unit
(`u.m`), not the first's dimensionless unit — this matches interface 1's
docstring note: "The first explicit unit normally determines the output
unit. If the first input has no explicit unit and a later input has a
non-dimensionless unit, that later unit can establish the common unit."

Recommended implementation, built from existing helpers already in this
file — reuse `_as_quantities` (already implemented, ~line 421) to convert
raw args to `Quantity`, then pick the reference quantity and use its
`_to_own_unit` (a `Quantity` method that also tolerates all-zero/non-finite
values in any unit, per `astropy/units/quantity_helper/converters.py`'s
`can_have_arbitrary_unit`):

```python
def _quantities2arrays(*args, unit_from_first=False):
    qs = _as_quantities(*args)
    if unit_from_first:
        ref = qs[0]
    else:
        ref = next((q for q in qs if q.unit != dimensionless_unscaled), qs[0])
    unit = ref.unit
    arrays = tuple(ref._to_own_unit(q) for q in qs)
    return arrays, unit
```

Place it directly after `_as_quantities` (around line 429), before its
first use (`arange_impl`, ~line 574).

---

## 1. `_iterable_helper` and `concatenate`

File: `astropy/units/quantity_helper/function_helpers.py`

`concatenate` (inside the `if NUMPY_LT_2_4:` block, ~line 442) is **already
fully implemented** in this file — do not touch it:

```python
if NUMPY_LT_2_4:
    @function_helper
    def concatenate(arrays, axis=0, out=None, **kwargs):
        arrays, kwargs, unit, out = _iterable_helper(
            *arrays, out=out, axis=axis, **kwargs
        )
        return (arrays,), kwargs, unit, out
else:
    pass
```

The only thing actually missing is `_iterable_helper` itself, which is
referenced (undefined) at this call site and at 4 others in the same file:
`choose` (~line 728), `select` (~line 735), `quantile` (~line 853),
`nanmedian` (~line 867). Add it near the top of the file, after
`_quantities2arrays` (see section 0).

Signature: `_iterable_helper(*args, out=None, **kwargs)` →
`(arrays, kwargs, unit, out)`.

- Convert `*args` to arrays/common unit via `_quantities2arrays(*args)`
  (default `unit_from_first=False` — do **not** pass `unit_from_first=True`
  here, since `select`'s use of the returned `unit` for
  `(1 * unit)._to_own_unit(default)` and the concatenate test above both
  rely on the "later non-dimensionless unit can win" behavior).
- Handle `out`: reuse the existing helper `_quantity_out_as_array(out)`
  (already defined in this file, ~line 262) which returns `out.view(np.ndarray)`
  if `out` is a `Quantity`, else raises `NotImplementedError`. Only call it
  if `out is not None`; when called, put the result into `kwargs["out"]`.
  Leave the original `out` (the `Quantity` or `None`) untouched in the
  returned tuple — callers rely on getting the original `Quantity` back
  (see `concatenate`'s call above, and the `TestConcatenate.test_concatenate`
  `out=` case).
- `kwargs` (any extra keyword args passed in, e.g. `axis=`, `mode=`,
  `overwrite_input=`) must be passed through unchanged except for the `out`
  key added/overwritten as above.

```python
def _iterable_helper(*args, out=None, **kwargs):
    if out is not None:
        kwargs["out"] = _quantity_out_as_array(out)
    arrays, unit = _quantities2arrays(*args)
    return arrays, kwargs, unit, out
```

Validate against `astropy/units/tests/test_quantity_non_ufuncs.py`
(`TestConcatenate`, plus `choose`/`select`/`quantile`/`percentile`/
`nanmedian` tests in the same file) and
`astropy/units/tests/test_quantity_array_methods.py` if present.

---

## 2. `TableElement.to_table` and `VOTableFile.get_first_table`

File: `astropy/io/votable/tree.py`

### `TableElement.to_table(self, use_names_over_ids=False)`

Insert as a method of `TableElement` (class starts ~line 2478), placed
right before the existing `from_table` classmethod (~line 3546-3547) — that
is the natural, symmetric counterpart and the file already has a large gap
there. `from_table` (already implemented, read it for the exact reverse
mapping) is:

```python
@classmethod
def from_table(cls, votable, table):
    kwargs = {}
    for key in ["ID", "name", "ref", "ucd", "utype"]:
        val = table.meta.get(key)
        if val is not None:
            kwargs[key] = val
    new_table = cls(votable, **kwargs)
    if "description" in table.meta:
        new_table.description = table.meta["description"]
    for colname in table.colnames:
        column = table[colname]
        new_table.add_field(Field.from_table_column(votable, column))
    if table.mask is None:
        new_table.array = ma.array(np.asarray(table))
    else:
        new_table.array = ma.array(np.asarray(table), mask=np.asarray(table.mask))
    return new_table
```

`to_table` is its inverse:

1. `from astropy.table import Table` (local import — this file already
   does local imports of `astropy.table.Table` elsewhere, e.g. in
   `_parse_parquet`, ~line 3283, to avoid a circular import).
2. Build `meta` dict from `self`'s `ID`, `name`, `ref`, `ucd`, `utype`
   attributes (only include keys whose value is not `None`), plus
   `description` if `self.description is not None` — this is exactly the
   `["ID", "name", "ref", "ucd", "utype"]` list used by `from_table`, mirrored.
3. Construct `table = Table(self.array, meta=meta)`. `self.array` is
   already a `numpy.ma.MaskedArray` with a structured dtype whose field
   *names* are each field's `field.ID` (the real dtype name) and whose
   *titles* are `field._unique_name` when they differ from the ID — see
   `create_arrays` (~line 2714-2771): `id = (x._unique_name, x.ID)` if they
   differ, else just `x.ID`, and `dtype.append((id, x.converter.format))`.
   So `self.array[field.ID]` always retrieves a field's column data, and
   `Table(self.array, ...)` will, by default, name columns after
   `self.array.dtype.names` — i.e. the field **IDs**. This matches the
   `use_names_over_ids=False` (default) behavior described in the docstring.
   `Field.uniqify_names` (already called during parsing, ~line 1439-1473)
   has already ensured both `field.ID` and `field._unique_name` are unique
   across the table, so no further de-duplication is needed here.
4. If `use_names_over_ids` is `True`: for every field in `self.fields`
   whose `field.ID != field._unique_name`, rename that column from
   `field.ID` to `field._unique_name` using `table.rename_columns` (bulk
   form, ~line 3133) or `table.rename_column` per field.
5. For every field in `self.fields`, fetch the corresponding column from
   `table` (keyed by `field._unique_name` if `use_names_over_ids` else
   `field.ID`) and call `field.to_table_column(column)` (already
   implemented, ~line 1719) to copy over `ucd`, `width`, `precision`,
   `utype`, `xtype`, `description`, `unit`, number format, and the
   VOTable-string-dtype/arraysize meta markers used for char/unicodeChar
   round-tripping.
6. Return `table`.

Tests to check against: `astropy/io/votable/tests/test_vo.py` (uses
`vot1.to_table(use_names_over_ids=...)` and
`votable.get_first_table().to_table()`), `astropy/io/votable/tests/test_converter.py`
(`table.to_table()`), and the round-trip reader
`astropy/io/votable/connect.py::read_table_votable`, which already calls
`table.to_table(use_names_over_ids=use_names_over_ids)` (~line 128) — so
`io.votable` file reading end-to-end depends on this method.

### `VOTableFile.get_first_table(self)`

Insert as a method of `VOTableFile` (class starts ~line 4138), in the blank
gap right after `iter_tables` (~line 4489-4501) and before
`get_table_by_id`.

Each `TableElement` has a boolean attribute `_empty` (default `False`, set
in `TableElement.__init__` ~line 2518) that becomes `True` when the table
was skipped during parsing — e.g. because of the `table_number` or
`table_id` `parse()` kwargs (see `TableElement.parse`, ~line 2816-2834:
`skip_table = True; self._empty = True`). `get_first_table` must skip such
tables:

```python
def get_first_table(self):
    for table in self.iter_tables():
        if not table._empty:
            return table
    raise IndexError("No table found in VOTABLE file.")
```

There is no existing `is_empty()` helper — use the `_empty` attribute
directly, matching how `TableElement.parse` sets it.

---

## 3. `Table._init_from_ndarray` and `Table.add_column`

File: `astropy/table/table.py`

### `Table._init_from_ndarray(self, data, names, dtype, n_cols, copy)`

Referenced (undefined) from `Table.__init__`'s dispatch logic (~line
822-826): it is selected for both structured arrays (`data.dtype.names`
truthy) and homogeneous 2-D arrays. By the time this method is called,
`__init__` has already resolved `names` to a full list of `n_cols` strings
(for structured input, defaulting to `data.dtype.names` unless the caller
passed explicit `names`; see ~line 900-903) and validated lengths via
`self._check_names_dtype` (~line 905). So `_init_from_ndarray` does **not**
need to re-derive defaults for `names`; it only needs to slice the array
into per-column data and delegate to the existing `_init_from_list`
machinery (same pattern already used by `_init_from_dict`, ~line 1455-1458,
and `_init_from_list` itself, ~line 1263-1279, which calls
`self._convert_data_to_col(col, copy, default_name, dt, name)` per column
and finishes with `self._init_from_cols(cols)`).

Recommended body:

```python
def _init_from_ndarray(self, data, names, dtype, n_cols, copy):
    struct = data.dtype.names is not None
    data_names = data.dtype.names or _auto_names(n_cols)
    names = [name or data_names[i] for i, name in enumerate(names)]

    cols = (
        [data[name] for name in data_names]
        if struct
        else [data[:, i] for i in range(n_cols)]
    )

    self._init_from_list(cols, names, dtype, n_cols, copy)
```

`_auto_names` is already imported at module scope (~line 34, from the
sibling module that defines default `col0`, `col1`, ... names) and already
used the same way in `_init_from_list` (~line 1273). Reusing
`_init_from_list` means `copy`, per-column `dtype`, and `MaskedColumn`
promotion are all handled by the already-working `_convert_data_to_col` /
`_init_from_cols` path — do not duplicate that logic.

Validate against the `Table(ndarray)` tests in `astropy/table/tests/test_init_table.py`
and `astropy/table/tests/test_table.py` (structured-array and 2-D
homogeneous-array construction, with/without `names`, with/without `copy`).

### `Table.add_column(self, col, index=None, name=None, rename_duplicate=False, copy=True, default_name=None)`

Insert in the large blank gap between `index_column` (ends ~line 2338) and
`add_columns` (~line 2481) — `add_columns` already calls this exact method
per-column, in reverse-index order for stable multi-insert:

```python
for ii in reversed(np.argsort(indexes, kind="stable")):
    self.add_column(
        cols[ii], index=indexes[ii], name=names[ii],
        default_name=default_names[ii], rename_duplicate=rename_duplicate,
        copy=copy,
    )
```

so the signature must match exactly (it does, per the interface
description).

Behavior, built from existing pieces already in this file:

1. `default_name = default_name or f"col{len(self.columns)}"`.
2. `name = name if name is not None else default_name`.
3. Convert `col` via the existing `self._convert_data_to_col(col, copy=copy,
   default_name=default_name, name=name)` (already implemented, ~line
   1282; handles `Column`, `MaskedColumn`, ndarray, mixins, and takes the
   final name from `name or data.info.name or default_name`).
4. Broadcast scalar / length-1 input to the table length when the table is
   non-empty, matching the docstring's "scalar or length=1 objects which
   get broadcast to match the table length": if `col.shape == ()` and the
   table already has columns, raise
   `TypeError("Empty table cannot have column set to scalar value")` only
   when `len(self.columns) == 0` (i.e. there's no length to broadcast to);
   otherwise when `(col.shape == () or col.shape[0] == 1) and len(self) > 0`,
   broadcast with `np.broadcast_to(col, (len(self),) + col.shape[1:],
   subok=True)` (use `col._apply(np.broadcast_to, ...)` instead for
   `ShapedLikeNDArray` mixins — this class is already imported at the top
   of the file, ~line 19, and currently unused elsewhere, which is a strong
   signal it belongs here).
5. Re-read `name = col.info.name` after conversion (step 3 may have set it
   from `col.info.name` rather than the passed `name`).
6. If `rename_duplicate`, uniquify `name` against `self.colnames` by
   appending `_1`, `_2`, ... (see the docstring's `b`/`b_1` example) and set
   `col.info.name` to the final unique name.
7. Insert `col` at position `index` (default: end, i.e.
   `len(self.columns)`). `TableColumns` (the `OrderedDict` subclass backing
   `self.columns`, class starts ~line 225) has **no** `insert()` method and
   forbids overwriting an existing key via `__setitem__`, so rebuild the
   ordered column mapping explicitly and hand it to the existing
   `_make_table_from_cols` static helper (already implemented, ~line
   1570-1593 — it does `table.columns = table.TableColumns((name, col) for
   ...)` and then calls `self._set_col_parent_table_and_mask(col)` for each
   column, which is exactly what's needed):

   ```python
   names_list = list(self.columns)
   cols_list = list(self.columns.values())
   pos = len(cols_list) if index is None else index
   names_list.insert(pos, name)
   cols_list.insert(pos, col)
   self._make_table_from_cols(self, cols_list, names=names_list)
   ```

Validate against `astropy/table/tests/test_table.py` (`add_column`,
`add_columns` test classes) — in particular the docstring's own examples
(inserting at `index=1` shifts existing columns right; `rename_duplicate`
produces `b_1`; unnamed/mixin columns get `col{n}`-style default names).

---

## 4. `UnicodeChar._binoutput_var` and `UnicodeChar._binparse_var`

File: `astropy/io/votable/converters.py`

`UnicodeChar` (class starts ~line 423) is a sibling of `Char` (~line 299),
which already has working `_binparse_var`/`_binoutput_var` for **ASCII**
(1 byte/char) data (~line 382-410). `UnicodeChar` needs the UTF-16-BE
(2 bytes/code-unit) equivalent. `UnicodeChar.__init__` already wires these
up (~line 439-443, 455-457): when `field.arraysize` is `"*"` or ends with
`"*"` (bounded variable-length), it sets
`self.binparse = self._binparse_var` / `self.binoutput = self._binoutput_var`.

**Do not** copy `Char`'s reliance on `self._parse_length` /
`self._write_length` — those are base-`Converter` helper methods that
`Char._binparse_var`/`_binoutput_var` call but that are **not defined
anywhere in this codebase** (another pre-existing, out-of-scope gap: the
`Converter.__init__`/method block around `astropy/io/votable/converters.py`
line 176-186 is empty). Implement the 4-byte length prefix directly with
`struct`, which is already imported at the top of this file (line 8), and
reuse the existing `_zero_int = b"\0\0\0\0"` module constant (line 55) for
the empty/masked case, matching `Char._binoutput_var`'s pattern:

```python
def _binoutput_var(self, value, mask):
    if mask or value is None or value == "":
        return _zero_int
    encoded = str(value).encode("utf_16_be")
    nchars = len(encoded) // 2
    if self.arraysize != "*" and nchars > self.arraysize:
        vo_warn(W46, ("unicodeChar", self.arraysize), None, None)
    return struct.pack(">I", nchars) + encoded

def _binparse_var(self, read):
    length = struct.unpack(">I", read(4))[0]
    value = read(length * 2).decode("utf_16_be")
    if self.arraysize != "*" and length > self.arraysize:
        vo_warn(W46, ("unicodeChar", self.arraysize), None, None)
    return value, False
```

Notes:
- The length prefix is a count of UTF-16 **code units** (2 bytes each), not
  bytes or Unicode code points — a non-BMP character becomes a surrogate
  pair (2 code units). `len(encoded) // 2` / `read(length * 2)` correctly
  reflect this since `utf_16_be` already encodes surrogate pairs.
- `W46` is already imported at the top of the file (line 32) and used the
  same way by `UnicodeChar.parse` (~line 464-467:
  `vo_warn(W46, ("unicodeChar", self.arraysize), config, pos)`) and by
  `Char._binparse_var`/`_binoutput_var` — match that call signature
  (`vo_warn(W46, (...), None, None)` is fine for the binary path since no
  `config`/`pos` is available there, same as `Char` does it).
- `mask` is always `False` on parse — `UnicodeChar` (like `Char`) does not
  support masked/null values; only `_binoutput_var` needs to check the
  `mask` argument (to emit a zero-length field for masked/`None`/empty
  input).

Validate against `astropy/io/votable/tests/test_converter.py` and any
BINARY-format round-trip tests involving `datatype="unicodeChar"` fields
with `arraysize="*"` or a bounded `"N*"` arraysize (e.g. grep the test
suite for `unicodeChar`).

---

## Cross-cutting checks

- After implementing, run at minimum:
  - `pytest astropy/units/tests/test_quantity_non_ufuncs.py -k concatenate or choose or select or quantile or nanmedian`
  - `pytest astropy/io/votable/tests/test_vo.py astropy/io/votable/tests/test_converter.py`
  - `pytest astropy/table/tests/test_init_table.py astropy/table/tests/test_table.py -k ndarray or add_column or add_columns`
- Do not modify `Char`'s or `Converter`'s existing methods — the
  `_parse_length`/`_write_length` and `Converter.__init__` gaps mentioned
  above are pre-existing, out-of-scope issues unrelated to the 4 interfaces
  here; leave them as-is unless a test you're asked to pass explicitly
  exercises fixed-length (`arraysize` without `*`) `unicodeChar` or `char`
  BINARY fields, which is outside this task's stated scope
  ("variable-length UTF-16-BE VOTable fields").

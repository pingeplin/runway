# 2609.0001 Quantity Concatenation and Selected Table/VOTable Operations

**Date:** 2026-09-10
**Status:** draft
**Author:** FeatureBench

## Context

This repository is `astropy`. Eight symbols across four files are currently absent from the codebase (no `def` exists for them at all), even though sibling/calling code already references them by name. They must be added so those existing call sites work:

1. `astropy/units/quantity_helper/function_helpers.py`:
   - `_iterable_helper(*args, out=None, **kwargs)` — a module-level private function. It is called by several existing `@function_helper`s already in the file: `concatenate` (line ~488, `_iterable_helper(*arrays, out=out, axis=axis, **kwargs)`), `choose` (line ~729, `_iterable_helper(*choices, out=out, mode=mode)`), `select` (line ~735, `_iterable_helper(*choicelist)`), `quantile`/`nanquantile`/`percentile`/`nanpercentile` (line ~853, `_iterable_helper(a, out=out, **kwargs)`), and `nanmedian` (line ~866, `return _iterable_helper(a, axis=axis, out=out, overwrite_input=overwrite_input, keepdims=keepdims)` — note `nanmedian` returns `_iterable_helper`'s result *directly* as its own `@function_helper` return value, so the 4-tuple `_iterable_helper` produces must already be exactly the `(args, kwargs, unit, out)` shape the function-helper machinery expects). None of these callers currently work.
   - `concatenate(arrays, axis=0, out=None, **kwargs)`, the `@function_helper` registered for `np.concatenate`, exists in two branches gated by `if NUMPY_LT_2_4: / else:` (line ~482). The `NUMPY_LT_2_4` branch has a body, but that body calls the undefined `_iterable_helper`, so it is non-functional. The `else` branch (NumPy ≥ 2.4) contains no `concatenate` definition at all — just a bare `pass` — so on NumPy ≥ 2.4 no `concatenate` helper is registered whatsoever.
2. `astropy/io/votable/tree.py`: `TableElement.to_table(self, use_names_over_ids=False)` (class `TableElement`, ~line 2478) and `VOTableFile.get_first_table(self)` (class `VOTableFile`, ~line 4138) — both entirely absent from their classes.
3. `astropy/table/table.py`: `Table._init_from_ndarray(self, data, names, dtype, n_cols, copy)` — entirely absent from the class, even though `Table.__init__`'s existing dispatch (~line 780-909) already selects it as `init_func` for both structured arrays (`data.dtype.names` truthy) and homogeneous 2-D arrays, and already calls `init_func(data, names, dtype, n_cols, copy)` at line ~909. `Table.add_column(self, col, index=None, name=None, rename_duplicate=False, copy=True, default_name=None)` — entirely absent from the class, even though several existing call sites already invoke it: `Table.add_columns` (~line 2481-2588, once per column: `self.add_column(cols[ii], index=indexes[ii], name=names[ii], default_name=default_names[ii], rename_duplicate=rename_duplicate, copy=copy)`) and `Table.__setitem__` (~line 2136-2140, `self.add_column(value, name=item, copy=True)` whenever `item` is a string not already in `self.colnames` — i.e., every `t['newcol'] = value` assignment).
4. `astropy/io/votable/converters.py`: `UnicodeChar._binoutput_var(self, value, mask)` and `UnicodeChar._binparse_var(self, read)` — entirely absent from the class, even though `UnicodeChar.__init__` (~line 432-462) already wires them up as `self.binoutput`/`self.binparse` whenever `field.arraysize == "*"` or `field.arraysize` ends with `"*"` (bounded variable-length).

**Undefined names this spec does not cover.** While reading the surrounding code, several other private names turned out to be referenced but nowhere defined in this snapshot of the repository, and are out of scope for this spec:
- `_quantities2arrays` (used by roughly fifteen *other*, already-decorated `@function_helper`s in `function_helpers.py`, none of which are in scope here — e.g. `histogram`, set-operation helpers, `interp`).
- `Converter._parse_length`/`Converter._write_length` (used by the sibling `Char` converter's already-present `_binparse_var`/`_binoutput_var`, and by `VarArray`, all in `converters.py`).
- `UnicodeChar._binparse_fixed`/`UnicodeChar._binoutput_fixed` (bound in `UnicodeChar.__init__` at line ~459-460 for any *fixed*-length `arraysize`, i.e. one that does not end in `"*"`; their absence means constructing a `UnicodeChar` converter for a fixed-length field currently raises `AttributeError` immediately in `__init__`, before any parsing happens — unrelated to and not fixed by this spec, which only covers the variable-length `_binoutput_var`/`_binparse_var` pair).
- `numpy_to_votable_dtype` and `_all_matching_dtype` (`converters.py`, called from `table_column_to_votable_datatype` at lines ~1507/1519) — as a result, `Field.from_table_column` and therefore `TableElement.from_table` (`tree.py` ~line 3547-3570) raise `NameError` for any ordinary (non-object-dtype) column. **`TableElement.from_table` cannot be used to build test fixtures in this snapshot** — construct `TableElement`/`Field` objects directly instead (see S10).
- `_make_masked_array` (`converters.py`, called at lines ~564/600/622/992/1015) and `bitarray_to_bool`/`bool_to_bitarray` (`converters.py` ~1146/1155) — variable-length numeric-array and `bit`-datatype fields cannot be parsed or written.
- `TableElement._parse_binary` (`tree.py`, called at lines ~2931/2937, no definition anywhere) — parsing a VOTable's BINARY/BINARY2 serialization is dead; only TABLEDATA-format fixtures work.
- `TableElement._resize_strategy` (`tree.py`, called at line ~3074) — TABLEDATA parsing raises once a table exceeds `DEFAULT_CHUNK_SIZE` (`tree.py` line 121, `= 256`) rows; test fixtures must stay under that row count.
- Any public "is this table empty" accessor for the internal `TableElement._empty` skip flag set during parsing (`tree.py` ~line 2828/2834) — no such accessor exists (and nothing in `astropy/` currently calls one); `get_first_table` must check the underlying condition directly rather than assume a named method.

None of these names appear in the Interface Contract below, and no acceptance scenario requires them to exist. The eight in-scope symbols must be implemented self-contained (writing whatever inline logic is needed) rather than assumed to build on top of these other, currently-undefined helpers. VOTable test fixtures (for `to_table`, `get_first_table`, and `UnicodeChar`) must, to stay within scope: use TABLEDATA (not BINARY/BINARY2) serialization; have fewer than 256 data rows; use only variable-length `unicodeChar`/`unicodeString` fields (never fixed-length, i.e. `arraysize` must be `"*"` or end in `"*"`); and avoid `bit`-datatype or variable-length numeric-array fields. Notably, `astropy/io/votable/tests/data/regression.xml` itself contains a fixed-length `unicodeString` FIELD (`fixed_unicode_test`, `arraysize="10"`, `tree.py:1404` maps `unicodeString` → `unicodeChar`) and so **cannot be parsed at all** in this snapshot — do not use it as a fixture source, including via `parse_single_table`/`test_select_columns_by_name_edge_cases`-style tests.

## Motivation

Without these eight symbols implemented:
- `numpy.concatenate`, `numpy.choose`, `numpy.select`, `numpy.quantile`/`numpy.nanquantile`, `numpy.percentile`/`numpy.nanpercentile`, and `numpy.nanmedian` all fail on `Quantity` input, because every one of their function helpers calls the undefined `_iterable_helper`.
- Parsing a VOTable file and calling `.to_table()` or `.get_first_table()` — the two most common entry points for turning VOTable data into an Astropy `Table` — fails, because neither method exists.
- `Table(ndarray_input)`, `Table.add_column(...)`, and even `t['newcol'] = value` (which routes through `add_column` via `__setitem__`) — all extremely common ways to build/mutate a `Table` — are broken or absent, which also breaks `Table.add_columns`, since it already calls `self.add_column(...)`.
- Round-tripping a VOTable `unicodeChar` field through BINARY serialization is broken whenever the field's `arraysize` is variable-length (`"*"` or bounded-variable, e.g. `"20*"`).

## Proposed Solution

### Overview

Add bodies for all eight symbols listed in Context so their observable behavior matches the authoritative docstrings in the Interface Contract below. No existing signature that other code already depends on changes: `_iterable_helper` and the `NUMPY_LT_2_4` branch of `concatenate` gain bodies; the NumPy ≥ 2.4 branch of `concatenate` gains a new function definition (replacing the bare `pass`) with its own documented positional-only signature; `to_table`, `get_first_table`, `_init_from_ndarray`, `add_column`, `_binoutput_var`, and `_binparse_var` are added as new methods on their respective existing classes, matching exactly the call patterns their sibling code (`add_columns`, `__setitem__`, `Table.__init__`, `UnicodeChar.__init__`) already uses.

### Key Components

- **`_iterable_helper(*args, out=None, **kwargs)`** — converts every element of `*args` to `Quantity` and determines one common unit across them (per the precedence rule in the Interface Contract's Notes), converts each to a plain `ndarray` in that unit, and — if `out` is given — validates it is a `Quantity` (raising `NotImplementedError` if not) and unwraps it to a plain `ndarray` view placed into `kwargs["out"]`. Must remain usable by all five existing callers listed in Context item 1, including `nanmedian`'s pattern of returning `_iterable_helper`'s result directly without destructuring it.
- **`concatenate(arrays, axis=0, out=None, **kwargs)`** (`NUMPY_LT_2_4` branch, already exists) and **`concatenate(arrays, /, axis=0, out=None, **kwargs)`** (new function to add under the `else:` branch, for NumPy ≥ 2.4) — both call `_iterable_helper` and return `(args, kwargs, unit, out)` per the Interface Contract. The existing `TestFunctionHelpersSignatureCompatibility` test (`test_quantity_non_ufuncs.py` ~line 3054) parametrizes over every registered `@function_helper` and checks its parameter kinds/defaults against the real NumPy target function's signature, so whichever branch is active for the installed NumPy version must have a signature NumPy itself would accept as compatible.
- **`TableElement.to_table(self, use_names_over_ids=False)`** — builds one `astropy.table.Column`/`MaskedColumn` per entry in `self.fields` (the table's *selected* FIELDs, in file order — not `self.all_fields`, which additionally includes FIELDs deselected via the VOTable-parse `columns=` filter and are not present as columns of `self.array`; not `self.iter_fields_and_params()`, which also yields PARAMs), taking each column's data/mask from the matching field of `self.array` (a NumPy masked array whose dtype has one named field per entry of `self.fields`). Calls each field's already-implemented `to_table_column(column)` method (~line 1719) to copy over `.meta`, `.description`, `.unit`, links, and VALUES metadata onto the new column. Table-level metadata is copied the same way `TableElement.from_table` (~line 3547) reads it back out: for each of `ID`, `name`, `ref`, `ucd`, `utype`, if the corresponding attribute on `self` is not `None`, set `table.meta[key]` to it; if `self.description` is not `None`, set `table.meta["description"]`. When `use_names_over_ids=True` produces a collision between two fields' `name` values, disambiguate using the same "append a number" convention the file already uses elsewhere for exactly this purpose — `Field.uniqify_names` (~line 1440-1470) appends `" 2"`, `" 3"`, … (a space, then the smallest integer ≥ 2 not already taken) to a colliding `name`. `to_table` must use that identical `"{name} {n}"` format (space-separated, starting at 2) when deduplicating column names, so behavior is consistent across the file even though `to_table`'s dedup operates on the resulting `Table`'s column names rather than mutating the FIELDs themselves.
- **`VOTableFile.get_first_table(self)`** — iterates `self.iter_tables()` (already implemented) and returns the first `TableElement` that was not skipped during parsing; raises `IndexError` if every table was skipped or there are no tables. "Skipped during parsing" is the same condition `TableElement.parse` (~line 2816-2833) already uses to set `self._empty = True` when a `table_number=` or `table_id=` parse filter excludes that table — it is not the same thing as "has zero rows" (a `TableElement` inside a `type="meta"` `Resource` legitimately has a zero-row `array` per the class docstring, without ever having `_empty` set, and must not be treated as skipped by this method).
- **`Table._init_from_ndarray(self, data, names, dtype, n_cols, copy)`** — for a structured array (`data.dtype.names` not `None`), produces one column per named field of `data`, using `names[i]` as the column name if `names[i]` is not `None`, else the field's own name from `data.dtype.names[i]`, with `dtype[i]` overriding the field's dtype when given (and `None` meaning "use the field's own dtype"). For a homogeneous 2-D array (`data.shape == (n_rows, n_cols)`), produces one column per `data[:, i]` slice, using `names[i]` as the column name — `names[i]` may legitimately be `None` (`Table.__init__` passes `names = [None] * n_cols` when the caller supplied neither `names=` nor a structured dtype), in which case an auto-generated `col{i}` name is used. `copy=True` produces columns holding independent data (mutating `data` afterward does not affect the table); `copy=False` produces columns that are views onto `data`'s memory (mutating `data` afterward is visible through the table), matching the existing `Table.__init__`-level `copy` semantics documented for every other `_init_from_*` method. Each field/column-slice needs the same per-column conversion the sibling `_init_from_list` method already applies before assembling into a `Table` (name resolution, per-column `dtype` override, `copy` handling, and `numpy.ma.MaskedArray` → `MaskedColumn` conversion for masked input) — `_init_from_list` (~line 1263-1280) does this by calling `self._convert_data_to_col(col, copy, default_name, dt, name)` once per column before calling `self._init_from_cols(cols)`; handing a raw `data[:, i]` ndarray slice or structured-dtype field array directly to `_init_from_cols` without going through that (or equivalent) per-column conversion skips name assignment, dtype override, and mask handling, and will not satisfy the scenarios below.
- **`Table.add_column(self, col, index=None, name=None, rename_duplicate=False, copy=True, default_name=None)`** — resolves the column's name in this order: explicit `name` argument, then `col.info.name` (if `col` already carries one, e.g. an existing `Column`), then `default_name`, then an auto-generated `f"col{len(self.columns)}"`. Converts `col` to a table-compatible column, broadcasting a scalar or length-1 input to the table's current length (including a table of length 0, where a scalar input — e.g. `add_column(9, name='a')` on an empty table — produces a zero-length column of the scalar's dtype rather than raising or broadcasting to length 1; this is the path `Table.setdefault` relies on for a fresh key on an empty table). If `col`'s length does not match a non-empty table's length (and is not a scalar/length-1 broadcastable input), raises `ValueError` whose message is exactly `"Inconsistent data column lengths"` (no additional detail appended — this is intentionally the same wording, but not the same full message, as the internal `_init_from_cols` construction-time check) and adds no column. If `self.masked` is `True`, the incoming column is converted to a `MaskedColumn` with an all-`False` mask if it is not already masked; adding an already-masked `MaskedColumn` to a non-masked table does not flip `self.masked` to `True` (masked-ness only ever propagates from table to column, never from column to table). If the resolved name already exists in `self.colnames`: when `rename_duplicate=False` (default), raises `ValueError`; when `rename_duplicate=True`, uniquifies the name by appending `_N` for the smallest positive integer `N` not already producing a name in `self.colnames` (so repeated collisions on the same base name produce `_1`, `_2`, `_3`, …). Inserts the resulting column into `self.columns` before `index` (or at the end if `index=None`).
- **`UnicodeChar._binoutput_var(self, value, mask)` / `UnicodeChar._binparse_var(self, read)`** — mirror the sibling `Char._binoutput_var`/`_binparse_var` (~lines 382-410) structurally (a 4-byte big-endian length prefix followed by the encoded payload; masked/`None`/empty values write a zero-length prefix and no payload), but the payload is UTF-16-BE (2 bytes per code unit) instead of ASCII (1 byte per character), and the length prefix counts UTF-16 code units (so a non-BMP character encoded as a UTF-16 surrogate pair counts as 2, not 1). Bound-checking and the `W46` warning use the UTF-16 code-unit count (not `len()` of the Python `str`, which counts Unicode code points) compared against `self.arraysize`, with warning arguments `("unicodeChar", self.arraysize)` — the same pair `UnicodeChar.parse` (~line 464-467) already passes to `vo_warn(W46, ...)` for the TABLEDATA path. Per the authoritative docstrings in the Interface Contract, both the write side (`_binoutput_var`, when a bounded arraysize is exceeded) and the read side (`_binparse_var`, when the decoded/declared code-unit count exceeds a bounded arraysize) issue this warning.

### Data Flow

**Quantity concatenation and friends:**
1. `numpy.concatenate(list_of_quantities, axis=0)` (or `numpy.choose`/`numpy.select`/`numpy.quantile`/`numpy.nanmedian`/…) dispatches (via `__array_function__`) to its registered function helper.
2. That helper calls `_iterable_helper(...)`, which converts its array-like positional arguments to `Quantity`, determines one common unit, converts each to a plain `ndarray` in that unit, and (if `out` was given) unwraps it to a plain `ndarray` view.
3. The helper returns `(args, kwargs, unit, out)`; astropy's `Quantity.__array_function__` machinery invokes the real NumPy function with `args`/`kwargs` and re-wraps the plain-`ndarray` result as `Quantity(result, unit, ...)` — writing into `out` in place when `out` was provided.

**VOTable → Table:**
1. `votable.parse("file.xml")` produces a `VOTableFile`.
2. `votable_file.get_first_table()` walks `self.iter_tables()` and returns the first `TableElement` not marked as skipped during parsing.
3. `table_element.to_table(use_names_over_ids=...)` reads `self.array` field-by-field (one per entry of `self.fields`), builds `astropy.table.Column`/`MaskedColumn` objects preserving dtype and mask, applies each field's `to_table_column` for unit/description/meta, resolves column names (`ID` vs. `name`, deduplicating `name`-based collisions with the `"{name} {n}"` convention when `use_names_over_ids=True`), and returns a `Table` whose `.meta` carries the table-level VOTable attributes.

**Table construction/mutation from ndarray:**
1. `Table(ndarray_data)` (optionally with `names=`/`dtype=`) dispatches to `_init_from_ndarray` once `__init__` has determined `n_cols` and, for structured arrays, `default_names = data.dtype.names`.
2. `_init_from_ndarray` builds one column per field/second-axis-slice via the same per-column conversion `_init_from_list` uses, applying `copy` semantics, and finishes construction via `self._init_from_cols(cols)`.
3. `Table.add_column(col, ...)` (called directly, via `add_columns`, or via `t['newcol'] = value`) resolves the column's name, checks for a collision against `self.colnames`, converts/broadcasts `col`, and inserts it into `self.columns` at `index` (default: end).

**UnicodeChar BINARY (de)serialization:**
1. Writing: `_binoutput_var(value, mask)` encodes `value` as UTF-16-BE, emits a 4-byte big-endian count of UTF-16 code units, followed by the encoded bytes; masked/`None`/empty values emit a 4-byte zero-length prefix and no data.
2. Reading: `_binparse_var(read)` reads 4 bytes as a big-endian code-unit count `n`, reads `2*n` more bytes via `read(...)`, and decodes them as UTF-16-BE, returning `(decoded_string, False)`.

### Interface Contract

All eight signatures below are exact and must not change (existing call sites depend on them verbatim).

```python
# astropy/units/quantity_helper/function_helpers.py

def _iterable_helper(*args, out=None, **kwargs):
    """
    Convert arguments to Quantity, and treat possible 'out'.

    Parameters
    ----------
    *args : array_like
        Variable number of array-like arguments to be converted to Quantity
        objects. The arguments must be mutually compatible in their units.
    out : Quantity or None, optional
        Optional output array. If provided, must be a Quantity object. Will
        be converted to a plain ndarray view for use with numpy functions.
    **kwargs : dict
        Additional keyword arguments that will be passed through unchanged.

    Returns
    -------
    arrays : tuple
        Tuple of arrays converted from the input arguments, with values in
        compatible units.
    kwargs : dict
        Updated keyword arguments dictionary. If 'out' was provided, it will
        contain an 'out' key with the array view of the output Quantity.
    unit : Unit
        The common unit derived from the input arguments.
    out : Quantity or None
        The original output Quantity object if provided, None otherwise.

    Raises
    ------
    NotImplementedError
        If the 'out' parameter is provided but is not a Quantity object.
    """

@function_helper
def concatenate(arrays, axis=0, out=None, **kwargs):
    """
    Concatenate arrays along an existing axis with proper unit handling.

    Parameters
    ----------
    arrays : sequence of array_like
        Same shape except possibly along `axis`. Each element is a Quantity
        or array-like convertible to Quantity.
    axis : int, optional
        Axis to join along; if None, arrays are flattened first. Default 0.
    out : Quantity, optional
        Destination array; must be a Quantity if inputs carry units.
    **kwargs : dict, optional
        Passed through to numpy.concatenate.

    Returns
    -------
    tuple
        (args, kwargs, unit, out) where args is a one-element tuple holding
        the tuple of converted array values, kwargs is updated for
        numpy.concatenate, unit is the common result unit, and out is the
        provided output Quantity (or None).

    Notes
    -----
    - All Quantity arguments must share a common-convertible unit, regardless
      of their values; otherwise astropy.units.UnitConversionError is
      raised. This applies even when every value is 0 — two Quantity
      objects with genuinely incompatible units (e.g. dimensionless and
      meters) are never compatible just because the numbers happen to be 0.
    - The unit is taken from the first argument that carries a `unit`
      attribute (i.e. is already a Quantity). A plain, non-Quantity
      argument (e.g. a bare ndarray or list, with no `unit` attribute) that
      precedes such a Quantity does not override that Quantity's unit: by
      Quantity's own value-conversion rules, a plain array consisting only
      of 0, inf, and/or nan values is accepted into *any* unit, so it
      imposes no unit constraint of its own.
    - NumPy < 2.4: signature is `concatenate(arrays, axis=0, out=None,
      **kwargs)` (not positional-only). NumPy >= 2.4: signature is
      `concatenate(arrays, /, axis=0, out=None, **kwargs)`.
    """


# astropy/io/votable/tree.py

class TableElement:
    def to_table(self, use_names_over_ids=False):
        """
        Convert this VOTable TABLE to an astropy.table.Table.

        Parameters
        ----------
        use_names_over_ids : bool, optional
            If True, use each selected FIELD's `name` as the resulting
            column name (deduplicating collisions by appending " 2", " 3",
            etc., the same convention `Field.uniqify_names` already uses
            elsewhere in this module). If False (default), use each FIELD's
            `ID` as the column name.

        Returns
        -------
        table : astropy.table.Table
            Contains the VOTable's data and metadata. `table.meta` holds
            table-level ID/name/ref/ucd/utype/description when present on
            this TableElement. Column-level unit/description/ucd/utype/
            links/VALUES metadata is preserved via each FIELD's existing
            `to_table_column` method. Masked VOTable values remain masked
            in the result.
        """

class VOTableFile:
    def get_first_table(self):
        """
        Return the first non-skipped TableElement in this VOTable file.

        Returns
        -------
        table : astropy.io.votable.tree.TableElement

        Raises
        ------
        IndexError
            If every table was skipped during parsing (e.g. via the
            `table_number` or `table_id` parse options), or there are no
            tables at all.
        """


# astropy/table/table.py

class Table:
    def _init_from_ndarray(self, data, names, dtype, n_cols, copy):
        """
        Initialize table columns from a structured or homogeneous ndarray.

        Parameters
        ----------
        data : numpy.ndarray
            Structured array (data.dtype.names is not None) or homogeneous
            2-D array of shape (n_rows, n_cols). May be a numpy.ma.MaskedArray,
            in which case per-column masks are preserved on the resulting
            columns.
        names : list of str or None
            Column names. Entries may be None (homogeneous array with no
            user-supplied names, or a structured-array field the caller did
            not rename), in which case the field's own dtype name (structured
            case) or an auto-generated `col{index}` name (homogeneous case)
            is used for that position.
        dtype : list of dtype or None
            Per-column dtypes. A None entry means "use this column's own
            dtype as found in `data`"; entries may be partially None (some
            columns overridden, others not).
        n_cols : int
            Number of columns to create.
        copy : bool
            Whether to copy input data into new, independent arrays (True)
            or create views onto `data` where possible (False).
        """

    def add_column(self, col, index=None, name=None, rename_duplicate=False,
                    copy=True, default_name=None):
        """
        Add a new column to the table using `col` as input. If `index` is
        given, insert before that position; otherwise append.

        Parameters
        ----------
        col : object
            Any data object acceptable as a Table column (including mixin
            columns and scalars/length-1 objects broadcastable to the table
            length).
        index : int or None
            Insert before this position, or append if None (default).
        name : str
            Column name.
        rename_duplicate : bool
            If True and the resolved name already exists in the table,
            uniquify it by appending "_N" (the smallest positive integer
            not already producing an existing name) rather than raising.
            Default False.
        copy : bool
            Copy the new column's data. Default True.
        default_name : str or None
            Name to use when neither `name` nor `col.info.name` is
            available. Defaults to `col{number_of_columns}`.

        Raises
        ------
        ValueError
            If the resolved column name already exists in the table and
            `rename_duplicate` is False; or if `col`'s length is
            incompatible with the table's current length (and is not a
            scalar/length-1 value broadcastable to it), with message
            exactly "Inconsistent data column lengths" and no column added.
        """


# astropy/io/votable/converters.py

class UnicodeChar:
    def _binoutput_var(self, value, mask):
        """
        Encode `value` for variable-length BINARY unicodeChar output.

        Parameters
        ----------
        value : str or None
        mask : bool
            True if the value is masked/missing.

        Returns
        -------
        bytes
            4-byte big-endian count of UTF-16 code units, followed by that
            many UTF-16-BE code units (2 bytes each). Masked/None/empty
            values yield 4 zero bytes and no data.

        Notes
        -----
        For bounded variable-length fields (arraysize ends with '*' but is
        not exactly '*'), warns (W46, with args ("unicodeChar",
        self.arraysize)) if the UTF-16 code-unit count of `value` exceeds
        the declared bound, but still writes the full string.
        """

    def _binparse_var(self, read):
        """
        Decode variable-length BINARY unicodeChar input.

        Parameters
        ----------
        read : callable
            read(n) returns the next n bytes from the binary stream.

        Returns
        -------
        value : str
        mask : bool
            Always False.

        Notes
        -----
        Reads a 4-byte big-endian count `n` of UTF-16 code units, then reads
        2*n bytes and decodes as UTF-16-BE. If arraysize is bounded (not
        "*") and `n` exceeds it, warns W46 with args ("unicodeChar",
        self.arraysize).
        """
```

## Alternatives Considered

### Have `UnicodeChar` reuse `Converter._parse_length`/`_write_length` by name

`Char._binparse_var`/`_binoutput_var` call `self._parse_length(read)`/`self._write_length(n)`. As noted in Context, neither is defined anywhere in this snapshot of `converters.py`, so `Char`'s own variable-length binary path is presently non-functional too. `UnicodeChar._binoutput_var`/`_binparse_var` must therefore not be written to *depend* on those two names existing; the required byte format (4-byte big-endian length, computed directly with e.g. `struct.pack(">I", n)` / `struct.unpack(">I", read(4))[0]`) is fully specified in the Interface Contract above and can be implemented inline. If a future change restores `_parse_length`/`_write_length` on the base `Converter` class, `UnicodeChar` may use them instead, since the observable byte format is identical either way — that is an implementation choice this spec does not mandate.

### Skip empty tables in `get_first_table` by checking `len(table.array) == 0`

Rejected: the `TableElement` class docstring states a table inside a `type="meta"` `Resource` legitimately has a zero-length `array` without having been skipped during parsing. Using row-count as the "empty" test would incorrectly skip such a table even when it is the only one available. The correct condition is the internal marker `TableElement.parse` already sets (`self._empty = True`) when a `table_number=`/`table_id=` filter excludes a table (see `tree.py` ~line 2816-2833) — i.e., "empty" means "skipped", not "zero rows" (see S16 below).

### `add_column` silently replaces on a name collision instead of raising

Rejected based on existing, in-repo test expectations: `astropy/table/tests/test_table.py::TestAddColumns::test_add_duplicate_column`/`test_add_duplicate_columns` already assert `pytest.raises(ValueError)` when adding a column whose name collides with an existing one and `rename_duplicate` is left at its default (`False`), and assert the `_1`/`_2`/… uniquification sequence when `rename_duplicate=True`. `add_column` must match those tests exactly (see S35).

## Acceptance Scenarios

### Happy Path — Quantity concatenation and friends

- **S1:** Given two `Quantity` arrays with the same unit, e.g. `Quantity([1, 2], u.m)` and `Quantity([3, 4], u.m)`, when `numpy.concatenate([a, b])` is called, then the result is a `Quantity` equal to `Quantity([1, 2, 3, 4], u.m)`.
- **S2:** Given two `Quantity` arrays with convertible but different units, e.g. `Quantity([1], u.m)` and `Quantity([100], u.cm)`, when `numpy.concatenate([a, b])` is called, then the result is a `Quantity` in the first array's unit (`u.m`) equal to `Quantity([1, 1], u.m)`.
- **S3:** Given `q1 = np.arange(6.0).reshape(2, 3) * u.m`, `q2 = q1.to(u.cm)`, and a preallocated `out = np.empty((4, 3)) * u.dimensionless_unscaled`, when `result = numpy.concatenate([q1, q2], out=out)` is called, then `result is out` (identity, not merely equal value), `out.unit == u.m`, and `out`'s values equal `np.concatenate([q1.value, q2.to_value(u.m)])` — matching `astropy/units/tests/test_quantity_non_ufuncs.py::TestConcatenate::test_concatenate`.
- **S4:** Given `q_list = [np.zeros((2, 3)), q1, q2]` where `q1 = np.arange(6.0).reshape(2, 3) * u.m` and `q2 = q1.to(u.cm)` (i.e. the *first* element of the list is a plain, unitless `ndarray` of zeros), when `numpy.concatenate(q_list)` is called, then the result's unit is `u.m` (taken from `q1`, the first element that actually carries a unit) — matching `TestConcatenate::test_concatenate`'s `q_list=[np.zeros(self.q1.shape), self.q1, self.q2], q_ref=self.q1` case.
- **S5:** Given `a = np.array([0, 1]).reshape((2, 1, 1))`, `q1 = np.array([1, 2, 3]).reshape((1, 3, 1)) * u.cm`, `q2 = np.array([-1, -2, -3, -4, -5]).reshape((1, 1, 5)) * u.m`, when `numpy.choose(a, (q1, q2))` is called, then the result equals `numpy.choose(a, (q1.value, q2.to_value(u.cm))) * u.cm` — matching `astropy/units/tests/test_quantity_non_ufuncs.py::TestUfuncLike::test_choose`.
- **S6:** Given `q = np.arange(9.0).reshape(3, 3) / 4.0 * u.m`, when `numpy.select([q < 0.55 * u.m, q > 1.0 * u.m], [q, q.to(u.cm)], default=-1.0 * u.km)` is called, then the result equals `numpy.select([q.value < 0.55, q.value > 1], [q.value, q.value], default=-1000) * u.m` — matching `TestUfuncLike::test_select`.
- **S7:** Given `q = np.arange(9.0).reshape(3, 3) / 4.0 * u.m`, when `numpy.quantile(q, 50 * u.percent)` is called, then the result is a `Quantity` equal to `numpy.quantile(q.value, 0.5) * u.m` — matching `astropy/units/tests/test_quantity_non_ufuncs.py::TestReductionLikeFunctions::test_quantile`.
- **S8:** Given `q = np.arange(9.0).reshape(3, 3) / 4.0 * u.m` with `q[1, 1] = np.nan` and `out = np.empty_like(q)`, when `o = numpy.nanmedian(q, out=out)` is called, then `o is out` and `o` equals `numpy.nanmedian(q)` computed without `out` — matching `astropy/units/tests/test_quantity_non_ufuncs.py::TestNanFunctions::test_nanmedian_out`, and confirming `nanmedian`'s pattern of returning `_iterable_helper`'s result directly still produces correct in-place output.

### Happy Path — VOTable → Table

- **S9:** Given a VOTable XML file with one non-empty `<TABLE>` containing FIELDs with `ID`, `unit`, and `ucd` attributes and at least one masked (missing) cell, when `votable.parse(path).get_first_table().to_table()` is called, then the returned `astropy.table.Table` has one column per FIELD named by `ID`, the corresponding column carries the FIELD's `unit` (accessible as `table[colname].unit`) and `ucd` (in `table[colname].meta["ucd"]`), and the masked cell is masked in the resulting column.
- **S10:** Given a `TableElement` whose `ID`, `name`, and `description` attributes are set directly (`TableElement.from_table` cannot be used to build this fixture in this snapshot — see Context; instead construct it directly, e.g. `vf = VOTableFile(); te = TableElement(vf, ID="t1", name="mytable"); te.description = "a table"` with at least one `Field` added and `te.array` populated), when `.to_table()` is called, then `result.meta["ID"] == "t1"`, `result.meta["name"] == "mytable"`, and `result.meta["description"] == "a table"`; and given a `TableElement` with no `ref`/`utype` set, then `"ref"`/`"utype"` are absent from `result.meta`.
- **S11:** Given a `TableElement` built directly (not via `from_table`, and not by parsing `regression.xml` — see Context) with two `Field`s of distinct `ID`s (`"col_a"`, `"col_b"`) and distinct `name`s (`"Column A"`, `"Column B"`), when `.to_table(use_names_over_ids=True)` is called, then the resulting `Table.colnames == ["Column A", "Column B"]` (the FIELDs' `name` values, not their `ID`s).
- **S12:** Given `to_table(use_names_over_ids=True)` on a `TableElement` with two FIELDs that share the same `name` (e.g. both `"flux"`), when called, then the resulting columns are named `"flux"` and `"flux 2"` (the space-plus-number convention `Field.uniqify_names` already uses in this file), and no exception is raised.
- **S13:** Given a `VOTableFile` produced by parsing a VOTable containing exactly one `<TABLE>` with data rows, when `.get_first_table()` is called, then it returns that `TableElement` (its `.array` has the same length/content as the parsed table).
- **S14:** Given a `VOTableFile` parsed with `table_number=1` from a file containing two `<TABLE>` elements, where the resulting file object still holds a `TableElement` for table 0 marked as skipped (per `TableElement.parse`'s `table_number` handling) alongside the fully-populated `TableElement` for table 1, when `.get_first_table()` is called, then the table-1 `TableElement` is returned, not the skipped table-0 one.
- **S15:** Given a `VOTableFile` where every table was skipped during parsing (e.g. `table_number` selected an index beyond the file's table count) or the file has zero `<TABLE>` elements, when `.get_first_table()` is called, then `IndexError` is raised.
- **S16:** Given a `VOTableFile` whose only `<TABLE>` has FIELDs but zero data rows because it lives inside a `type="meta"` `Resource` (not because it was skipped by a parse filter), when `.get_first_table()` is called, then that `TableElement` is returned (no `IndexError`), and `.to_table()` on it returns a `Table` with `len(table) == 0` and `table.colnames` matching the FIELDs.

### Happy Path — Table construction and mutation from ndarray

- **S17:** Given a homogeneous 2-D `numpy.ndarray` of shape `(2, 3)` and `names=['a', 'b', 'c']`, when `Table(data, names=names)` is constructed, then the resulting `Table` has columns `'a'`, `'b'`, `'c'` whose values equal `data[:, 0]`, `data[:, 1]`, `data[:, 2]` respectively.
- **S18:** Given `data = np.array([(1, 2, 3), (3, 4, 5)], dtype="i4")` (a homogeneous 2-D array) with no `names=` argument, when `Table(data)` is constructed, then `Table.colnames == ['col0', 'col1', 'col2']` — matching `astropy/table/tests/test_init_table.py::TestInitFromNdarrayHomo::test_default_names`.
- **S19:** Given a structured `numpy.ndarray` with fields `('x', 'i4')`, `('y', 'f8')`, when `Table(data)` is constructed with no explicit `names`, then the resulting `Table.colnames` equals `['x', 'y']` and the columns' dtypes match the structured fields' dtypes.
- **S20 (mixed partial names/dtype, homogeneous):** Given `data = np.array([(1, 2, 3), (3, 4, 5)], dtype="i4")`, when `Table(data, names=["a", None, "c"], dtype=[None, None, "f8"])` is constructed, then `Table.colnames == ["a", "col1", "c"]`, `t["a"].dtype.type == np.int32`, `t["col1"].dtype.type == np.int32`, `t["c"].dtype.type == np.float64`, and every column's `.name` equals its key in `colnames` — matching `astropy/table/tests/test_init_table.py::TestInitFromNdarrayHomo::test_partial_names_dtype` exactly.
- **S21 (mixed partial names/dtype, structured):** Given `data = np.array([(1, 2, 3), (3, 4, 5)], dtype=[("x", "i8"), ("y", "i4"), ("z", "i8")])`, when `Table(data, names=["e", None, "d"], dtype=["f4", None, "f8"])` is constructed, then `Table.colnames == ["e", "y", "d"]`, `t["e"].dtype.type == np.float32`, `t["y"].dtype.type == np.int32`, `t["d"].dtype.type == np.float64` — matching `TestInitFromNdarrayStruct::test_partial_names_dtype`.
- **S22 (copy=False view, homogeneous):** Given `data = np.array([(1, 2, 3), (3, 4, 5)], dtype="i4")`, when `t = Table(data, copy=False)` is constructed and then `t["col1"][1] = 0`, then `data[1][1] == 0` too (the table column is a view onto `data`) — matching `TestInitFromNdarrayHomo::test_ndarray_ref`.
- **S23 (copy=False view, structured):** Given a structured array with fields `('x', 'i8')`, `('y', 'i4')`, `('z', 'i8')`, when `t = Table(data, copy=False)` is constructed and then `t["x"][1] = 0` and `t[0]["y"] = 0`, then `data["x"][1] == 0` and `data["y"][0] == 0` too — matching `TestInitFromNdarrayStruct::test_ndarray_ref`.
- **S24 (masked structured input):** Given a `numpy.ma.MaskedArray` with a structured dtype (fields `('x', 'i4')`, `('y', 'f8')`) where one element of column `'x'` is masked, when `Table(masked_structured_array)` is constructed, then `t['x']` is a `MaskedColumn` with that element's mask `True`, `t.has_masked_columns is True`, and — per existing astropy ≥ 4.0 behavior (`astropy/table/tests/test_masked.py::TestTableInit::test_mask_false_if_input_mask_not_true`, which this spec must not weaken) — `t.masked is False` (masked *columns* do not implicitly flip the table-wide `masked` flag). This is the dependency `to_table` (S9) relies on for propagating masked VOTable cells into a `Table`.

### Happy Path — add_column

- **S25:** Given `t = Table([[1, 2], [0.1, 0.2]], names=('a', 'b'))` and `col_c = Column(name='c', data=['x', 'y'])`, when `t.add_column(col_c)` is called, then `t.colnames == ['a', 'b', 'c']` and `t['c']` equals `['x', 'y']`.
- **S26:** Given the table from S25 (now with columns `a, b, c`), when `t.add_column(['p', 'q'], name='d', index=1)` is called, then `t.colnames == ['a', 'd', 'b', 'c']` (inserted *before* index 1) and `t['d']` equals `['p', 'q']`.
- **S27:** Given `t = Table([[1, 2], [0.1, 0.2]], names=('a', 'b'))`, when `t.add_column(1.1, name='b', rename_duplicate=True)` is called, then `t.colnames == ['a', 'b', 'b_1']` and `t['b_1']` is `[1.1, 1.1]` (the scalar broadcast to the table's length).
- **S28:** Given `t = Table([[1, 2], [0.1, 0.2]], names=('a', 'b'))`, when `t.add_column(['x', 'y'])` is called with no `name` and no `default_name`, then the new column is named `'col2'` (`col{number_of_columns_before_adding}`).
- **S29:** Given `t = Table()` (empty, zero columns and zero rows), when `t.add_column([1, 2])` is called with no `name`, then `t.colnames == ['col0']` and `t['col0']` equals `[1, 2]` — matching `astropy/table/tests/test_table.py::TestAddName::test_default_name`.
- **S30 (`__setitem__` hot path):** Given `t = Table([[1, 2]], names=['a'])`, when `t['b'] = [3, 4]` is executed, then `t.colnames == ['a', 'b']` and `t['b']` equals `[3, 4]`; and when `t['c'] = 5` is executed afterward, then `t['c']` equals `[5, 5]` (broadcast) — exercising `Table.__setitem__`'s existing `self.add_column(value, name=item, copy=True)` call (`table.py` ~line 2136-2140).
- **S39 (`setdefault` on an empty table with a scalar default):** Given `t = Table()` (empty), when `t.setdefault("a", 9)` is called (which routes through `__setitem__` → `add_column`), then `len(t) == 0` (the column is *not* broadcast to length 1), `t.colnames == ["a"]`, and `t["a"].dtype == int` — matching `astropy/table/tests/test_table.py::test_empty_table_setdefault_scalar`.
- **S40 (masked table, plain column):** Given `t = Table(masked=True)`, when `t.add_column(MaskedColumn(name="a", data=[1, 2, 3], mask=[0, 1, 0]))` is called, then `t.masked is True` (unchanged) and `t["a"]` is a `MaskedColumn` with `t["a"].mask == [False, True, False]` — matching `astropy/table/tests/test_masked.py::TestAddColumn::test_add_masked_column_to_masked_table`.
- **S41 (non-masked table, masked column added):** Given `t = Table(masked=False)` with an existing plain `Column` `"a"`, when `t.add_column(MaskedColumn(name="b", data=[4, 5, 6], mask=[1, 0, 1]))` is called, then `t.masked is False` (adding a masked column never flips it), `t["b"]` is a `MaskedColumn` with the given mask, and `t["a"]` remains a plain `Column` with no `.mask` attribute — matching `TestAddColumn::test_add_masked_column_to_non_masked_table`.

### Happy Path — UnicodeChar BINARY variable-length

- **S31:** Given a UTF-16-BE `unicodeChar` FIELD with `arraysize="*"` and a Python string containing a non-BMP character (e.g. `"\U0001D11E"`, the musical G-clef, which is 2 UTF-16 code units), when `converter._binoutput_var(value, mask=False)` is called and the resulting bytes are fed back through `converter._binparse_var(read)`, then the round-tripped tuple is `(value, False)`, and the encoded bytes' 4-byte length prefix equals `2` (code units), not `1` (Python `len()`/code points) or `4` (UTF-8 bytes).
- **S32:** Given `converter._binoutput_var(None, mask=False)`, `converter._binoutput_var("", mask=False)`, and `converter._binoutput_var("anything", mask=True)` for a variable-length `UnicodeChar` field, when each is called, then every one returns exactly 4 zero bytes (`b"\x00\x00\x00\x00"`) with no trailing payload; and given those same 4 zero bytes fed through `_binparse_var(read)`, then the result is `("", False)` and no further bytes are consumed from `read`.
- **S33:** Given a bounded variable-length `unicodeChar` field (`arraysize="3*"`) and a value whose UTF-16 code-unit count is 5 (exceeding the bound of 3), when `_binoutput_var(value, mask=False)` is called, then a `W46` warning (message args `("unicodeChar", 3)`) is issued but the full 5-code-unit payload is still written (not truncated) with a length prefix of `5`; when those written bytes are then fed through `_binparse_var(read)` on a converter with the same bounded arraysize, then a `W46` warning is issued again and the full original string is still returned.

### Error Scenarios

- **S34:** Given two `Quantity` arrays with incompatible units, e.g. `Quantity([1], u.m)` and `Quantity([1], u.s)`, when `numpy.concatenate([a, b])` is called, then `astropy.units.UnitConversionError` is raised — concatenation does not silently coerce or drop a unit.
- **S35:** Given `Quantity(np.zeros(3), u.dimensionless_unscaled)` (an *explicitly* dimensionless `Quantity`, not a plain ndarray) followed by `Quantity([1, 2, 3], u.m)`, when `numpy.concatenate([a, b])` is called, then `astropy.units.UnitConversionError` is raised — unlike S4, a value of all zeros does not exempt a `Quantity` (which already has a `unit` attribute) from needing a genuinely convertible unit, per `Quantity._to_own_unit`'s rule that the 0/inf/nan exemption applies only to inputs that lack a `unit` attribute in the first place.
- **S36:** Given `_iterable_helper(Quantity([1, 2], u.m), out=np.empty(2))` is called directly with `out` being a plain `ndarray` (not a `Quantity`), then `NotImplementedError` is raised, per `_iterable_helper`'s documented `Raises` section.
- **S37:** Given `numpy.concatenate([Quantity([1, 2], u.m), object()])` — a second list element that cannot be converted to a `Quantity` at all — when called, then `TypeError` is raised, matching `TestConcatenate::test_concatenate`'s `pytest.raises(TypeError): np.concatenate([self.q1, object()])` assertion.
- **S38:** Given `t = Table(); t.add_column(Column(name='a', data=[1, 2, 3]))` followed by `t.add_column(Column(name='a', data=[4, 5, 6]))` (a second column with the same name, `rename_duplicate` left at its default `False`), when the second `add_column` call is made, then `ValueError` is raised and the table still contains only the original `'a'` column with its original data `[1, 2, 3]` — matching `astropy/table/tests/test_table.py::TestAddColumns::test_add_duplicate_column`.
- **S42:** Given `t = table.table_helpers.simple_table(2)` (a 2-row table), when `t.setdefault("f", [1, 2, 3])` is called (a 3-element default for a 2-row table, routing through `__setitem__` → `add_column`), then `ValueError` is raised with message exactly `"Inconsistent data column lengths"` (verified with `pytest.raises(ValueError, match="^Inconsistent data column lengths$")`) and `"f"` is not added to `t.columns` — matching `astropy/table/tests/test_table.py::test_table_setdefault_wrong_shape`.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that would *fail if the behavior were wrong*. A green suite that passes for the wrong reason does not satisfy this contract — `/verify` will hunt for vacuous tests by asking, of each behavior, "what is the smallest change that breaks this, and would any test catch it?"

Ground rules specific to this spec:

- **Do not change any of the eight signatures** given in the Interface Contract — `_iterable_helper(*args, out=None, **kwargs)`, `concatenate(arrays, axis=0, out=None, **kwargs)` under `NUMPY_LT_2_4` and `concatenate(arrays, /, axis=0, out=None, **kwargs)` otherwise, `TableElement.to_table(self, use_names_over_ids=False)`, `VOTableFile.get_first_table(self)`, `Table._init_from_ndarray(self, data, names, dtype, n_cols, copy)`, `Table.add_column(self, col, index=None, name=None, rename_duplicate=False, copy=True, default_name=None)`, `UnicodeChar._binoutput_var(self, value, mask)`, `UnicodeChar._binparse_var(self, read)`. Tests that import and call pytest-collected code will bind against these exact names/argument orders.
- **Preserve every existing call site.** `_iterable_helper` must keep working for `concatenate`, `choose`, `select`, `quantile`/`nanquantile`/`percentile`/`nanpercentile`, and `nanmedian` (all named in Context item 1) — do not special-case it only for `concatenate`'s call pattern. `Table.add_column` must keep `Table.add_columns`, `Table.__setitem__`, and `Table.setdefault` (which itself calls `__setitem__`) working exactly as their existing code already calls it — `add_columns`'s own docstring/doctests, `__setitem__`'s `self.add_column(value, name=item, copy=True)` call, and the `setdefault`/masked-table tests named in the Definition of Done are effectively additional acceptance criteria for `add_column`.
- **Do not assume `_quantities2arrays`, `Converter._parse_length`/`_write_length`, `UnicodeChar._binparse_fixed`/`_binoutput_fixed`, or any `TableElement.is_empty()` helper exists** — as documented in Context, none of these are defined in this codebase snapshot. Implement `_iterable_helper` and `UnicodeChar._binoutput_var`/`_binparse_var` self-contained (inline unit/byte-format logic), and implement `get_first_table`'s skip check directly against whatever internal marker `TableElement.parse` already sets. `UnicodeChar` test fixtures must use variable-length `arraysize` only (see Context) to avoid the unrelated, out-of-scope fixed-length `AttributeError`.
- For `to_table`/`get_first_table`, build fixtures either as small literal VOTable XML strings parsed inline in the test, or by constructing `TableElement`/`Field` objects directly (`TableElement.from_table` is **not** usable as a fixture builder in this snapshot — see Context: it depends on the undefined `numpy_to_votable_dtype` and raises `NameError` for ordinary columns). `astropy/io/votable/tests/test_vo.py::test_select_columns_by_name_edge_cases` is a useful *read-only* reference for the `self.fields` vs. `self.all_fields` distinction, but its own fixture (`data/regression.xml`) cannot currently be parsed at all (see Context) — do not depend on that file, and do not expect that test to pass.
- Respect the fixture constraints in Context's last paragraph for any VOTable XML written inline: TABLEDATA serialization only, fewer than 256 data rows, and no fixed-length `unicodeChar`/`unicodeString`, `bit`, or variable-length numeric-array fields.
- For `UnicodeChar`, write tests against actual encode/decode byte content (e.g., assert the 4-byte length prefix's integer value and the UTF-16-BE payload), not just "no exception raised."
- The existing tests named throughout this spec must continue to pass unmodified; they are not to be weakened or deleted to make new code pass. This includes tests in files this spec's eight symbols do not touch (e.g. `test_masked.py::TestTableInit::test_mask_false_if_input_mask_not_true`, cited in S24, must keep passing exactly as today).

Write tests to the project's conventions (pytest, under each package's existing `tests/` directory, e.g. `astropy/units/tests/`, `astropy/io/votable/tests/`, `astropy/table/tests/`) and to these principles (the same ones `/verify` scores against — see `references/test-desiderata.md` and `references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects (returned values, raised exceptions, resulting table contents/meta/units), not internals like which private helper was called.
- **Every test can fail** — no copy-pasted expected values, no asserting a constant, no tautologies (AP-2, AP-4).
- **Deterministic, isolated, readable** — no dependence on file-system/network state beyond fixtures created in the test itself; AAA structure with inline setup.

## Definition of Done

Because three names referenced by neighboring, out-of-scope code (`_quantities2arrays`, `Converter._parse_length`/`_write_length`, `UnicodeChar._binparse_fixed`/`_binoutput_fixed`) remain undefined per Context, a blanket "full test suite is green" is not an achievable or meaningful criterion — any pre-existing test whose *only* failure reason is a dependency on one of those three names (e.g. `test_converter.py::test_oversize_unicode`/`test_unicode_mask`, which construct fixed-length `unicodeChar` converters; the roughly fifteen other `function_helpers.py` helpers built on `_quantities2arrays`; `Char`'s own binary variable-length path) is out of this spec's scope and may remain failing. `/verify` checks the following instead:

- [ ] All newly written tests for S1–S42 pass.
- [ ] The following pre-existing tests, which exercise the eight in-scope symbols and do not depend on any of the three out-of-scope names, continue to pass unmodified:
  - `astropy/units/tests/test_quantity_non_ufuncs.py::TestConcatenate::test_concatenate`
  - `astropy/units/tests/test_quantity_non_ufuncs.py::TestUfuncLike::test_choose`, `::test_select`
  - `astropy/units/tests/test_quantity_non_ufuncs.py::TestReductionLikeFunctions::test_quantile`, `::test_percentile`
  - `astropy/units/tests/test_quantity_non_ufuncs.py::TestNanFunctions::test_nanmedian`, `::test_nanmedian_out`
  - `astropy/units/tests/test_quantity_non_ufuncs.py::TestFunctionHelpersCompleteness::test_no_duplicates`, `::test_all_included`
  - `astropy/units/tests/test_quantity_non_ufuncs.py::TestFunctionHelpersSignatureCompatibility` (at least its `concatenate` case)
  - `astropy/table/tests/test_table.py::TestAddName::test_default_name`, `::test_override_name`
  - `astropy/table/tests/test_table.py::TestAddColumns::test_add_duplicate_column`, `::test_add_duplicate_columns`
  - `astropy/table/tests/test_init_table.py::TestInitFromNdarrayHomo::test_default_names`, `::test_ndarray_ref`, `::test_partial_names_dtype`, `::test_partial_names_ref`
  - `astropy/table/tests/test_init_table.py::TestInitFromNdarrayStruct::test_ndarray_ref`, `::test_partial_names_dtype`, `::test_partial_names_ref`
  - `astropy/table/tests/test_masked.py::TestTableInit::test_mask_false_if_input_mask_not_true`
  - `astropy/table/tests/test_masked.py::TestAddColumn::test_add_masked_column_to_masked_table`, `::test_add_masked_column_to_non_masked_table`, `::test_add_non_masked_column_to_masked_table`, `::test_convert_to_masked_table_only_if_necessary`
  - `astropy/table/tests/test_table.py::test_table_setdefault`, `::test_table_setdefault_wrong_shape`, `::test_empty_table_setdefault`, `::test_empty_table_setdefault_scalar` (these exercise `add_column` via `Table.setdefault` → `__setitem__`)
  - `astropy/io/votable/tests/test_converter.py::test_bounded_variable_size_unicode`
  - `astropy/io/votable/tests/test_vo.py::test_select_columns_by_name_edge_cases` is **excluded** from this list: its fixture, `data/regression.xml`, contains a fixed-length `unicodeString` FIELD that cannot be parsed in this snapshot regardless of this spec's implementation (see Context and Trade-offs) — it is expected to remain failing.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under the smallest break of its behavior (thought-mutation).
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale docstrings).

## Trade-offs and Limitations

- Variable-length VOTable array fields (including `unicodeChar`) are explicitly documented as not necessarily round-tripping identically through `Table` (`to_table`'s own docstring Notes) — S31's round-trip scenario is scoped to the converter's raw binary encode/decode, not a full VOTable-file round trip through `Table`.
- `UnicodeChar._binparse_fixed`/`_binoutput_fixed` (the fixed-length, non-`"*"`-arraysize path) do not exist in this codebase and are out of scope for this spec; any test exercising a fixed-length `unicodeChar` converter will hit an unrelated, pre-existing `AttributeError` at construction time regardless of what this spec's two in-scope methods do. All `UnicodeChar` scenarios in this spec (S31–S33) use variable-length `arraysize` values (`"*"` or `"N*"`) specifically to avoid that path.
- This spec deliberately does not implement `_quantities2arrays` or `Converter._parse_length`/`_write_length`, even though they are referenced by neighboring code, because they fall outside the eight symbols named in Context. Pre-existing tests that depend solely on those names are expected to remain failing (see Definition of Done); that is separate, pre-existing broken behavior this spec's scope does not extend to.
- The exact deduplication format for `to_table(use_names_over_ids=True)` (`"{name} {n}"`, space-separated, starting at 2) is this spec's own decision, chosen for consistency with `Field.uniqify_names`'s existing convention in the same file, since no pre-existing test in this repository pins a different format for this specific code path.
- Whether `UnicodeChar._binoutput_var` (the *write* side) should warn `W46` for a bounded variable-length overflow is likewise this spec's own decision, made because the authoritative Interface Description docstring given for this task states it explicitly ("warns if the input string length exceeds the specified maximum length"). No pre-existing test in this repository pins this behavior for the binary write path specifically (the sibling `Char` converter's own binary path is out of scope per Context, and `UnicodeChar.parse`'s existing W46 warning covers only the TABLEDATA path).
- `astropy/io/votable/tests/data/regression.xml` cannot be parsed in this snapshot at all: it contains a fixed-length `unicodeString` FIELD, and `unicodeString` maps to `UnicodeChar`, whose fixed-length methods (`_binparse_fixed`/`_binoutput_fixed`) are undefined (see Context). This is why `test_select_columns_by_name_edge_cases` is excluded from the Definition of Done's must-pass list and why S9/S10/S11/S16 build their own fixtures rather than reusing `regression.xml`.

## References

- `astropy/units/quantity_helper/function_helpers.py` (module docstring at top of file; existing `@function_helper` implementations such as `full_like`, `putmask`, `place`, `copyto` for the `(args, kwargs, unit, out)` return convention; existing callers of `_iterable_helper` at `concatenate`, `choose`, `select`, `quantile`/`percentile`, `nanmedian`).
- `astropy/units/tests/test_quantity_non_ufuncs.py`: `TestConcatenate::test_concatenate`, `TestUfuncLike::test_choose`/`test_select`, `TestReductionLikeFunctions::test_quantile`/`test_percentile`, `TestNanFunctions::test_nanmedian`/`test_nanmedian_out`, `TestFunctionHelpersCompleteness`, `TestFunctionHelpersSignatureCompatibility` — pre-existing tests whose passing is required and whose fixtures ground most of the concatenate/choose/select/quantile/nanmedian scenarios above.
- `astropy/units/quantity.py`: `Quantity._to_own_unit` (the 0/inf/nan arbitrary-unit exemption, and its restriction to inputs lacking a `unit` attribute) and `Quantity._not_implemented_or_raise` (the `TypeError`-on-incompatible-`out`/`types` path).
- `astropy/io/votable/tree.py`: `TableElement.from_table` (~line 3547), `Field.to_table_column` (~line 1719), `Field.uniqify_names` (~line 1440-1470, the `"{name} {n}"` dedup convention), `TableElement.fields`/`all_fields` properties (~line 2649-2670), `TableElement.parse`'s `table_number`/`table_id` skip handling (~line 2816-2833).
- `astropy/io/votable/tests/test_vo.py::test_select_columns_by_name_edge_cases` and its `data/regression.xml` fixture.
- `astropy/table/table.py`: `Table.__init__` ndarray dispatch (~line 780-909), `Table.add_columns` (~line 2481-2588), `Table.__setitem__` (~line 2136-2140), sibling `_init_from_list`/`_convert_data_to_col`/`_init_from_dict` methods.
- `astropy/table/tests/test_table.py`: `TestAddName::test_default_name`/`test_override_name`, `TestAddColumns::test_add_duplicate_column`/`test_add_duplicate_columns` — pre-existing tests whose passing is required and whose fixtures ground S29/S38.
- `astropy/table/tests/test_init_table.py`: `TestInitFromNdarrayHomo`/`TestInitFromNdarrayStruct` — pre-existing tests whose passing is required and whose fixtures ground S18/S20–S23.
- `astropy/table/tests/test_masked.py::TestTableInit::test_mask_false_if_input_mask_not_true` and `TestAddColumn` (all four tests) — pre-existing tests grounding the masked-column-without-table-wide-flag behavior in S24, S40, S41.
- `astropy/table/tests/test_table.py::test_table_setdefault`/`test_table_setdefault_wrong_shape`/`test_empty_table_setdefault`/`test_empty_table_setdefault_scalar` — pre-existing tests, reached via `Table.setdefault` → `__setitem__` → `add_column`, grounding S39/S42 and the exact `"Inconsistent data column lengths"` error message.
- `astropy/io/votable/converters.py`: `numpy_to_votable_dtype`/`_all_matching_dtype` (undefined; makes `TableElement.from_table` unusable for non-object-dtype columns — see Context and S10), `_make_masked_array`/`bitarray_to_bool`/`bool_to_bitarray` (undefined; variable-length numeric-array and `bit` fields out of scope).
- `astropy/io/votable/tree.py`: `_parse_binary` (undefined; BINARY/BINARY2 parsing out of scope), `_resize_strategy`/`DEFAULT_CHUNK_SIZE` (undefined/256; TABLEDATA fixtures must stay under 256 rows), `unicodeString` → `unicodeChar` mapping at line ~1404 (why `data/regression.xml`'s `fixed_unicode_test` FIELD makes that file unparsable in this snapshot).
- `astropy/io/votable/converters.py`: `Char._binparse_var`/`_binoutput_var`/`_binparse_fixed`/`_binoutput_fixed` (~lines 382-420) as the structural sibling to mirror for `UnicodeChar`; `UnicodeChar.parse` (~line 464-467) for the existing `W46` warning-args convention on the unicode side.
- `astropy/units/errors.py`: `UnitConversionError(UnitsError, ValueError)`.

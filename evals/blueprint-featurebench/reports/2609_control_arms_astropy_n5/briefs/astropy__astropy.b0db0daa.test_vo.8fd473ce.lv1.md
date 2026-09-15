# Implementation Brief: Restore VOTable tree navigation/conversion methods

## Target file

`/testbed/astropy/io/votable/tree.py` (in this checkout: `astropy/io/votable/tree.py`).

Five methods/bodies have been stripped from this file, leaving behind their
docstrings-as-comments-free blank gaps (runs of blank lines) inside three
classes. Restore each one **in place**, at the blank gap indicated below.
Do not change any other code, signatures, decorators, or class attributes —
they are already correct and other code depends on their exact current form
(e.g. `_version_namespace_map`, `_lookup_by_attr_factory`,
`_lookup_by_id_or_name_factory` all already exist and must not be touched).

Match indentation and style of the surrounding code (4-space indent,
docstrings in the existing `numpydoc`-lite style used throughout this file).

---

## 1. `ParamRef.get_ref` — class `ParamRef` (around line 2256)

Insert a `get_ref` method right after the `ref` property's `@ref.deleter`
block (after `self._ref = None`, before the blank run that precedes `class
Group`).

There is an exact sibling implementation to copy the pattern from:
`FieldRef.get_ref` (same file, ~line 2245-2253):

```python
def get_ref(self):
    """
    Lookup the :class:`Field` instance that this :class:`FieldRef`
    references.
    """
    for field in self._table._votable.iter_fields_and_params():
        if isinstance(field, Field) and field.ID == self.ref:
            return field
    vo_raise(KeyError, f"No field named '{self.ref}'", self._config, self._pos)
```

For `ParamRef.get_ref`, mirror this exactly but:
- Match against `Param` instances instead of `Field` (`isinstance(field, Param)`).
- Compare `field.ID == self.ref`.
- Iterate `self._table._votable.iter_fields_and_params()` (same source —
  `iter_fields_and_params` yields both FIELD and PARAM elements, so filtering
  by `isinstance(..., Param)` is required to only match PARAM elements).
- On no match, raise via `vo_raise(KeyError, f"No field named '{self.ref}'", self._config, self._pos)`
  (keep the same message text/style as `FieldRef.get_ref` for consistency;
  `vo_raise` is already imported/used elsewhere in this file).

`Param` is defined later in this same file (`class Param(Field)`, ~line
1784) and is already resolvable at call time (method body, not class body),
so no import changes are needed. `vo_raise` is already imported at the top
of the file (from `.exceptions`) and used elsewhere (e.g. in `FieldRef.get_ref`).

---

## 2. `TableElement.to_table` — class `TableElement` (large blank gap around

line 3480-3519, immediately before `@classmethod def from_table(cls, votable, table):`)

Insert a `to_table` instance method there. Note `TableElement.__repr__`,
`__bytes__`, and `__str__` (lines ~2550-2560) already call `self.to_table()`,
so this method is load-bearing for those too.

Required behavior (matches the docstring already present in the class,
do not delete/alter that docstring — only the interface spec's abridged
version is shown below, the real file has the full docstring already):

```python
def to_table(self, use_names_over_ids=False):
    meta = {}
    for key in ("ID", "name", "ref", "ucd", "utype", "description"):
        val = getattr(self, key, None)
        if val is not None:
            meta[key] = val

    if use_names_over_ids:
        names = [field.name for field in self.fields]
        unique_names = []
        for i, name in enumerate(names):
            new_name = name
            i = 2
            while new_name in unique_names:
                new_name = f"{name}{i}"
                i += 1
            unique_names.append(new_name)
        names = unique_names
    else:
        names = [field.ID for field in self.fields]

    from astropy.table import Table

    table = Table(self.array, names=names, meta=meta)

    for name, field in zip(names, self.fields):
        column = table[name]
        field.to_table_column(column)

    return table
```

Key details to get right:
- Import `Table` locally inside the method (`from astropy.table import
  Table`), not at module top-level. This file already follows this pattern
  elsewhere (see `TableElement._parse_parquet`, ~line 3283, which does
  `from astropy.table import Table` inline) — presumably to avoid a
  circular import between `astropy.io.votable` and `astropy.table`.
- Use `self.fields` (the `TableElement.fields` property, ~line 2649) — not
  `self.all_fields` — to build columns and column names; `self.fields` is
  the property that reflects the fields actually backing `self.array`'s
  columns.
- Populate `table.meta` only with attributes that are not `None`, from
  `ID`, `name`, `ref`, `ucd`, `utype`, `description` (in that order is
  not significant, but only set present ones — don't put `None` values
  into `meta`).
- Per-column metadata (units, descriptions, UCD, LINKs, etc.) is delegated
  entirely to `Field.to_table_column(column)`, which already exists
  (~line 1719) and is fully implemented — do not duplicate its logic here.
- `use_names_over_ids=False` (default) uses each field's `ID` attribute as
  the astropy `Table` column name; `use_names_over_ids=True` uses each
  field's `name` attribute, de-duplicating collisions by appending `2`,
  `3`, ... to repeated names (see the dedup loop above — needed because
  `name` is not guaranteed unique, but `Table` column names must be).
- Table-level `INFO`/`LINK` elements are intentionally NOT copied into
  `table.meta` (only the scalar attributes listed above are copied).

Validate against `astropy/io/votable/tests/test_table.py`, which exercises
`to_table()` and `to_table(use_names_over_ids=...)` extensively (e.g. lines
~66-73, 172, 199, 237, 447-473, 530-545, 592, 643-683, 750, 795), and
`astropy/io/votable/tests/test_tree.py`.

---

## 3. `VOTableFile.__repr__` — class `VOTableFile` (blank gap around lines

4167-4171, immediately after `self._groups = HomogeneousList(Group)` in
`__init__`, before the `@property def config` block)

```python
def __repr__(self):
    n_tables = len(list(self.iter_tables()))
    return f"<VOTABLE>... {n_tables} tables ...</VOTABLE>"
```

`self.iter_tables()` already exists (~line 4490) and recursively yields all
`TableElement` instances across all resources (including nested resources),
counting empty tables too. Keep the exact output format
`"<VOTABLE>... N tables ...</VOTABLE>"` since the docstring in the
interface spec pins this literal string shape.

---

## 4. `VOTableFile.get_first_table` — class `VOTableFile` (blank gap around

lines 4498-4507, between `def iter_tables(self): ...` and
`get_table_by_id = _lookup_by_attr_factory(...)`)

```python
def get_first_table(self):
    """
    Often, you know there is only one table in the file, and
    that's all you need.  This method returns that first table.
    """
    for table in self.iter_tables():
        if len(table.array):
            return table
    raise IndexError("No table found in VOTABLE file.")
```

Confirmed by grep: `TableElement` has no `is_empty()` method anywhere in
this file, so "empty" must be tested directly via `table.array` — its
docstring (on `class TableElement`, ~line 2478) states `array` is
zero-length when the table has no data (e.g. parsed with a table-selection
option that skipped this table's data, or `Resource.type == 'meta'`). Use
`len(table.array)` truthiness (or `len(table.array) > 0`) as the
non-empty check, exactly as above — do not invent or call an `is_empty()`
method.

---

## 5. `VOTableFile.iter_values` — class `VOTableFile` (blank gap around lines

4577-4584, immediately after the `get_field_by_id_or_name = ...` block and
before `get_values_by_id = _lookup_by_attr_factory(...)`)

```python
def iter_values(self):
    """
    Recursively iterate over all VALUES_ elements in the VOTABLE_
    file.
    """
    for field in self.iter_fields_and_params():
        yield field.values
```

`self.iter_fields_and_params()` already exists just above this gap
(~line 4539) and recursively yields every FIELD/PARAM in the file
(including inside GROUP elements, via each Resource/TableElement/Group's
own `iter_fields_and_params`). Every `Field`/`Param` instance carries a
`.values` attribute pointing to its `Values` element (see `class Values`,
~line 948, and `class Field`, ~line 1299) — yield that directly; do not
filter out defaulted `Values` instances (`Values.is_defaults()` is
irrelevant here per the interface spec — include everything).

---

## Verification

After implementing all five methods, run:

```
cd /testbed && python -m pytest astropy/io/votable/tests/test_tree.py astropy/io/votable/tests/test_table.py -q
```

Also do a quick manual sanity check that nothing else in the module
references these methods with a different call signature — grep for
`get_ref(`, `to_table(`, `get_first_table(`, `iter_values(`, and `__repr__`
usages within `astropy/io/votable/` to confirm the restored methods are
consumed as expected (e.g. `TableElement.__repr__`/`__bytes__`/`__str__`
call `self.to_table()` with no arguments — verify that still works with the
new default `use_names_over_ids=False`).

Do not modify class attributes, decorators, or any other method in
`tree.py` beyond filling these five gaps. Do not add new imports at module
level — the one new import needed (`astropy.table.Table`) must stay local
to `TableElement.to_table`, matching this file's existing pattern for
avoiding circular imports with `astropy.table`.

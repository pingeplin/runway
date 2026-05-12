# CSV normalizer

Build a tiny CSV normalization pipeline in the `normalizer` package.

The public API is:

```python
from normalizer import normalize_csv

normalize_csv(input_path: str, output_path: str) -> dict
```

It reads `input_path`, normalizes the contents, writes `output_path`, and
returns a `dict` with summary info (e.g., row count, column names).

The normalization rules:

1. Column headers become `snake_case` (strip whitespace, lowercase,
   non-alphanumeric → underscore, collapse repeated underscores, trim
   underscores at the ends). Header collisions after normalization should
   be disambiguated with `_2`, `_3`, ... suffixes in document order.
2. Cell values are whitespace-stripped.
3. Where a column's values look numeric, coerce them — `int` if all
   integers, else `float`. A column with mixed numeric and non-numeric
   values stays as strings. Empty cells stay empty.
4. Handle input encoding: utf-8, utf-8-sig (BOM), latin-1 fallback.
5. Normalize line endings on write (`\n`).
6. Skip completely-blank rows.

Internal layout (no rules on file shape — but the starter already splits
work across `reader.py`, `columns.py`, `writer.py`):

- `reader.py` — encoding detection + raw row iteration
- `columns.py` — header normalization, type inference
- `writer.py` — write normalized rows

Don't change the public API. Keep `normalize_csv` exported from
`normalizer/__init__.py`.

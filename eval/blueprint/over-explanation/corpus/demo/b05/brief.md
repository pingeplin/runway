# CSV schema validator

Write a function `validate_rows(rows, schema)` that validates parsed CSV rows
against a small column schema and reports the problems it finds. The `rows`
argument is a list of dictionaries, where each dictionary is one parsed CSV row
mapping a column name to that cell's already-parsed value. The `schema` argument
is a dictionary that maps each expected column name to a type name drawn from
the set `{"int", "str", "bool"}`. The function returns a list of human-readable
error strings, one string per row that has a problem, and it returns an empty
list when every row satisfies the schema.

## What counts as a problem

For each row, the validator checks the columns named by the schema. There are
exactly two kinds of problem the validator reports. The first kind is a missing
column: the row dictionary does not contain a key that the schema requires. The
second kind is a wrong type: the row contains the column, but its value does not
match the type name the schema assigns to that column. Any column present in the
row but absent from the schema is simply ignored; the schema is the authority on
which columns matter, and extra columns are not an error.

## One error per row, in order

The validator reports at most one error per row, namely the first problem it
finds in that row. Because it stops at the first problem per row, a row with two
bad columns still yields exactly one error string. Columns are examined in the
order they appear in the schema dictionary, so "first problem" means the
problem on the earliest schema column that is missing or mistyped. The returned
error list is in row order: errors for earlier rows appear before errors for
later rows, and rows with no problem contribute nothing to the list.

## Type matching

Type matching uses the row value's actual runtime type. A schema type of `"int"`
matches a Python `int`, `"str"` matches a Python `str`, and `"bool"` matches a
Python `bool`. Note that in Python `bool` is a subclass of `int`, but for this
validator they are kept distinct: a boolean value does not satisfy an `"int"`
column, and an integer value does not satisfy a `"bool"` column. This keeps the
three type names mutually exclusive, which matters because the schema authority
must be unambiguous about what each column holds.

## Stable error message format

The error message format must be stable and is defined here so every caller can
rely on it. Rows are numbered from zero, using the row's index in the input
list. A missing-column error has the exact form:

    row {i}: missing column '{col}'

A wrong-type error has the exact form:

    row {i}: column '{col}' expected {type}, got {actual}

In both forms, `{i}` is the zero-based row index, `{col}` is the offending
column name, `{type}` is the schema type name (`int`, `str`, or `bool`), and
`{actual}` is the Python type name of the value actually found in the row
(for example `int`, `str`, `bool`, `float`, or `NoneType`). The column name is
wrapped in single quotes exactly as shown.

## Edge cases

An empty `rows` list returns an empty list, since there is nothing to validate.
An empty `schema` imposes no requirements, so every row trivially passes and the
result is an empty list.

For example, with the schema `{"id": "int", "name": "str"}`, the row
`{"id": 1, "name": "Ada"}` passes, the row `{"name": "Ada"}` yields
`row 0: missing column 'id'`, and the row `{"id": "x", "name": "Ada"}` yields
`row 0: column 'id' expected int, got str`.

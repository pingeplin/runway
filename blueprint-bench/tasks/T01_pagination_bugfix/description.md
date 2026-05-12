# Fix the pagination off-by-one bug

The `pagination.paginate(items, page, page_size)` function in this codebase
is broken in a subtle way: when the requested page is the *last* page and
the items don't divide evenly into `page_size`, it returns one too few
items. The two existing tests in `tests/test_pagination.py` happen to pass
because they only cover pages where `page * page_size` is well within the
list bounds.

Fix the bug. The function's intended contract is unchanged:

- `page` is 1-indexed.
- `page_size` is a positive integer.
- Items are sliced in order; returned slices are non-overlapping.
- A page beyond the data returns an empty list, never raises.
- `page_size` of 0 or a negative `page` should raise `ValueError`.

Keep the function signature the same. Don't change its module location.

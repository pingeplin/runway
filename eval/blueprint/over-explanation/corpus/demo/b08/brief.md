# Stable pagination cursor

Implement keyset (cursor-based) pagination over a sorted list of integer ids.
Write a function `page(items, cursor, size)` that returns one page of results
together with the cursor needed to fetch the page after it.

The `items` argument is a list of integers that is already sorted in ascending
order. The `cursor` argument is the pagination position: it is `None` for the
very first page, and otherwise it is the last id that was returned on the
previous page. The `size` argument is the maximum number of items the page may
contain.

The function returns a two-element list `[page_items, next_cursor]`. The
`page_items` element is the list of items for this page, and `next_cursor` is
the cursor a caller would pass back in to retrieve the following page.

Requirements:

- A page contains only items that are strictly greater than `cursor`. Because
  `cursor` is the last id already seen, the item equal to the cursor must not be
  repeated.
- A page contains at most `size` items. Take the items in ascending order, and
  stop once `size` items have been collected even if more items remain greater
  than the cursor.
- The `next_cursor` is the last id on the returned page. This last id becomes
  the cursor for the next call, which is exactly how keyset pagination walks
  forward through the list.
- If the returned page is empty — because no items are greater than the cursor,
  or because the list has been fully paged through — then `next_cursor` is
  `null`. An empty page signals that the end has been reached.
- When `cursor` is `None`, every item is eligible, so paging starts from the
  smallest id.

For example, with `items = [10, 20, 30, 40, 50]`, calling `page(items, None, 2)`
returns `[[10, 20], 20]`, then `page(items, 20, 2)` returns `[[30, 40], 40]`,
then `page(items, 40, 2)` returns `[[50], 50]`, and finally `page(items, 50, 2)`
returns `[[], null]` because no id is greater than `50`.

# Running total

Write a function `running_total(numbers)` that takes a list of numbers and
returns a new list of the same length, where the element at index `i` is the
sum of all input elements from index `0` through `i` inclusive (the running,
or cumulative, total).

Requirements:

- The input list must not be mutated; return a new list.
- An empty input list returns an empty list.
- The result has the same length as the input.
- Negative numbers are supported and simply add (subtract) into the total.

For example, `running_total([1, 2, 3])` returns `[1, 3, 6]`, and
`running_total([])` returns `[]`.

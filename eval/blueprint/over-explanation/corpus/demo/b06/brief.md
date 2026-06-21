# Exponential backoff schedule

Write a function `backoff_delays(retries, base, factor, cap)` that computes the
sequence of delays a retry loop should wait before each attempt. The schedule is
a classic exponential backoff schedule: the delay grows by a constant
multiplicative factor on each successive attempt, up to a ceiling.

The function returns a list of delays, one delay per attempt. The list has
exactly `retries` elements. The delay before attempt `i` (counting from `i = 0`
for the first attempt) is `base * factor ** i`, but never larger than `cap`. In
other words, the delay before attempt `i` is `min(cap, base * factor ** i)`.
Because the exponent `i` grows by one on each attempt, the delay before each
attempt is the previous delay multiplied by `factor`, until the value reaches the
ceiling and is clamped to `cap` from then on.

Requirements:

- The returned list has exactly `retries` elements, in order from the first
  attempt (index 0) to the last.
- The delay at index `i` is `min(cap, base * factor ** i)`.
- The cap is an absolute ceiling: no returned delay ever exceeds `cap`.
- The schedule is deterministic. There is no jitter and no randomness of any
  kind; calling the function twice with the same arguments returns the same list.
- `retries` is a non-negative integer. When `retries` is `0`, the function
  returns an empty list because there are no attempts to schedule.

For example, `backoff_delays(4, 1.0, 2.0, 100.0)` returns
`[1.0, 2.0, 4.0, 8.0]`, since each delay doubles and none reaches the cap. With a
low cap, `backoff_delays(4, 1.0, 2.0, 5.0)` returns `[1.0, 2.0, 4.0, 5.0]`: the
fourth delay would be `8.0` but is clamped down to the ceiling of `5.0`. As noted
above, the cap is an absolute ceiling, so once an attempt's uncapped delay meets
or exceeds `cap`, every later delay in the list is also `cap`.

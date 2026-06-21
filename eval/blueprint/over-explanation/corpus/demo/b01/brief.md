# Fixed-window rate limiter

Write a function `allowed(timestamps, limit, window)` that decides, for a stream
of incoming requests, which requests a fixed-window rate limiter would permit.
A rate limiter is a component that caps how many requests are accepted within a
recurring slice of time, and a fixed-window rate limiter is the variety that
chops time into back-to-back windows of equal length and counts requests inside
each one separately.

The `timestamps` argument is a list of integer second-timestamps, one per
incoming request, given in non-decreasing order (each timestamp is greater than
or equal to the one before it). The `limit` argument is the maximum number of
requests that may be permitted within any single window. The `window` argument
is the length of each window in seconds. The function returns a list of booleans
of the same length as `timestamps`, where the element at index `i` is `True` if
the request at index `i` is permitted and `False` if it is rejected.

The windows are fixed and aligned to multiples of `window`. The window that a
request at time `t` belongs to starts at `t - (t % window)` and spans `window`
seconds from there. In other words, requests are bucketed by `t // window`, so
all requests whose timestamp falls in the same aligned window share one counter.

Within each window, the limiter permits at most `limit` requests. Process the
requests in the order given. For each request, if the count of already-permitted
requests in that request's window is below `limit`, permit it and increment that
window's count; otherwise reject it. Rejected requests do not consume capacity
and do not count toward the limit. Because the same window can only ever permit
up to `limit` requests, the running counter for a window never exceeds `limit`.

A few clarifying points. An empty `timestamps` list returns an empty list. The
counts reset at each window boundary, so a request that lands in a fresh window
is permitted even if the previous window was already full. The result list
always has the same length as the input list, since every request produces
exactly one boolean verdict.

For example, with `limit = 2` and `window = 10`, the timestamps
`[0, 1, 2, 11]` produce `[True, True, False, True]`: the first two requests at
times 0 and 1 fill the window `[0, 10)`, the request at time 2 is rejected
because that window is already at its limit of two, and the request at time 11
is permitted because it lands in the next window `[10, 20)` whose counter is
fresh.

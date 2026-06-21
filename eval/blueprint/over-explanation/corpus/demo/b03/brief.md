# LRU cache trace

Write a function `lru_results(operations, capacity)` that simulates a
least-recently-used (LRU) cache of fixed `capacity` and returns the list of
results produced by the "get" operations, in the order those gets occur.

The cache has a fixed `capacity`, which is the maximum number of distinct keys
it may hold at any one time. The `operations` argument is a list of operations
applied to the cache in order. Each operation is itself a list. A put operation
has the shape `["put", key, value]` and a get operation has the shape
`["get", key]`.

A "get" looks up a key. If the key is present in the cache, the get returns its
current value; if the key is absent, the get returns `None` (which serializes
to `null`). Either way, a "get" on a present key counts as a use of that key.

A "put" inserts a key with a value, or, if the key already exists, updates its
value. A put also counts as a use of that key. If inserting a brand-new key
would make the number of distinct keys exceed `capacity`, the cache first
evicts the single least-recently-used key — the key whose most recent use is
furthest in the past — to make room. Updating the value of a key that already
exists never triggers an eviction, because it does not increase the number of
distinct keys.

Recency is what drives eviction. Both gets and puts count as uses, and any use
makes its key the most recently used. The least-recently-used key is therefore
the one that has gone the longest since its last get or put. When a new key must
be inserted into a full cache, that least-recently-used key is the one evicted.

The function returns a list containing exactly one entry per "get" operation, in
the order the gets were encountered: the value found, or `None` when the key was
absent. Put operations produce no entry in the returned list.

For example, with `capacity` 2 and operations
`[["put","a",1],["put","b",2],["get","a"],["put","c",3],["get","b"],["get","c"]]`,
the get on "a" returns 1 (which also refreshes "a" as recently used), so when
"c" is put the least-recently-used key is "b", which is evicted; the get on "b"
then returns `None` and the get on "c" returns 3. The result is `[1, null, 3]`.

If `operations` is empty, there are no gets, so the function returns an empty
list.

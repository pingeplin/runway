# Idempotent webhook dedupe

Our payment provider delivers webhooks to us at-least-once, which means the same
payment event can arrive more than one time. Because the provider retries on any
network hiccup, we routinely receive duplicate deliveries of an event we have
already handled. To make our processing safe under these retries, we need it to
be idempotent: handling the same event twice must have the same effect as
handling it once.

Write a function `process(events)` that consumes a batch of incoming webhook
events and returns the list of events that were actually applied. Each event in
the input is a two-element list `[idempotency_key, amount]`, where
`idempotency_key` is a string that the provider guarantees is stable across
retries of the same logical event, and `amount` is the payment amount.

The function must apply each idempotency key at most once. The first time a key
is seen, that event is applied and its key is recorded as applied. Any later
event carrying a key that has already been applied is a duplicate delivery and
must be ignored. Because the key is the unit of identity, a later duplicate is
ignored even when its `amount` differs from the amount seen on the first
delivery; the first delivery wins and the differing amount on the duplicate does
not change anything and does not cause a second application.

Return the list of idempotency keys that were applied, in first-seen order —
that is, in the order the keys first appeared in the input. Do not include a key
more than once in the returned list, since each key is applied at most once.

An empty input list of events returns an empty list, because there is nothing to
apply. The input list itself is processed in order and is not mutated.

For example, `process([["k1", 10], ["k1", 99], ["k2", 5]])` returns
`["k1", "k2"]`: `k1` is applied on its first delivery, the second `["k1", 99]`
is a duplicate of an already-applied key and is ignored despite the different
amount, and `k2` is applied on its first delivery.

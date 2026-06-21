# Distributed lease coordinator

We run a fleet of stateless worker processes, and at any moment exactly one of
them must hold a particular resource — for example, the right to compact a shard
or to drive a singleton background job. To coordinate this, we are building a
distributed lease coordinator: a small service that hands out time-bounded
leases on named resources so that, at most, one client holds a given resource at
a time. Because workers can crash, hang, or be partitioned away at any instant,
the coordinator cannot rely on clients to release leases cleanly; instead, every
lease is time-bounded and expires on its own. Design the coordinator's
correctness model and its client-facing interface.

## What a lease is

A lease is a grant of a named resource to a single client for a bounded duration.
When a client acquires a lease on a resource, the coordinator records the holder
and an expiry time, and it returns a fencing token to the client. The lease is
valid only until its expiry time; after that instant the coordinator considers
the lease expired and the resource free, whether or not the previous holder ever
heard about the expiry. The whole point of the time bound is that the coordinator
can reclaim a resource from a crashed or partitioned holder without that holder's
cooperation, since a holder that has vanished will never release the lease
explicitly.

## Fencing tokens

Every successful acquire returns a fencing token, which is a strictly increasing
integer. The coordinator maintains a single monotonic counter per resource: each
new grant of a resource — whether a fresh acquire after the previous lease
expired or a hand-off to a different client — increments the counter and the new
holder receives the next value. The token is therefore strictly greater than the
token of any previous holder of that resource, and tokens for a given resource
never repeat and never decrease, even across coordinator restarts. The token
exists so that a downstream store can reject a stale writer: a holder presents
its token with every protected operation, and the store remembers the highest
token it has accepted and refuses any operation carrying a token lower than that
high-water mark. This is what makes the system safe even when a slow,
partitioned holder believes it still holds a lease that has in fact expired and
been re-granted — its writes carry an old, smaller token and are fenced off.

## Renewal

A client that wants to keep a resource past its current expiry renews the lease
before it expires. A renewal extends the expiry time of an existing, still-valid
lease, and critically it keeps the same fencing token, because the holder has not
changed — renewal is not a new grant. A renewal is only honored if it arrives
while the lease is still valid and is presented by the current holder; a renewal
that arrives after the lease has already expired is rejected, because by then the
resource may already have been granted to someone else, and silently resurrecting
the old holder would let two clients believe they hold the same resource at once.
A client whose renewal is rejected must treat itself as no longer holding the
lease.

## Expiry and clock skew

Expiry is decided by the coordinator's own clock, not by any client's clock, so
that there is a single authority on whether a lease is still valid. Because the
coordinator and its clients do not share a perfectly synchronized clock, the
coordinator must account for clock skew when it tells a client how long a lease
is good for. The lease duration the coordinator promises to a client must be the
nominal duration reduced by a safety margin at least as large as the maximum
assumed clock skew, so that a client never believes its lease is still valid
after the coordinator has already expired it. In other words, the client's view
of validity must always be conservative relative to the coordinator's: the client
should consider its lease expired strictly before the coordinator would, never
after. A lease must never be considered valid by a client at a moment when the
coordinator already considers it free, because that is exactly the split-brain
window the whole design exists to prevent.

## Client interface

The coordinator exposes three operations to clients. `acquire(resource, client,
ttl)` attempts to take a lease on a resource for the requesting client for the
requested time-to-live; it succeeds only if the resource is currently free
(unheld or expired) and, on success, returns a fencing token and the
skew-adjusted expiry. `renew(resource, client, token, ttl)` extends an existing
lease held by the same client and carrying the same token; it succeeds only if
that client is the current valid holder and returns the new expiry while keeping
the token unchanged. `release(resource, client, token)` voluntarily gives up a
lease the client currently holds, freeing the resource immediately; a release is
honored only from the current holder presenting the current token, so that a
stale holder cannot release a lease that has since been re-granted to someone
else. Every operation is rejected when its preconditions do not hold rather than
silently coerced, because in a coordination service a quietly wrong answer is far
more dangerous than an explicit failure the client can react to.

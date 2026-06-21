# Feature-flag rollout service

Design a feature-flag rollout service that decides, for a given user and a
given flag, whether that flag is on or off at evaluation time. The service is
the single authority every application calls to ask "is flag X enabled for
user U right now?", and the whole point of this design is to make that answer
fast, deterministic, and safe to change without a deploy. This document
specifies the design decisions, constraints, and interfaces an implementer must
honor; it does not prescribe a storage engine or wire format.

## Evaluation interface

The core interface is a single evaluation call, `evaluate(flag_key, user)`,
that returns a boolean decision for that user and flag at the moment it is
called. The `flag_key` is a stable string identifier for the flag, and `user`
is a context object carrying at least a stable `user_id` string plus an
arbitrary bag of attributes (for example country, plan, or signup date) used by
targeting rules. Evaluation must be a pure function of the flag's current
configuration and the supplied user context: given the same configuration and
the same user, the call always returns the same decision. Evaluation must never
block on a network round trip on the hot path, so the implementation reads from
an in-memory snapshot of flag configuration rather than querying a database per
call.

## Decision order

A flag's decision is computed by applying its inputs in a fixed, documented
order, and that order is itself a load-bearing design decision because it
determines who wins when rules conflict. The order is: first the global kill
switch, then targeting rules, then the percentage rollout, then the flag's
default. The global kill switch is checked first and overrides everything: if a
flag is killed, `evaluate` returns off for every user regardless of any
targeting rule or rollout percentage. If the flag is not killed, targeting
rules are evaluated next in their listed order, and the first rule that matches
the user decides the result immediately. If no targeting rule matches, the
percentage rollout is applied. If the rollout does not place the user in the
enabled bucket, the flag's configured default value is returned.

## Percentage rollout must be sticky

The percentage rollout enables the flag for a configured percentage of users,
an integer from 0 to 100 inclusive, and this assignment must be sticky per user
id. Stickiness means that a given user always lands in the same bucket for a
given flag as long as the percentage does not change, so a user does not flip
between on and off across calls, processes, or machines. To achieve this
without storing per-user state, the bucket is derived deterministically by
hashing the combination of the flag key and the user id into a value in the
range 0 to 99, and the user is enabled iff that bucket value is strictly less
than the configured percentage. Because the hash includes the flag key, the
same user can be in different buckets for different flags, which avoids every
flag rolling out to the same unlucky cohort first. A rollout of 0 enables the
flag for no users, and a rollout of 100 enables it for every user.

## Targeting rules

A targeting rule names a user attribute, an operator, and a value, and it
yields a forced decision (on or off) when it matches. Targeting rules are
evaluated before the percentage rollout, so a matching rule short-circuits the
rollout entirely and a user matched by a rule never falls through to the
hashing step. Rules are tried in their listed order and the first match wins,
which means rule order within a flag is significant and the implementer must
preserve the order the configuration declares.

## Global kill switch

Every flag has a global kill switch that, when engaged, forces the flag off for
all users immediately and unconditionally. The kill switch exists so an
operator can disable a misbehaving flag in one action without editing or
deleting its targeting rules and rollout percentage, so that the original
configuration is preserved and can be restored by simply disengaging the
switch. Because the kill switch is checked before any other input, engaging it
is the fast, safe way to stop a rollout in an incident.

## Audit of flag changes

Every change to a flag's configuration must be recorded in an append-only audit
log, and the audit log is never edited or deleted in place. Each audit entry
records who made the change, when it was made, the flag key affected, and the
before and after configuration values, so that any past state of a flag can be
reconstructed from the log. Audit logging applies to all configuration changes,
including engaging or disengaging the kill switch, editing targeting rules, and
changing the rollout percentage. The audit log is a write path concern and is
explicitly out of the hot evaluation path, so recording an audit entry must
never slow down or block an `evaluate` call.

## Out of scope

Per-user manual overrides stored individually, scheduled or time-windowed
rollouts, and multivariate (non-boolean) flags are out of scope for this
design, which is deliberately limited to boolean flags decided by the four
inputs above.

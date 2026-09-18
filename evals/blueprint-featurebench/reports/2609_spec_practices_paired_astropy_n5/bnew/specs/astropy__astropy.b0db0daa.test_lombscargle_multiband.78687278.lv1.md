# 2609.0001 Core Utility Restorations

**Date:** 2026-09-18
**Status:** draft
**Author:** FeatureBench

## Context

The feature request names five utility functions/methods across the
astropy codebase whose bodies are currently missing (each site is either
blank or absent entirely). A sixth site, `astropy/timeseries/periodograms/lombscargle_multiband/core.py`,
is not one of the five named interfaces and its algorithmic code is out of
scope, but two of its plain plumbing helpers — `strip_units` and
`get_unit` — are also blank while being called from 9+ sites inside that
module's `LombScargleMultiband` class (see item 6/7 below); every method
of that class currently raises `NameError` the instant it runs. Because
that module cannot execute at all without them, restoring these two
helpers is a prerequisite for exercising the module, not a scope
expansion — see Out of Scope, which excludes the rest of that module's
algorithm.

1. `quantity_day_frac` in `astropy/time/utils.py` — not defined. It is
   imported and called from `astropy/time/formats.py:336`
   (`TimeFormat._check_val_type`) whenever a `Time` is constructed from a
   `Quantity` with time units.
2. `broadcast_arrays` in `astropy/utils/masked/function_helpers.py` — not
   defined. `astropy/utils/masked/core.py`'s `MaskedNDArray.__array_function__`
   dispatches `numpy.broadcast_arrays(*masked_or_plain_arrays)` to it via the
   `DISPATCHED_FUNCTIONS` registry populated by the `@dispatched_function`
   decorator (see the neighboring `broadcast_to` at line 281 for the
   equivalent `@apply_to_both`-based sibling).
3. `has_units` in `astropy/timeseries/periodograms/lombscargle/core.py` —
   not defined. It is called at lines 152, 165, 172, 179, and 188 inside
   `LombScargle.__init__`/`autofrequency` to decide whether inputs carry
   `astropy.units` and therefore need `strip_units`/`get_unit` handling.
4. `_check_leapsec` in `astropy/time/core.py` — not defined. It is called
   from `Time._set_scale` (line 797) every time a scale conversion touches
   `"utc"`, and must coordinate with the module-level `_LeapSecondsCheck`
   enum (`NOT_STARTED`/`RUNNING`/`DONE`), the `_LEAP_SECONDS_CHECK` global,
   and the `_LEAP_SECONDS_LOCK` (`threading.RLock()`) already declared at
   `astropy/time/core.py:151-158`, plus the existing `update_leap_seconds`
   function (`astropy/time/core.py:3381-3402`). The blank block at lines
   3363-3380 is where it belongs.
5. `Table.__array__` in `astropy/table/table.py` — not defined on the
   `Table` class (`astropy/table/table.py:589`). `Table.as_array` (line 649)
   already builds a structured `ndarray`/`MaskedArray` copy of the table and
   is the natural building block.
6. `strip_units` in `astropy/timeseries/periodograms/lombscargle_multiband/core.py`
   — not defined and not imported (the blank block at lines 19-32 of that
   file, right after the already-defined `has_units` at lines 17-18).
   Called at lines 424-428, 469, 471, 533, 536, 590, 652, and 655 inside
   `LombScargleMultiband.power`/`autofrequency`/`design_matrix`/`model`/
   `offset`. The sibling module `lombscargle/core.py:23` has its own copy
   of the same helper, but the multiband module does not import it — it
   must have its own definition.
7. `get_unit` in `astropy/timeseries/periodograms/lombscargle_multiband/core.py`
   — not defined, same blank block. Called at lines 546, 617, 619, and 691
   to re-attach `self.y`'s unit to fitted values and parameters. Note that
   `has_units` *is* already defined in this file (line 17, its own
   independent copy); only `strip_units`/`get_unit` are missing.

Items 1-5 are the five interfaces the feature request names explicitly.
Items 6-7 are a strict prerequisite of exercising the `LombScargleMultiband`
class at all (see Motivation) and are restored as thin, self-contained
plumbing — not as an expansion into "the Lomb–Scargle algorithm," which
remains out of scope (see Out of Scope). None of the seven requires
touching Astropy's general unit-conversion machinery, the `Time`/`TimeFormat`
date system, the `Table` column/row machinery, coordinate transforms, or
the Lomb–Scargle periodogram algorithm itself. Each has callers already in
the tree that will start working the moment the function exists.

## Motivation

Because these seven call sites are exercised deep inside otherwise-unrelated
features (constructing a `Time` from a `Quantity`, broadcasting a
`MaskedNDArray`, running `LombScargle`, running `LombScargleMultiband`,
doing any UTC time-scale conversion, and calling `np.array(table)`), their
absence currently causes `NameError`/`AttributeError` failures the moment
any of those code paths run — not just in dedicated unit tests for these
functions, but in any downstream test that happens to exercise them. The
`lombscargle_multiband` case is the sharpest instance of this: its own
`tests/` directory (`astropy/timeseries/periodograms/lombscargle_multiband/tests/`)
currently holds only an empty `__init__.py`, meaning any test file added
there — for example to test the module this workspace is named after —
would fail immediately on `strip_units`/`get_unit`, before ever reaching
the five explicitly-named interfaces. Restoring exactly these seven
bodies, with exactly the documented signatures, unblocks all of that
surrounding functionality without requiring changes anywhere else.

## Proposed Solution

### Overview

Implement each of the seven functions/methods in place, at the file and
(for `_check_leapsec`, `has_units`, `quantity_day_frac`, `strip_units`,
`get_unit`) the blank spot where it is evidently meant to live (surrounded
by existing blank lines in `astropy/time/utils.py`,
`astropy/timeseries/periodograms/lombscargle/core.py`, and
`astropy/timeseries/periodograms/lombscargle_multiband/core.py`).
Each implementation is self-contained and uses only what is already
imported/available in its file — no new dependencies, no changes to public
signatures beyond what is specified below.

### Key Components

- **`quantity_day_frac(val1, val2=None)`** — `astropy/time/utils.py`.
  Returns a `(day, frac)` pair of float64 scalars/arrays whose exact sum is
  the total time expressed in days. For a single quantity (`val2 is None`)
  the pair carries `day_frac`'s own postcondition: `day` is integer-valued
  and `abs(frac) <= 0.5`. When `val2` is given, each argument is converted
  to days independently and the two pairs are summed component-wise, so
  `val1` and `val2` may carry *different* time units; only the exact-sum
  property is required of the two-argument result (`frac` may exceed 0.5,
  and the caller at `astropy/time/formats.py:336` renormalizes). When a
  quantity's unit is a pure multiplicative
  scale of `astropy.units.day`, the conversion must retain `day_frac`'s
  two-double precision: the `1/86400` rounding error must not leak into the
  result, so the pair returned for a duration expressed in seconds equals
  the pair returned for the identical duration expressed in days
  (`quantity_day_frac(864000000 * u.s) == quantity_day_frac(10000 * u.day)
  == (10000.0, 0.0)`, where a naive multiply by `u.s.to(u.day)` would
  return a non-zero `frac`). When the unit is not a pure
  scale of `day` and the conversion is only available some other way (e.g.
  through an enabled equivalency), it falls back to `.to_value(u.day)`,
  returning `(complete_value, 0.0)` — potentially with reduced precision.
  `val1` must carry a unit convertible to time; if it does not, the
  `astropy.units` conversion machinery's `UnitsError` (or subclass)
  propagates to the caller (see `astropy/time/formats.py:336`, which
  catches it and re-raises as `UnitConversionError`).
- **`broadcast_arrays(*args, subok=False)`** — `astropy/utils/masked/function_helpers.py`,
  registered as a `@dispatched_function`. Broadcasts every argument's
  unmasked data against the others to the common result shape, broadcasts
  each `Masked` argument's mask to that same shape, and pairs them back up
  via `Masked(...)`; an argument that was not `Masked` on the way in comes
  back as a plain array, not a mask-free `Masked` (the file's existing
  `_get_data_and_mask_array`/`_get_data_and_mask_arrays` helpers are
  available for the split). Honors
  `subok` exactly as `broadcast_to` (line 281 in the same file) already
  does for the analogous single-array case. The observable contract is on
  the *caller* side: `np.broadcast_arrays(...)` on masked input must return
  the same container type (`list` on NumPy < 2.0, `tuple` on NumPy >= 2.0 —
  see the `NUMPY_LT_2_0` import already present in this file) that
  `np.broadcast_arrays` returns for that NumPy version, including for a
  single input array (do not special-case arity down to a bare array). Note
  that `MaskedNDArray.__array_function__` unpacks a dispatched helper's
  return value as `result, mask, out = dispatched_result`
  (`astropy/utils/masked/core.py:1043`) and returns `result` unchanged when
  `mask is None`, so the container of broadcast arrays is what reaches the
  caller.
- **`has_units(obj)`** — `astropy/timeseries/periodograms/lombscargle/core.py`.
  Returns `True` when `obj` carries a `unit` attribute and `False`
  otherwise (`False` for a plain `numpy.ndarray`, `True` for a `Quantity`),
  matching the interface docstring's examples exactly.
- **`strip_units(*arrs)`** — `astropy/timeseries/periodograms/lombscargle_multiband/core.py`,
  a per-module copy of the helper at `lombscargle/core.py:23` (the
  multiband module does not import it). Returns each argument as a plain
  `numpy.ndarray` with any unit discarded, mapping `None` to `None`. Called
  with exactly one argument it returns that single converted value
  directly; called with more than one it returns an iterable of the
  converted values in argument order, so `t_fit, dy = strip_units(self._trel,
  self.dy)` (line 469) unpacks correctly even when `self.dy` is `None`.
- **`get_unit(obj)`** — `astropy/timeseries/periodograms/lombscargle_multiband/core.py`,
  a per-module copy of the helper at `lombscargle/core.py:19`. Returns
  `obj.unit` when `obj` carries one, and the dimensionless multiplicative
  identity `1` otherwise, so that `y_fit * get_unit(self.y)` (line 546)
  yields a `Quantity` for unit-carrying input and leaves a plain
  `numpy.ndarray` plain.
- **`_check_leapsec()`** — `astropy/time/core.py`, in the blank block at
  lines 3363-3380, immediately above `update_leap_seconds`. Ensures the
  ERFA leap second table update (`update_leap_seconds()`, already defined
  at line 3381) is attempted at most once per process, and that concurrent callers
  from multiple threads neither start a second update nor return before
  the in-flight update completes. Implemented as a check-lock-check around
  the existing module globals `_LEAP_SECONDS_CHECK` (an instance of the
  existing `_LeapSecondsCheck` enum: `NOT_STARTED` / `RUNNING` / `DONE`)
  and `_LEAP_SECONDS_LOCK`: read `_LEAP_SECONDS_CHECK` without the lock as
  a fast path when it is already `DONE`; otherwise acquire
  `_LEAP_SECONDS_LOCK`, and **only if the state is still `NOT_STARTED`**
  set it to `RUNNING`, call `update_leap_seconds()`, and set it to `DONE`
  before releasing. Re-checking for `NOT_STARTED` rather than merely "not
  `DONE`" is load-bearing in both directions the enum documents at
  `astropy/time/core.py:151-158`: a second thread that wins the lock after
  the first has finished sees `DONE` and skips, and a *re-entrant* call on
  the thread already inside `update_leap_seconds()` (which constructs
  `Time` objects, and which is why `_LEAP_SECONDS_LOCK` is an `RLock`
  rather than a `Lock`) sees `RUNNING`, skips, and returns — it must not
  recurse into `update_leap_seconds()` again.
- **`Table.__array__(self, dtype=None, copy=COPY_IF_NEEDED)`** —
  `astropy/table/table.py`, a method on `Table` (`COPY_IF_NEEDED` is
  already imported from `astropy.utils.compat` at line 20). For
  `dtype is None`, returns `self.as_array()` (line 649) with any mask
  discarded (i.e. as a plain `numpy.ndarray`, not a
  `numpy.ma.MaskedArray`, per the interface docstring's "masks are not
  preserved" note) — for a masked `as_array()` result this means returning
  `.data` (or an equivalent unmasked view). For `dtype=object`, returns a
  0-d `object`-dtype `numpy.ndarray` wrapping `self` (matching the
  interface docstring's example where `np.array(t, dtype=object)` prints
  the table's own repr). For every other non-`None` `dtype` — including a
  dtype that happens to match the table's own structured dtype — raises
  `ValueError`, mirroring `Row.__array__` (`astropy/table/row.py:101-102`),
  because coercion is not allowed.

### Data Flow

1. `Time(quantity_with_time_unit)` → `TimeFormat._check_val_type` →
   `quantity_day_frac(val1, val2)` → `(day, frac)` fed into the existing
   `day_frac`-based JD machinery.
2. `np.broadcast_arrays(masked_or_plain_1, masked_or_plain_2, ...)` →
   NumPy's `__array_function__` protocol → `MaskedNDArray.__array_function__`
   → `DISPATCHED_FUNCTIONS[np.broadcast_arrays]` → the new
   `broadcast_arrays` helper → per-array `Masked(...)` results.
3. `LombScargle(t, y, dy=...)` → `has_units(t)`/`has_units(y)`/`has_units(dy)`
   → branches to `strip_units`/`get_unit` handling already present in the
   file.
4. `Time.utc` (or any scale conversion through `"utc"`) → `Time._set_scale`
   → `_check_leapsec()` → (at most once per process) `update_leap_seconds()`
   → ERFA's leap-second table is current for the subsequent ERFA call.
5. `np.array(table)` / `np.asarray(table)` → NumPy calls
   `table.__array__(dtype, copy)` → `Table.as_array()` (unmasked) or an
   object-dtype wrapper around `table`.
6. `LombScargleMultiband(t, y, bands, dy).power(frequency)` →
   `strip_units(self._trel)`/`strip_units(self.y)`/`strip_units(self.bands)`/
   `strip_units(self.dy)` → the unit-free arrays handed to
   `lombscargle_multiband(...)`; on the way back,
   `LombScargleMultiband.model`/`offset` multiply the fitted values by
   `get_unit(self.y)` to restore `self.y`'s unit.

### Interface Contract

```python
# astropy/time/utils.py
def quantity_day_frac(val1, val2=None):
    """Returns (day, frac): float64 scalars/ndarrays, see Context/Key Components."""

# astropy/utils/masked/function_helpers.py
@dispatched_function
def broadcast_arrays(*args, subok=False):
    """np.broadcast_arrays(*masked) must yield a list (NumPy < 2.0) or tuple
    (NumPy >= 2.0) of broadcast arrays; the helper itself returns the
    (result, mask, out) triple that __array_function__ unpacks."""

# astropy/timeseries/periodograms/lombscargle/core.py
def has_units(obj) -> bool: ...

# astropy/time/core.py
def _check_leapsec() -> None: ...

# astropy/table/table.py (method on Table)
def __array__(self, dtype=None, copy=COPY_IF_NEEDED) -> np.ndarray: ...

# astropy/timeseries/periodograms/lombscargle_multiband/core.py
def strip_units(*arrs):
    """One arg -> that value as a plain ndarray (None -> None);
    more than one -> an iterable of them, in order."""

def get_unit(obj):
    """Returns obj.unit if present, else the scalar 1."""
```

These seven signatures must match exactly — they are called positionally
and by keyword from existing, unmodified call sites (see Context).

## Out of Scope

- Astropy's general unit-conversion/`Quantity` system — `quantity_day_frac`
  only consumes it (`astropy.units`, already imported in `astropy/time/utils.py`).
- The rest of the `Time`/`TimeFormat` machinery (JD storage, format
  parsing, scale-transform graph) beyond the single `_check_leapsec` call
  site and `quantity_day_frac`'s two callers.
- The rest of `astropy.utils.masked` (the `Masked`/`MaskedNDArray` classes,
  other `DISPATCHED_FUNCTIONS`/`APPLY_TO_BOTH_FUNCTIONS` entries) beyond
  `broadcast_arrays` itself.
- `Table`'s general construction, column/row manipulation, I/O, or indexing
  — only `__array__` (and its existing dependency `as_array`, which is
  already implemented and must not be modified).
- Coordinate transformations and the Lomb–Scargle periodogram algorithm
  itself (`implementations/`, `_statistics.py`, `implementations/mle.py`)
  — `has_units`/`strip_units`/`get_unit` are pure predicates/converters
  with no periodogram logic of their own.
- Everything else in `LombScargleMultiband`
  (`astropy/timeseries/periodograms/lombscargle_multiband/core.py`) beyond
  the two blank helpers `strip_units`/`get_unit` — the class's fitting,
  regularization, and statistics logic is unchanged and out of scope;
  `strip_units`/`get_unit` are restored only because the class cannot run
  at all without them (see Motivation).
- Actually fetching/parsing a real leap-second file over the network —
  `_check_leapsec` only has to call the existing `update_leap_seconds`,
  not reimplement it.

## Acceptance Scenarios

### Happy Path

- **S1:** Given a `Quantity` `5 * u.day`, when `quantity_day_frac(val1)` is
  called with no `val2`, then it returns a `(day, frac)` pair whose sum
  (via the file's own `day_frac`/float arithmetic) equals `5.0` days, with
  `day` an integer-valued float and `abs(frac) <= 0.5`.
- **S2:** Given two `Quantity` values with time units (e.g. `1 * u.day` and
  `12 * u.hour`), when `quantity_day_frac(val1, val2)` is called with both
  arguments, then the returned `(day, frac)` pair sums to `1.5` days.
- **S3:** Given a plain `numpy.ndarray` (e.g. `np.array([1, 2, 3])`), when
  `has_units(arr)` is called, then it returns `False`; given `5 * u.meter`,
  when `has_units(quantity)` is called, then it returns `True`.
- **S4:** Given two `MaskedNDArray` instances of different broadcastable
  shapes (e.g. shapes `(2, 3)` and `(3,)`), each with its own boolean mask,
  when `np.broadcast_arrays(masked_a, masked_b)` is called, then each
  returned element is a `MaskedNDArray` whose `.unmasked` equals
  `np.broadcast_arrays(masked_a.unmasked, masked_b.unmasked)` for that
  position and whose `.mask` equals the same broadcast applied to the two
  inputs' masks.
- **S5:** Given a `Table` with columns `a=[1, 2]` and `b=[3, 4]`, when
  `np.array(t)` is called (no `dtype`), then the result is a structured
  `numpy.ndarray` (not a `Table`, not a `MaskedArray`) with dtype fields
  `('a', ...)` and `('b', ...)`, equal element-wise to
  `t.as_array()` with any mask stripped.
- **S6:** Given `Time("2019-01-01T00:00:00", scale="tai")`, when its `.utc`
  property is read (the conversion that calls `_check_leapsec()`), then the
  result is `Time("2018-12-31T23:59:23.000", scale="utc")` — the 37-second
  TAI−UTC offset in force on that date.
- **S14:** Given a `LombScargleMultiband` built from `t` in days, `y` in
  `u.mag`, `bands`, and `dy` left as `None`, when `.power(frequency)` is
  called, then it returns a finite power array of the same shape as
  `frequency` — the `dy=None` argument passes through `strip_units` as
  `None` rather than raising.
- **S15:** Given a plain `numpy.ndarray` `arr`, when `arr * get_unit(arr)`
  is evaluated, then the product is still a plain `numpy.ndarray` equal to
  `arr`; given `arr * u.mag`, when `arr * get_unit(arr * u.mag)` is
  evaluated, then the product is a `Quantity` with unit `u.mag`.

### Edge Cases

- **S7:** Given a single `MaskedNDArray` (arity 1), when
  `np.broadcast_arrays(masked_a, subok=True)` is called, then the result
  is still a `list` (NumPy < 2.0) or `tuple` (NumPy >= 2.0) of length 1 —
  not a bare array — and the one element shares memory with `masked_a`'s
  unmasked data (a view, not a copy).
- **S8:** Given masked inputs whose unmasked data is an `ndarray` subclass
  (e.g. `Masked(Quantity)`, as in the existing
  `TestMaskedQuantityBroadcast` setup), when
  `np.broadcast_arrays(ma, mb, mc, subok=False)` is called, then every
  returned element's `.unmasked` is exactly `numpy.ndarray` (subclass
  dropped) while its `.mask` still equals the correspondingly broadcast
  input mask.
- **S9:** Given a time `Quantity` for which `val1.unit.to(u.day)` raises
  `UnitsError` while `val1.to_value(u.day)` succeeds (no stock astropy unit
  has been confirmed to satisfy both halves — the test may have to supply a
  unit whose `to` raises), when `quantity_day_frac(val1)` is called, then it
  returns `(val1.to_value(u.day), 0.0)` rather than raising.
- **S18:** Given a mix of plain and masked inputs — plain `a`, `Masked` `mb`,
  plain `c` — when `np.broadcast_arrays(a, mb, c, subok=True)` is called,
  then `result[0]` and `result[2]` are plain `numpy.ndarray`s equal to `a`
  and to `c` broadcast to the common shape, while `result[1]` is `Masked`
  with both its data and its mask broadcast to that shape (the existing
  `test_broadcast_arrays_not_all_masked` pins this).
- **S19:** Given a `Table` with a masked column (at least one masked
  element), when `np.array(t)` is called with no `dtype`, then
  `type(np.array(t)) is numpy.ndarray` — not `numpy.ma.MaskedArray` — and
  the previously-masked position holds the underlying fill/data value, i.e.
  masks are not preserved.
- **S17:** Given `_LEAP_SECONDS_CHECK` is `RUNNING` — the state that holds
  while the calling thread is already inside `update_leap_seconds()`, which
  itself builds `Time` objects — when that same thread reaches
  `_check_leapsec()` again, then the call returns without invoking
  `update_leap_seconds()` a second time (no recursion, no `RecursionError`,
  and the state is still `RUNNING` afterwards).
- **S16:** Given `864000000 * u.s` (exactly 10000 days), when
  `quantity_day_frac` is called on it, then it returns exactly
  `(10000.0, 0.0)`, bit-identical to `quantity_day_frac(10000 * u.day)` —
  the inexact `1/86400` conversion factor must not be multiplied into the
  result.
- **S10:** Given a `Table`, when `np.array(t, dtype=object)` is called,
  then the result is a 0-d `object`-dtype `numpy.ndarray` whose single
  element is `t` itself (`arr.item() is t` or `arr[()]  is t`), matching
  the interface docstring's example.
- **S11:** Given `Time._set_scale` is invoked from multiple threads
  concurrently, each converting to/from `"utc"` for the first time in the
  process (module-level `_LEAP_SECONDS_CHECK` freshly reset to
  `NOT_STARTED`), when all threads run concurrently (e.g. via
  `ThreadPoolExecutor`), then `update_leap_seconds` is invoked exactly
  once across all threads combined — observable by monkeypatching
  `astropy.time.core.update_leap_seconds` with a call-counting wrapper —
  and every thread's resulting `Time` value is correct; this mirrors
  `astropy/time/tests/test_update_leap_seconds.py::TestUpdateLeapSeconds::test_init_thread_safety`.

### Error Scenarios

- **S12:** Given a `Quantity` with a non-time unit (e.g. `5 * u.meter`),
  when `quantity_day_frac(val1)` is called, then it raises (propagates)
  `astropy.units.UnitsError` (or a subclass), which
  `astropy/time/formats.py:336`'s existing `except u.UnitsError` clause
  relies on to re-raise as `UnitConversionError`.
- **S13:** Given a `Table`, when `np.array(t, dtype=np.float64)` (or any
  concrete non-`object` dtype) is called, then `Table.__array__` raises
  `ValueError`.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*. A green suite that passes for
> the wrong reason does not satisfy this contract — `/verify` will hunt for
> vacuous tests by asking, of each behavior, "what is the smallest change
> that breaks this, and would any test catch it?"

Implement all seven functions/methods exactly at the file paths and with
exactly the signatures given in Interface Contract — they are called from
existing, unmodified code elsewhere in the tree (see Context/Data Flow),
so any signature drift breaks those call sites. Do not modify
`day_frac`, `as_array`, `update_leap_seconds`, `_LEAP_SECONDS_CHECK`,
`_LEAP_SECONDS_LOCK`, `_LeapSecondsCheck`, `_get_data_and_mask_array(s)`,
`broadcast_to`, `NUMPY_LT_2_0`, or `COPY_IF_NEEDED` — build on top of them
as-is.

Write tests to the project's conventions (the existing files
`astropy/time/tests/`, `astropy/utils/masked/tests/test_function_helpers.py`,
`astropy/table/tests/test_table.py`,
`astropy/timeseries/periodograms/lombscargle/tests/`,
`astropy/timeseries/periodograms/lombscargle_multiband/tests/` — currently
only `__init__.py`, so tests for S14/S15 are a new file there) and to
these principles (the same ones `/verify` scores against — see
`references/test-desiderata.md` and `references/anti-patterns.md` in the
blueprint plugin):

- **Behavioral over structural** — assert observable output (return
  values, raised exceptions, broadcast shapes/masks), not internals; the
  suite must survive refactoring of how each function is implemented
  internally.
- **Every test can fail** — no copy-pasted expected values, no asserting a
  constant, no tautologies (AP-2, AP-4). In particular, for S11
  (thread-safety), assert on the actual converted values from every
  thread, not just "no exception was raised."
- **Deterministic, isolated, readable** — the leap-second scenarios (S6,
  S11) must reset/restore `astropy.time.core._LEAP_SECONDS_CHECK` (and any
  ERFA leap-second table state they mutate) so they do not leak into other
  tests, matching the existing `teardown_method` pattern in
  `test_update_leap_seconds.py`.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Test suite is green.
- [ ] Every acceptance scenario (S1…S19) maps to at least one test.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
      the smallest break of its behavior (thought-mutation).
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
      first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings).

## Trade-offs and Limitations

- The non-scaling fallback path for `quantity_day_frac` (S9) is documented
  as potentially reduced-precision by the interface description itself;
  the spec does not require bit-exact precision guarantees for that path,
  only that it returns `(complete_value, 0.0)` without raising.
- `_check_leapsec`'s thread-safety scenario (S11) depends on timing and
  the `ThreadPoolExecutor`-based test pattern already used in
  `test_update_leap_seconds.py`; it is inherently a best-effort
  concurrency test rather than a formal proof of correctness.

## References

- `astropy/time/utils.py` (`day_frac`, existing two-double arithmetic
  helpers)
- `astropy/time/formats.py:280-345` (`TimeFormat._check_val_type`, the
  sole caller of `quantity_day_frac`)
- `astropy/utils/masked/function_helpers.py:280-291` (`broadcast_to`, the
  analogous single-array `@apply_to_both` sibling of `broadcast_arrays`)
- `astropy/utils/masked/core.py:1032-1052` (`MaskedNDArray.__array_function__`,
  how `DISPATCHED_FUNCTIONS` results are consumed)
- `astropy/utils/masked/tests/test_function_helpers.py:159-167` (existing
  `test_broadcast_arrays`/`check2` pattern)
- `astropy/time/core.py:151-158,797,3363-3380,3381-3402` (`_LeapSecondsCheck`,
  `_LEAP_SECONDS_CHECK`, `_LEAP_SECONDS_LOCK`, `_set_scale`,
  `update_leap_seconds`)
- `astropy/time/tests/test_update_leap_seconds.py::TestUpdateLeapSeconds::test_init_thread_safety`
- `astropy/table/table.py:649-709` (`Table.as_array`, the building block
  for `__array__`)
- `astropy/table/row.py:93-104` (`Row.__array__`, the sibling that already
  shows the dtype-coercion `ValueError` and mask-dropping behavior)
- `astropy/table/tests/test_table.py:1593-1606`
  (`test_convert_numpy_object_array`, `test_convert_list_numpy_object_array`
  — existing tests that already pin `np.array(t, dtype=object)`)
- `astropy/utils/masked/tests/test_functions.py:425-449`
  (`test_broadcast_arrays`, `test_broadcast_arrays_not_all_masked`,
  `test_broadcast_arrays_subok_false` — existing expectations for mixed
  masked/plain input and `subok`)
- `astropy/timeseries/periodograms/lombscargle/core.py:19-28` (`get_unit`,
  `strip_units` — the intact single-band siblings the multiband copies
  mirror)
- `astropy/timeseries/periodograms/lombscargle_multiband/core.py:17-32,
  424-428, 469-471, 533-546, 590-691` (`has_units` already defined; the
  blank block where `strip_units`/`get_unit` belong, and their call sites)
- `astropy/timeseries/periodograms/lombscargle_multiband/tests/` currently
  contains only `__init__.py`, so tests exercising `LombScargleMultiband`
  (including S14/S15) are a new file

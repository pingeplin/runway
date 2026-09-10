# 2609.0001 Astropy Utility Interfaces: Five Missing Helper Functions

**Date:** 2026-09-10
**Status:** draft (revised after spec review, 2026-09-10)
**Author:** FeatureBench

> **Review note.** Every file/line reference below was re-checked against
> this checkout during spec review. Three things changed: the claim that
> nothing outside the five files needs to change was wrong (two import
> lines were stripped along with the functions); two companion helpers in
> `lombscargle_multiband/core.py` are also missing and have been added to
> scope (S21); and several other removals exist in this checkout that are
> explicitly **out** of scope (see "Companion gaps found during review").

## Context

This astropy checkout has five small, unrelated utility interfaces that are
entirely absent — each leaving a run of blank lines where the definition
used to be. Each one is a leaf-level helper that other, much larger
subsystems (Time, Table, Quantity/Masked arrays, Lomb-Scargle
periodograms) call into. Those subsystems do not need to be built or
redesigned: they already exist and already call these exact names. Two of
them do, however, need their `import` line repaired, because the missing
name was dropped from the import as well as from the module that defined
it (details below) — so "no changes outside the five files" was not
accurate and has been corrected here.

Confirmed by reading the code in this checkout (line numbers re-verified
during review):

1. `astropy/time/utils.py` already defines `day_frac(val1, val2, factor=None, divisor=None)` (lines 19-76) — a high-precision two-float day/fraction summer used throughout `astropy.time`. It does **not** define `quantity_day_frac`, the `Quantity`-aware wrapper around it (lines 78-121 are the empty gap where it belongs). Its in-repo caller, `TimeFormat._check_val_type` (`astropy/time/formats.py` line 336), calls the bare name `quantity_day_frac(val1, val2)` — but the import at `astropy/time/formats.py` line 20 reads `from .utils import day_frac, two_product, two_sum`, i.e. the name is **not** imported there, so that call site raises `NameError` today. Restoring that import is in scope (see Interface Contract).
2. `astropy/utils/masked/function_helpers.py` defines the `MaskedNDArray` numpy-override machinery: `apply_to_both = FunctionAssigner(APPLY_TO_BOTH_FUNCTIONS)` and `dispatched_function = FunctionAssigner(DISPATCHED_FUNCTIONS)` (lines 196-197), a `_get_data_and_mask_arrays` helper (lines 210-215), and an existing `broadcast_to` override (lines 280-290) that follows the `@apply_to_both` pattern. There is no override for `np.broadcast_arrays`; lines 705-736, between the `block` and `insert` helpers, are the empty gap where it belongs.
3. `astropy/timeseries/periodograms/lombscargle/core.py` calls a module-level `has_units(...)` helper at lines 152, 165, 172, 179, and 188, but the function itself is not defined anywhere in the file or its imports (lines 14-18 are the empty gap where it belongs; its siblings `get_unit` (line 19) and `strip_units` (line 23) are intact and show the house style). Two other modules depend on the same name:
   - `astropy/timeseries/periodograms/bls/core.py` calls the bare name `has_units` at lines 17, 20, 755, 762, 791 and 797, but its import at line 11 reads `from astropy.timeseries.periodograms.lombscargle.core import strip_units` — `has_units` was dropped from it, so those call sites raise `NameError` today. Restoring that import is in scope. (`astropy/timeseries/periodograms/bls/tests/test_bls.py` line 11 imports `has_units` from `lombscargle.core` directly.)
   - `astropy/timeseries/periodograms/lombscargle_multiband/core.py` keeps its own copy of `has_units` (line 17) but is missing `get_unit` and `strip_units` (empty gap at lines 20-30) although it calls them at lines 424-428, 469, 471, 533-536, 546, 590, 617, 619, 652, 655 and 691. See "Companion gaps found during review" below.
4. `astropy/time/core.py` defines the leap-second-check state machine — `_LeapSecondsCheck` enum (`NOT_STARTED`/`RUNNING`/`DONE`, lines 151-154), the `_LEAP_SECONDS_CHECK` module global (line 157), and `_LEAP_SECONDS_LOCK = threading.RLock()` (line 158) — and calls `_check_leapsec()` at line 797 inside `Time._set_scale` whenever a scale conversion involves `"utc"`. The function `_check_leapsec` itself is not defined. `update_leap_seconds(files=None)` (~line 3381) already exists and performs the actual leap-second-table refresh via `astropy.utils.iers.LeapSeconds.auto_open`.
5. `astropy/table/table.py`'s `Table` class already has `as_array(self, keep_byteorder=False, names=None)` (line 649) which builds a structured `ndarray`/`MaskedArray` from the table's columns, preserving masks. `Table` has no `__array__` dunder method (empty gap at lines 1172-1197, immediately after `index_mode`), so `np.array(some_table)` does not go through a table-aware code path today. `COPY_IF_NEEDED` is already imported (line 20), and `Row.__array__` (`astropy/table/row.py` lines 93-104) is the in-repo template for the signature, the docstring wording and the `ValueError("Datatype coercion is not allowed")` behaviour. The existing tests in `astropy/table/tests/test_table.py::TestConvertNumpyArray` (lines 1533-1606) already pin the expected behaviour.

### Companion gaps found during review

This checkout is missing more than the five interfaces above. Reviewing the
files confirmed the following, which the original draft did not mention:

- **In scope, added during review** — `get_unit(obj)` and `strip_units(*arrs)`
  are missing from `astropy/timeseries/periodograms/lombscargle_multiband/core.py`
  (gap at lines 20-30) while being called throughout that module. They are
  the same two helpers that still exist verbatim in the sibling module
  `astropy/timeseries/periodograms/lombscargle/core.py` (lines 19-28), and
  that module's surviving `has_units` (line 17) shows the intended local-copy
  style, so their contract is unambiguous. They are specified in S21.
- **Out of scope, not specified here** — the following are also stubbed out in
  this checkout, cannot be reconstructed from the surrounding code without
  guessing, and are deliberately **not** requirements of this spec:
  `ShapedLikeNDArray.ndim` (`astropy/utils/shapes.py`, gap at lines 250-255;
  the class docstring at line 212 still promises it), the nested `get_err_str`
  helper inside `UnitBase._apply_equivalencies` (`astropy/units/core.py`,
  gap at lines 511-519, called at lines 520-521), a `BaseTimeSeries` member
  (`astropy/timeseries/core.py`, gap at lines 55-96), a `TimeString`-family
  member (`astropy/time/formats.py`, gap at lines 1682-1723), and a `Table`
  initialization helper (`astropy/table/table.py`, gap at lines 1440-1454,
  between `_convert_data_to_col` and `_init_from_dict`). Their absence means a
  whole-package pytest run cannot be green regardless of this spec; see
  Definition of Done for what "green" means here.

## Motivation

These five functions are called by (or are the intended entry point for)
existing code paths — `Time`/`TimeDelta` construction from `Quantity`
values, numpy dispatch for `MaskedNDArray`, the Lomb-Scargle periodogram's
unit-awareness checks, `Time`'s UTC scale conversions, and numpy's array
protocol for `Table`. Without them, those call sites raise `NameError`/
`AttributeError` at runtime or simply don't exist yet, and the associated
pytest suites for each subsystem cannot pass. Each is small and
self-contained, so the fix is to implement exactly these five interfaces
against their exact existing call sites, plus the two one-line import
restorations those call sites need (`astropy/time/formats.py` line 20 and
`astropy/timeseries/periodograms/bls/core.py` line 11, from which the
missing names were also dropped) and the two companion helpers in
`lombscargle_multiband/core.py`. Beyond those, nothing upstream or
downstream changes.

## Proposed Solution

### Overview

Implement each of the five functions/methods in place, in their existing
files, using the helper machinery and patterns that already exist next to
each stub. No new files, no new modules, no changes to public APIs beyond
adding the named interfaces themselves — plus the wiring (two import
lines) and the two companion helpers listed under "Key Components".

### Key Components

- **`quantity_day_frac`** (`astropy/time/utils.py`) — Quantity-to-day-pair converter, built on top of the existing `day_frac`.
- **`broadcast_arrays`** (`astropy/utils/masked/function_helpers.py`) — `np.broadcast_arrays` override for `MaskedNDArray`, registered through the `dispatched_function` registry. Note that the helper must keep track of *which* arguments were masked (S9 requires plain arguments to come back plain), so `_get_data_and_mask_arrays` — which manufactures an all-`False` mask for unmasked arguments and thereby erases that distinction — can only be used alongside a separate record of which arguments were `Masked`.
- **`has_units`** (`astropy/timeseries/periodograms/lombscargle/core.py`) — trivial attribute-presence check.
- **`_check_leapsec`** (`astropy/time/core.py`) — process-lifetime-once, thread-safe gate in front of `update_leap_seconds()`, built on the existing `_LeapSecondsCheck` enum/lock/global.
- **`Table.__array__`** (`astropy/table/table.py`) — numpy array-protocol dunder, built on the existing `as_array()`.

Wiring and companion helpers (necessary for the above to be reachable, see
"Companion gaps found during review"):

- **`from .utils import day_frac, quantity_day_frac, two_product, two_sum`**
  (`astropy/time/formats.py` line 20) — restore `quantity_day_frac` in the
  import used by the call site at line 336.
- **`from astropy.timeseries.periodograms.lombscargle.core import has_units, strip_units`**
  (`astropy/timeseries/periodograms/bls/core.py` line 11) — restore
  `has_units` in the import used by the call sites at lines 17/20/755/762/791/797.
- **`get_unit` / `strip_units`**
  (`astropy/timeseries/periodograms/lombscargle_multiband/core.py`) — module-local
  copies identical in behaviour to the surviving ones in
  `lombscargle/core.py` lines 19-28, next to the `has_units` already there.

### Data Flow

Each of the five is independent; there is no shared data flow between
them. Per-component flow:

1. **`quantity_day_frac`**: `val1` (and optional `val2`) `Quantity` → obtain
   the pure scale factor from `val1.unit` to `u.day` (e.g. `val1.unit.to(u.day)`),
   which raises for units that are not convertible to days by a plain scale →
   if a scale exists, hand the *unconverted* value plus that scale to the
   existing `day_frac` (i.e. plain `day_frac(value, 0.0)` when the factor is
   exactly 1, `day_frac(value, 0.0, factor=...)` for factors `> 1`, and
   `day_frac(value, 0.0, divisor=u.day.to(val1.unit))` for factors `< 1`, so
   that e.g. seconds are divided by the exactly-representable
   `86400.0` rather than multiplied by the inexact `1/86400`) → if no scale
   factor can be obtained, fall back to `val1.to_value(u.day)` as the first
   return value with `0.0` as the second (this path gives up the extra
   precision but still honours enabled equivalencies) → if `val2` is given,
   convert each argument independently by the same rules and return the
   componentwise sums of the two `(day, frac)` pairs (no renormalization, so
   `abs(frac)` may exceed 0.5 in the two-argument case).
2. **`broadcast_arrays`**: `*args` (mix of `MaskedNDArray` and plain
   array-likes) → record which args are `Masked` and separate those into
   `(data, mask)` → broadcast the unwrapped
   data to one common shape with `np.broadcast_arrays(..., subok=subok)` and
   broadcast each masked arg's mask to that same shape → rewrap **only** the
   originally-masked args as `Masked` (leaving plain args plain) → produce a
   `list` (numpy < 2.0) or `tuple` (numpy >= 2.0), matching
   `numpy.broadcast_arrays`'s own version-dependent return type (checked via
   `astropy.utils.compat.NUMPY_LT_2_0`).

   Note on the registry protocol: `dispatched_function` (i.e.
   `FunctionAssigner`, `astropy/units/quantity_helper/function_helpers.py`
   lines 188-214) registers the helper and returns it **unwrapped**, and
   `MaskedNDArray.__array_function__` (`astropy/utils/masked/core.py` lines
   1033-1055) expects a `(result, mask, out)` triple from it, returning
   `result` as-is when `mask is None`. So the helper itself returns
   `(broadcast_list_or_tuple, None, None)`, and the container described above
   is what `np.broadcast_arrays(...)` returns — not what a direct call to the
   module-level helper returns. All acceptance scenarios below are stated in
   terms of `np.broadcast_arrays(...)` for that reason.
3. **`has_units`**: `obj` → `hasattr(obj, "unit")` → `bool`.
4. **`_check_leapsec`**: caller (typically `Time._set_scale`) → if
   `_LEAP_SECONDS_CHECK` is already `DONE`, return without calling
   `update_leap_seconds()` (this check may be made before taking the lock;
   either way the observable is the same) → otherwise take
   `_LEAP_SECONDS_LOCK` and re-read the state → if `NOT_STARTED`, set it to
   `RUNNING`, call `update_leap_seconds()`, then set it to `DONE` → if
   `RUNNING` (a reentrant call on the same thread, which the `RLock` admits),
   return without invoking `update_leap_seconds()` a second time and without
   deadlocking → concurrent callers on other threads block until the state is
   `DONE` and then return, so `update_leap_seconds()` runs exactly once per
   process for a given `NOT_STARTED` starting state.
5. **`Table.__array__`**: `np.array(table)` or `np.asarray(table)` →
   `dtype` validated (`None` or `object` only; anything else raises
   `ValueError`) → for `dtype=object`, return a 0-d object array whose single
   element **is** the table itself (mirroring how numpy then builds arrays of
   tables from lists) → otherwise delegate to `self.as_array()` to build the
   structured array → strip/ignore any mask on the result (return the
   underlying `ndarray` data, not a `MaskedArray`, even for masked tables) →
   return. The `copy` parameter exists so the signature satisfies numpy 2's
   array protocol; `as_array()` always builds new data, and no behaviour is
   specified here for an explicit `copy=False`.

### Interface Contract

```python
# astropy/time/utils.py
def quantity_day_frac(val1, val2=None):
    """Return (day, frac) float64/ndarray pair, sum == val1(+val2) in days."""

# astropy/utils/masked/function_helpers.py
@dispatched_function
def broadcast_arrays(*args, subok=False):
    """Like numpy.broadcast_arrays, applied to data and mask of Masked inputs.

    Returns the (result, mask, out) triple required by the dispatched_function
    protocol, with mask None; `np.broadcast_arrays(...)` therefore yields the
    list (numpy < 2.0) / tuple (numpy >= 2.0) of broadcast arrays.
    """

# astropy/timeseries/periodograms/lombscargle/core.py
def has_units(obj):
    """True iff obj has a 'unit' attribute."""

# astropy/time/core.py
def _check_leapsec():
    """Ensure update_leap_seconds() runs at most once per process, thread-safely."""

# astropy/table/table.py (method on Table)
def __array__(self, dtype=None, copy=COPY_IF_NEEDED):
    """Return a structured ndarray copy of the table; no mask preserved.

    dtype=object returns a 0-d object array wrapping the table itself; any
    other non-None dtype raises ValueError.
    """

# astropy/timeseries/periodograms/lombscargle_multiband/core.py
def get_unit(obj):
    """obj.unit if present, else 1 (same contract as lombscargle/core.py)."""

def strip_units(*arrs):
    """None for None, else np.asarray(a); a single arg returns one value,
    several args return an iterable of values (same contract as
    lombscargle/core.py lines 23-28)."""
```

Wiring (import lines that must be restored so the names above resolve at
their existing call sites):

```python
# astropy/time/formats.py line 20
from .utils import day_frac, quantity_day_frac, two_product, two_sum

# astropy/timeseries/periodograms/bls/core.py line 11
from astropy.timeseries.periodograms.lombscargle.core import has_units, strip_units
```

Signatures must match exactly — these are imported and called by name from
an external pytest suite. Do not rename parameters, add required
parameters, or change the module paths above.

## Alternatives Considered

### Implement `quantity_day_frac` by always calling `.to_value(u.day)` directly

Simpler, but discards precision for the common case (ordinary time units
like seconds/days/years converting to days via a pure scale factor),
which is the entire reason `day_frac`'s two-float Shewchuk arithmetic
exists elsewhere in this file. Rejected — the docstring in the interface
description explicitly calls for high-precision arithmetic in the normal
case, with the direct-conversion path reserved as a fallback.

### Implement `broadcast_arrays` as a thin call to `np.broadcast_to` per array

Would require computing the broadcast shape twice (once to determine it,
once via `broadcast_to` per array) and duplicates logic numpy's own
`broadcast_arrays` already provides. Rejected for the data arrays in favour
of passing them straight through `np.broadcast_arrays` and rewrapping,
consistent with how `broadcast_to` in the same file delegates to the
corresponding numpy function. (Each masked argument's mask still has to be
brought to the resulting common shape individually — `np.broadcast_to` is
the natural tool for that step, since only the data arrays participate in
determining the shape.)

### Implement `_check_leapsec` with a simple non-reentrant `Lock`

A plain (non-reentrant) `threading.Lock` would deadlock if `_check_leapsec`
is ever called again from within the same thread while already holding
the lock (e.g., if `update_leap_seconds()` itself triggers another scale
conversion involving UTC). The module already defines
`_LEAP_SECONDS_LOCK` as an `RLock` specifically to avoid this. Rejected
plain `Lock`; use the existing `RLock` and state enum together so a
same-thread reentrant call observes `RUNNING` and returns without
re-invoking `update_leap_seconds()`.

## Acceptance Scenarios

### Happy Path

- **S1:** Given scalar `Quantity` values in seconds that are an exact whole
  number of days — `n * 86400 * u.s` — when `quantity_day_frac(val1)` is
  called with a single argument, then for **every** `n` it returns exactly
  `(float(n), 0.0)`: `day == n` and `frac == 0.0`, with no residual. Sweep a
  broad set of `n`, not one hand-picked value: every `n` in `1..1000` plus a
  few large ones (e.g. 12345678 and 987654321 — both keep `n * 86400` well
  under `2**53`, so the input is exact). This is the scenario that pins the
  precision requirement. Dividing by the exactly-representable `86400.0`
  (the `divisor=` route through `day_frac`) is exact for every such `n`,
  whereas multiplying by `val1.unit.to(u.day)` — the inexact float
  `1/86400` — is off by around half an ulp, so it lands on a nonzero `frac`
  for a good fraction of the sweep. One value could pass either way by
  luck; the sweep cannot. Additionally, given `36000 * u.s`, `day + frac`
  equals `36000 / 86400` to within one ulp and `abs(frac) <= 0.5` (the
  single-argument bound inherited from `day_frac`).
- **S2:** Given two `Quantity` values, when `quantity_day_frac(val1, val2)`
  is called, then the result is the componentwise sum of the two inputs'
  individual conversions, and the pair still adds up to the right total:
  for `val1 = 2450000 * u.day` and `val2 = 36000 * u.s`, `day == 2450000.0`
  exactly (the integer part is carried in `day`, so no precision is lost in
  the fraction) and `day + frac == 2450000 + 36000 / 86400` to within one
  ulp; for `val1 = 1 * u.day` and `val2 = 12 * u.hour`, `day + frac == 1.5`
  exactly and the returned pair equals the componentwise sum of
  `quantity_day_frac(val1)` and `quantity_day_frac(val2)`. Note that the
  two-argument result is **not** renormalized, so `abs(frac) <= 0.5` is not
  required here.
- **S3:** Given `a = Masked(np.array([1.0, 2.0, 3.0]), mask=[False, True, False])`
  and a plain `b = np.array([[10.0], [20.0]])`, when `np.broadcast_arrays(a, b)`
  is called (dispatching to the `broadcast_arrays` override), then a
  two-element sequence is returned in which: element 0 is a `Masked` array of
  shape `(2, 3)` whose `.unmasked` equals `np.broadcast_to(a.unmasked, (2, 3))`
  and whose `.mask` equals `np.broadcast_to(a.mask, (2, 3))` (i.e.
  `[[False, True, False], [False, True, False]]`), and element 1 is a plain
  `np.ndarray` of shape `(2, 3)` equal to `np.broadcast_to(b, (2, 3))`.
- **S4:** Given `np.array([1, 2, 3])`, `has_units(arr)` returns `False`;
  given `5 * u.meter`, `has_units(quantity)` returns `True`; given `None`
  (the value `dy` takes at `lombscargle/core.py` line 152), `has_units(None)`
  returns `False`; and given any object that merely carries a `unit`
  attribute (not a `Quantity`), it returns `True` — the contract is
  attribute presence, not `Quantity`-ness.
- **S5:** Given `astropy.time.core._LEAP_SECONDS_CHECK` reset to
  `_LeapSecondsCheck.NOT_STARTED` and `astropy.time.core.update_leap_seconds`
  replaced by a call-counting double, when `_check_leapsec()` is called once,
  then the double is invoked exactly once and `_LEAP_SECONDS_CHECK` is left
  as `_LeapSecondsCheck.DONE`.
- **S6:** Given `t = Table([[1, 2], [3, 4]], names=("a", "b"))`, when
  `np.array(t)` is called, then it returns a structured array of length 2
  with `list(result.dtype.names) == ["a", "b"]` and
  `result.tolist() == [(1, 3), (2, 4)]`; `type(result) is np.ndarray` (not a
  subclass and not a `np.ma.MaskedArray`); and the result is a fresh array,
  not the same object as `t.as_array()`. `np.asarray(t)` gives the same
  result as `np.array(t)`.

### Edge Cases

- **S7:** Given an input for which the scale factor to days cannot be
  obtained but a direct conversion still can — the "fallback" path — when
  `quantity_day_frac(val1)` is called, then it returns `(val1.to_value(u.day), 0.0)`
  without raising. Because no stock astropy unit reaches this branch
  *and* converts successfully (see S18 for the branch's failure mode), this
  is verified with a minimal stand-in: an object whose `.unit.to(u.day)`
  raises `u.UnitConversionError` (the exception a real unit raises, so that
  any reasonable `except` clause in the implementation catches it) and whose
  `.to_value(u.day)` returns a known number (e.g. `3.0`), standing in for a
  conversion that is only possible via an enabled equivalency. Expected
  result: `(3.0, 0.0)`.
- **S8:** Given array-valued `Quantity` inputs
  `val1 = np.array([1.0, 2.0, 3.0]) * u.day` and
  `val2 = np.array([12.0, 0.0, 6.0]) * u.hour`, when
  `quantity_day_frac(val1, val2)` is called, then `day` and `frac` are both
  `ndarray`s of shape `(3,)` (not scalars), `day` equals `[1.0, 2.0, 3.0]`
  and `day + frac` equals `[1.5, 2.0, 3.25]` exactly.
- **S9:** Given a mix of masked and plain arguments — e.g.
  `plain_a = np.arange(3.0)`,
  `masked_b = Masked(np.zeros((2, 3)), mask=[[False, True, False], [True, False, False]])`,
  `plain_c = np.ones((2, 1))`, common shape `(2, 3)` — when
  `np.broadcast_arrays(plain_a, masked_b, plain_c, subok=True)` is called
  (at least one argument must be `Masked` for numpy to dispatch to this
  override at all), then every element comes back broadcast to
  the common shape, the element for `masked_b` is `Masked` with its mask
  broadcast to that shape, and the elements for `plain_a`/`plain_c` are
  **not** `Masked` (`isinstance(result[i], Masked)` is `False`); their values
  equal `np.broadcast_to(plain_a, shape)` / `np.broadcast_to(plain_c, shape)`.
- **S10:** Given a `Masked` instance wrapping an `ndarray` subclass — e.g.
  `ma = Masked(np.arange(3.0) * u.m, mask=[False, True, False])` and
  `other = np.zeros((2, 1))` — when `np.broadcast_arrays(ma, other, subok=True)`
  is called, then the masked result's `.unmasked` is still a `Quantity`
  (subclass preserved, and its unit is still `u.m`); and when the same call
  is made with `subok=False`, the result is still `Masked` — masking is never
  dropped, only subclassing — but is a plain `MaskedNDArray` with
  `type(result[0].unmasked) is np.ndarray`. Mask values are identical in both
  cases. This is the same meaning `subok` has for the neighbouring
  `broadcast_to` helper (`function_helpers.py` lines 280-290) and matches
  `test_functions.py::TestMaskedArrayBroadcast::test_broadcast_arrays_subok_false`.
- **S11:** Given `_LEAP_SECONDS_CHECK` reset to `NOT_STARTED` and
  `update_leap_seconds` replaced by a double that itself calls
  `_check_leapsec()` again (a reentrant call on the same thread, which is
  what the `RLock` and the `RUNNING` state exist for), when `_check_leapsec()`
  is called, then it returns (no deadlock, and the test completes rather than
  hanging), the double is invoked exactly once, and the final state is `DONE`.
- **S12:** Given `_LEAP_SECONDS_CHECK` is already `DONE` and
  `update_leap_seconds` replaced by a call-counting double, when
  `_check_leapsec()` is called, then the double is **not** invoked and the
  state remains `DONE`.
- **S13:** Given a masked table with at least one masked entry — e.g.
  `t = Table([[1, 2], [3, 4]], names=("a", "b"), masked=True)` with
  `t["a"].mask = [False, True]` — when `t.__array__()` is called, then
  `np.ma.isMaskedArray(t.__array__())` is `False`, while
  `np.ma.isMaskedArray(t.as_array())` on the same table is `True`. The
  contrast between the two is the behaviour under test: `__array__` drops the
  mask that `as_array()` keeps. Field names and shape are unchanged
  (`list(result.dtype.names) == ["a", "b"]`, `len(result) == 2`).
  **Assert this on `__array__` directly, not on `np.array(t)`:** `np.array`
  and `np.asarray` default to `subok=False` and would strip a returned
  `MaskedArray` to a base `ndarray` themselves, so a `np.array(t)`-based
  assertion passes even for an implementation that never drops the mask —
  i.e. it would be vacuous.
- **S14:** Given `t = Table([[1, 2], [3, 4]], names=("a", "b"))`, when
  `np.array(t, dtype=object)` is called, then it returns a 0-d
  object-dtype `ndarray` whose single element is the table itself
  (`result.shape == ()`, `result.dtype == object`, `result[()] is t`).
  Consequently `np.array([t, t, t], dtype=object)` has shape `(3,)` with each
  element a `Table` — the behaviour already pinned by
  `test_table.py::TestConvertNumpyArray::test_convert_list_numpy_object_array`.
- **S16:** Given a single masked argument `ma`, when
  `np.broadcast_arrays(ma, subok=True)` is called, then the result is a
  one-element container (`list` on numpy < 2.0, `tuple` on numpy >= 2.0, per
  `astropy.utils.compat.NUMPY_LT_2_0`), its element has the same values and
  mask as `ma`, and it is a **view**, not a copy:
  `np.may_share_memory(result[0], ma.unmasked)` is `True`. (An
  implementation that materialises copies fails the existing
  `test_function_helpers.py::TestShapeManipulation::test_broadcast_arrays`,
  lines 159-168.)
- **S17:** Given `_LEAP_SECONDS_CHECK` reset to `NOT_STARTED` and
  `update_leap_seconds` replaced by a double that counts its calls and does
  not return until all four worker threads have signalled that they are
  about to call `_check_leapsec()` (each thread sets its own
  `threading.Event` immediately before the call; the double waits for all
  four, with a timeout so a broken implementation fails instead of hanging
  the suite). Do not use a sleep — it makes overlap a coin flip — and do not
  make the double wait on a `Barrier` that the other threads must reach
  *through* `_check_leapsec()`, since they will be blocked on the lock and
  never reach it. When four threads call `_check_leapsec()` concurrently,
  then:
  the double is invoked exactly once in total; every thread returns (none
  hangs); **and every thread observes `_LEAP_SECONDS_CHECK is DONE` at the
  moment its own call returns**. That last assertion is the one that bites:
  an implementation that returns early on the `RUNNING` state without
  distinguishing "this thread" from "another thread" lets a second thread
  return while the table is still being loaded, and it is not caught by the
  call count or by the post-join state.

### Error Scenarios

- **S15:** Given `t = Table([[1, 2], [3, 4]], names=("a", "b"))`, when
  `Table.__array__` is invoked with a dtype that is neither `None` nor
  `object` — both via numpy, `np.array(t, dtype=[("c", "i8"), ("d", "i8")])`
  (the case already asserted at `test_table.py` line 1549), and directly,
  `t.__array__(dtype=np.float64)` — then it raises `ValueError`. Use the
  same message as the sibling `Row.__array__` (`row.py` line 102):
  `"Datatype coercion is not allowed"`.
- **S18:** Given a `Quantity` whose unit is not convertible to days at all,
  e.g. `5 * u.m`, when `quantity_day_frac(val1)` is called, then it raises
  `u.UnitConversionError` (a subclass of `u.UnitsError`). This matters
  beyond the function itself: `TimeFormat._check_val_type`
  (`formats.py` lines 335-341) catches `u.UnitsError` around this call and
  re-raises it as `UnitConversionError("only quantities with time units can
  be used to instantiate Time instances.")`, so an implementation that
  raised, say, `TypeError` or `AttributeError` here would break that
  contract.

### Wiring and Companion Scenarios

- **S19:** Given `astropy.time.formats`, when the `Quantity` branch of
  `TimeFormat._check_val_type` (lines 326-341) is exercised — e.g. by
  constructing the format object directly,
  `TimeJD(2450000.5 * u.day, None, "tai", 3, "*", "*")`, which
  `TimeFormat.__init__` routes through `_check_val_type` — then no
  `NameError: name 'quantity_day_frac' is not defined` is raised and the
  resulting `jd1 + jd2 == 2450000.5`.
- **S20:** Given `astropy.timeseries.periodograms.bls.core.validate_unit_consistency`,
  when it is called as `validate_unit_consistency(5 * u.m, 3)`, then no
  `NameError: name 'has_units' is not defined` is raised and the result is
  `3 * u.m`; and when called as
  `validate_unit_consistency(5.0, 3 * u.dimensionless_unscaled)`, the result
  is the plain value `3.0` (not a `Quantity`), per lines 16-23 of that
  module.
- **S21:** Given `astropy.timeseries.periodograms.lombscargle_multiband.core`,
  when `get_unit` and `strip_units` are used as that module already calls
  them, then: `get_unit(5 * u.m) == u.m` and `get_unit(np.array([1.0])) == 1`;
  `strip_units(None) is None`; `strip_units(np.arange(3.0) * u.m)` is a plain
  `np.ndarray` equal to `[0.0, 1.0, 2.0]` with no `unit` attribute; and
  `strip_units(np.arange(3.0) * u.m, None)` unpacks to two values, the first
  a plain `np.ndarray`, the second `None`. Behaviour must match the surviving
  implementations in `lombscargle/core.py` lines 19-28.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*. A green suite that passes for
> the wrong reason does not satisfy this contract — `/verify` will hunt
> for vacuous tests by asking, of each behavior, "what is the smallest
> change that breaks this, and would any test catch it?"

**Scope discipline:** implement the five interfaces listed above, at their
exact existing file paths and signatures, plus the two import restorations
and the two `lombscargle_multiband` companion helpers listed under "Key
Components" and "Interface Contract". Do **not** build out Astropy's
general unit system, the Time/date system, the `Table` type beyond
`__array__`, coordinate transformations, or the Lomb-Scargle algorithm —
all of that already exists in this codebase and is out of scope. Do **not**
attempt the "out of scope" gaps listed under "Companion gaps found during
review" (`ShapedLikeNDArray.ndim`, `get_err_str`, and the three larger
removed members); they cannot be reconstructed from this checkout without
guessing, and inventing behaviour for them is worse than leaving them.
Reuse existing helpers each stub sits next to (`day_frac`,
`_get_data_and_mask_array(s)` — subject to the caveat under Key
Components, `as_array`, the `_LeapSecondsCheck` enum/lock/global) rather
than reimplementing their logic.

Implement however you work best — blueprint does not prescribe order,
cadence, or commit structure. Only the result is checked. Write tests to
the project's conventions (this repo uses `pytest`; see
`astropy/time/tests/test_update_leap_seconds.py` for the leap-second state
reset pattern, `astropy/utils/masked/tests/test_function_helpers.py` and
`astropy/utils/masked/tests/test_functions.py` for the masked-broadcast
patterns, `astropy/timeseries/periodograms/lombscargle/tests/` and
`astropy/timeseries/periodograms/bls/tests/test_bls.py` for the periodogram
helpers, and `astropy/table/tests/test_table.py::TestConvertNumpyArray` for
the table array protocol. Note
`astropy/timeseries/periodograms/lombscargle_multiband/tests/` currently
contains only `__init__.py`, so S21's tests are new files there) and to
these principles (the same ones `/verify` scores against):

- **Behavioral over structural** — assert observable output/effects
  (return values, raised exceptions, mask contents, call counts on
  `update_leap_seconds`), not internals; the suite must survive
  refactoring.
- **Every test can fail** — no copy-pasted expected values, no asserting
  a constant, no tautologies.
- **Deterministic, isolated, readable** — for `_check_leapsec`, isolate
  process-global state (`_LEAP_SECONDS_CHECK`, `_LEAP_SECONDS_LOCK`)
  between tests (e.g. monkeypatch/reset the module globals) rather than
  relying on test execution order; use AAA structure with inline setup.
  Substitute a double for `update_leap_seconds` so no test depends on
  network access, ERFA state, or leap-second table freshness.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Every acceptance scenario (S1-S21) maps to at least one test, and
      those tests pass.
- [ ] These pre-existing tests, which exercise the interfaces above and are
      not expected to touch the out-of-scope gaps, pass:
      `astropy/utils/masked/tests/test_functions.py::TestMaskedArrayBroadcast`
      (and its `TestMaskedQuantityBroadcast`/`TestMaskedLongitudeBroadcast`
      subclasses),
      `astropy/utils/masked/tests/test_function_helpers.py::TestShapeManipulation::test_broadcast_arrays`,
      and, in `astropy/table/tests/test_table.py::TestConvertNumpyArray`, the
      three tests `test_convert_numpy_array`, `test_convert_numpy_object_array`
      and `test_convert_list_numpy_object_array` (the byteswap tests in that
      class read files and build tables from structured arrays, which needs
      the out-of-scope `table.py` gap at lines 1440-1454). If one of these
      still fails for a reason traceable to an out-of-scope gap rather than
      to the interfaces specified here, record that rather than working
      around it.
- [ ] The four call sites that reference the restored names resolve them:
      no `NameError` from `astropy/time/formats.py` line 336,
      `astropy/timeseries/periodograms/bls/core.py` lines 17/20, or the
      `get_unit`/`strip_units` calls in
      `astropy/timeseries/periodograms/lombscargle_multiband/core.py`.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
      the smallest break of its behavior (thought-mutation).
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
      first); no anti-pattern violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings) in any touched file.

**"Green" is scoped deliberately.** A whole-package `pytest astropy` run
cannot pass in this checkout regardless of this spec, because of the
out-of-scope gaps recorded under "Companion gaps found during review"
(most sharply `ShapedLikeNDArray.ndim`, which `Time` and the
representation classes rely on). Do not treat a full-repo red run as a
failure of this spec, and do not "fix" it by guessing at those gaps.

## Trade-offs and Limitations

- `_check_leapsec`'s "at most once per process" guarantee is inherently
  process-global, mutable state; tests that exercise it must reset
  `astropy.time.core._LEAP_SECONDS_CHECK` (and must not leave it mutated
  in a way that breaks other tests in the same process/session).
- `quantity_day_frac`'s fallback path (S7) trades precision for
  correctness/generality when a unit cannot be expressed as a simple
  scale to days; this is a documented, intentional limitation of the
  interface, not a bug to fix. Its test necessarily uses a stand-in object
  (no stock astropy unit both misses the scale path and converts
  successfully), so S7 is the one scenario coupled to the attribute access
  the implementation makes (`val1.unit.to(u.day)` then `val1.to_value(u.day)`);
  S18 covers the same branch with a real `Quantity`.
- `broadcast_arrays`'s return type (`list` vs `tuple`) is
  numpy-version-dependent by design, mirroring `numpy.broadcast_arrays`
  itself — apart from the container-type check in S16, which keys off
  `NUMPY_LT_2_0` exactly as the existing test does, tests should check
  element-wise content and `subok`/mask behaviour rather than asserting a
  specific container type.
- The five interfaces are not the only code missing from this checkout.
  The out-of-scope gaps listed in "Companion gaps found during review" mean
  large parts of `astropy.time`, `astropy.units` error handling,
  `astropy.timeseries` and `astropy.table` remain broken after this spec is
  fully satisfied. That is expected and accepted here.

## Open Questions

- [ ] Scope call made during review, flagged for the requester rather than
      silently absorbed: `get_unit`/`strip_units` in
      `lombscargle_multiband/core.py` were **added** to this spec (S21)
      because they are missing yet called throughout that module, and their
      contract is fixed verbatim by the surviving copies in
      `lombscargle/core.py`. The five larger out-of-scope gaps were
      **excluded**, because specifying them would mean inventing behaviour.
      If the requester wants those covered too, they need their own spec.
- [ ] Consequence the requester must weigh: **this spec can be fully
      satisfied while a Lomb-Scargle (or `Time`, or `Table`) test suite is
      still red.** Concretely, `LombScargle._validate_inputs`
      (`lombscargle/core.py` lines 156-159) and its multiband counterpart
      rely on `units.UnitConversionError` being raised for mismatched `dy`
      units — but with `get_err_str` missing from
      `UnitBase._apply_equivalencies`, that path raises `NameError` first;
      and anything that feeds `Time` objects into a periodogram needs
      `ShapedLikeNDArray.ndim`. Both are Tier-C gaps excluded above.

## References

- `astropy/time/utils.py` (existing `day_frac`, lines 19-76)
- `astropy/time/formats.py` (call site at line 336; import to restore at
  line 20; `TimeFormat.__init__`/`_check_val_type`, lines 157-172 and
  321-366)
- `astropy/utils/masked/function_helpers.py` (existing `broadcast_to`
  lines 280-290, `_get_data_and_mask_array(s)` lines 200-215,
  `apply_to_both`/`dispatched_function` lines 196-197)
- `astropy/utils/masked/core.py` (`__array_function__` dispatch contract,
  lines 1009-1055)
- `astropy/units/quantity_helper/function_helpers.py` (`FunctionAssigner`,
  lines 188-214 — registers and returns the helper unwrapped)
- `astropy/utils/masked/tests/test_functions.py` (existing broadcast
  expectations, lines 401-457) and
  `astropy/utils/masked/tests/test_function_helpers.py` (lines 159-168)
- `astropy/time/core.py` (`_LeapSecondsCheck`, `_LEAP_SECONDS_CHECK`,
  `_LEAP_SECONDS_LOCK` lines 151-158; call site line 797;
  `update_leap_seconds` line 3381) and
  `astropy/time/tests/test_update_leap_seconds.py` (state reset pattern,
  lines 85-102)
- `astropy/table/table.py` (existing `Table.as_array`, line 649;
  `COPY_IF_NEEDED` import, line 20), `astropy/table/row.py`
  (`Row.__array__` template, lines 93-104), and
  `astropy/table/tests/test_table.py::TestConvertNumpyArray` (lines
  1533-1606)
- `astropy/timeseries/periodograms/lombscargle/core.py` (call sites of
  `has_units`; surviving `get_unit`/`strip_units`, lines 19-28),
  `astropy/timeseries/periodograms/bls/core.py` (import line 11, call sites
  lines 16-23 and 755-797), and
  `astropy/timeseries/periodograms/lombscargle_multiband/core.py`
  (surviving `has_units` line 17, gap at lines 20-30)

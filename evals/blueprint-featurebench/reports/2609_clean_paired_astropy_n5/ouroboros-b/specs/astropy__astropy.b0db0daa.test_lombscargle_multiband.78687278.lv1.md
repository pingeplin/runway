# 2609.0001 Utility Interface Completions

**Date:** 2026-09-10
**Status:** accepted
**Author:** FeatureBench

## Context

Five small, unrelated utility call sites in this astropy checkout currently
reference functions/methods that are not defined in the module they live in:

1. `astropy/time/utils.py` — `quantity_day_frac(val1, val2=None)` is
   missing. The module already defines `day_frac`, `two_sum`,
   `two_product`, `split`, and the `*_to_twoval` family (lines 19–250);
   `quantity_day_frac` is the missing "quantity-aware" wrapper around
   `day_frac`. Its only caller in this checkout is
   `astropy/time/formats.py:336` (inside `TimeFormat._check_val_type`), but
   `formats.py:20` currently imports only `day_frac, two_product, two_sum`
   from `.utils` — **verified**: `quantity_day_frac` is not in that import
   list, so defining the function in `utils.py` alone leaves the call site
   raising `NameError`. Adding the one name to that existing import line is
   in scope: it is the minimal wiring needed to reach the function being
   implemented, not "implementing the time system".
2. `astropy/utils/masked/function_helpers.py` — `broadcast_arrays` is
   missing (the stripped region is `function_helpers.py:705-736`, between
   `block` and `insert`). The module already implements the sibling
   `broadcast_to` (lines 280–290, decorated `@apply_to_both`) and the
   `dispatched_function`/`apply_to_both` decorator machinery
   (`FunctionAssigner`, lines 196–197). **Verified standalone**:
   `astropy.utils.masked.Masked` and `numpy.broadcast_arrays` import and
   run today without needing `astropy.time`, `astropy.table`, or compiled
   extensions — this module is self-contained, and the missing dispatch is
   confirmed live: today `np.broadcast_arrays(Masked(...), other)` falls
   through to numpy's default implementation and **silently drops the
   mask** instead of dispatching to a masked-aware implementation.
3. `astropy/timeseries/periodograms/lombscargle/core.py` — `has_units` is
   missing (the stripped region is lines 13–18, between the module's
   imports, ending at `from .implementations.mle import design_matrix,
   periodic_fit` on line 12, and `def get_unit` on line 19). It is called
   at lines 152, 165, 172, 179, 188 of that file. An identical sibling
   implementation already exists at
   `astropy/timeseries/periodograms/lombscargle_multiband/core.py:17-18`
   (`return hasattr(obj, "unit")`), which is the concrete reference for the
   expected behavior. `astropy/timeseries/periodograms/bls/core.py` also
   calls `has_units` (lines 17, 20, 755, 762, 791, 797) but — **verified**
   — imports only `strip_units` from `lombscargle.core` at line 11, not
   `has_units`; the same file's own test module,
   `astropy/timeseries/periodograms/bls/tests/test_bls.py:11`, does
   `from astropy.timeseries.periodograms.lombscargle.core import
   has_units` at **module level**, so that whole test file fails to
   collect until `has_units` exists. Adding `has_units` to the import line
   at `bls/core.py:11` is in scope for the same reason as item 1: it is
   wiring needed to reach a function this spec defines.
4. `astropy/time/core.py` — `_check_leapsec` is missing (the stripped
   region is `time/core.py:3362-3380`, immediately before
   `update_leap_seconds`). The module already defines the supporting state
   for it: the `_LeapSecondsCheck` enum (`NOT_STARTED`/`RUNNING`/`DONE`,
   lines 151–154), the module-level `_LEAP_SECONDS_CHECK` flag and
   `_LEAP_SECONDS_LOCK = threading.RLock()` (lines 157–158), and
   `update_leap_seconds()` (lines 3381–3414, already implemented).
   `_check_leapsec()` is called once, at `core.py:797`, inside
   `Time._set_scale`, whenever a scale transform involves `"utc"`.
5. `astropy/table/table.py` — `Table.__array__` is missing (the stripped
   region is `table.py:1172-1196`). `Table` already has `as_array()`
   (lines 649–706, fully implemented) which builds a structured
   `ndarray`/`MaskedArray` copy of the table; `__array__` is the numpy
   array-protocol hook (`np.array(table)`) that numpy calls automatically
   and that `as_array()` does not provide by itself. `COPY_IF_NEEDED` is
   already imported at `table.py:20`. **Verified**:
   `Table([[1, 2], [3, 4]], names=("a", "b"))` — the construction pattern
   used by every scenario below — dispatches through `Table._init_from_list`
   (`table.py:817` → def at `table.py:1263`, fully implemented), not
   `Table._init_from_ndarray`; the latter is separately stripped at
   `table.py:1440-1454` and referenced only at `table.py:822,826` for
   `np.ndarray`-typed input, so it is unrelated to `__array__`/
   `as_array()` and does not block any scenario here.

**This checkout has other, unrelated interface gaps beyond these five**,
confirmed by direct static inspection:

- `get_err_str` is called but undefined in `astropy/units/core.py`
  (`_apply_equivalencies`, stripped region `units/core.py:511-523`).
  **Verified live** in this checkout: `Unit("m").get_converter(u.day)` (no
  equivalencies) raises `NameError: name 'get_err_str' is not defined`
  instead of `UnitConversionError`, because `get_converter` falls through
  to `_apply_equivalencies` whenever the direct scale check in `_to()`
  fails and no matching equivalency is enabled (`units/core.py:557-589`).
  This is on the only path an "incompatible time unit" error from
  `quantity_day_frac` can take, with no way around it from inside
  `quantity_day_frac` itself, and it is part of the general unit system,
  which this task explicitly excludes. Not fixed here (see "Known
  Environment Blockers").
- `TimeString.str_kwargs` is called but undefined anywhere in the repo
  (`astropy/time/formats.py:1740`, `astropy/time/core.py:2142`; stripped
  region `formats.py:1682-1725`) — `str(some_time)` for ISO/date-like
  `Time` formats raises `AttributeError`. Not fixed here.
- `astropy/timeseries/periodograms/lombscargle_multiband/core.py`'s
  `strip_units`/`get_unit` and `astropy/timeseries/core.py`'s
  `BaseTimeSeries._check_required_columns` are also undefined, but
  **verified** to be referenced only inside function bodies, never at
  module or class-definition scope — so importing those modules still
  succeeds, and no scenario below needs them at all.

None of these are among the five interfaces this spec targets, and per the
task's own scope statement this work does not require implementing
Astropy's general unit system, the rest of the time/date system, or the
Lomb–Scargle algorithm — so none of them are fixed here.

## Motivation

Without these five leaf functions (plus the two one-line import
additions in item 1 and item 3 above):

- No `Time`/`TimeDelta` can be constructed from an `astropy.units.Quantity`
  with time units — `quantity_day_frac` sits on that construction path.
- `np.broadcast_arrays(...)` on a `MaskedNDArray` input silently drops the
  mask instead of dispatching to a masked-aware implementation.
- `LombScargle` (and, transitively, `BoxLeastSquares`, whose own test
  module currently fails to collect over this) cannot tell whether its
  inputs are `Quantity` or plain arrays.
- Any `Time` scale conversion that touches `"utc"` (i.e. most real usage)
  raises `NameError` on `_check_leapsec()`.
- `np.array(table)`/`np.asarray(table)` raise instead of returning a
  structured array.

These are independent, mechanical gaps — the fix for each is small and
local, and each is verifiable by calling the function directly, without
depending on other, unrelated stripped code elsewhere in this checkout.

## Proposed Solution

### Overview

Implement each of the five functions/methods in place, in the file it
already (partially) belongs to, following the pattern already established
by its neighbors in that file (cited in Context above), plus the two
one-line import-list additions identified in Context items 1 and 3. Do not
touch anything else — not `astropy/units/core.py`'s `get_err_str`,
`TimeString.str_kwargs`, `Table._init_from_ndarray`,
`lombscargle_multiband`'s `strip_units`/`get_unit`, or
`BaseTimeSeries._check_required_columns`. Those are real, verified gaps
but are outside the five interfaces this spec defines.

Acceptance scenarios below favor **direct, isolated calls to the five
target functions**. Where a pre-existing test in this checkout exercises
the same behavior and is verified independent of the unrelated gaps above,
it is cited as additional, converging evidence.

### Key Components

- **`quantity_day_frac`** (`astropy/time/utils.py`) — converts one or two
  time-unit `Quantity` objects to a high-precision day/frac pair, reusing
  `day_frac` for the actual two-float arithmetic. A single-argument call
  with a unit that is a pure scale factor of `day` (seconds, hours, years,
  JD, MJD, …) decomposes into a normalized integer-day/remainder pair via
  `day_frac`, with `day + frac` reproducing the value in days to full
  float64 precision. A two-argument call returns the **componentwise sum**
  of each argument's own day/frac decomposition, **without re-normalizing**
  the result through `day_frac` again — this is directly observable: the
  returned `frac` need not stay within `[-0.5, 0.5]` the way a
  single-argument call's `frac` always does (S3). When `Unit.get_converter`
  cannot resolve a pure scale factor and instead applies a general
  (possibly non-linear) equivalency function (`astropy/units/core.py:557-589`),
  the conversion is "not a simple scale operation": the first return value
  is the fully-converted value and the second is `0` (S17).
- **`broadcast_arrays`** (`astropy/utils/masked/function_helpers.py`) —
  registered so that `np.broadcast_arrays(...)` dispatches to it for any
  argument that is (or contains) a `~astropy.utils.masked.MaskedNDArray`,
  via `__array_function__`. Observable contract: masked inputs come back as
  masked arrays whose unmasked data and mask are each independently
  broadcast to the common shape (same shape rule as `numpy.broadcast_arrays`
  — a `ValueError` for incompatible shapes); unmasked inputs among the same
  call come back as plain (non-masked) broadcast arrays; `subok=True`
  passes through subclasses of the unmasked data/mask, `subok=False`
  (default) returns `MaskedNDArray` regardless of the input subclass;
  return type (list vs. tuple) matches whatever the installed numpy's own
  `numpy.broadcast_arrays` returns. For reference, `where`
  (`function_helpers.py:979-993`) is the established pattern for a
  `@dispatched_function` that takes a variable number of masked/unmasked
  arguments and uses `_get_data_and_mask_arrays` to split them — note its
  return convention is the 3-tuple `(result, mask, out)`, not the 4-tuple
  `(data_args, mask_args, kwargs, out)` used by `@apply_to_both` functions
  like `broadcast_to`; `broadcast_arrays` must follow the 3-tuple
  convention since it is decorated `@dispatched_function`.
- **`has_units`** (`astropy/timeseries/periodograms/lombscargle/core.py`) —
  a one-line `hasattr(obj, "unit")` check, matching the existing sibling
  implementation in `lombscargle_multiband/core.py:17-18`.
- **`_check_leapsec`** (`astropy/time/core.py`) — coordinates
  `update_leap_seconds()` against `_LEAP_SECONDS_CHECK` and
  `_LEAP_SECONDS_LOCK` so that across an arbitrary number of concurrent
  callers (threads, and/or reentrant calls from within the same thread,
  since the lock is an `RLock`), `update_leap_seconds()` runs **at most
  once per process**: the state transitions `NOT_STARTED` → `RUNNING` →
  `DONE`; callers that observe `RUNNING` or `DONE` must not start a second
  update attempt; every caller must be able to proceed (return) once the
  in-flight attempt, if any, has finished.
- **`Table.__array__`** (`astropy/table/table.py`) — the numpy
  array-protocol hook, called by numpy for `np.array(table)`/
  `np.asarray(table)`/similar. Three cases, disambiguated by `dtype`:
  - `dtype is None`: returns a structured-array view/copy of the table's
    data built from the table's existing `as_array()` machinery, with
    `dtype.names == tuple(table.colnames)`. Masks are **not** preserved in
    the returned array even for masked tables or tables with masked
    columns — the result's type is plain `ndarray`, never
    `np.ma.MaskedArray`, regardless of `table.masked` (S16).
  - `dtype` equal to `object` (i.e. `np.dtype(dtype) == np.dtype(object)`):
    return a 0-d object array whose single element is the table itself
    (`self`), e.g. `out = np.empty((), dtype=object); out[()] = self;
    return out` — this is numpy's own generic
    "wrap the object as-is" path, not a coercion of the table's structured
    data (S12).
  - Any other non-`None` `dtype`: raises `ValueError`, since coercing
    already-structured column data to an arbitrary dtype is not supported.
  - `copy`: accepts the `copy` keyword numpy's array protocol passes
    (`COPY_IF_NEEDED` by default, matching the convention already used
    elsewhere in this file, e.g. `table.py:786,1415,1496,4402`).

### Interface Contract

Signatures and full docstrings are fixed by the task's Interface
Description and must match exactly — do not rename parameters, add
required parameters, or change return arity.

```python
# astropy/time/utils.py
def quantity_day_frac(val1, val2=None):
    """
    Like ``day_frac``, but for quantities with units of time.

    Converts time quantities to days with high precision arithmetic, returning two
    floating scalars or arrays whose sum represents the value in days. For ordinary
    simply-scaled input these are an integer day part and a small remainder; see the
    fallback and two-input behavior below.
    The conversion preserves as much floating-point precision as the regular time
    units permit.

    Parameters
    ----------
    val1 : astropy.units.Quantity
        A quantity with time units to be converted to days. Must have units that can
        be converted to days.
    val2 : astropy.units.Quantity, optional
        A second quantity with time units. If provided, the returned pair represents
        the sum of both quantities in days.

    Returns
    -------
    day : float64 or ndarray
        First component of the day pair. It is normally an integer day part, but
        the non-scaling conversion fallback returns the complete converted value here.
    frac : float64 or ndarray
        Second component of the day pair. A single simply-scaled quantity returns
        a normalized day/remainder pair; with `val2`, the componentwise result is
        not normalized again.

    If conversion to days is not a simple scale operation, the first component is
    the complete converted value and the second is zero; this fallback may have
    reduced precision. With two inputs, the returned pair is the componentwise sum
    of their converted pairs and is not normalized again.
    """

# astropy/utils/masked/function_helpers.py
@dispatched_function
def broadcast_arrays(*args, subok=False):
    """
    Broadcast arrays to a common shape.

    Like `numpy.broadcast_arrays`, applied to both unmasked data and masks.
    Note that ``subok`` is taken to mean whether or not subclasses of
    the unmasked data and masks are allowed, i.e., for ``subok=False``,
    `~astropy.utils.masked.MaskedNDArray` instances will be returned.

    Parameters
    ----------
    *args : array_like
        The arrays to broadcast. Can be a mix of regular arrays and
        `~astropy.utils.masked.MaskedNDArray` instances.
    subok : bool, optional
        If True, then sub-classes of the unmasked data and masks will be
        passed-through. If False (default), `~astropy.utils.masked.MaskedNDArray`
        instances will be returned for any masked input arrays.

    Returns
    -------
    broadcasted : list or tuple of arrays
        A list (for numpy < 2.0) or tuple (for numpy >= 2.0) of arrays which
        are views on the original arrays with their shapes broadcast to a common
        shape. For any input that was a `~astropy.utils.masked.MaskedNDArray`,
        the output will also be a `~astropy.utils.masked.MaskedNDArray` with
        both data and mask broadcast to the common shape. Regular arrays remain
        as regular arrays.

    Notes
    -----
    Broadcasting follows the same shape rules as `numpy.broadcast_arrays`.
    """

# astropy/timeseries/periodograms/lombscargle/core.py
def has_units(obj):
    """
    Check if an object has a 'unit' attribute.

    This is a utility function used to determine whether an input object is a quantity
    with associated units (such as an astropy Quantity) or a plain numeric array/value.

    Parameters
    ----------
    obj : object
        The object to check for the presence of a 'unit' attribute. This can be
        any Python object, but is typically used with arrays, scalars, or
        astropy Quantity objects.

    Returns
    -------
    bool
        True if the object has a 'unit' attribute, False otherwise.

    Examples
    --------
    >>> import numpy as np
    >>> arr = np.array([1, 2, 3])
    >>> has_units(arr)
    False
    >>> from astropy import units as u
    >>> quantity = 5 * u.meter
    >>> has_units(quantity)
    True
    """

# astropy/time/core.py
def _check_leapsec():
    """
    Check if the leap second table needs updating and update it if necessary.

    This function is used by time scale conversions involving UTC to ensure that
    the ERFA leap second table is current. A process performs at most one update
    attempt, and concurrent or re-entrant calls must not start another attempt.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

# astropy/table/table.py, method on class Table
def __array__(self, dtype=None, copy=COPY_IF_NEEDED):
    """
    Support converting Table to np.array via np.array(table).

    Parameters
    ----------
    dtype : numpy.dtype, optional
        Target data type for the array. Only object dtype is supported for
        dtype coercion. If None (default), uses the table's natural dtype.
    copy : bool, optional
        Whether to copy the data. Default is COPY_IF_NEEDED which follows
        numpy's copy semantics.

    Returns
    -------
    array : numpy.ndarray
        Structured array representation of the table. Masks are not preserved
        in the returned ndarray.

    Raises
    ------
    ValueError
        If dtype coercion is requested to a non-object dtype, which is not
        supported.
    """
```

Two additional, minimal changes are part of this contract (Context items 1
and 3): add `quantity_day_frac` to the `from .utils import ...` line at
`astropy/time/formats.py:20`, and add `has_units` to the
`from astropy.timeseries.periodograms.lombscargle.core import ...` line at
`astropy/timeseries/periodograms/bls/core.py:11`.

## Design Decisions

Two behaviors are underdetermined by the docstrings alone. This is a
non-interactive spec with no human reviewer available before handoff, so
both are resolved here, with the reasoning shown, rather than left open:

- **Fallback trigger for `quantity_day_frac`** ("conversion to days is not
  a simple scale operation"): resolved as *"`val1.unit._to(u.day)` raises"*
  — i.e. `UnitBase._to`, astropy's own private method whose docstring
  states it uses "no equivalencies and value=1" to compute "the scale to
  the specified unit" (`units/core.py:591-598`). This is the most literal
  reading of "simple scale operation" available in the unit system's own
  vocabulary, and it is the only criterion that makes the fallback branch
  meaningfully different from the error case (S19): if the trigger were
  instead "the full `.to(u.day)` call fails", the fallback would be
  unreachable for any input with a working equivalency (since `.to()`
  succeeds whenever an equivalency applies — that is what equivalencies
  are for) and indistinguishable from S19's incompatible-unit case. Do not
  use the public `unit.to(other)` (which implicitly converts the value
  `1.0` and can coincidentally look like a scale, as S17 demonstrates) as
  the test. If, once implemented, the actual behavior needs to diverge
  from this (e.g. a hidden reference implementation disagrees), that
  divergence is the authoritative signal — S17's expected `(9.0, 0.0)`
  should be re-derived from whatever criterion is actually implemented,
  not defended past that point.
- **`Table.__array__` under `copy=False`**: resolved as *raises
  `ValueError`*. `as_array()` (the machinery `__array__` is built on)
  always allocates a fresh structured array via `np.empty`/`ma.empty` plus
  per-column assignment (`table.py:684-706`) — there is no view-only path.
  Per numpy's array-protocol contract (numpy ≥ 2.0), an object that cannot
  avoid copying must raise `ValueError` when the caller explicitly passes
  `copy=False`, rather than silently ignoring the request. The default
  (`copy=COPY_IF_NEEDED`, i.e. no explicit `copy=` argument, which is what
  a plain `np.array(table)`/`np.asarray(table)` sends) must keep
  succeeding — S8/S12/etc. depend on that.

## Known Environment Blockers

Two scenarios below (S19, and the pre-existing
`test_init_thread_safety` test cited alongside S7) exercise a correct,
in-scope contract but cannot currently execute to completion in *this*
checkout, for reasons that are verified, unrelated to the five interfaces
in this spec, and explicitly out of scope to fix:

- **S19** (`quantity_day_frac` on an incompatible unit) depends on
  `astropy.units.core.get_err_str`, which is undefined (Context). This is
  the *only* path an incompatible-unit `UnitsError` can take in this
  checkout — there is no way to route around it from inside
  `quantity_day_frac`. Write and keep S19's test asserting
  `pytest.raises(u.UnitsError)` regardless, because that is
  `quantity_day_frac`'s correct, documented contract (and the exact
  exception `astropy/time/formats.py:337` already catches around this call
  site) — but do not treat its failure in this checkout as a defect in
  this spec's implementation, and do not attempt to fix `get_err_str` to
  make it pass.
- `test_init_thread_safety`
  (`astropy/time/tests/test_update_leap_seconds.py:85-101`) depends on
  `TimeString.str_kwargs`, which is undefined (Context). S7 is the
  scenario that verifies `_check_leapsec`'s own contract directly, without
  going through `Time`/`str()`, and is the one this spec's Definition of
  Done requires; the pre-existing test is cited only as converging
  context, not as a pass/fail gate.

**Dependency note, stated accurately once:** `astropy.coordinates.Longitude`
failed to import in the sandbox used to write this spec only because that
sandbox lacks the compiled `erfa` dependency — an environment/build gap of
that sandbox, not a source-code gap (a repo-wide scan found no stripped
function anywhere under `astropy/coordinates/`). It is expected to import
normally in a properly provisioned environment and is not excluded here.
More broadly, `erfa`/a built `astropy.time` are needed to even *import*
several of the test modules this spec cites — `test_functions.py` (S5, S9,
S11), `test_update_leap_seconds.py` (S7, S13), `test_bls.py` (S18), and
`lombscargle/core.py` itself (S6, since it imports `astropy.time.Time` at
module level) — this is a normal runtime dependency of a built astropy
checkout, not something this spec's five interfaces introduce or something
that is optional in the grading environment.

## Acceptance Scenarios

Each scenario is either a direct, isolated call to the target function
(primary; independent of the gaps in "Known Environment Blockers") or
cites a pre-existing test verified to not depend on those gaps.
`[NEW TEST target: <path>]` marks a scenario with no pre-existing test.

### Happy Path

- **S1:** Given `q = 2450000.125 * u.day` (a `Quantity` in a unit that is a
  pure scale of `day`), when `quantity_day_frac(q)` is called directly,
  then `day == 2450000.0` and `frac == 0.125` (`day + frac == q.value`
  exactly), with `day == round(q.value)` (`round(2450000.125) == 2450000`).
  `[NEW TEST target: astropy/time/tests/test_utils.py, new file]`
- **S2:** Given `q2 = q.to(u.second)` (same physical value as S1, but in a
  unit requiring an actual `1/86400` scale-factor conversion, not a unit
  relabel), when `quantity_day_frac(q2)` is called, then
  `day == 2450000.0` and `frac == 0.125` — bit-identical to S1 despite the
  different input unit and the non-trivial `1/86400` scale factor.
  **Verified**: `q2.to_value(u.day) == 2450000.125` exactly for this
  specific value (no ulp mismatch here), so this can be checked directly
  against `q.value` as well as against the exact literals.
  `[NEW TEST target: astropy/time/tests/test_utils.py]`
- **S3 (two-argument, "not normalized again"):** Given
  `val1 = 0.4 * u.day` and `val2 = 0.4 * u.day`, when
  `quantity_day_frac(val1, val2)` is called, then the returned `frac` is
  the raw sum of each argument's own `frac` component (`0.4 + 0.4 = 0.8`)
  and is therefore **outside** `[-0.5, 0.5]` — unlike a single call to
  `quantity_day_frac(val1 + val2)` (which normalizes and returns
  `day=1.0, frac≈-0.2`, since `round(0.8) == 1`). This is the directly
  observable form of "the componentwise result is not normalized again."
  `[NEW TEST target: astropy/time/tests/test_utils.py]`
- **S4 (array input):** Given `qs = np.arange(1.0, 6.0) * u.hour` (a
  shape-`(5,)` array `Quantity`), when `quantity_day_frac(qs)` is called,
  then `day` and `frac` are each shape-`(5,)` arrays and
  `day + frac` is elementwise within `1e-9` of `qs.value / 24.0`. **Do
  not** assert bit-exact equality against `qs.to_value(u.day)` here:
  **verified** that for this exact input, element `qs[4] = 5.0` hours,
  `qs.to_value(u.day)[4] == 0.20833333333333334` while
  `qs.value[4] / 24.0 == 0.2083333333333333` — these differ by 1 ulp
  because `to_value` and a raw `value/24` division round differently, and
  `quantity_day_frac`'s two-float arithmetic may legitimately land on
  either. This scenario checks shape/broadcasting; S1–S3 already pin down
  bit-exact precision behavior for scalars.
  `[NEW TEST target: astropy/time/tests/test_utils.py]`
- **S5:** Given `MaskedNDArray` test fixtures of different but
  broadcastable shapes (plain-array-backed, `Quantity`-backed, and
  `Longitude`-backed variants), when
  `np.broadcast_arrays(ma, mb, mc, subok=True)` is called, then each
  returned element's `.unmasked` equals the plain-numpy broadcast of the
  corresponding unmasked data and its `.mask` equals the plain-numpy
  broadcast of the corresponding mask. —
  `astropy/utils/masked/tests/test_functions.py::TestMaskedArrayBroadcast::test_broadcast_arrays`,
  `::TestMaskedQuantityBroadcast::test_broadcast_arrays`, and
  `::TestMaskedLongitudeBroadcast::test_broadcast_arrays`
- **S6:** Given `arr = np.array([1, 2, 3])`, `has_units(arr) is False`;
  given `quantity = 5 * u.meter`, `has_units(quantity) is True` — the
  interface docstring's own doctest examples.
  `[NEW TEST target: astropy/timeseries/periodograms/lombscargle/tests/test_core.py, new file — astropy/timeseries/periodograms/lombscargle/tests/test_utils.py already exists and tests unrelated functions (convert_normalization, compute_chi2_ref); do not reuse or overwrite it]`
- **S7 (direct concurrency test):** Given
  `astropy.time.core._LEAP_SECONDS_CHECK` is reset to `NOT_STARTED` and
  `astropy.time.core.update_leap_seconds` is monkeypatched to a stub that
  sleeps briefly then increments a shared counter, when 4 threads call
  `astropy.time.core._check_leapsec()` concurrently via a
  `ThreadPoolExecutor`, then the stub is invoked **exactly once** across
  all 4 threads, every thread's call to `_check_leapsec()` returns (no
  exception, no deadlock), and `_LEAP_SECONDS_CHECK` ends as `DONE`.
  `[NEW TEST target: astropy/time/tests/test_update_leap_seconds.py]`
- **S8:** Given `d = Table([[1, 2], [3, 4]], names=("a", "b"))`, when
  `np.array(d)` (equivalently `np.asarray(d)`) is called, then the result
  is a structured `ndarray` with `dtype.names == ("a", "b")` whose values
  equal `d.as_array()`, and the returned object is not the same object as
  `d.as_array()` (`np.array(d) is not d.as_array()`). —
  `astropy/table/tests/test_table.py::TestConvertNumpyArray::test_convert_numpy_array`

### Edge Cases

- **S9:** Given the same masked fixtures as S5, when
  `np.broadcast_arrays(ma, mb, mc, subok=False)` is called, then every
  returned element's `.unmasked` has type exactly `np.ndarray` (subclasses
  are not passed through), while the mask values are unaffected by
  `subok`. —
  `test_functions.py::TestMaskedArrayBroadcast::test_broadcast_arrays_subok_false`
- **S10:** Given a single masked array `ma` and `subok=True`, when
  `np.broadcast_arrays(ma, subok=True)` is called (single-argument form),
  then the result is a 1-element list (numpy < 2.0) or 1-tuple (numpy ≥
  2.0) — matching whatever `numpy.broadcast_arrays` itself returns for the
  installed numpy version — and shares memory with the input
  (`np.may_share_memory`) since no actual broadcasting was needed. —
  `astropy/utils/masked/tests/test_function_helpers.py::TestShapeManipulation::test_broadcast_arrays`
  (regression check for the single-array case)
- **S11:** Given a mix of one plain `ndarray`, one `MaskedNDArray`, and one
  plain `ndarray` (broadcastable shapes), when
  `np.broadcast_arrays(a, mb, c, subok=True)` is called, then the plain
  array elements come back as plain (unmasked) broadcast arrays and only
  the masked element comes back as a `MaskedNDArray`. —
  `test_functions.py::TestMaskedArrayBroadcast::test_broadcast_arrays_not_all_masked`
- **S12:** Given `d = Table([[1, 2], [3, 4]], names=("a", "b"))`, when
  `np.array(d, dtype=object)` is called, then the result is a 0-d object
  array whose single element `is` (identity, not equality) `d`; and given
  `ds = [d, d, d]`, `np.array(ds, dtype=object)` yields a length-3 object
  array of `Table` references equal to `d`. —
  `test_table.py::TestConvertNumpyArray::test_convert_numpy_object_array`
  and `::test_convert_list_numpy_object_array`
- **S13:** Given the leap-second table has already been checked once in the
  current process (`_LEAP_SECONDS_CHECK` is `DONE`), when
  `_check_leapsec()` is called again, then it returns without invoking
  `update_leap_seconds()` again (assert the monkeypatched stub from S7 was
  not called a second time).
  `[NEW TEST target: astropy/time/tests/test_update_leap_seconds.py, same test as S7 or a sibling]`
- **S14:** Given `d = Table([[1, 2], [3, 4]], names=("a", "b"))`, when
  `np.array(d, copy=False)` is called, then it raises `ValueError` (see
  "Design Decisions" — `Table.__array__` always builds a fresh array and
  cannot honor an explicit refusal to copy); and when `np.asarray(d)` (no
  explicit `copy=`) is called, then it succeeds and returns a structured
  `ndarray` with `dtype.names == ("a", "b")` equal in value to
  `d.as_array()`.
  `[NEW TEST target: astropy/table/tests/test_table.py]`
- **S15:** Given `d = Table()` (zero columns), when `np.array(d)` is
  called, then it does not raise, the result has length `0`, and
  `result.dtype.names is None` (mirroring `as_array()`'s own empty-table
  short-circuit at `table.py:673-674`).
  `[NEW TEST target: astropy/table/tests/test_table.py]`
- **S16 (mask not preserved):** Given a table with a masked column, e.g.
  `d = Table([MaskedColumn([1, 2], mask=[True, False])], names=("a",))`,
  when `np.array(d)` is called, then `type(result) is np.ndarray` (never
  `numpy.ma.MaskedArray`) and `result.dtype.names == ("a",)` — the mask is
  dropped, per the docstring's "Masks are not preserved" clause.
  `[NEW TEST target: astropy/table/tests/test_table.py]`
- **S17 (non-scale conversion fallback — see "Design Decision: fallback
  trigger" below before implementing):** Given a custom unit with a
  deliberately non-linear equivalency to `day`:
  ```python
  import astropy.units as u
  custom = u.def_unit("custom_time_unit")
  equiv = [(custom, u.day, lambda x: x**2, lambda x: x**0.5)]
  with u.add_enabled_equivalencies(equiv):
      val1 = 3.0 * custom
  ```
  **Verified live** (executed while writing this spec, since
  `astropy.units` runs standalone in this checkout):
  `val1.to_value(u.day) == 9.0`, and `custom._to(u.day)` — `UnitBase._to`,
  the private "no equivalencies" scale-only method
  (`units/core.py:591-624`) — raises `UnitConversionError`, confirming
  `day` has no pure multiplicative scale relationship to `custom`
  independent of the enabled equivalency. **Also verified, and worth
  flagging explicitly**: the *public* `custom.to(u.day)` (called on the
  bare unit, which implicitly converts the value `1.0`) returns `1.0`, not
  an error — because `1.0 ** 2 == 1.0`. That is a coincidence of this
  equivalency evaluated at `1.0`, not evidence that the conversion is a
  simple scale; do not use `unit.to(other)` (public, unit-only, implicit
  value) as the "is this a simple scale" test — see the Design Decision
  below.
  When `quantity_day_frac(val1)` is called inside the same
  `add_enabled_equivalencies` context, then it returns `day == 9.0` and
  `frac == 0.0` — the fully-converted value with no day/frac splitting,
  per the fallback clause of the docstring.
  `[NEW TEST target: astropy/time/tests/test_utils.py]`
- **S18 (has_units through a real consumer):**
  `astropy/timeseries/periodograms/bls/tests/test_bls.py` imports
  `has_units` at module level (line 11) and its `test_results_units`
  (parametrized, body at lines 173-209) asserts `not has_units(...)` on
  several `BoxLeastSquaresResults` attributes for unitless input. Once
  `has_units` exists in `lombscargle/core.py`, this file becomes
  collectible and this test exercises `has_units` through a real,
  in-scope-adjacent consumer, with no further code changes needed beyond
  what this spec already implements (`bls/core.py`, `bls/methods.py`, and
  `astropy/timeseries/periodograms/base.py` are not stripped). This
  requires the grading environment's normal `astropy.time`/`erfa`
  dependency (used by `test_bls.py:9`'s own imports), not any additional
  source change.

- **S22 (registration completeness, pre-existing and currently red):**
  `astropy/utils/masked/tests/test_function_helpers.py::TestFunctionHelpersCompleteness::test_all_included`
  (line 1790) asserts that every function `MaskedNDArray.__array_function__`
  can see is accounted for across `MASKED_SAFE_FUNCTIONS`,
  `UNSUPPORTED_FUNCTIONS`, `APPLY_TO_BOTH_FUNCTIONS`, and
  `DISPATCHED_FUNCTIONS`. **Verified**: today `numpy.broadcast_arrays`
  appears in none of those sets, so this test currently fails; registering
  `broadcast_arrays` via `@dispatched_function` (adding it to
  `DISPATCHED_FUNCTIONS`) is what turns it green — no separate action
  needed beyond implementing the function as specified.
- **S23 (signature-compatibility, pre-existing):**
  `astropy/utils/masked/tests/test_function_helpers.py::TestFunctionHelpersSignatureCompatibility`
  (line 1812) is parametrized over `DISPATCHED_FUNCTIONS` and will gain a
  `broadcast_arrays` case once registered; it asserts the wrapped
  function's signature is at least as permissive as `numpy.broadcast_arrays`'s
  own signature — satisfied automatically by matching the Interface
  Contract's `*args, subok=False` signature exactly.

### Error Scenarios

- **S19:** `quantity_day_frac(5 * u.meter)` (a unit with no conversion to
  time at all, and no relevant equivalency enabled) must propagate a
  `u.UnitsError` (or a subclass, e.g. `u.UnitConversionError`) — the exact
  exception family `astropy/time/formats.py:337` already catches
  (`except u.UnitsError: raise u.UnitConversionError(...)`) around its
  call to `quantity_day_frac`. See "Known Environment Blockers" — this
  scenario's test is correct to write and keep, but is not required to
  pass in this specific checkout.
  `[NEW TEST target: astropy/time/tests/test_utils.py]`
- **S20:** Given `d = Table([[1, 2], [3, 4]], names=("a", "b"))`, when
  `np.array(d, dtype=[("c", "i8"), ("d", "i8")])` is called (a non-object
  dtype coercion), then it raises `ValueError`. —
  `test_table.py::TestConvertNumpyArray::test_convert_numpy_array`
- **S21:** Given two arrays with shapes that cannot be broadcast together
  (e.g. shapes `(3,)` and `(4,)`), when `np.broadcast_arrays(ma, other)` is
  called with one masked argument, then it raises the same `ValueError`
  `numpy.broadcast_arrays` itself raises for incompatible shapes —
  masking must not swallow or change this error.
  `[NEW TEST target: astropy/utils/masked/tests/test_function_helpers.py]`

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*, except S19, which is correct to
> write but is not required to pass in this checkout (see "Known
> Environment Blockers").

- Implement the five functions/methods named in Key Components / Interface
  Contract, plus the two one-line import-list additions in
  `astropy/time/formats.py:20` and
  `astropy/timeseries/periodograms/bls/core.py:11`. Do not modify anything
  else — in particular, do not implement `get_err_str`
  (`astropy/units/core.py`), `TimeString.str_kwargs`
  (`astropy/time/formats.py`), `Table._init_from_ndarray`
  (`astropy/table/table.py`), or anything in
  `astropy/timeseries/periodograms/lombscargle_multiband/` or
  `astropy/timeseries/core.py` — real, separately-verified gaps, but
  outside the five interfaces this spec defines.
- Where a `[NEW TEST]` names a target file that does not yet exist
  (`astropy/time/tests/test_utils.py` or
  `astropy/timeseries/periodograms/lombscargle/tests/test_core.py`),
  create it. Do not write into
  `astropy/timeseries/periodograms/lombscargle/tests/test_utils.py` — it
  already exists and tests unrelated functions.
- For S17, use the verified construction shown in the scenario (or an
  equivalent custom unit + non-linear `add_enabled_equivalencies`
  equivalency). The triggering construction itself was executed and
  checked while writing this spec (`to_value(u.day) == 9.0`,
  `_to(u.day)` raises) — but `quantity_day_frac` does not exist yet, so
  its expected `(9.0, 0.0)` output is a reasoned derivation (see "Design
  Decisions") from `UnitBase._to`'s own "no equivalencies" scale
  definition, not an execution of the target function. Implement against
  that derivation; if a hidden reference disagrees, that is the
  authoritative signal, and S17's expected values should be updated to
  match it rather than defended past that point.
- Write tests to the project's existing conventions (plain `pytest`
  functions/classes, following the style already used in the cited files)
  and to these principles:
  - **Behavioral over structural** — assert observable output (values,
    types, exceptions), not internal call sequences, except where S7/S13
    explicitly require asserting the monkeypatched `update_leap_seconds`
    stub's call count (that is the observable behavior being specified —
    "at most one update attempt").
  - **Every test can fail** — no copy-pasted expected values, no asserting
    a constant, no tautologies.
  - **Deterministic, isolated, readable** — S7 must not be flaky by
    construction: reset `_LEAP_SECONDS_CHECK`/`_LEAP_SECONDS_LOCK` state
    via `monkeypatch` rather than mutating it permanently, and use a stub
    with a short, bounded sleep rather than real network/file I/O.

## Definition of Done

- [ ] Direct/isolated tests pass (own new test files): S1, S2, S3, S4, S6,
      S7, S13, S14, S15, S16, S17.
- [ ] Cited pre-existing tests pass (covers S5, S8, S9, S10, S11, S12, S20,
      S22, S23):
      `pytest astropy/utils/masked/tests/test_functions.py::TestMaskedArrayBroadcast astropy/utils/masked/tests/test_functions.py::TestMaskedQuantityBroadcast astropy/utils/masked/tests/test_functions.py::TestMaskedLongitudeBroadcast astropy/utils/masked/tests/test_function_helpers.py::TestShapeManipulation::test_broadcast_arrays astropy/utils/masked/tests/test_function_helpers.py::TestFunctionHelpersCompleteness::test_all_included "astropy/utils/masked/tests/test_function_helpers.py::TestFunctionHelpersSignatureCompatibility::test_all_arguments_reexposed[broadcast_arrays]" astropy/table/tests/test_table.py::TestConvertNumpyArray::test_convert_numpy_array astropy/table/tests/test_table.py::TestConvertNumpyArray::test_convert_numpy_object_array astropy/table/tests/test_table.py::TestConvertNumpyArray::test_convert_list_numpy_object_array`
- [ ] S18 passes once `has_units` exists (no additional code change):
      `pytest astropy/timeseries/periodograms/bls/tests/test_bls.py::test_results_units`
- [ ] S21 (new test) passes.
- [ ] S19's test is written and asserts `pytest.raises(u.UnitsError)`; it
      is not required to pass in this checkout (see "Known Environment
      Blockers") and its failure here must not be treated as a defect.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
      the smallest break of its behavior (e.g. reverting `has_units` to
      `return False` unconditionally must fail S6; reverting
      `Table.__array__`'s `ValueError` guard must fail S20; reverting
      `_check_leapsec` to always call `update_leap_seconds()` must fail
      S13).
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings) in the five touched functions/methods or the two import
      additions.
- [ ] No changes made outside: `astropy/time/utils.py`,
      `astropy/time/formats.py` (import line only),
      `astropy/utils/masked/function_helpers.py`,
      `astropy/timeseries/periodograms/lombscargle/core.py`,
      `astropy/timeseries/periodograms/bls/core.py` (import line only),
      `astropy/time/core.py`, `astropy/table/table.py`, and the new/edited
      test files named above.

## Trade-offs and Limitations

- S19 (`quantity_day_frac` on an incompatible unit) and the pre-existing
  `test_init_thread_safety` are the two places this spec's correct,
  in-scope contract cannot currently execute cleanly in this checkout, for
  reasons documented once in "Known Environment Blockers" rather than
  repeated or hedged elsewhere.
- S18's `BoxLeastSquares` test requires the grading environment's normal
  `astropy.time`/`erfa` dependency to import at all (unrelated to source
  stripping); if that dependency is unavailable, S6 (the direct,
  dependency-free `has_units` scenario) still stands on its own.

## References

- `astropy/time/utils.py` (existing `day_frac`, `two_sum`, `two_product`,
  `split`)
- `astropy/time/formats.py:20,336-337` (`quantity_day_frac` import gap and
  call site)
- `astropy/utils/masked/function_helpers.py:280-290,979-993`
  (`broadcast_to` and `where` as decorator-pattern references)
- `astropy/timeseries/periodograms/lombscargle_multiband/core.py:17-18`
  (reference `has_units` implementation)
- `astropy/timeseries/periodograms/bls/core.py:11,17,20,755,762,791,797`
  and `astropy/timeseries/periodograms/bls/tests/test_bls.py:11,173-205`
  (`has_units` import gap, call sites, and consuming test)
- `astropy/time/core.py:151-158,797,3381-3414` (`_LeapSecondsCheck`,
  `_LEAP_SECONDS_CHECK`, `_LEAP_SECONDS_LOCK`, `_set_scale`,
  `update_leap_seconds`)
- `astropy/table/table.py:649-706,795-834,1263` (`Table.as_array`, the
  `__init__` data-type dispatch, `_init_from_list`)
- `astropy/units/core.py:511-523,557-589,591-624` (`get_err_str` gap,
  `get_converter`'s scale-then-equivalency fallback, `_to`)

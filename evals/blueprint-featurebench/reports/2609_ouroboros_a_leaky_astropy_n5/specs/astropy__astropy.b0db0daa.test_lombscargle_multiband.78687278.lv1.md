# 2609.0001 Utility Interface Restoration

**Date:** 2026-09-10
**Status:** draft
**Author:** EP Lin

## Context

Five function/method definitions are **completely absent** from the astropy
source tree — not merely empty-bodied, but missing entirely (signature,
decorator, and docstring all gone, leaving a blank gap of blank lines in
their place):

1. `quantity_day_frac(val1, val2=None)` — gap at
   `astropy/time/utils.py:77-121`, between `day_frac` (ends `:76`) and
   `two_sum` (starts `:122`).
2. `broadcast_arrays(*args, subok=False)` — gap at
   `astropy/utils/masked/function_helpers.py:706-736`, between `block`
   (ends `:704`) and `insert` (starts `:737`).
3. `has_units(obj)` — gap at
   `astropy/timeseries/periodograms/lombscargle/core.py:14-18`, between the
   imports and `get_unit` (starts `:19`).
4. `_check_leapsec()` — gap at `astropy/time/core.py:3363-3380`, between
   `OperandTypeError` (ends `:3362`) and `update_leap_seconds` (starts
   `:3381`).
5. `Table.__array__(self, dtype=None, copy=COPY_IF_NEEDED)` — gap at
   `astropy/table/table.py:1172-1197`, between `index_mode` (ends `:1171`)
   and `_check_names_dtype` (starts `:1198`).

Each is a leaf-level helper consumed by other, unrelated parts of the
codebase (`Time`, `MaskedNDArray`, `LombScargle`, and `Table`). The
Interface Contract section below is the authoritative source for what each
definition must contain — it does **not** reproduce docstrings already
present in the file (there is nothing there to reproduce); it specifies the
full definition the agent must write from scratch.

**Scope decision.** A codebase scan (see References) found that other,
unrelated regions were stripped the same way — this list is confirmed but
**not exhaustive** (the scan was not repository-wide): e.g.
`astropy/units/core.py:510-519` (the `get_err_str` helper that
`_apply_equivalencies`'s error path calls — undefined anywhere in the tree),
`astropy/timeseries/core.py:55-97`, `astropy/time/formats.py:1682-1724`
(`TimeString.str_kwargs`, called from `formats.py:1740` and
`core.py:2142` — undefined anywhere in the tree, so any `Time.iso`/`str(Time)`
call currently raises `AttributeError`), `astropy/utils/shapes.py:250-254`,
`astropy/timeseries/periodograms/lombscargle_multiband/core.py:20-30`, and
`Table._init_from_ndarray` at `astropy/table/table.py:1440-1454` (itself
still called from `Table.__init__` at `table.py:822` and `:826`, so
constructing a `Table` from a structured `ndarray` currently raises
`AttributeError`). This spec deliberately covers **only** the five
interfaces listed above, per the task's explicit instruction that
implementing "Astropy's general unit system, time/date system, table type,
coordinate transformations, or Lomb–Scargle algorithm" is out of scope; see
Definition of Done for how pre-existing, unrelated failures caused by these
other gaps are handled, and Alternatives Considered for why scope was not
widened.

`BoxLeastSquares` (`astropy/timeseries/periodograms/bls/core.py`) is a
**separate, out-of-scope consumer** of a function named `has_units`: its
own module import at `bls/core.py:11` currently reads only
`from astropy.timeseries.periodograms.lombscargle.core import strip_units`
— the `has_units` import was also stripped from that line, so
`bls/core.py` will keep raising `NameError` at `has_units` call sites
(`:17`, `:20`, `:755`, `:762`, `:791`, `:797`) regardless of this spec.
Fixing that import is a one-line change to `bls/core.py`, which is not one
of the five files this spec authorizes changes to — it is out of scope, and
`astropy/timeseries/periodograms/bls/tests/test_bls.py` is expected to stay
red until it (or the wider periodogram scope it belongs to) is addressed
elsewhere.

## Motivation

Until these five definitions are restored, any code path that calls into
them fails outright (`NameError`/`AttributeError`, since the names don't
exist) or, once restored incorrectly, silently returns wrong values:

- `Time` construction from a `Quantity` with time units (e.g.
  `Time(5 * u.day)`, or any format that stores `jd1`/`jd2` from a quantity)
  goes through `astropy/time/formats.py:336`
  (`val1, val2 = quantity_day_frac(val1, val2)`).
- `astropy.utils.masked.MaskedNDArray` loses `numpy.broadcast_arrays`
  support, breaking masked-array code that broadcasts multiple arrays
  together — see `astropy/utils/masked/tests/test_function_helpers.py:159`
  (`test_broadcast_arrays`) and
  `astropy/utils/masked/tests/test_functions.py:401-453`
  (`TestMaskedArrayBroadcast` and its `TestMaskedQuantityBroadcast` /
  `TestMaskedLongitudeBroadcast` subclasses).
- `LombScargle` (`astropy/timeseries/periodograms/lombscargle/core.py`)
  uses `has_units` internally (e.g. at `:152,165,172,179,188`) to decide
  whether inputs/outputs should carry `Quantity` units; without it,
  `LombScargle` construction raises `NameError` before any algorithmic code
  runs. (`has_units` is also used by `bls/core.py`, but restoring it here
  does not fix `bls/core.py` — see the Scope decision above.)
- `Time` scale conversions that touch UTC call `_check_leapsec()` (called
  from `Time._set_scale`, `astropy/time/core.py:797`) to make sure the ERFA
  leap-second table is current; without it, every UTC-touching `Time`
  operation raises `NameError`.
- `np.array(table)` / `np.asarray(table)` and any numpy function that
  invokes the array protocol on a `Table` fail without a working
  `__array__` — see `astropy/table/tests/test_table.py:1535`
  (`test_convert_numpy_array`) and `:1593`
  (`test_convert_numpy_object_array`).

Restoring exactly these five definitions unblocks all of the above.

## Proposed Solution

### Overview

Write the full definition (signature, decorator where applicable, and a
docstring matching the Interface Contract below) for each of the five
functions/methods, in place, at the line ranges given in Context. No new
files, no new public names, no signature changes, no changes to any other
region of any of these five files, and no changes to any other file
(including `bls/core.py`).

### Key Components

The following are implementation notes to orient the agent — they describe
a known-correct approach, not additional testable requirements. (No
acceptance scenario below asserts these mechanics directly; scenarios only
assert observable behavior.)

- **`quantity_day_frac`** — convert a time `Quantity` (or a pair of them) to
  a high-precision day/fractional-day pair by reusing the existing
  `day_frac(val1, val2, factor=None, divisor=None)` helper defined earlier
  in the same file (`astropy/time/utils.py:19`) for the actual two-float
  summation, rather than reimplementing double-double arithmetic. The
  `try: val1.unit.to(u.day) / except Exception: fallback` structure must
  catch any `Exception` (not a narrower type) around the `.unit.to(u.day)`
  call, since that call's failure mode is not itself part of this
  function's contract.
- **`broadcast_arrays`** — a `@dispatched_function` (decorator already
  defined in this module) that unwraps `Masked` inputs (via
  `astropy.utils.masked.core.Masked`, imported locally to avoid a circular
  import — follow the local-import pattern used by `block()` immediately
  above the gap), calls `np.broadcast_arrays` on the unmasked data, calls
  `np.broadcast_to` on each mask, and re-wraps masked results in
  `Masked(...)`. Must follow the `dispatched_function` contract used
  throughout this module (confirmed at `astropy/utils/masked/core.py:1043`,
  `result, mask, out = dispatched_result`): return a 3-tuple
  `(results, None, None)`, where `results` is itself a `list` (numpy < 2.0)
  or `tuple` (numpy >= 2.0) of per-argument broadcast results — see
  `block()`'s `return result, None, None` for the pattern.
- **`has_units`** — `hasattr(obj, "unit")`. An equivalent, already-working
  `has_units` exists at
  `astropy/timeseries/periodograms/lombscargle_multiband/core.py:17` as a
  reference for the exact expected behavior.
- **`_check_leapsec`** — gate a single call to the existing
  `update_leap_seconds(files=None)` function (defined immediately after the
  gap, in the same file) behind the module-level state machine already
  declared earlier in the file (`astropy/time/core.py:151-158`): the
  `_LeapSecondsCheck` enum (`NOT_STARTED` / `RUNNING` / `DONE`), the
  `_LEAP_SECONDS_CHECK` global, and `_LEAP_SECONDS_LOCK`
  (`threading.RLock()`). Required state-transition contract: if
  `_LEAP_SECONDS_CHECK` is not `DONE`, acquire `_LEAP_SECONDS_LOCK`; after
  acquiring, re-check — if still `NOT_STARTED`, set it to `RUNNING`, call
  `update_leap_seconds()`, then set it to `DONE`; if it is anything other
  than `NOT_STARTED` at that point (i.e. `RUNNING` from a re-entrant caller,
  or `DONE` from a racing thread that finished first), return without
  calling `update_leap_seconds()` again. What happens if
  `update_leap_seconds()` itself raises is not part of this contract (see
  Trade-offs and Limitations).
- **`Table.__array__`** — with `dtype is None` (or unspecified), return
  `self.as_array()` (`Table.as_array()` already exists and is unmodified),
  unwrapping a `numpy.ma.MaskedArray` result to its plain `.data` if masked
  (`copy` is not consulted on this path — matches `as_array()`'s existing,
  unmodified behavior). With `np.dtype(dtype) == object` (numpy always
  passes a `numpy.dtype` instance here, not the builtin `object`, so the
  comparison must go through `np.dtype(...)`), return a 0-d object array
  (`out = np.array(None, dtype=object); out[()] = self; return out`) whose
  sole element is `self` (the `Table` itself, not its column data) —
  `copy` is accepted in the signature (numpy's array-protocol dispatch
  requires it), but not consulted on this path either: passing
  `copy=copy` straight into `np.array(None, dtype=object, copy=copy)`
  would raise under numpy's "unable to avoid copy" semantics when
  `copy=False`, which is not the intended behavior. With any other
  explicit, non-`None` dtype (i.e. `dtype is not None and
  np.dtype(dtype) != object`), raise `ValueError`.

### Data Flow

These five functions are independent of one another; each is only reachable
through its own call sites listed in Motivation. There is no shared data
flow between them — treat each as an isolated unit of work.

### Interface Contract

```python
# astropy/time/utils.py, at the gap between day_frac (:76) and two_sum (:122)
def quantity_day_frac(val1, val2=None):
    """Like ``day_frac``, but for quantities with units of time.

    Converts time quantities to days with high precision arithmetic,
    returning two floating scalars or arrays whose sum represents the value
    in days.

    If ``val2`` is given, returns the componentwise sum of
    ``quantity_day_frac(val1)`` and ``quantity_day_frac(val2)`` — i.e.
    ``(d1 + d2, f1 + f2)`` — without renormalizing.

    For a single argument: if ``val1.unit.to(u.day)`` succeeds (the unit is
    convertible to days by a simple scale factor), convert via the
    high-precision ``day_frac`` helper. If that factor is less than 1
    (e.g. seconds), divide by the reciprocal conversion factor rather than
    multiply by the factor itself, since a factor like 1/86400 is not
    exactly representable as a float; if the factor is greater than 1 (e.g.
    years), multiply directly; if the factor is exactly 1.0 (the unit is
    already days), call ``day_frac(val1.value, 0.0)`` with neither
    ``factor`` nor ``divisor``. In all three cases the result is a
    normalized ``(day, frac)`` pair with ``frac`` in ``[-0.5, 0.5]``.

    If ``val1.unit.to(u.day)`` raises any `Exception` (the failure mode is
    not part of this function's contract — it depends on unit-conversion
    internals outside this function), fall back to
    ``(val1.to_value(u.day), 0.0)``. If that also raises, propagate the
    exception.

    Parameters
    ----------
    val1 : astropy.units.Quantity
        A quantity with time units to be converted to days.
    val2 : astropy.units.Quantity, optional
        A second quantity with time units.

    Returns
    -------
    day, frac : float64 or ndarray
    """


# astropy/utils/masked/function_helpers.py, at the gap between block() (:704) and insert() (:737)
@dispatched_function
def broadcast_arrays(*args, subok=False):
    """Broadcast arrays to a common shape.

    Like `numpy.broadcast_arrays`, applied to both unmasked data and masks.
    ``subok`` controls whether subclasses of the unmasked data are passed
    through (``True``) or replaced with base `~numpy.ndarray` (``False``);
    masking itself is always preserved regardless of ``subok``.

    Returns the dispatched_function 3-tuple ``(results, None, None)``, where
    ``results`` is a `list` (numpy < 2.0) or `tuple` (numpy >= 2.0) with one
    entry per positional argument: a plain broadcast array for plain-array
    inputs, a `~astropy.utils.masked.MaskedNDArray` (data and mask both
    broadcast to the common shape) for `Masked` inputs.
    """


# astropy/timeseries/periodograms/lombscargle/core.py, at the gap before get_unit() (:19)
def has_units(obj):
    """Return True if obj has a 'unit' attribute, else False."""


# astropy/time/core.py, at the gap between OperandTypeError (:3362) and update_leap_seconds() (:3381)
def _check_leapsec():
    """Ensure the ERFA leap-second table is current.

    Performs at most one `update_leap_seconds()` call per process. Safe
    under concurrent calls (only one thread performs the update; others
    wait on `_LEAP_SECONDS_LOCK` and then see it already done) and under
    re-entrant calls (a call arriving while `_LEAP_SECONDS_CHECK` is
    already `RUNNING` on the current thread, e.g. triggered from inside
    `update_leap_seconds()` itself, returns without recursing).

    Uses module globals `_LEAP_SECONDS_CHECK` (a `_LeapSecondsCheck` value
    that transitions `NOT_STARTED` -> `RUNNING` -> `DONE`) and
    `_LEAP_SECONDS_LOCK`.
    """


# astropy/table/table.py, at the gap between index_mode() (:1171) and _check_names_dtype() (:1198)
    def __array__(self, dtype=None, copy=COPY_IF_NEEDED):
        """Support converting Table to np.array via np.array(table).

        dtype is None (default): return self.as_array(), unwrapped from
        MaskedArray to plain ndarray via `.data` if masked. `copy` is not
        consulted on this path.

        np.dtype(dtype) == object: return a 0-d object array
        (`out = np.array(None, dtype=object); out[()] = self; return out`)
        whose sole element is `self` (the Table object itself, not its
        column data). `copy` is accepted in the signature for numpy
        array-protocol compatibility but not consulted on this path.

        any other explicit dtype: raise ValueError.
        """
```

No public signatures change. No new modules, exports, or `__all__` entries
are introduced.

## Acceptance Scenarios

### Happy Path

- **S1:** Given `val1 = 86399 * u.s` (chosen because `1/86400` is not
  exactly representable as a `float64`), when `quantity_day_frac(val1)` is
  called, then, with `decimal.localcontext(decimal.Context(prec=40))` (the
  technique used at `astropy/time/tests/test_precision.py:322`,
  `test_two_sum`) used to compute the reference
  `ref = Decimal(86399) / Decimal(86400)`, `dd_err`
  (`= abs(Decimal(day) + Decimal(frac) - ref)`) and `naive_err`
  (`= abs(Decimal((86399 * u.s).to_value(u.day)) - ref)`): `dd_err < Decimal("1e-20")`
  and `naive_err > Decimal("1e-17")` (the naive single-`float64` conversion
  is measurably less accurate than the required result). `frac` lies in
  `[-0.5, 0.5]`. This must fail for a naive implementation that returns
  `val1.to_value(u.day), 0.0`.
- **S2:** Given a scalar `Quantity` with a unit whose day-conversion factor
  is greater than 1 (e.g. `2 * u.yr`), when `quantity_day_frac(val1)` is
  called, then `day` and `frac` sum to the value in days and `frac` lies in
  `[-0.5, 0.5]`.
- **S3a (componentwise, not pre-summed):** Given two `Quantity` arguments
  `val1 = 1 * u.day`, `val2 = 500000000 * u.ns` (chosen so the nanosecond
  value loses precision if naively summed in `float64` before conversion),
  when `quantity_day_frac(val1, val2)` is called, then the result equals
  the componentwise sum `(d1 + d2, f1 + f2)` of `quantity_day_frac(val1)`
  and `quantity_day_frac(val2)` computed independently.
- **S3b (sum is not renormalized):** Given `val1 = 0.6 * u.day`,
  `val2 = 0.6 * u.day` (each individually normalizes to
  `quantity_day_frac(val_i) == (1.0, -0.4)`), when
  `quantity_day_frac(val1, val2)` is called, then the result is the raw
  componentwise sum `(2.0, -0.8)` — not the renormalized equivalent
  `(1.0, 0.2)` that `day_frac`-style normalization would produce for the
  same total. This must fail for an implementation that renormalizes the
  two-argument result.
- **S3c (array input):** Given `val1 = [86399, 1] * u.s`, when
  `quantity_day_frac(val1)` is called, then `day` and `frac` are arrays of
  shape `(2,)` and each element matches the corresponding scalar-input
  result from `quantity_day_frac(86399 * u.s)` / `quantity_day_frac(1 * u.s)`.
- **S4:** Given a plain (unmasked) `numpy.ndarray` and a
  `~astropy.utils.masked.MaskedNDArray` of a different but broadcast-compatible
  shape, when `numpy.broadcast_arrays(plain, masked)` is called (the public
  dispatch entry point, which routes through this module's
  `broadcast_arrays`), then the plain array is returned broadcast to the
  common shape as a plain array, and the masked array is returned as a
  `MaskedNDArray` whose `.unmasked` data and `.mask` are both broadcast to
  that same common shape (mirrors
  `astropy/utils/masked/tests/test_functions.py:433-439`,
  `test_broadcast_arrays_not_all_masked`).
- **S5:** Given two `MaskedNDArray` inputs of broadcast-compatible shapes,
  when `numpy.broadcast_arrays(a, b, subok=True)` is called, then both
  outputs are `MaskedNDArray` instances with correctly broadcast data and
  masks (mirrors `test_functions.py:425-431`, `test_broadcast_arrays`).
- **S6:** Given a single `MaskedNDArray` input `ma`, when
  `numpy.broadcast_arrays(ma, subok=True)` is called, then the result is a
  `list` (numpy < 2.0) or `tuple` (numpy >= 2.0) of length 1 whose sole
  element is a `MaskedNDArray` sharing memory with `ma`'s unmasked data
  (`np.may_share_memory(result[0], ma) is True`) — this pins the
  single-argument case against the regression at
  `astropy/utils/masked/tests/test_function_helpers.py:163-168`.
- **S7:** Given `MaskedNDArray`-wrapped `Quantity` inputs (i.e.
  `Masked(Quantity(...))`, so the unmasked data is itself an `ndarray`
  *subclass* — mirrors the setup in
  `TestMaskedQuantityBroadcast(TestMaskedArrayBroadcast, QuantitySetup)`,
  `test_functions.py:452-453`), when
  `numpy.broadcast_arrays(a, b, c, subok=False)` is called, then outputs
  remain `MaskedNDArray` (masking is preserved regardless of `subok`), but
  `type(result.unmasked) is np.ndarray` for each — the `Quantity` subclass
  of the underlying data is dropped, unlike the `subok=True` case in S5
  where it would be preserved. This must fail for an implementation that
  ignores `subok` on the data array (a plain `ndarray`-backed test input
  would pass regardless, since `type(plain_ndarray) is np.ndarray` already
  holds either way — mirrors `test_functions.py:441-449`,
  `test_broadcast_arrays_subok_false`).
- **S8:** Given an `astropy.units.Quantity` object (e.g. `5 * u.m`), when
  `has_units(quantity)` is called, then it returns `True`.
- **S9:** Given a plain `numpy.ndarray` or a plain Python number, when
  `has_units(obj)` is called, then it returns `False`.
- **S10:** Given a process/test where `_LEAP_SECONDS_CHECK` is reset to
  `_LeapSecondsCheck.NOT_STARTED` and `update_leap_seconds` is monkeypatched
  to a call-counting stand-in, when `_check_leapsec()` is called twice in
  sequence, then the stand-in is invoked exactly once in total across both
  calls (the second call does not increment the count again).
- **S11:** Given a `Table` with only unmasked columns (e.g.
  `Table([[1, 2], [3, 4]], names=["a", "b"])`), when `np.array(t)` is
  called, then the result is a structured `numpy.ndarray` (not a `Table`,
  not a `MaskedArray`, and `result is not t.as_array()`) whose field names
  equal `t.colnames` and whose values equal `t.as_array()`'s values
  (mirrors `astropy/table/tests/test_table.py:1535`,
  `test_convert_numpy_array`).
- **S12:** Given any `Table` `t`, when `np.array(t, dtype=object)` is
  called, then the result is a 0-d object-dtype `numpy.ndarray` and
  `result[()] is t` (identity — not `Table.__eq__`, since `__eq__` returns
  an elementwise comparison rather than a bool) — mirrors
  `test_table.py:1593`, `test_convert_numpy_object_array`.
- **S12b (`copy` accepted but not consulted on the object path):** Given a
  `Table` `t`, when `np.array(t, dtype=object, copy=True)` is called, then
  the result is a 0-d object array with `result[()] is t` — the same
  outcome as S12 with `copy` left at its default. (Calling with
  `copy=False` is not part of this contract; see Interface Contract for
  why `copy` is accepted but ignored on this path.)

### Edge Cases

- **S13:** Given `val1 = 5 * u.day`, with the bound method
  `val1.unit.to` monkeypatched (e.g. via
  `monkeypatch.setattr(val1.unit, "to", raiser)`) to raise `RuntimeError`
  unconditionally, while `Quantity.to_value` is left unmodified (so
  `val1.to_value(u.day) == 5.0` still succeeds independently of
  `val1.unit.to`), when `quantity_day_frac(val1)` is called, then it
  returns `(5.0, 0.0)` via the documented fallback, without raising. This
  directly exercises the `except Exception:` branch regardless of which
  real-world unit/equivalency combination would naturally trigger it.
- **S14:** Given `numpy.broadcast_arrays(masked, other)` called with shapes
  that cannot be broadcast together, when it is called, then it raises the
  same exception type `numpy.broadcast_arrays` raises for the equivalent
  all-plain-array call.
- **S15:** Given an object that simply lacks a `unit` attribute (e.g.
  `None`, `object()`), when `has_units(obj)` is called, then it returns
  `False` without raising. (Objects whose `__getattr__` raises something
  other than `AttributeError` are outside this contract — see Trade-offs
  and Limitations.)
- **S16:** Given two threads that both call `_check_leapsec()` while
  `update_leap_seconds` is monkeypatched to a stand-in that blocks briefly
  (e.g. on a `threading.Event`) before returning, and
  `_LEAP_SECONDS_CHECK` starts at `NOT_STARTED`, when both threads' calls
  are joined, then the stand-in's invocation count is exactly 1 (assert the
  count, not lock-acquisition order or timing).
- **S17:** Given a stand-in for `update_leap_seconds` that itself calls
  `_check_leapsec()` before returning (simulating a re-entrant call, e.g. a
  UTC conversion triggered from within the update logic), when the outer
  `_check_leapsec()` is called, then the whole call completes (no deadlock)
  within a bounded test timeout, and the stand-in's invocation count stays
  at 1 (the re-entrant inner call must not trigger a second update).
- **S18:** Given a masked `Table` (`Table(..., masked=True)` or containing a
  `MaskedColumn`), when `np.array(t)` is called with `dtype=None`, then the
  result is a plain (non-masked) `numpy.ndarray` — mask information is not
  present in the returned array, matching `Table.as_array()`'s existing,
  unmodified behavior.

### Error Scenarios

- **S19:** Given a `Table` `t`, when
  `np.array(t, dtype=[("c", "i8"), ("d", "i8")])` (or any concrete
  non-object dtype) is called, then it raises `ValueError` — mirrors
  `test_table.py:1548-1549` (inside `test_convert_numpy_array`).
- **S20:** Given a `Quantity` `val1` with no valid time conversion at all —
  concretely `val1 = 5 * u.m` with no time-related equivalency enabled —
  when `quantity_day_frac(val1)` is called, then it raises some exception
  (does not return a numeric result). Note: upstream, this raises
  `u.UnitConversionError`; in this tree it currently raises `NameError`
  from the unrelated, out-of-scope gap at `astropy/units/core.py:510-519`
  (`get_err_str` is called but not defined) — only "raises, does not
  silently return a bogus value" is part of this scenario's contract, not
  a specific exception class.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*. A green suite that passes for the
> wrong reason does not satisfy this contract — `/verify` will hunt for
> vacuous tests by asking, of each behavior, "what is the smallest change
> that breaks this, and would any test catch it?"

Scope reminder: write **only** the five definitions named in the Interface
Contract, at the five gaps named in Context. Do not modify any other region
of `astropy/time/utils.py`, `astropy/utils/masked/function_helpers.py`,
`astropy/timeseries/periodograms/lombscargle/core.py`,
`astropy/time/core.py`, or `astropy/table/table.py`, and do not touch
`astropy.units` internals, `astropy/timeseries/periodograms/bls/core.py`
(including its broken `has_units` import — out of scope, see Context),
`Table._init_from_ndarray` (also stripped, but not one of the five target
interfaces — leave it as found), coordinate transforms, or the
Lomb–Scargle periodogram algorithms.

Existing tests to consult (do not need to be rewritten, but pass for the
five interfaces in scope and can be used to sanity-check the expected
numeric/behavioral contract — some of the files below contain unrelated
tests that stay red because of the out-of-scope gaps named in Context; only
the specific tests/lines cited are expected to be affected by this spec):

- `astropy/time/tests/test_precision.py:321-335` — `test_two_sum`, showing
  the `decimal.localcontext` precision-checking technique reused in S1.
- `astropy/time/tests/test_precision.py` — the `test_day_frac_*` family
  (day_frac itself, unmodified, used as a reference).
- `astropy/time/formats.py:336` — the sole in-tree caller of
  `quantity_day_frac`, reached via `Time` construction from a `Quantity`.
- `astropy/time/tests/test_update_leap_seconds.py`
  (`TestUpdateLeapSeconds`) — note some of its tests may be blocked by the
  unrelated `TimeString.str_kwargs` gap (`formats.py:1682-1724`), which
  breaks `str(Time)`/`.iso`; that is out of scope for this spec.
- `astropy/utils/masked/tests/test_function_helpers.py:159-168`
  (`test_broadcast_arrays`, includes the single-argument regression case).
- `astropy/utils/masked/tests/test_functions.py:401-453`
  (`TestMaskedArrayBroadcast`: `test_broadcast_arrays`,
  `test_broadcast_arrays_not_all_masked`,
  `test_broadcast_arrays_subok_false`; and its subclasses
  `TestMaskedQuantityBroadcast`, `TestMaskedLongitudeBroadcast`, which
  exercise `subok` against genuine `ndarray` subclasses).
- `astropy/table/tests/test_table.py:1535-1550`
  (`test_convert_numpy_array`), `:1593-1596`
  (`test_convert_numpy_object_array`), `:1598-1601`
  (`test_convert_list_numpy_object_array`) — all in class
  `TestConvertNumpyArray`.

Write tests to the project's conventions (pytest, function-based tests
colocated in each module's `tests/` directory) and to these principles (the
same ones `/verify` scores against — see `references/test-desiderata.md`
and `references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects, not
  internals; the suite must survive refactoring. For `_check_leapsec`,
  assert the observable effect (whether the monkeypatched
  `update_leap_seconds` stand-in was invoked, and how many times), not lock
  acquisition order or timing.
- **Every test can fail** — no copy-pasted expected values, no asserting a
  constant, no tautologies (AP-2, AP-4). For `quantity_day_frac` (S1-S3c),
  assert `day` and `frac` **separately** (or against a `Decimal` reference,
  per S1) rather than `day + frac == expected`, which collapses the extra
  precision back into a single `float64` and passes equally for a naive
  `val1.to_value(u.day), 0.0` implementation. For `broadcast_arrays` `subok`
  (S7), use inputs whose unmasked data is an `ndarray` *subclass*
  (`Quantity`), not a plain `ndarray` — otherwise `subok=False` and
  `subok=True` produce identical, indistinguishable results.
- **Deterministic, isolated, readable** — inject clocks/randomness, no
  cross-test state, AAA structure with inline setup. Any test touching the
  `_LEAP_SECONDS_CHECK` / `_LEAP_SECONDS_LOCK` module globals must save and
  restore that state (or use `monkeypatch`) so one test's leap-second check
  does not leak into another test's expectations.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Every scenario S1, S2, S3a, S3b, S3c, S4-S12, S12b, S13-S20 has a new,
      dedicated test that exercises it, and all such new tests pass.
- [ ] For each of the five restored interfaces, running its most directly
      relevant existing test file/class from "Existing tests to consult"
      above does not regress relative to its pre-implementation (before
      this spec's changes) baseline — i.e. any test in those files that
      passed before restoring the five definitions still passes, and the
      specific cited tests/line ranges (not necessarily the whole file)
      pass. A pre-existing failure that is traceable to one of the named,
      out-of-scope gaps in Context (`units/core.py:510-519`,
      `formats.py:1682-1724`, `Table._init_from_ndarray`,
      `bls/core.py:11`, or any other stripped region discovered during
      implementation) is not a blocker for this Definition of Done, but
      must be named explicitly (file:line and which gap it traces to) in
      the verification report rather than silently ignored.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
      the smallest break of its behavior (thought-mutation).
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
      first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings) in any of the five restored definitions.

## Alternatives Considered

### Widen scope to restore every stripped region found during the codebase scan

The scan that surfaced the five target gaps also found several other
unrelated gaps (listed in Context: `units/core.py`, `timeseries/core.py`,
`time/formats.py`, `utils/shapes.py`,
`lombscargle_multiband/core.py:20-30`, `Table._init_from_ndarray`, and the
broken import in `bls/core.py`). Restoring all of them in one spec was
considered, but the task's own scope statement explicitly excludes the
systems those gaps belong to (general unit system, table type, periodogram
algorithms). Rejected in favor of the narrow, explicitly-authorized scope;
the other gaps are left as known, named, out-of-scope pre-existing
conditions rather than silently ignored, and the Definition of Done is
written as a baseline-delta so it does not falsely fail a correct
implementation of the five in-scope interfaces because of them.

### Reimplement each function from first principles instead of matching the documented contract

Each function has existing callers and existing tests (see References and
"Existing tests to consult") written against a specific, known-good
contract. Deviating from it — e.g. changing `broadcast_arrays`'s return
arity, or making `quantity_day_frac` always use plain
`val1.to_value(u.day)` instead of the divide-when-factor-<1 precision trick
— would silently reduce precision or break the dispatch protocol callers
depend on. Rejected in favor of matching the documented contract in the
Interface Contract section exactly.

## Security Considerations

None of these five functions accept untrusted external input in a way that
differs from their surrounding, already-trusted call sites (in-process
values already validated by `Time`, `Table`, `MaskedNDArray`, or
`LombScargle`). No new I/O, deserialization, or privilege boundary is
introduced. `_check_leapsec`'s only I/O is delegating to the existing,
unmodified `update_leap_seconds()`.

## Trade-offs and Limitations

- `quantity_day_frac`'s precision trick (dividing by the reciprocal
  conversion factor when it is less than 1, rather than multiplying by the
  potentially-inexact factor itself) only holds for astropy's built-in,
  simply-scaled time units; it does not improve precision for custom units
  or equivalency-based/monkeypatched-failure conversions, which fall back
  to plain `Quantity.to_value` (S13).
- What happens if `update_leap_seconds()` itself raises inside
  `_check_leapsec()` is not specified by this spec (no scenario covers it);
  the documented behavior is silent about error recovery, and this spec
  does not add any — a raising `update_leap_seconds()` leaves
  `_LEAP_SECONDS_CHECK` at `RUNNING` and the propagated exception is the
  caller's problem, exactly as before restoration.
- `has_units` is intentionally a thin `hasattr` wrapper: objects with a
  `__getattr__`/property named `unit` that raises something other than
  `AttributeError` on access will propagate that exception rather than
  being treated as "no units" — this is existing, accepted behavior being
  restored, not a new limitation, and is not covered by any acceptance
  scenario (see S15's parenthetical).
- `_check_leapsec`'s single-attempt-per-process guarantee means a
  leap-second table that becomes stale mid-process (e.g. a long-running
  server process spanning a new leap-second announcement) is not
  re-checked without an explicit `update_leap_seconds()` call — existing,
  intentional behavior being restored, not a new limitation.
- `Table.__array__`'s mask-dropping behavior (S18) matches
  `Table.as_array()`'s existing behavior and is not something this task
  changes.
- This spec does not address `Table._init_from_ndarray`, the broken
  `has_units` import in `bls/core.py`, or the other stripped regions listed
  in Context; the overall test suite will not be fully green until those
  are addressed by other work.

## References

- `astropy/time/formats.py:336` — sole in-tree caller of
  `quantity_day_frac`.
- `astropy/utils/masked/function_helpers.py` — `block()` immediately above
  the `broadcast_arrays` gap, showing the local-import-of-`Masked` and
  `return result, None, None` dispatch pattern to follow; `astropy/utils/masked/core.py:1043`
  confirms the `result, mask, out = dispatched_result` unpacking contract.
- `astropy/timeseries/periodograms/lombscargle_multiband/core.py:17` — an
  already-working, unstubbed `has_units` with identical intended behavior.
- `astropy/timeseries/periodograms/bls/core.py:11,17,20,755,762,791,797` —
  a separate, out-of-scope consumer whose own import of `has_units` was
  also stripped; not fixed by this spec (see Context/Scope decision).
- `astropy/time/core.py:151-158,797` — `_LeapSecondsCheck` enum,
  `_LEAP_SECONDS_CHECK`, `_LEAP_SECONDS_LOCK` module globals, and the
  `Time._set_scale` call site that invokes `_check_leapsec()`.
- `astropy/table/table.py` — `Table.as_array()` (unmodified, existing
  method that `__array__` delegates to for the `dtype=None` path);
  `Table.__init__` at `:822,826` still calls the also-stripped, out-of-scope
  `_init_from_ndarray`.
- `astropy/units/core.py:236-238,510-519,626-643` — `Unit.to()`'s
  `equivalencies` parameter defaults to `[]`, which folds in any globally
  enabled equivalencies via `set_enabled_equivalencies`; and the
  `get_err_str` gap referenced by S20.

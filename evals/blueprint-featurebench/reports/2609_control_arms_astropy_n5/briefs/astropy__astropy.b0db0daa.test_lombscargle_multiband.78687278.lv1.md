# Implementation Brief: Five Missing Astropy Utility Interfaces

Repo root for all work: `/testbed/`. All five gaps below are real — I confirmed
each function/method is currently absent from its target file (verified by
reading the files and grepping for callers that already reference the missing
symbol). Do not touch anything else; do not implement the general unit
system, Time/TimeDelta formats, Table internals, coordinate transforms, or
the Lomb–Scargle algorithm itself — only the five interfaces below.

Run tests with `python -m pytest <path> -x -q` from `/testbed/`. No
dependencies need installing.

---

## 1. `quantity_day_frac` — `/testbed/astropy/time/utils.py`

Insert this function after `day_frac` (currently ends at line 76) and before
`two_sum` (line 122) — there is a blank gap there already.

The file already provides the building blocks you need:
- `day_frac(val1, val2, factor=None, divisor=None)` (line 19) — exact
  Shewchuk summation returning an integer/fractional day pair.
- `two_sum`, `two_product`, `split` — lower-level precision helpers, not
  needed directly for this function.

`import astropy.units as u` is already imported at the top of the file.

**Caller contract (must not break):** `/testbed/astropy/time/formats.py`
around line 328-337, inside `TimeJD._check_val_type` (used by all formats
via `_check_val_type`):

```python
try:
    val1, val2 = quantity_day_frac(val1, val2)
except u.UnitsError:
    raise u.UnitConversionError(
        "only quantities with time units can be "
        "used to instantiate Time instances."
    )
```

So: if `val1` has a unit that is not convertible to time/day, you must let a
`u.UnitsError` (or subclass, e.g. `u.UnitConversionError` /
`u.UnitTypeError`) propagate out — do not catch and re-wrap it yourself.
`val1` and (if given) `val2` are `astropy.units.Quantity` instances (the
caller wraps plain values with `u.Quantity(val1, copy=False)` beforehand).

**Required behavior (from the interface docstring — follow it exactly):**

- **Single argument (`val2 is None`):**
  - Determine whether converting `val1`'s unit to `u.day` is a pure scale
    factor, e.g. via `val1.unit.to(u.day)`. If that succeeds, use `day_frac`
    with that scale as `factor` against `val1.value` (and `0.0` since there
    is no second addend) so you get an exact integer-day / fractional-day
    pair without losing precision to an intermediate `.to(u.day)` float
    conversion. This is the "ordinary simply-scaled input" path — return
    `(day, frac)` from `day_frac`.
  - If the unit-to-day conversion is *not* a simple scale (raises something
    other than a plain incompatible-unit failure — practically, use a
    try/except around the scale-factor lookup and fall back on genuine
    failure to produce a factor), fall back to `val1.to_value(u.day)` for
    the complete value and return `(that_value, zeros_like(that_value))`.
    Do **not** swallow a genuine `u.UnitsError` here — only fall back for
    non-scale-conversion cases; wrong-dimension errors must still propagate
    (see caller contract above).
- **Two arguments:** compute the day/frac pair for `val1` and for `val2`
  independently (same logic as the single-argument case, applied to each),
  then return their **componentwise sum** — `(day1 + day2, frac1 + frac2)` —
  *without* re-normalizing through `day_frac`'s two_sum trick again. The
  docstring is explicit that the two-input result "is not normalized again."

Validate against `/testbed/astropy/time/tests/test_basic.py`,
`test_custom_formats.py`, `test_methods.py`, and `test_precision.py` — none
call `quantity_day_frac` directly, but all construct `Time`/`TimeDelta` from
`Quantity` inputs (e.g. seconds, years) and check round-trip precision, so
they exercise this function thoroughly. Also run
`/testbed/astropy/time/tests/test_update_leap_seconds.py` and general
`astropy/time/tests/` since `Time` construction from quantities is
pervasive.

---

## 2. `broadcast_arrays` — `/testbed/astropy/utils/masked/function_helpers.py`

Add this as a `@dispatched_function`-decorated function. Good insertion
point: right after `broadcast_to` (defined at line ~281) since it's the
closest sibling function, or near `outer` (line ~293) — either is fine, this
module has no strict ordering requirement, just group it with other
broadcast/shape helpers.

The module already has everything you need:
- `_get_data_and_mask_array(array)` (line 200) — for one arg, returns
  `(data, mask)`, synthesizing an all-`False` mask if the arg is not
  `Masked`.
- `_get_data_and_mask_arrays(arrays)` (line 210) — same, vectorized over an
  iterable, returning `(datas_tuple, masks_tuple)`.
- `dispatched_function = FunctionAssigner(DISPATCHED_FUNCTIONS)` (line 197).

**How `dispatched_function` results are consumed** (see
`astropy/utils/masked/core.py`, `Masked.__array_function__`, lines
~1031-1051, and `_masked_result`, lines ~1071-1090): a dispatched function
must return a 3-tuple `(result, mask, out)`. If `result` is itself a tuple,
`_masked_result` recurses element-by-element, zipping `result`, `mask`
(broadcast to same length if it isn't already a list/tuple), and `out`. Each
element ends up wrapped as `Masked(result_i, mask_i)` — note that even
originally-*unmasked* inputs end up wrapped as `MaskedNDArray` with an
all-`False` mask (confirmed empirically: `Masked(some_ndarray, None)`
produces a `MaskedNDArray` with a `False`-filled mask, not a bare `ndarray`).
This matches the existing test `test_broadcast_arrays_subok_false` in
`/testbed/astropy/utils/masked/tests/test_functions.py` (~line 441), which
asserts `type(mb_.unmasked) is np.ndarray` for *every* returned element,
including ones from unmasked inputs.

**Implementation approach:**
```python
@dispatched_function
def broadcast_arrays(*args, subok=False):
    """... (use the docstring given in the interface description) ..."""
    are_masked = [isinstance(arg, Masked) for arg in args]
    data, masks = _get_data_and_mask_arrays(args)
    results = np.broadcast_arrays(*data, subok=subok)
    mask_results = np.broadcast_arrays(*masks, subok=subok)
    return results, mask_results, None
```
Check whether `np.broadcast_arrays` on a single argument still returns an
iterable of length 1 in the installed numpy (it does here — numpy 2.5.3
returns a tuple even for a single array); confirm this handles the
regression test in `test_function_helpers.py` (~line 159-166) that checks
`np.broadcast_arrays(self.ma, subok=True)` for a *single* masked array
still returns a tuple/list of length 1 whose element shares memory with the
input (`np.may_share_memory`).

**Tests to run:**
- `/testbed/astropy/utils/masked/tests/test_function_helpers.py::TestShapeManipulation::test_broadcast_arrays` (~line 159)
- `/testbed/astropy/utils/masked/tests/test_functions.py::TestMaskedArrayBroadcast::test_broadcast_arrays`, `test_broadcast_arrays_not_all_masked`, `test_broadcast_arrays_subok_false` (~lines 425-446)

For reference (do not copy verbatim — different data model), there is an
analogous `broadcast_arrays` for `Distribution` objects in
`/testbed/astropy/uncertainty/function_helpers.py` (~line 105) showing the
same "broadcast a mix of wrapped/unwrapped inputs" idea, but it uses the
`function_helper` (not `dispatched_function`) protocol, so its return
convention differs — do not mimic its return statement.

---

## 3. `has_units` — `/testbed/astropy/timeseries/periodograms/lombscargle/core.py`

Insert between `strip_units` (ends ~line 27) and `class LombScargle` — there
is a blank gap there already. The identical function already exists (and is
in active use) in the sibling module
`/testbed/astropy/timeseries/periodograms/lombscargle_multiband/core.py`
(line 17-18):

```python
def has_units(obj):
    return hasattr(obj, "unit")
```

Use exactly this implementation (it matches the interface docstring: "True
if the object has a 'unit' attribute, False otherwise"). This module's
`LombScargle` class already calls `has_units(...)` at lines 152, 165, 172,
179, 188 — those call sites are otherwise complete and will start working
once this function exists.

**Tests:** `/testbed/astropy/timeseries/periodograms/lombscargle/tests/` —
run the full directory; several tests construct `LombScargle` with
`Quantity` time/flux arrays and rely on unit-handling branches gated by
`has_units`.

---

## 4. `_check_leapsec` — `/testbed/astropy/time/core.py`

Insert this function near the module-level leap-second state, right after
the existing definitions (around line 158, after `_LEAP_SECONDS_LOCK =
threading.RLock()`):

```python
class _LeapSecondsCheck(enum.Enum):
    NOT_STARTED = 0  # No thread has reached the check
    RUNNING = 1      # A thread is running update_leap_seconds (_LEAP_SECONDS_LOCK is held)
    DONE = 2         # update_leap_seconds has completed


_LEAP_SECONDS_CHECK = _LeapSecondsCheck.NOT_STARTED
_LEAP_SECONDS_LOCK = threading.RLock()
```

These already exist (lines 150-158) — `_check_leapsec` is the missing piece
that drives this state machine. It is called from `Time._set_scale` (line
797) whenever a scale transform touches `"utc"`. The module already defines
`update_leap_seconds(files=None)` (line 3381) which does the actual
ERFA-table update and never raises (turns exceptions into warnings).

**Required behavior**, per the module's own state-machine comments and the
existing test `/testbed/astropy/time/tests/test_update_leap_seconds.py::TestUpdateLeapSeconds::test_init_thread_safety`
(~line 82-100):
- The check must run **at most once per process** (per the enum comments:
  `NOT_STARTED` → `RUNNING` → `DONE`).
- Concurrent/re-entrant calls (the test spins up 4 threads via
  `ThreadPoolExecutor`, each constructing a `Time` and converting to `tai`,
  which triggers `_set_scale` → `_check_leapsec`) must not each launch their
  own `update_leap_seconds()` call — only one thread should do the actual
  update; the others should either block until it's done or simply skip
  since it's already `DONE`.
- Use the module-level `_LEAP_SECONDS_LOCK` (an `RLock`, already defined) to
  guard the state transition, and the module-level `global
  _LEAP_SECONDS_CHECK` to track state. A pattern like:

```python
def _check_leapsec():
    global _LEAP_SECONDS_CHECK
    if _LEAP_SECONDS_CHECK != _LeapSecondsCheck.DONE:
        with _LEAP_SECONDS_LOCK:
            if _LEAP_SECONDS_CHECK == _LeapSecondsCheck.NOT_STARTED:
                _LEAP_SECONDS_CHECK = _LeapSecondsCheck.RUNNING
                update_leap_seconds()
                _LEAP_SECONDS_CHECK = _LeapSecondsCheck.DONE
```

  (An outer unlocked check before acquiring the lock is a reasonable
  optimization to avoid lock contention once `DONE`, but it is optional —
  correctness matters more than that micro-optimization. The important
  parts the test actually depends on are: the module-level
  `_LEAP_SECONDS_CHECK` / `_LeapSecondsCheck` names existing and being
  monkeypatchable exactly as referenced by the test, and only one
  `update_leap_seconds()` call happening under concurrent access without
  raising.)

**Tests:** run
`/testbed/astropy/time/tests/test_update_leap_seconds.py` in full (it
monkeypatches `astropy.time.core._LEAP_SECONDS_CHECK` and
`astropy.time.core._LeapSecondsCheck` directly by name, so those names must
match exactly), plus a broad run of `/testbed/astropy/time/tests/` since
`_check_leapsec` is on the hot path for any UTC-involving scale conversion.

---

## 5. `Table.__array__` — `/testbed/astropy/table/table.py`

Add as a method on the `Table` class. The class attribute block the
interface description quotes (`meta`, `Row`, `Column`, `MaskedColumn`,
`TableColumns`, `TableFormatter`, `read`, `write`, `pprint_exclude_names`,
`pprint_include_names`, `info = TableInfo()`) is spread across the class:
most of those attributes sit near the top of the class body (~line
631-646), but `info = TableInfo()` is the **last** line of the `Table`
class body, at line 4338 (immediately before `class QTable(Table):`).
**Add `__array__` right after `info = TableInfo()` at line 4338**, i.e. as
the last method of the `Table` class, matching the ordering implied by the
interface description.

`from astropy.utils.compat import COPY_IF_NEEDED` is already imported at
the top of the file (line 20).

There is already a closely related method, `as_array(self,
keep_byteorder=False, names=None)` (line 649), which builds a structured
`ndarray` (or `numpy.ma.MaskedArray` if the table is masked) from the
table's columns. `__array__` should produce the **unmasked** structured
array — the interface docstring is explicit: "Masks are not preserved in
the returned ndarray."

**Required behavior (from the interface docstring):**
- `dtype=None` (default): return a structured `ndarray` of all table data,
  field names matching column names, masks stripped even if the table is
  masked. `as_array()` is a reasonable base to build on, but note it
  returns a `numpy.ma.MaskedArray` for masked tables — `np.asarray(...)` on
  that gives you the underlying data view without the mask, which matches
  "masks are not preserved."
- `dtype` given and it is (`np.dtype(dtype) == object`): **do not** try to
  coerce the table's structured data into an object array. Instead the
  expected result is a **0-d object array whose single element is the
  `Table` instance itself** — confirmed by
  `/testbed/astropy/table/tests/test_table.py::TestMetaTable::test_convert_numpy_object_array`
  (~line 1592-1597):
  ```python
  np_d = np.array(d, dtype=object)
  assert isinstance(np_d, np.ndarray)
  assert np_d[()] is d
  ```
  A safe way to build this without infinite recursion through `__array__`
  itself: create an empty object array and assign the table into a slot,
  e.g. `out = np.empty((), dtype=object); out[()] = self; return out`.
  (Also see `test_convert_list_numpy_object_array`, ~line 1599-1604, which
  wraps a *list* of tables with `np.array(ds, dtype=object)` — that path
  goes through numpy's own list-of-objects handling calling `__array__` on
  each table with `dtype=object`, so your single-table `dtype=object`
  handling above must satisfy both tests.)
- `dtype` given and it is anything else (not `None`, not `object`): raise
  `ValueError` (per the docstring: "If dtype coercion is requested to a
  non-object dtype, which is not supported").
- `copy` parameter: accept it (default `COPY_IF_NEEDED`) for API
  compatibility with numpy's `__array__` protocol dispatch, but the
  underlying `as_array()`-based construction already copies data into a new
  structured array, so it's reasonable to not thread `copy` through
  further; just accept the parameter so callers using `np.array(t,
  copy=...)` don't error.

**Tests to run:**
- `/testbed/astropy/table/tests/test_init_table.py::TestInitFromNdarrayStruct::test_ndarray_ref` (~line 318, `assert np.all(np.array(t) == self.data)`)
- `/testbed/astropy/table/tests/test_table.py::TestMetaTable::test_convert_numpy_object_array` and `test_convert_list_numpy_object_array` (~lines 1592-1605)
- Broad run of `/testbed/astropy/table/tests/test_table.py` and
  `/testbed/astropy/table/tests/test_masked.py` since `np.array(table)` is
  used incidentally throughout for equality assertions.

---

## General validation

After implementing all five, run at minimum:
```
python -m pytest astropy/time/ astropy/utils/masked/ astropy/table/ \
  astropy/timeseries/periodograms/lombscargle/ \
  astropy/timeseries/periodograms/lombscargle_multiband/ -q
```
from `/testbed/`, and confirm no new failures relative to a baseline run
(some unrelated pre-existing failures/skips in this environment, e.g. tests
requiring network access marked `remote_data`, are expected and not your
concern).

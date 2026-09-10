# 2609.0001 Uncertainty Distribution Interfaces

**Date:** 2026-09-10
**Status:** draft
**Author:** FeatureBench
**Reviewed:** 2026-09-10 — testability review; every requirement re-grounded against
`core.py`, `function_helpers.py`, the two oracle test files, and the `Quantity`
reference implementation.

## Context

`astropy/uncertainty/` implements `Distribution`, a scalar-or-array value type that
carries a Monte Carlo sample set instead of (or in addition to) a single value, so that
uncertainty propagates automatically through arithmetic and NumPy operations. The
sub-package has three source files:

- `astropy/uncertainty/core.py` — the `Distribution`, `ScalarDistribution`,
  `ArrayDistribution`, `_DistributionRepr`, and `NdarrayDistribution` classes.
- `astropy/uncertainty/function_helpers.py` — the dispatch tables
  (`DISTRIBUTION_SAFE_FUNCTIONS`, `FUNCTION_HELPERS`, `DISPATCHED_FUNCTIONS`,
  `UNSUPPORTED_FUNCTIONS`) that `Distribution.__array_function__` consults, built with the
  `FunctionAssigner` helper already used by `astropy/units/quantity_helper/function_helpers.py`.
- `astropy/uncertainty/distributions.py` — `normal`/`poisson`/`uniform` sample-generating
  convenience functions. **This file is complete and must not be touched**; it already
  calls `cls(samples, **kwargs)` and expects a working `Distribution.__new__`.

In the current tree, `core.py` and `function_helpers.py` have had large chunks of their
bodies blanked out (replaced with empty lines), while everything around the gaps —
imports, class scaffolding, and several already-working methods — is untouched. The
surviving code tells you exactly what the missing pieces must plug into:

- `Distribution.dtype` (core.py:186-195) reads `super().dtype["samples"].base["sample"]`
  and its setter calls a not-yet-defined `self._get_distribution_dtype(dtype,
  self.n_samples, itemsize=...)`. This means the physical/storage dtype of every
  Distribution instance **must** be a structured dtype with exactly one top-level field
  named `"samples"`, declared as a sub-array of length `n_samples`, whose base dtype is
  itself a one-field struct named `"sample"` holding the user-facing dtype. Concretely,
  for a user dtype `dt` and sample count `n`:
  `np.dtype([("samples", np.dtype([("sample", dt)]), (n,))])`. The inner `"sample"`
  struct may additionally be *padded* to a larger itemsize (that is what the setter's
  `itemsize=` argument is for); see `_get_distribution_dtype` in Key Components.
- `Distribution.astype` (core.py:197-199) calls the same
  `self._get_distribution_dtype(dtype, self.n_samples)` helper — so that helper is a
  required, shared piece of surface, not a private implementation detail you're free to
  name differently. (`astype` is on the live path: `Quantity.__new__` calls
  `value.astype(float)` on integer input, which is what
  `TestInit.test_quantity_init_with_distribution` exercises.)
- `Distribution.distribution` (core.py:182-184, inherited by `ArrayDistribution`) already
  does `return self["samples"]["sample"]` — that property is **already implemented** and
  works once the storage dtype above exists; do not re-implement it.
- `ArrayDistribution.__getitem__`/`__setitem__` (core.py:592-636) already assume
  `self.distribution` and `self["samples"]` behave as described above, already handle
  string field indexing, `Distribution`-typed boolean masks, and structured sub-fields.
  Do not modify them; the missing constructor/dtype code must make them work, not the
  other way around.
- `Distribution.pdf_mean`, `pdf_var`, `pdf_mad`, `pdf_smad`, `pdf_percentiles`,
  `pdf_histogram`, `_not_implemented_or_raise`, `__eq__`, `__ne__` (core.py:339-510) are
  already implemented and already call `self.distribution`, `self.pdf_median`, and
  `np.abs(self - median)` (i.e., they depend on ufunc dispatch working). Do not modify
  them.
- The module imports `normalize_axis_index`, `_parse_gufunc_signature`, and `DummyArray`
  at the top of `core.py` (lines 15-22) but nothing currently uses them, so the removed
  code did. These are *hints*, not requirements — an implementation that satisfies the
  behavior below without one of them is acceptable (as is leaving one unused). The likely
  roles are: `_parse_gufunc_signature` to find a generalized ufunc's core dimensions in
  `__array_ufunc__`; `normalize_axis_index` to translate a user-supplied `axis` against
  the *logical* (sample-axis-excluded) shape; and `DummyArray` (the
  `numpy.lib.stride_tricks` helper behind `as_strided`) to build structured views of
  sample data with hand-computed strides in `__new__`/`view`, which plain
  `ndarray.view(dtype)` cannot express (see the padded-storage requirement in Key
  Components).
- `core.py:25` currently reads `from .function_helpers import FUNCTION_HELPERS` — only
  one of the four dispatch collections is imported. `__array_function__` needs
  `DISPATCHED_FUNCTIONS` as well (`np.broadcast_arrays` cannot be expressed as a
  `FUNCTION_HELPERS` entry; see S12/S13), and `DISTRIBUTION_SAFE_FUNCTIONS` /
  `UNSUPPORTED_FUNCTIONS` if those branches are implemented. **Extending that import line
  (or replacing it with `from . import function_helpers` and attribute access) is
  explicitly allowed** and is the one expected edit outside the blanked-out regions.
- `function_helpers.py` already defines `function_helper = FunctionAssigner(FUNCTION_HELPERS)`
  and `dispatched_function = FunctionAssigner(DISPATCHED_FUNCTIONS)` (mirroring
  `astropy/units/quantity_helper/function_helpers.py`, which is a complete, working
  reference implementation of the same dispatch-table pattern for `Quantity`). The gap
  between that line and the final `__all__` block is where the `Distribution`-specific
  function helpers belong.
- The blank regions (all-empty lines) in the current tree are: `core.py` 59-181,
  201-338, 372-378, 387-394, 403-415, 528-591, and `function_helpers.py` 74-151. The
  sizes of the small `core.py` gaps line up with the missing members: 372-378 sits
  between `__ne__` and `pdf_mean` (the natural home of the `n_samples` property),
  387-394 between `pdf_mean` and `pdf_var` (`pdf_std`), and 403-415 between `pdf_var`
  and `pdf_mad` (`pdf_median`). Exact placement is not part of the contract; line counts
  are not either (the file may grow or shrink).
- `astropy/uncertainty/tests/test_distribution.py` (690 lines) and
  `astropy/uncertainty/tests/test_functions.py` (98 lines) are complete, already-written
  test suites for this module. They currently fail at collection/run time because the
  class they import cannot be constructed. They are the ground truth for behavior in
  this spec and are not to be edited.

## Motivation

As shipped, `Distribution` cannot be instantiated at all (`__new__` is missing), so the
entire `astropy.uncertainty` sub-package — including the already-complete
`distributions.py` helpers (`normal`, `poisson`, `uniform`) and the already-complete
statistics methods (`pdf_mean`, `pdf_var`, `pdf_mad`, `pdf_smad`, `pdf_percentiles`,
`pdf_histogram`) — is unusable. Every test in `test_distribution.py` and
`test_functions.py` fails. Filling in the missing construction, NumPy protocol dispatch,
and two statistics methods is what turns this scaffold into a working feature.

## Proposed Solution

### Overview

Implement the missing pieces of `Distribution` construction and NumPy interoperability in
`astropy/uncertainty/core.py`, plus the corresponding function-dispatch table entries in
`astropy/uncertainty/function_helpers.py`, so that the existing (untouched) test suites in
`astropy/uncertainty/tests/` pass. No new files, no new public modules, no changes to
`astropy/uncertainty/__init__.py` or `astropy/uncertainty/distributions.py`, and no
changes to the already-implemented members listed in Context. The only expected edit
outside the blanked-out regions is extending the dispatch-table import at `core.py:25`.

### Key Components

- **`Distribution._get_distribution_dtype(dtype, n_samples, itemsize=None)`** (new,
  `core.py`) — a `staticmethod`/`classmethod` that builds the physical structured storage
  dtype described in Context above:
  `np.dtype([("samples", np.dtype([("sample", dtype)]), (n_samples,))])`. Used by the
  already-implemented `dtype` setter and `astype`, and by `__new__`/`view` when they wrap
  sample data.
  - `itemsize`, when given, is the byte size of one *sample slot* and may be larger than
    `np.dtype(dtype).itemsize`; the returned inner struct must be padded to it (e.g.
    `np.dtype({"names": ["sample"], "formats": [dtype], "itemsize": itemsize})`) so that
    the total storage itemsize is `n_samples * itemsize` and the per-sample stride is
    `itemsize`.
  - This padding is load-bearing, not cosmetic: it is the only way to express a samples
    array whose trailing-axis stride exceeds its itemsize as a structured view, which is
    what makes no-copy construction/indexing possible. Concretely, in
    `TestStructuredDistribution.test_getitem` (S17) the already-implemented
    `__getitem__` builds `Distribution(np.moveaxis(self.distribution["a"], ...))` from a
    field view whose sample stride is 40 bytes while its itemsize is 8, and the test
    asserts `np.may_share_memory(d_i, self.d)` — so `__new__` must reach
    `_get_distribution_dtype(dtype, n, itemsize=40)`-equivalent storage rather than
    copying. The same mechanism is what lets the already-implemented `dtype` setter
    (which passes `itemsize=super().dtype["samples"].base.itemsize`) reassign the exposed
    dtype without changing `n_samples` or the buffer size — numpy's in-place `dtype`
    assignment requires the total itemsize to be unchanged. (The `dtype` setter itself is
    not exercised by the oracle tests; see Trade-offs.)

- **`Distribution.n_samples`** (new, `core.py`, property) — the fixed length of the
  trailing sample axis, as an `int`: `self.distribution.shape[-1]`, or equivalently
  `super().dtype["samples"].shape[0]` (the latter also holds for `ScalarDistribution`,
  an `np.void` subclass with no array shape of its own). Used by the existing `dtype`
  setter (`core.py:193`), by `_DistributionRepr` (`core.py:645,650,654,660`), and directly
  by user code/tests (`distr.n_samples`).

- **`Distribution.__new__(cls, samples)`** (new, `core.py`) — per the interface
  docstring below. Must:
  - Accept any input compatible with `numpy.asanyarray`, including a `Distribution`
    instance (unwrap via its `.distribution`, i.e. re-expose the same samples, not
    double-wrap). (No oracle test calls `Distribution(<a Distribution>)` directly — the
    `Quantity` round-trips go through `view`/`np.array(..., subok=True)` instead — so
    implement this defensively; the suite will not catch a mistake here.)
  - Raise `TypeError` (message must match the substring `"Attempted to initialize a
    Distribution with a scalar"`) when the (asanyarray-converted) input has `shape ==
    ()` — a scalar has no axis to use as the sample axis.
  - Pick/build the concrete subclass from the sample-array's class: reuse or populate
    `Distribution._generated_subclasses` (keyed by the sample array's type) so that the
    same sample-array class always maps to the *same* generated `Distribution` subclass
    object (`np.ndarray` → the existing `NdarrayDistribution`; a `Quantity` subclass `Q`
    → a generated class that is simultaneously a `Distribution`, an `ArrayDistribution`,
    and a `Q` — this generated class satisfies `isinstance(x, Q)`, `isinstance(x,
    Distribution)`, and `x.value` reconstructs an `NdarrayDistribution`; see S2/S3
    below). Identity of the generated class matters: `TestBroadcast.test_broadcast_arrays`
    asserts `type(bda) is type(bdb) is type(self.da)`, so wrapping a fresh result array
    must land on the cached class, not a freshly built one.
  - The observable requirement on the generated class is that `repr`/`str`/
    `_repr_latex_` report `n_samples` even for `Quantity` distributions (`test_reprs`,
    S20); the expected route is inheriting `_DistributionRepr` (as `NdarrayDistribution`
    does) so those methods win MRO over `Quantity.__repr__`. Generated classes should
    also set `_samples_cls` to the sample-array class they wrap, mirroring the existing
    `ArrayDistribution._samples_cls = np.ndarray` (nothing in the oracle reads it
    directly, but it is pre-existing scaffolding for exactly this purpose).
  - Take a *view* (not a copy) of the input sample data with the structured storage
    dtype from `_get_distribution_dtype`, sharing memory whenever the trailing axis has
    a safe (non-negative-stride, or single-element-with-zero-stride) layout for
    reinterpretation; copy only when a safe view isn't possible (e.g. negative trailing
    stride). Per the class docstring already in the file (core.py:48-54), "the data will
    not be copied unless it is not possible to take a view (generally, only when the
    strides of the last axis are negative)". This must hold for sample arrays whose
    trailing axis is *not* contiguous — `test_numpy_init_T`/`test_quantity_init_T` pass
    `arr.T`, and S17 asserts memory sharing for a structured field view — which is why
    the storage dtype's sample slot must be padded to the input's trailing stride (see
    `_get_distribution_dtype` above) instead of relying on `ndarray.view(dtype)`.
  - Preserve subclass metadata carried by the sample array itself (e.g. a `Quantity`'s
    `unit`) on the returned object.

- **`Distribution.__array_function__(self, function, types, args, kwargs)`** (new,
  `core.py`) — per the interface docstring below. Dispatch against the
  `function_helpers.py` collections in the same style as
  `astropy/units/quantity.py:1837` (`Quantity.__array_function__`, a working reference in
  this repo):
  1. Function in `DISTRIBUTION_SAFE_FUNCTIONS` → delegate to `super().__array_function__`.
  2. Function in `FUNCTION_HELPERS` → call the helper to get `(args, kwargs, out)`,
     invoke the function on the unwrapped args (helpers convert `Distribution` args to
     their `.distribution` arrays before returning them), then **re-wrap**: an array
     result becomes a new `Distribution` over the trailing sample axis. Invoke it in a
     way that still lets the *samples'* class handle itself — plain `function(*args,
     **kwargs)` re-dispatches normally (no `Distribution` is left in `args`, so there is
     no recursion) and is what lets `Quantity` samples convert units in S10;
     `super().__array_function__(function, types, args, kwargs)`, as `Quantity` does, is
     also acceptable. If `out` is
     truthy, no re-wrapping happens and `out` is returned unchanged — this is the
     convention already documented for `FUNCTION_HELPERS` at `function_helpers.py:51-55`
     ("If ``out`` is set to `True`, then no further processing should be done").
  3. Function in `DISPATCHED_FUNCTIONS` → call the helper, which has already computed the
     **final** result; return it **without** re-wrapping. The committed docstring at
     `function_helpers.py:34-42` says such a helper "should return the result of the
     function". Returning `(result, out)` and honoring the same truthy-`out` convention
     as (2) is equally acceptable, as long as `__array_function__` and the helpers agree
     — what is *not* acceptable is re-wrapping a dispatched result, because that breaks
     S12/S13 (`np.broadcast_arrays` returns a mix in which the plain-array element must
     keep its own type: `type(bdc) is type(self.c)`).
  4. Otherwise → defer to `super().__array_function__` (no warning is required; a
     `UNSUPPORTED_FUNCTIONS` branch returning `NotImplemented` is optional, since that
     set is empty).
  - `NotImplementedError` raised by a helper must be turned into
    `self._not_implemented_or_raise(function, types)` (already implemented at
    `core.py:339-353`), not propagated.
  - Re-wrapping rules (branch 2 only, and shared with `__array_ufunc__`):
    - A plain array/`Quantity` result → `Distribution` of it (its trailing axis is the
      sample axis).
    - A result that is already a `Distribution` → returned unchanged (never double-wrap).
    - A `tuple`/`list` result → each element re-wrapped by these same rules, outer
      container type preserved.
    - A scalar (non-array, non-`Distribution`) result → returned as-is.

- **`Distribution.__array_ufunc__(self, ufunc, method, *inputs, **kwargs)`** (new,
  `core.py`; required by the Acceptance Scenarios below and by every arithmetic test in
  `test_distribution.py`, e.g. `test_add_quantity`, `test_add_distribution`,
  `test_scalar_quantity_distribution`, `test_distr_angle`, `TestComparison`).
  Requirements:
  - Ordinary (non-generalized) ufuncs apply sample-wise: a plain-shaped input (no sample
    axis) broadcasts against every sample of a `Distribution` input; two `Distribution`
    inputs combine sample-by-sample at the same index. Mechanically this means replacing
    each `Distribution` input by its `.distribution` and each non-`Distribution` input by
    `np.asanyarray(input)[..., np.newaxis]` before delegating (note Python/NumPy scalars
    such as the `50` in `d > 50` and the `-1.0` in `*= -1.0` must survive this step),
    then re-wrapping.
  - Delegation must preserve the samples' *own* array behavior, because the samples may
    be `Quantity`/`Quantity` subclasses: unit conversion, unit-driven class decay and
    unit errors all have to come from the samples' `__array_ufunc__`, not be
    re-implemented here (S5 adds kpc and pc distributions; S9 requires `Angle + Angle`
    → `Angle` but `Angle * Angle` → plain `Quantity`, and `ad *= ad` → `u.UnitTypeError`).
  - `out=`: an explicit output must be forwarded as the *unwrapped* samples array of the
    `out` Distribution (so the underlying implementation writes into the shared buffer
    and, for `Quantity` samples, `Quantity.check_output` can reject an impossible unit
    conversion), and the original `out` object is what gets returned. This is what makes
    the in-place cases in S9 (`ad += ad` stays an `Angle` distribution; `ad *= ad` raises
    `u.UnitTypeError`) and S19 (`d[d > 50] *= -1.0`) work.
  - `method="reduce"` called *without* an explicit `axis` (NumPy's default of reducing
    over all axes) must reduce over all of the Distribution's *logical* axes while still
    producing a `Distribution` — the hidden sample axis must never be included in, or
    destroyed by, the reduction. Oracle: `np.min(p_dist)` in S21. An explicit `axis`
    (including negative values) must likewise be interpreted against the logical shape.
  - Comparisons (`__eq__`/`__ne__` at `core.py:362-370`) already forward to
    `np.equal`/`np.not_equal` and rely on this method; do not special-case them here.
    Comparison results are `Distribution`s of booleans (S27), and deferral to an operand
    with `__array_ufunc__ = None` must keep working (S24) — in particular, do not define
    `__lt__`/`__gt__`/etc. on `Distribution`, since `ndarray`'s own binop override
    already returns `NotImplemented` in that case.
  - Results follow the same array→`Distribution` wrapping / scalar passthrough /
    explicit-`out` rules as `__array_function__` above.
  - Generalized ufuncs (ones with a core-dimension signature, e.g. `np.matmul`) must
    keep the sample axis "outside" the signature's core dimensions — i.e. the ufunc
    operates per-sample, not across samples. `_parse_gufunc_signature` (imported at
    `core.py:17/20`) identifies the core dimensions.
  - An explicit `axes=` keyword on a generalized ufunc call is not supported: raise
    `NotImplementedError` (deliberately *not* routed through
    `_not_implemented_or_raise` — it is a hard "we don't support this" case, not a
    "maybe someone else does" case).
  - **Coverage note:** the two gufunc bullets above (and `method` values other than
    `"__call__"`/`"reduce"`, e.g. `"accumulate"`/`"at"`/`"outer"`) are *not* exercised by
    the oracle suite; see Trade-offs. Implement them, but expect no test to fail if they
    are wrong — a reviewer must read them.

- **`ArrayDistribution.view(self, dtype=None, type=None)`** (new, `core.py`, replacing
  the blank body at `core.py:528-591`) — per the interface docstring below. It must
  accept the same argument spellings `numpy.ndarray.view` does, i.e. `view()`,
  `view(dtype)`, `view(type)` (a class passed as the first positional argument),
  `view(dtype, type)`, and keyword forms; `test_distr_angle_view_as_quantity` uses
  `ad.view(u.Quantity)`, `ad.view(qd.__class__)` and `ad.view(qd.dtype, qd.__class__)`,
  and `test_distr_cannot_view_new_dtype` uses `ad.view("2i8", distr.__class__)`.
  - **Type handling.** The result is always a `Distribution` instance (never a bare
    `ndarray`/`Quantity`). When the requested `type` is a non-`Distribution`
    `ndarray` subclass `C`, return an instance of the generated `Distribution` subclass
    for `C` (reusing `Distribution._generated_subclasses`/the same machinery as
    `__new__`). This is what makes `Quantity.value` (internally `self.view(np.ndarray)`)
    return an `NdarrayDistribution` (S2), what makes `ad.view(u.Quantity)` decay `Angle`
    → `Quantity` while staying a `Distribution` (S16), and what makes
    `Quantity._new_view` — and therefore `.to()`/`.to_value()` (S28) — work, since it
    ends in `obj.view(quantity_subclass)`.
  - When `type` is *already* a `Distribution` subclass, return an instance of it
    directly (`ad.view(qd.__class__)` must give the plain `Quantity` distribution class,
    S16). Restricting that path to `dtype is None or dtype == self.dtype` is a
    reasonable reading but is **not** oracle-covered except via the error case below;
    see Trade-offs.
  - **A no-argument `.view()`** returns a new object of the same class sharing memory
    (`qd4.__class__ is qd3.__class__` and `np.may_share_memory(qd4, qd3)`, S16).
  - **Dtype handling.** `dtype` refers to the *exposed* (user-facing) dtype, never the
    structured storage dtype. The required, test-pinned outcomes are:
    - Same itemsize as the current exposed dtype: the new dtype's sub-array dimensions
      (if any) are appended to the *logical* shape, `n_samples` is unchanged, and memory
      is shared. `Distribution([2.0j, 3.0, 4.0j]).view("2f8")` (logical shape `()`,
      `c16`, 3 samples) → logical shape `(2,)` with
      `.distribution == np.moveaxis(orig.distribution.view("2f8"), -2, -1)`;
      a `(2,)`-shaped `u4` distribution `.view("4u1")` → logical shape `(2, 4)`
      (S14/S15).
    - Larger itemsize that exactly consumes the trailing logical axis
      (`shape[-1] * self.dtype.itemsize == np.dtype(dtype).itemsize`): that axis is
      **dropped**, not left as a size-1 axis. `uint8.view("u4")` must give logical shape
      `(2,)` with `.distribution` *equal in shape and value* to the original `(2, 2)`
      samples array, and `r.view("c16")` must give logical shape `()`. This is the main
      trap in this method: `numpy.ndarray.view` leaves a trailing axis of size 1 in this
      situation, and `assert_array_equal` compares shapes strictly, so a `(2, 1)`
      logical shape fails S14/S15.
    - No logical axis available to supply the extra bytes (`self.ndim == 0`, e.g.
      `Distribution([2.0, 3.0, 4.0]).view(np.dtype("2i8"))`): `ValueError` whose message
      contains `"can only be viewed"`. The same message is required when a
      `Distribution` subclass is passed as `type` alongside such a dtype
      (`distr.view(np.dtype("2i8"), distr.__class__)`, `ad.view("2i8", distr.__class__)`)
      and for the `Angle` case `ad.view(np.dtype("2i8"))` (S23).
    - Trailing logical axis not contiguous (e.g. the transpose of the `"4u1"` view
      above): `ValueError` whose message contains `"last axis must be contiguous"`
      (S15). Check this *before* the itemsize-relation check, so that
      `uint8.T.view("u4")` reports contiguity rather than `"can only be viewed"`.
    - Mechanism hint: for the same-itemsize case,
      `Distribution(np.moveaxis(self.distribution.view(dtype), -2, -1))` produces exactly
      the shapes the tests expect (given the padded storage from `__new__`). For the
      itemsize-changing case, move the sample axis off the last position before letting
      numpy view the samples — then numpy's own checks apply to the *logical* last axis
      and produce the `"last axis must be contiguous"` message verbatim.
    - Itemsize relations other than the two above (non-exact growth such as a
      `(2, 8)`-shaped `u1` distribution viewed as `u4`, or shrinking to a non-sub-array
      dtype) are **unspecified** by this contract and untested: the trailing logical
      axis lives *inside* one sample slot, so partial consumption would interleave
      samples. Raising `ValueError("... can only be viewed ...")` for them is the
      recommended default.

- **`Distribution.pdf_median(self, out=None)`** (new, `core.py`, replacing a blank body
  among the other `pdf_*` methods) — `np.median(self.distribution, axis=-1, out=out)`,
  returning the samples' array/Quantity type (not a `Distribution`) with one fewer
  dimension, matching `pdf_mean`'s existing pattern at `core.py:379-386`.

- **`Distribution.pdf_std(self, dtype=None, out=None, ddof=0)`** (new, `core.py`) —
  `self.distribution.std(axis=-1, dtype=dtype, out=out, ddof=ddof)`, mirroring the
  already-implemented `pdf_var` at `core.py:395-401`.

- **`function_helpers.py` dispatch-table entries** (new) — populate
  `DISTRIBUTION_SAFE_FUNCTIONS`/`FUNCTION_HELPERS`/`DISPATCHED_FUNCTIONS` (using the
  `function_helper`/`dispatched_function` `FunctionAssigner` decorators already defined
  at `function_helpers.py:71-72`) for at least:
  - `numpy.empty_like` — preserve the `Distribution` subclass and its `n_samples` on the
    output, while honoring an explicitly requested `dtype` (interpreted as the *exposed*
    dtype, so the storage dtype is `_get_distribution_dtype(dtype, n_samples)`).
    **Not exercised by the oracle suite** — include it (it is listed here for parity with
    how `Quantity` treats `np.empty_like`, and because an unhelped `np.empty_like` would
    hand back the raw structured dtype), but verify it by hand:
    `np.empty_like(da).shape == da.shape`, `np.empty_like(da).n_samples == da.n_samples`,
    `type(np.empty_like(da)) is type(da)`, and
    `np.empty_like(da, dtype="f4").dtype == np.dtype("f4")`.
  - `numpy.broadcast_to` — broadcast a `Distribution`'s *logical* shape (excluding the
    hidden sample axis) to the requested shape, keeping the sample count and following
    `subok` for the type of the result (see `TestBroadcast.test_broadcast_to`).
  - `numpy.broadcast_arrays` — broadcast a mix of `Distribution` and plain-array
    arguments against each other's logical shapes; a plain array argument keeps its own
    type in the result (not promoted to `Distribution`), and `subok=False` decays every
    `Distribution` result's `.distribution` (and any plain-array result) to a base
    `ndarray` (see `TestBroadcast.test_broadcast_arrays[_subok_false]`).
  - `numpy.concatenate` — resolve the common sample count across every `Distribution`
    argument; broadcast plain-array arguments to that sample count along a new trailing
    axis, as if they were single-sample distributions; interpret `axis` against the
    logical (sample-axis-excluded) shape (normalize negatives against the logical
    `ndim`); and let the *samples'* own type handle units, so that concatenating an `m`
    distribution with a `km` one converts correctly
    (`TestQuantityDistributionConcatenation`). Oracle:
    `TestConcatenation.test_concatenate` and `test_concatenate_not_all_distribution`.
    A supplied `out=` is accepted only when it is itself a `Distribution` (otherwise
    raise `NotImplementedError` per the module's documented convention); **the `out=`
    path is not oracle-covered.** Mirror the numpy signature of the installed numpy —
    `arrays` became positional-only in numpy 2.4, which is why
    `astropy/units/quantity_helper/function_helpers.py:482-501` defines the helper twice
    behind `NUMPY_LT_2_4`.
  - Every helper must follow the module's committed docstrings: `FUNCTION_HELPERS`
    entries return `(args, kwargs, out)` (`function_helpers.py:45-60`) and
    `DISPATCHED_FUNCTIONS` entries return the final result
    (`function_helpers.py:34-42`; returning `(result, out)` is fine too if
    `__array_function__` unpacks it that way — see the `__array_function__` bullet). Do
    not edit those docstrings. Every helper must raise `NotImplementedError` when an
    argument breaks the Distribution/non-Distribution expectation, so
    `Distribution.__array_function__` can convert that into
    `_not_implemented_or_raise`.

### Data Flow

1. A caller does `Distribution(samples)` (directly, or via `distributions.normal`/
   `poisson`/`uniform`, or via `Distribution.__array_function__`/`__array_ufunc__`
   producing a new result). `__new__` normalizes `samples` to an array-like, validates
   it isn't scalar, resolves/creates the matching generated subclass, and returns a view
   with the structured storage dtype.
2. Downstream NumPy calls (`np.mean(d)`, `d + other`, `np.concatenate((d1, d2))`, …) hit
   `__array_function__`/`__array_ufunc__` on the `Distribution` object because it is
   listed among `types`. Both methods normalize inputs (unwrap `.distribution`, apply
   any needed axis bookkeeping), delegate to the real NumPy implementation on the
   unwrapped samples (so `Quantity` samples still do their own unit handling), and
   re-wrap array results as new `Distribution` instances of the correct sample count —
   except for `DISPATCHED_FUNCTIONS` results and explicit `out=` arguments, which are
   already final.
3. `pdf_*` methods (`pdf_mean`, `pdf_median`, `pdf_std`, `pdf_var`, `pdf_mad`,
   `pdf_smad`, `pdf_percentiles`, `pdf_histogram`) read `self.distribution` directly and
   reduce over `axis=-1`, returning plain arrays/`Quantity` (never `Distribution`).
4. `ArrayDistribution.__getitem__`/`__setitem__` (already implemented) rely on
   `self.distribution`/`self["samples"]` behaving per the storage-dtype contract from
   `__new__`/`_get_distribution_dtype` to slice/assign correctly, including moving the
   sample axis to stay trailing after structured-field indexing.

### Interface Contract

```python
# astropy/uncertainty/core.py

class Distribution:
    _generated_subclasses = {}

    @staticmethod
    def _get_distribution_dtype(dtype, n_samples, itemsize=None): ...
        # returns np.dtype([("samples", np.dtype([("sample", dtype)]), (n_samples,))])
        # itemsize, if given, is the per-sample slot size: the inner one-field
        # struct is padded to it, so total itemsize == n_samples * itemsize.

    @property
    def n_samples(self): ...
        # -> int, the fixed trailing sample-axis length

    def __new__(cls, samples): ...
        # TypeError("Attempted to initialize a Distribution with a scalar ...")
        # if np.asanyarray(samples).shape == ()
        # NB: distributions.py calls cls(samples, **kwargs) with any extra
        # user keywords; no oracle test passes extras, so accepting only
        # `samples` is sufficient.

    def __array_function__(self, function, types, args, kwargs): ...
        # dispatch via DISTRIBUTION_SAFE_FUNCTIONS / FUNCTION_HELPERS /
        # DISPATCHED_FUNCTIONS / fallback to super(), as in
        # astropy/units/quantity.py Quantity.__array_function__ (line 1837).
        # FUNCTION_HELPERS results are re-wrapped as Distribution (unless the
        # helper signalled `out`); DISPATCHED_FUNCTIONS results are final and
        # returned as-is.

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs): ...
        # sample-wise application, delegating to the samples' own
        # __array_ufunc__ so units/subclass decay/unit errors come from there;
        # `out` forwarded as the out Distribution's samples, `out` returned;
        # axis-free reduce over all logical axes; gufunc core dims preserved
        # around the sample axis; NotImplementedError if `axes` is given.

    def pdf_median(self, out=None): ...
        # np.median(self.distribution, axis=-1, out=out)

    def pdf_std(self, dtype=None, out=None, ddof=0): ...
        # self.distribution.std(axis=-1, dtype=dtype, out=out, ddof=ddof)


class ArrayDistribution(Distribution, np.ndarray):
    _samples_cls = np.ndarray

    def view(self, dtype=None, type=None): ...
        # accepts view(), view(dtype), view(type), view(dtype, type);
        # always returns a Distribution;
        # ValueError("... can only be viewed ...") when the new dtype's itemsize
        #   cannot be supplied by consuming the trailing logical axis;
        # ValueError("... last axis must be contiguous ...") when that axis is
        #   not contiguous
```

```python
# astropy/uncertainty/function_helpers.py

@function_helper
def concatenate(arrays, axis=0, out=None, **kwargs):
    # (arrays is positional-only for numpy >= 2.4)
    ...
    return args, kwargs, out  # NotImplementedError if incompatible

@function_helper
def broadcast_to(array, shape, subok=False): ...
    return args, kwargs, out

@dispatched_function
def broadcast_arrays(*args, subok=False): ...
    return result  # final: a list/tuple mixing Distribution and plain arrays

@dispatched_function
def empty_like(prototype, dtype=None, ...): ...
    return result  # final
```

(Exact parameter lists and the choice between `function_helper` and
`dispatched_function` are an implementation choice; what is fixed by this spec is (a)
the externally observable behavior in the Acceptance Scenarios below and (b) that a
`FUNCTION_HELPERS` result is re-wrapped as a `Distribution` while a
`DISPATCHED_FUNCTIONS` result is returned untouched. `np.broadcast_arrays` in
particular *must* be dispatched (or otherwise flagged as final), because its result
mixes `Distribution` and plain-array elements that re-wrapping would corrupt — see
S12/S13.)

## Alternatives Considered

### Store samples as a trailing real ndarray axis instead of a structured dtype field

Simpler conceptually (no custom dtype machinery), but incompatible with the
already-implemented, must-not-change code: `Distribution.distribution`,
`__getitem__`, `__setitem__`, and the `dtype` property/setter all assume a structured
`"samples"`/`"sample"` field dtype (see Context). Changing that would require rewriting
working code outside this task's scope. Not chosen.

### Give `Distribution` its own bespoke ufunc/function dispatch scheme unrelated to `Quantity`'s

`astropy/units/quantity.py` and `astropy/units/quantity_helper/function_helpers.py`
already solve the "wrap NumPy protocol, unwrap args, rewrap array results, dict-of-
dicts dispatch table" problem in this exact codebase, using the same `FunctionAssigner`
`function_helpers.py` already imports. Reusing that shape minimizes surprising,
one-off design and matches the docstrings already committed to `function_helpers.py`.
Chosen as the reference pattern (not copied verbatim, since Distribution has no "unit"
concept — its `FUNCTION_HELPERS` contract is `(args, kwargs, out)` and its
`DISPATCHED_FUNCTIONS` helpers return an already-final result, rather than `Quantity`'s
`(args, kwargs, unit, out)` / `(result, unit, out)` where `unit is None` is the signal
not to re-wrap).

## Acceptance Scenarios

The primary oracle for this feature is the **existing, unmodified** test suite at
`astropy/uncertainty/tests/test_distribution.py` and
`astropy/uncertainty/tests/test_functions.py`. Every scenario below names the concrete
test(s) that already encode it — running
`pytest astropy/uncertainty/tests/test_distribution.py astropy/uncertainty/tests/test_functions.py`
must show all of them passing (no skips other than the pre-existing
`pytest.mark.skipif(not HAS_SCIPY, ...)` / `pytest.skip("distribution stretch goal ...")`
markers already in the file, which are out of scope for this task).

### Happy Path
- **S1:** Given a plain NumPy array of shape `(n0, n1)`, when `Distribution(arr)` is
  called, then it succeeds and produces an `NdarrayDistribution` whose *logical* shape
  drops the trailing axis: for the `(4, 10000)` array in
  `TestDistributionStatistics`, `.shape == (4,)`, `.size == 4`, `.n_samples == 10000`,
  `.distribution.shape == (4, 10000)` and `.distribution.size == 40000`
  (`TestDistributionStatistics.test_shape`/`test_size`/`test_n_samples`/`test_n_distr`).
  Construction must also succeed for a `(4, 1000)` array and for one whose trailing axis
  is non-contiguous, i.e. `arr_t.T` (`TestInit.test_numpy_init`,
  `TestInit.test_numpy_init_T`, which assert only that the call does not raise).
- **S2:** Given a `Quantity` array `pq = parr << u.ct`, when `Distribution(pq)` is
  called, then the result `pqd` is simultaneously an instance of `u.Quantity` and
  `Distribution`, `pqd.value` is itself a `Distribution` (an `NdarrayDistribution`), and
  `pqd.value.distribution` equals `parr` (`TestInit.test_quantity_init`;
  `test_quantity_init_T` additionally requires it for a non-contiguous trailing axis).
  Note `Quantity.value` is implemented as `self.view(np.ndarray)`, so this scenario is
  a requirement on `ArrayDistribution.view`'s type handling as much as on `__new__`.
- **S3:** Given an existing integer-dtype `Distribution` `pd`, when `pd << u.ct` is
  evaluated, then the result is a `Distribution`+`Quantity` with unit `u.ct` and
  `.value.distribution` equal to `pd.distribution.astype(float)`
  (`TestInit.test_quantity_init_with_distribution`). Mechanically this goes through
  `Quantity.__new__` → `Distribution.astype(float)` (already implemented, and hence
  through `_get_distribution_dtype`) → `view(<Quantity subclass>)`, *not* through
  `Distribution.__new__`.
- **S4:** Given `distr = Distribution(data * u.kpc)` built from a `(4, 10000)`-shaped
  array, when `distr.pdf_mean()`, `distr.pdf_median()`, `distr.pdf_std()`,
  `distr.pdf_var()` are called, then each returns a plain `Quantity` (not a
  `Distribution`) of shape `(4,)` matching `np.mean/median/std/var(data, axis=-1)` within
  tolerance (`pdf_var`'s unit being `kpc**2`); each accepts an `out=` argument that is
  returned **by identity** (`result is out`) and filled with the correct values; and
  `pdf_std`/`pdf_var` honor `ddof=1` (checked together with `out=`)
  (`TestDistributionStatistics.test_pdf_mean/_median/_std/_var`). With scipy installed,
  `pdf_mad`/`pdf_smad` (already implemented, but dependent on the new `pdf_median` and on
  `np.abs(self - median)` dispatch) must satisfy the same type/`out` rules
  (`test_pdf_mad_smad`).
- **S5:** Given the kpc `Distribution` above, when `distr + [2000, 0, 0, 500] * u.pc` is
  evaluated (a plain `Quantity` in a *different but compatible* unit) or when it is added
  to another `Distribution` whose samples are in `pc`, then the result is a new
  `Distribution` whose `pdf_median()`/`pdf_var()` match the elementwise sum of the
  underlying sample arrays after unit conversion — i.e. the unit handling comes from the
  samples, and the sample axis is not broadcast against the plain operand's last axis
  (`TestDistributionStatistics.test_add_quantity`, `test_add_distribution`).
- **S6:** Given `ds.normal(center, std=..., n_samples=100)` /
  `ds.poisson(center, n_samples=100)` / `ds.uniform(lower=..., upper=..., n_samples=1000)`
  (already-implemented helpers that call `cls(samples, **kwargs)`), when each is called,
  then it returns a working `Distribution` with the requested shape and
  `n_samples`, and the built-in statistics (`pdf_std`, `pdf_mean`, sample min/max) are
  consistent with the requested distribution parameters (`test_helper_normal_samples`,
  `test_helper_poisson_samples`, `test_helper_uniform_samples`).
- **S7:** Given a `Distribution` of logical shape `(2,)` — built either from a
  `(2, 1000)` array/`Quantity` or via `ds.normal(center=[1, 2], std=[3, 4],
  n_samples=1000)` — when it is unpacked directly (`d1, d2 = distr`, i.e. iteration
  through integer `__getitem__`), then each element is itself a `Distribution` (a
  `ScalarDistribution`, since `super().__getitem__` yields an `np.void` that the
  already-implemented `__getitem__` re-views) (`test_index_assignment_quantity`,
  `test_index_assignment_array`).
- **S8:** Given `np.sin(Distribution([90.0, 30.0, 0.0] * u.deg))`, when evaluated, then
  the result is a `Distribution` and a `Quantity`, and equals
  `Distribution(np.sin([90.0, 30.0, 0.0] * u.deg))`
  (`test_scalar_quantity_distribution` — a ufunc-dispatch regression test).
- **S9:** Given `ad = Angle(Distribution([2.0, 3.0, 4.0]), "deg")` (constructing a
  `Quantity` subclass *from* a `Distribution`, which reaches
  `ArrayDistribution.view(Angle)`), then:
  - `ad + ad` is both an `Angle` and a `Distribution`;
  - `ad * ad` is a `Distribution` and a `u.Quantity` but **not** an `Angle` (the
    resulting `deg2` unit forces the subclass to decay);
  - `ad += ad` leaves `ad` an `Angle`+`Distribution` whose `.distribution` equals that of
    `ad + ad` (so the in-place ufunc must write through to the samples buffer);
  - `ad *= ad` raises `u.UnitTypeError` (the unit error must propagate out of the
    samples' `__array_ufunc__`/`check_output`, not be swallowed)
  (`test_distr_angle`).
- **Fixture for S10-S13** (`test_functions.py::ArraySetup`): raw samples
  `a` of shape `(2, 3, 4)` → `da = Distribution(a)` with logical shape `(2, 3)` and
  `n_samples == 4`; raw samples `b` of shape `(3, 4)` → `db` with logical shape `(3,)`
  and `n_samples == 4`; plus a plain array `c` of shape `(2, 1)` (no sample axis). The
  `QuantitySetup` subclasses re-run every case with `a`/`da` in `m`, `b`/`db` in `km`
  and `c` in `Mm`. Units behave differently per function: `concatenate` must let the
  samples *convert* (the result takes the first argument's unit, exactly as
  `np.concatenate` on plain `Quantity` arrays does), while `broadcast_to`/
  `broadcast_arrays` must leave each argument's unit **unchanged** — S12 asserts
  `bdb.distribution == np.broadcast_arrays(a, b, subok=True)[1]`, which is still in
  `km`.
- **S10 (concatenate):** Given the fixture above, when
  `np.concatenate((da, db[np.newaxis]), axis=0)` is called, then the result is a
  `Distribution` of logical shape `(3, 3)` whose `.distribution` equals
  `np.concatenate((a, b[np.newaxis]), axis=0)` — i.e. the logical `axis=0` maps to raw
  axis 0 and the trailing sample axis is untouched
  (`TestConcatenation.test_concatenate`, and the `Quantity` variant
  `TestQuantityDistributionConcatenation`, where `km` samples are converted to `m`).
- **S11 (concatenate, mixed types):** Given the fixture above, when
  `np.concatenate((c, da), axis=1)` is called (a plain `(2, 1)` array first, a
  `Distribution` second), then the result is a `Distribution` of logical shape `(2, 4)`
  whose `.distribution` equals
  `np.concatenate((np.broadcast_to(c[..., np.newaxis], c.shape + (da.n_samples,), subok=True), a), axis=1)`
  — the plain argument is broadcast across the resolved sample count along a new
  trailing axis (`TestConcatenation.test_concatenate_not_all_distribution`).
- **S12 (broadcast_to / broadcast_arrays):** Given the fixture above, when
  `np.broadcast_to(db, da.shape, subok=True)` is called, then the result has logical
  shape `(2, 3)` and `.distribution` equal to `np.broadcast_to(b, a.shape, subok=True)`;
  and when `np.broadcast_arrays(da, db, c, subok=True)` is called, then
  `type(bda) is type(bdb) is type(da)` (the same generated subclass object),
  `type(bdc) is type(c)` (the plain argument is **not** promoted to a `Distribution`),
  `bda.distribution`/`bdb.distribution` equal `np.broadcast_arrays(a, b, subok=True)`,
  and `bdc` equals `np.broadcast_to(c, da.shape, subok=True)` (logical shape `(2, 3)`,
  no sample axis) (`TestBroadcast.test_broadcast_to`/`test_broadcast_arrays`, and the
  `Quantity` variants).
- **S13 (broadcast_arrays, subok=False):** Given the same inputs as S12, when
  `np.broadcast_arrays(da, db, c, subok=False)` is called, then the `Distribution`
  results remain `Distribution`s but their samples decay to the base class
  (`type(bda.distribution) is type(bdb.distribution) is np.ndarray`), the plain argument
  decays too (`type(bdc) is np.ndarray`), and the values match the `subok=False` numpy
  results (`TestBroadcast.test_broadcast_arrays_subok_false`). I.e. `subok` controls the
  *samples'* class, never whether the result is a `Distribution`.

### Edge Cases
- **S14:** Given `c = Distribution([2.0j, 3.0, 4.0j])` (`c16`, logical shape `()`,
  `n_samples == 3`), when `r = c.view("2f8")` is called, then `r.shape == c.shape + (2,)`
  (i.e. `(2,)`), `np.may_share_memory(r, c)` holds, and
  `r.distribution == np.moveaxis(c.distribution.view("2f8"), -2, -1)`; and when
  `c2 = r.view("c16")` is called, then `c2.distribution` equals `c.distribution` **with
  the same shape `(3,)`** (so `c2`'s logical shape is `()` — the consumed trailing axis
  is gone, not left as size 1) and `np.may_share_memory(c2, c)` holds
  (`test_distr_view_different_dtype1`).
- **S15:** Given `uint32 = Distribution(np.array([[...], [...]], dtype="u4"))` of logical
  shape `(2,)` with `n_samples == 2`, when `uint8 = uint32.view("4u1")` is called, then
  `uint8.shape == uint32.shape + (4,)`, `np.may_share_memory(uint8, uint32)` holds, and
  `uint8.distribution == np.moveaxis(uint32.distribution.view("4u1"), -2, -1)`; when
  `uint8.view("u4")` is called, then it shares memory with `uint32` and its
  `.distribution` equals `uint32.distribution` **with the same shape `(2, 2)`** (logical
  shape back to `(2,)`); and when `uint8.T.view("u4")` is called, then it raises
  `ValueError` matching `r"last axis must be contiguous"`
  (`test_distr_view_different_dtype2`).
- **S16:** Given `ad = Angle(Distribution([2.0,3.0,4.0]), "deg")`, then
  `qd = ad.view(u.Quantity)` is a `Distribution` and a `u.Quantity` but not an `Angle`;
  `ad.view(qd.__class__)` and `ad.view(qd.dtype, qd.__class__)` (i.e. passing the
  already-generated `Distribution`-`Quantity` class, with and without an explicit
  unchanged dtype) each give a non-`Angle` `Quantity`+`Distribution` with
  `.distribution` equal to `qd.distribution`; and a no-argument `qd3.view()` returns an
  object of exactly the same class that shares memory with `qd3`
  (`test_distr_angle_view_as_quantity`).
- **S17:** Given `d = Distribution(data)` where `data` has the structured dtype
  `[("a","f8"), ("b","(2,2)f8")]` and shape `(3, 4, 5)` (so `d.shape == (3, 4)` and
  `d.n_samples == 5`, per `TestStructuredAdvancedIndex.test_init`), when it is indexed by
  field name (`d["a"]`, `d["b"]`) or by index/slice (`d[-2]`, `d[1:3]`), then the result
  is a `Distribution` with `d_i.shape == d.shape + dtype[item].shape` for field names,
  its `.distribution` equals `np.moveaxis(data[item], d.ndim, -1)` (sample axis pushed
  back to the end past the field's own sub-shape), and `np.may_share_memory(d_i, d)`
  holds — the field view's sample stride exceeds its itemsize, so this only works with
  padded storage (`TestStructuredDistribution.test_getitem`, plus
  `test_setitem_index_slice`/`test_setitem_field`, and the `Quantity` variant
  `TestStructuredQuantityDistribution`).
- **S18:** Given `d = Distribution(np.arange(60.0).reshape(3, 4, 5))` (logical shape
  `(3, 4)`, 5 samples) and a pair-of-integer-arrays advanced index `item`, when `d[item]`
  is evaluated then `v.shape == item[0].shape` and `v.distribution` equals
  `raw_samples[item]`; when `d[item] = 0.0` or `d[item] = d[item]` (assigning a
  `Distribution` value) is executed, the samples match the same operation applied to the
  raw array; and out-of-range/malformed advanced indices (`([0, 4],)`,
  `([0], [0], [0])`) raise `IndexError` (`TestGetSetItemAdvancedIndex`, plus the
  `Quantity` and structured-dtype variants).
- **S19:** Given `d = Distribution([90.0, 30.0, 0.0])` (logical shape `()`, 3 samples),
  when `d[d > 50] = 0.0` is executed then `d == Distribution([0.0, 30.0, 0.0])`, and when
  `d[d > 50] *= -1.0` is executed then `d == Distribution([-90.0, 30.0, 0.0])` — i.e.
  boolean-mask indexing with a `Distribution` mask selects *samples* and the read/modify/
  write cycle lands back in the original buffer (`TestSetItemWithSelection`).
- **S20:** Given `darr = np.arange(30).reshape(3, 10)` and `distr =
  Distribution(darr * u.kpc)`, when `repr(distr)`, `str(distr)`, and
  `distr._repr_latex_()` are evaluated, then each contains `n_samples=10` (or the LaTeX
  equivalent `n_{\rm samp}=10`) (`test_reprs`).
- **S21:** Given `p_dist = ds.poisson([1, 5, 30, 400] * u.count, n_samples=100)`
  (logical shape `(4,)`), when `p_min = np.min(p_dist)` is evaluated (a whole-array
  reduction with no `axis`), then `isinstance(p_min, Distribution)` and
  `p_min.shape == ()` — the logical axis is reduced away while the sample axis survives —
  and `np.all(p_min >= 0)` is true (`test_helper_poisson_samples`). Whether `p_min` is a
  0-d array distribution or a `ScalarDistribution` void is unspecified; only
  `isinstance`, `.shape` and the comparison are required.

### Error Scenarios
- **S22:** Given a 0-d input, e.g. `parr.ravel()[0]`, when `Distribution(...)` is called
  on it, then it raises `TypeError` matching `r"Attempted to initialize a Distribution
  with a scalar"` (`test_init_scalar`).
- **S23:** Given `distr = Distribution([2.0, 3.0, 4.0])` (logical shape `()`, so there
  is no logical axis that could supply the extra bytes), then each of
  `distr.view(np.dtype("2i8"))`, `distr.view(np.dtype("2i8"), distr.__class__)`,
  `ad.view(np.dtype("2i8"))` and `ad.view("2i8", distr.__class__)` (where
  `ad = Angle(distr, "deg")`) raises `ValueError` matching `r"can only be viewed"` — note
  the message is required on the `type=<Distribution subclass>` paths too
  (`test_distr_cannot_view_new_dtype`).
- **S24:** Given a `Distribution` and an object that opts out of the ufunc protocol
  (`__array_ufunc__ = None`), when they are compared with `==`, `!=` or `>`, then the
  `Distribution` side defers so Python falls back to the other object's
  `__eq__`/`__ne__`/`__lt__` (the test asserts the result is the string `"eq"`/`"ne"`/
  `"gt"` returned by that object). `__eq__`/`__ne__` (already implemented) handle the
  first two; for `>` this means `Distribution` must **not** define its own rich
  comparisons, so `ndarray`'s binop override keeps returning `NotImplemented`
  (`TestComparison.test_distribution_comparison_defers_correctly`).
- **S25:** Given a helper that raises `NotImplementedError` for its arguments, when the
  call also involves a plain (non-`Distribution`) `ndarray`/`ndarray`-subclass in
  `types`, then `Distribution._not_implemented_or_raise` (already implemented at
  `core.py:339-353`) raises `TypeError` rather than returning `NotImplemented`. The
  requirement on new code is only the *routing*: helpers raise `NotImplementedError`,
  and `__array_function__` converts it via `_not_implemented_or_raise`. **No oracle test
  reaches this path** (every helped function in the suite is used compatibly), so verify
  it by reading the code or with an ad-hoc call such as
  `np.concatenate((da, db), out=np.empty(...))`.
- **S26:** Given a generalized ufunc call with an explicit `axes=` keyword against a
  `Distribution` input, when invoked, then `Distribution.__array_ufunc__` raises
  `NotImplementedError` rather than attempting (and silently mis-handling) axis
  reinterpretation. **Not oracle-covered** (the suite calls no gufunc); verify by hand,
  e.g. `np.matmul(d, d, axes=[(-2, -1), (-2, -1), (-2, -1)])` on a 2-D-logical
  distribution.

### Additional Scenarios

- **S27 (comparisons produce distributions):** Given `d = Distribution([90.0, 30.0, 0.0])`
  (logical shape `()`, 3 samples), when `d == 0.0`, `d != 0.0` or `d > 50` is evaluated,
  then the result is a `Distribution` of booleans equal to
  `Distribution(op(d.distribution, 0.0))`
  (`TestComparison.test_distribution_can_be_compared_to_non_distribution`). This also
  pins that `assert_array_equal` between two `Distribution`s works, which the whole
  suite relies on. Caution when self-checking: such an assertion compares two structured
  arrays and then reduces the boolean `Distribution` result, so it is not obviously a
  strict element-wise check — when verifying your own work, compare the `.distribution`
  arrays (and shapes) directly rather than relying on
  `assert_array_equal(d1, d2)` alone.
- **S28 (unit conversion round trips):** Given `distr = ds.normal(10 * u.cm,
  n_samples=100, std=1 * u.cm)`, when `distr.to(u.m)` and `distr.to_value(u.m)` are
  called, then each result is still a `Distribution` (a `Quantity` one for `to`, an
  `NdarrayDistribution` for `to_value`) whose `pdf_mean()` matches
  `distr.pdf_mean()` converted to metres; and given a unitless distribution
  `ds.normal(10, n_samples=100, std=1)`, `.to(u.m)`/`.to_value(u.m)` raise
  `AttributeError` (`test_distr_to`, `test_distr_to_value`, `test_distr_noq_to`,
  `test_distr_noq_to_value`). Mechanically these go through `Quantity._new_view` →
  `np.array(..., subok=True)` → `.view(<Quantity subclass>)`, i.e. the same `view` type
  rule as S2/S16.
- **S29 (structured dtype plus structured unit):** Given `data` with dtype
  `[("a","f8"), ("b","(2,2)f8")]` and shape `(3, 4, 5)`, when
  `Distribution(data << u.Unit("km, m"))` is called, then the result has
  `.unit == u.Unit("km, m")`, `.distribution` equal to that structured `Quantity`, and
  `.value.distribution` equal to the raw structured array; and when `d << u.Unit("km, m")`
  is applied to an existing structured `Distribution`, the result carries the same unit
  (`TestStructuredQuantityDistributionInit`).
- **S30 (1-D input / scalar centre):** Given a 1-D samples array (e.g. from
  `ds.normal(center=0, std=2, n_samples=100)`, `ds.uniform(lower=0, upper=2,
  n_samples=100)`, `ds.poisson(center=2, n_samples=100)`, with or without units), when
  the `Distribution` is created, then its logical shape is `()` and
  `.n_samples == 100` — a 1-D input is a scalar distribution, **not** an error (contrast
  S22, which is about a 0-d input) (`test_wrong_kw_fails`).
- **S31 (already-implemented statistics keep working):** Given `Distribution(np.random.randn(2, 3, 1000))`,
  `distr.pdf_histogram(bins=10)` returns arrays of shape `(2, 3, 10)` and `(2, 3, 11)`;
  given the `(4, 10000)` kpc fixture, `pdf_percentiles([10, 50, 90])` returns a
  `Quantity` (not a `Distribution`) of shape `(3, 4)`; and for an `ndarray`-backed
  distribution `_repr_latex_()` returns `None` (`test_histogram`, `test_percentile`,
  `test_array_repr_latex`). These exercise `.shape`/`.size`/`.distribution` consistency
  rather than new code.
- **S32 (copy):** Given any `Distribution`, `d.copy()` returns an object of the same
  class with the same logical shape, `n_samples` and values, writable and independent of
  the original (used by `TestGetSetItemAdvancedIndex.test_setitem` and
  `TestStructuredDistribution.test_setitem_*`, which mutate the copy and compare against
  the untouched original).

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass using the existing,
> unmodified test files `astropy/uncertainty/tests/test_distribution.py` and
> `astropy/uncertainty/tests/test_functions.py` as your oracle. Do not edit those test
> files. Do not edit `astropy/uncertainty/distributions.py` or
> `astropy/uncertainty/__init__.py`. Do not modify the already-implemented methods
> listed in Context (`distribution` property, `dtype` getter/setter, `astype`,
> `__getitem__`, `__setitem__`, `pdf_mean`, `pdf_var`, `pdf_mad`, `pdf_smad`,
> `pdf_percentiles`, `pdf_histogram`, `_not_implemented_or_raise`, `__eq__`, `__ne__`,
> `_DistributionRepr`) — your new code must satisfy their existing expectations, not the
> reverse. The one sanctioned edit outside the blank regions is extending the
> `from .function_helpers import FUNCTION_HELPERS` line at `core.py:25`.
>
> A green suite that passes for the wrong reason does not satisfy this contract. Before
> considering a scenario done, ask: "what is the smallest change that breaks this
> behavior, and does the existing test actually catch it?" (e.g., a `view()` that always
> returns a copy instead of sharing memory would still pass a naive equality check but
> must fail `np.may_share_memory` assertions already present in the tests — make sure
> your implementation is exercised by, not merely adjacent to, those assertions).
>
> Several requirements here are deliberately **not** oracle-covered (gufunc handling and
> the `axes=` rejection, `accumulate`/`at`/`outer`, `empty_like`, the `dtype` setter,
> `concatenate(out=...)`, `_not_implemented_or_raise` routing, `Distribution(<a
> Distribution>)`, `broadcast_to(subok=False)`). A green suite does not validate them;
> implement them from the descriptions above and state in your summary how you checked
> each one (ad-hoc REPL check or code reading). Do not delete or weaken them because no
> test fails.
>
> Recommended implementation order: (1) `_get_distribution_dtype` + `n_samples` +
> `__new__` (unblocks basic construction, S1/S2/S22/S30), (2) `__array_ufunc__`
> (unblocks arithmetic, comparisons, S5/S8/S9/S19/S24/S27), (3) `pdf_median`/`pdf_std`
> (S4), (4) `ArrayDistribution.view` (S14-S16/S23/S28), (5) `__array_function__` plus
> the `function_helpers.py` entries for
> `empty_like`/`broadcast_to`/`broadcast_arrays`/`concatenate` (S10-S13, S21). Run
> `pytest astropy/uncertainty/tests/test_distribution.py astropy/uncertainty/tests/test_functions.py -v`
> after each stage.

## Definition of Done

- [ ] `pytest astropy/uncertainty/tests/test_distribution.py
      astropy/uncertainty/tests/test_functions.py` is fully green (aside from the
      pre-existing `HAS_SCIPY`/stretch-goal skips already in the files).
- [ ] Every oracle-covered acceptance scenario maps to at least one passing test in
      those files (see the test names cited in each scenario). This covers
      S1-S24 and S27-S32.
- [ ] The scenarios/requirements explicitly marked "not oracle-covered" (S25, S26, the
      gufunc and non-`__call__`/`reduce` method bullets, `empty_like`, the `dtype`
      setter, `concatenate(out=...)`, `Distribution(<a Distribution>)`,
      `broadcast_to(subok=False)`, and the `type=<Distribution subclass>` dtype
      restriction) are implemented, and the implementation summary says how each was
      checked (ad-hoc check or code reading). They are **not** allowed to be omitted or
      stubbed.
- [ ] `astropy/uncertainty/distributions.py` and `astropy/uncertainty/__init__.py` are
      unchanged.
- [ ] The already-implemented methods listed in Context/"For the Implementing Agent"
      are unchanged. A diff review should show only: additions inside the blanked-out
      regions of `core.py` and `function_helpers.py` (the new
      `_get_distribution_dtype`/`n_samples`/`__new__`/`__array_function__`/
      `__array_ufunc__`/`view`/`pdf_median`/`pdf_std` bodies and the dispatch-table
      entries), plus — at most — an extended import list on `core.py:25`.
- [ ] No stub/placeholder bodies remain in the newly written code (no bare `pass`, no
      `raise NotImplementedError` standing in for required behavior; `NotImplementedError`
      appears only where this spec calls for it, i.e. the gufunc `axes=` rejection and
      helper argument-mismatch signalling). Pre-existing empty bodies —
      `ScalarDistribution` and `NdarrayDistribution` — stay as they are.

## Trade-offs and Limitations

- The exact split of `empty_like`/`broadcast_to`/`broadcast_arrays`/`concatenate`
  between `FUNCTION_HELPERS` and `DISPATCHED_FUNCTIONS` is left to the implementer;
  only the externally observable behavior in S10-S13 — plus the rule that dispatched
  results are final and never re-wrapped — is part of the contract.
- **Requirements this spec states that the oracle suite does not exercise.** They are
  still required (see Definition of Done), but a green run is no evidence about them,
  so they need a reading/ad-hoc check:
  - generalized-ufunc handling, including the `axes=` rejection (S26), and ufunc
    `method` values other than `"__call__"` and `"reduce"` (`accumulate`, `at`,
    `outer`, `reduceat`);
  - `numpy.empty_like` (no test calls it on a `Distribution`);
  - the already-implemented `dtype` *setter* (no test assigns `d.dtype = ...`), so the
    `itemsize` argument of `_get_distribution_dtype` is only indirectly pinned — by the
    memory-sharing assertions in S15/S17;
  - `np.concatenate(..., out=...)` and the `NotImplementedError` →
    `_not_implemented_or_raise` routing (S25);
  - `Distribution(<a Distribution>)` unwrapping;
  - `np.broadcast_to(..., subok=False)` on a `Distribution`;
  - the "only `dtype is None` or the current dtype is allowed when `type` is a
    `Distribution` subclass" restriction in `view` (only its error message is pinned,
    by S23);
  - `UNSUPPORTED_FUNCTIONS`/`DISTRIBUTION_SAFE_FUNCTIONS` remaining empty is acceptable:
    nothing in the suite requires an entry in either, and the fallback branch of
    `__array_function__` covers `np.min`, `np.median`, `np.may_share_memory`, etc.
- Itemsize relations in `view` beyond the two tested ones (same itemsize with sub-array
  dims; growth that exactly consumes the trailing logical axis) are intentionally left
  unspecified — see the `view` bullet in Key Components.
- `test_helper_normal_exact` and `test_helper_poisson_exact` are explicitly
  `pytest.skip("distribution stretch goal not yet implemented")` in the existing test
  file and are out of scope for this task; `test_pdf_mad_smad` is `HAS_SCIPY`-gated
  (it only needs `pdf_median`/`pdf_mad`, both covered here, so run it with scipy
  installed if possible).
- Structured-dtype storage (`"samples"`/`"sample"` nested field) is an existing,
  load-bearing design decision inherited from the already-implemented code, not a
  choice made by this spec; alternatives were not considered for that reason (see
  Alternatives Considered).

## References

- `astropy/uncertainty/core.py` — target file for `Distribution`/`ArrayDistribution`.
- `astropy/uncertainty/function_helpers.py` — target file for dispatch tables.
- `astropy/uncertainty/distributions.py` — consumer of `Distribution.__new__` (do not
  modify).
- `astropy/uncertainty/tests/test_distribution.py`,
  `astropy/uncertainty/tests/test_functions.py` — acceptance oracle (do not modify).
- `astropy/units/quantity.py` (`Quantity.__array_function__` at line 1837,
  `Quantity.__array_ufunc__` at line 594, `_result_as_quantity` at 675) — reference
  implementation of the same NumPy protocol dispatch pattern in this codebase. Note the
  contracts differ by one element: `Quantity` helpers return
  `(args, kwargs, unit, out)` / `(result, unit, out)`, whereas `Distribution` has no
  unit concept.
- `astropy/units/quantity.py` `_new_view` (line 745), `value`, `to`, `to_value` — the
  callers that force `ArrayDistribution.view` to return a `Distribution` for a
  non-`Distribution` requested type (S2, S16, S28); `Quantity.__new__` is what calls
  `Distribution.astype(float)` (S3).
- `astropy/units/quantity_helper/function_helpers.py` — reference implementation of the
  `FunctionAssigner`-based dispatch-table pattern (`FunctionAssigner` at line 188,
  `concatenate` at 482-501 with its `NUMPY_LT_2_4` signature split); note that for
  `Quantity`, `broadcast_to`/`broadcast_arrays`/`empty_like` are merely listed in
  `SUBCLASS_SAFE_FUNCTIONS` (lines 87-116) because plain subclass propagation suffices
  there — `Distribution` needs real helpers because of the hidden sample axis.

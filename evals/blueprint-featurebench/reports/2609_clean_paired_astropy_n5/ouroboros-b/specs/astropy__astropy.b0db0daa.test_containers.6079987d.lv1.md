# 2609.0001 Uncertainty Distribution Interfaces

**Date:** 2026-09-10
**Status:** draft
**Author:** FeatureBench

## Context

`astropy/uncertainty` implements Monte-Carlo–style uncertainty propagation:
a `Distribution` wraps an array of samples and behaves, as much as
possible, like an ordinary NumPy array or `~astropy.units.Quantity`. Every
`Distribution` has a **logical shape** — the shape a user sees via
`.shape`, `.ndim`, etc. — and a trailing **sample axis** of length
`n_samples` that is hidden from the logical shape but exposed via
`.distribution` (whose shape is `logical_shape + (n_samples,)`).
`Distribution.__new__` picks a concrete subclass based on the type of the
input samples: `NdarrayDistribution` for plain arrays, and one dynamically
generated class per distinct sample-array type otherwise — e.g.
`QuantityDistribution` for `Quantity` input and a separate,
`Angle`-specific generated class for `Angle` input (cached in
`Distribution._generated_subclasses`, keyed by the sample array's type).
Storage is an `ArrayDistribution` (`Distribution` + `np.ndarray`) whose
element dtype hides the sample axis inside a structured field, so the
ndarray's own `.shape` is the logical shape while its *dtype* encodes the
per-sample layout.

In the current state of `astropy/uncertainty/core.py`, the methods central
to this design have been removed, leaving the file syntactically valid but
functionally inert — `Distribution(...)` cannot even be constructed:

- `Distribution.__new__` — object construction and subclass dispatch.
- `Distribution.__array_function__` — the NumPy `__array_function__`
  protocol entry point.
- `Distribution.pdf_median`, `Distribution.pdf_std` — sample-axis reductions.
- `ArrayDistribution.distribution` — the property that exposes the raw
  sample array.
- `ArrayDistribution.view` — the `ndarray.view` override that keeps views
  as `Distribution` instances.
- Supporting glue that other, still-present code calls but which is itself
  undefined or unimplemented: a `n_samples` property; NumPy ufunc dispatch
  (`__array_ufunc__` — the module imports `_parse_gufunc_signature`,
  `normalize_axis_index`, and `DummyArray` at `core.py:16-22`, all
  currently unused, which is exactly the machinery generalized-ufunc
  dispatch needs); `Distribution._get_distribution_dtype(dtype, n_samples,
  itemsize=None)`, called by the already-present, unchanged `dtype.setter`
  (`core.py:190-195`) and `astype` (`core.py:197-199`) but defined nowhere;
  and `astropy/uncertainty/function_helpers.py` registrations for
  `numpy.empty_like`, `numpy.broadcast_to`, `numpy.broadcast_arrays`,
  `numpy.concatenate`, and `numpy.may_share_memory`/`numpy.shares_memory`.

Everything else in the module is intact and unmodified, and it depends on
the missing pieces: `pdf_mean`, `pdf_var`, `pdf_mad`/`pdf_smad`,
`pdf_percentiles`, `pdf_histogram`, `__getitem__`/`__setitem__`,
`__eq__`/`__ne__`, `dtype`/`dtype.setter`/`astype`, `_DistributionRepr`,
`ScalarDistribution`, `NdarrayDistribution`, and the sample-generation
helpers in `astropy/uncertainty/distributions.py` (`normal`, `poisson`,
`uniform`) all call into `.distribution`, `.n_samples`, or rely on
`Distribution()` succeeding. The existing, unmodified test suites
`astropy/uncertainty/tests/test_distribution.py` and
`astropy/uncertainty/tests/test_functions.py` fail across the board today
and are the ground truth this spec restores against; the doctest examples
in `docs/uncertainty/index.rst` are a secondary, non-blocking source of
ground truth for observable output (e.g. repr text).

## Motivation

Without `__new__`, `Distribution(...)` cannot be constructed at all, so the
entire `astropy.uncertainty` sub-package — and anything downstream that
composes it with other astropy types (e.g. `astropy.coordinates.Angle`, as
exercised in `test_distr_angle`) — is non-functional. Restoring these
methods is not optional cleanup; it is the whole feature. This spec
inlines the full observable contract, drawn from the surviving class
docstrings and the unmodified test files. One fact in that contract was
directly verified by experiment rather than merely read off a docstring:
`numpy.may_share_memory`/`numpy.shares_memory` route through
`__array_function__` and raise `TypeError` when it returns `NotImplemented`
(see the `may_share_memory` bullet under Key Components and S7). The
implementing agent needs no external document beyond this spec.

## Proposed Solution

### Overview

Re-implement, in `astropy/uncertainty/core.py`, the methods/properties
named above plus the supporting glue (`n_samples`, `__array_ufunc__`,
`_get_distribution_dtype`), and, in `astropy/uncertainty/function_helpers.py`,
the five NumPy-function registrations, so that the two existing test files
pass unmodified and the behaviors listed under "not yet covered by an
existing test" below are covered by new tests. No public signature, class
name, or file location may change from what is already present in
`core.py`, `function_helpers.py`, `distributions.py`, or `__init__.py`.

### Key Components

- **`Distribution.__new__(cls, samples)`** — Accepts anything
  `numpy.asanyarray`-compatible, including an existing `Distribution`
  (whose `.distribution` is used as the new samples). Raises
  `TypeError("Attempted to initialize a Distribution with a scalar ...")`
  for 0-d input (no axis is available to serve as the sample axis).
  Otherwise the *last* axis of the (possibly 1-d) input becomes the sample
  axis; the remaining axes become the logical shape (a 1-d input yields a
  0-d, "scalar" `Distribution`). Resolves/creates the concrete subclass
  for `type(samples)` via `Distribution._generated_subclasses` (cached, so
  repeated use of the same sample type returns the same generated class:
  `QuantityDistribution` for `Quantity` samples, a separate generated class
  for `Angle` samples (`test_distr_angle`/S7/S16 require it to still be an
  `Angle`, which a shared `QuantityDistribution` could not be), and
  `NdarrayDistribution` for plain-array input). Storage shares memory with
  the input via a view whenever the trailing-sample layout permits one —
  per the surviving docstring (`core.py:48-53`): "the data will not be
  copied unless it is not possible to take a view (generally, only when
  the strides of the last axis are negative)"; a single-sample
  (`n_samples == 1`), zero-stride input remains constructible.
- **`Distribution.n_samples`** (property) — the fixed length of the
  trailing sample axis; used by `__repr__`/`__str__`/`_repr_latex_`
  (`_DistributionRepr`, already implemented) and by the reduction methods.
- **`Distribution._get_distribution_dtype(dtype, n_samples, itemsize=None)`**
  `[INFERRED]` — builds the internal structured storage dtype that hides
  `n_samples` samples of `dtype` behind `Distribution`'s single-field
  layout; needed so the already-present `dtype.setter` and `astype`
  continue to work (they call this method today with no definition
  present).
- **`Distribution.__array_function__(self, function, types, args, kwargs)`** —
  Routes supported NumPy functions to `astropy/uncertainty/function_helpers.py`'s
  `FUNCTION_HELPERS` / `DISPATCHED_FUNCTIONS` / `DISTRIBUTION_SAFE_FUNCTIONS`
  registries (already-present `FunctionAssigner`-based machinery, currently
  empty), converts `Distribution` args to their `.distribution` arrays,
  and rewraps array-shaped results as `Distribution` (a scalar result stays
  a scalar; a tuple/list result keeps its container type, with each element
  independently typed according to its corresponding input — a
  `Distribution` input position yields a `Distribution` output element, a
  plain-array input position yields a plain-array output element, per S13;
  an explicit `Distribution` `out=`/return is returned by identity). Functions whose default NumPy
  implementation already produces correct results against a `Distribution`
  — because that implementation itself reduces to ufunc calls or to other
  supported functions, e.g. `numpy.min`/`numpy.amin` and `numpy.all` (both
  exercised on `Distribution` operands by `test_helper_poisson_samples`) —
  must resolve by letting the default implementation run, e.g. via a
  `DISTRIBUTION_SAFE_FUNCTIONS` entry (which registry to use is the
  implementing agent's choice — see the `function_helpers.py` registrations
  note below) — by delegating to
  `super().__array_function__(function, types, args, kwargs)`, which then
  re-enters through `__array_ufunc__` for any ufunc reduction inside it;
  this is exactly what `DISTRIBUTION_SAFE_FUNCTIONS`'s own in-repo
  docstring describes ("functions that work fine on Distribution classes
  already... most... internally use `numpy.ufunc` or other functions that
  are already covered"). Only when neither a registered helper/dispatcher
  nor this safe-function delegation applies does `__array_function__` fall
  back to `Distribution._not_implemented_or_raise` (already implemented,
  unchanged): `TypeError` if a non-`Distribution` `np.ndarray` subclass is
  among the operand types, `NotImplemented` otherwise.
- **`Distribution.__array_ufunc__(self, function, method, *inputs, **kwargs)`**
  `[INFERRED — name/signature is the standard NumPy protocol entry point;
  absent from core.py today]` — Ordinary ufuncs (`method == "__call__"`,
  e.g. `np.sin`, `+`, comparisons) apply sample-wise: non-`Distribution`
  operands broadcast against every sample, and two `Distribution` operands
  broadcast their sample axes the same way NumPy broadcasts any trailing
  axis (`n_samples == 1` broadcasts against any `N`). `method == "reduce"`
  called with `axis=None` (NumPy's own default when no axis is given to
  e.g. `ndarray.min()`) acts over every logical axis while keeping the
  sample axis intact — `np.min(p_dist)` (`p_dist.min(axis=None)` ->
  `np.minimum.reduce(p_dist, axis=None)`) yields a 0-d `Distribution`, not
  a bare scalar (S10). `method == "accumulate"` accumulates along the
  given logical axis (NumPy's own default `axis=0`; `accumulate` does not
  accept `axis=None`), never over the sample axis. In-place calls (`out=self`, or
  operators like `+=`) write through to the stored samples and keep the
  receiver's exact class. Generalized ufuncs (non-empty `signature`, e.g.
  `np.matmul`) keep the sample axis trailing, outside the function's core
  dimensions, and reject the `axes` keyword with `NotImplementedError`
  (the reserved axis makes a caller-supplied `axes` mapping ambiguous).
  Comparison dunders (`__eq__`, `__ne__`; already implemented, unchanged)
  defer to `NotImplemented` when the other operand sets
  `__array_ufunc__ = None`, letting the other operand's reflected method run.
- **`function_helpers.py` registrations**, using the existing
  `function_helper`/`dispatched_function` decorators:
  - `numpy.empty_like(prototype, dtype=None, order="K", subok=True, shape=None)`
    — returns a `Distribution` of `prototype`'s type with the same
    `n_samples` (same `subok`-stays-a-`Distribution` rule as
    `broadcast_to`/`broadcast_arrays` above); `subok=False` only downgrades
    the result's `.distribution` to a plain `np.ndarray`, not the result
    itself; `dtype`, if given, sets the per-sample dtype; `shape`, if
    given, is interpreted against the *logical* shape (the sample axis is
    always appended automatically); `order` is passed straight through to
    the underlying array allocation, same as it would be for
    `prototype.distribution` directly.
  - `numpy.broadcast_to(array, shape, subok=...)` — logical-shape
    broadcast; a `Distribution` input stays a `Distribution` output
    regardless of `subok` (per `test_broadcast_arrays_subok_false`'s own
    comment: "subok affects ndarray subclasses but not distribution
    itself") — `subok` only controls whether *that* `Distribution`'s
    `.distribution` (its underlying sample-array class, e.g. `Quantity`)
    stays that class (`subok=True`) or downgrades to plain `np.ndarray`
    (`subok=False`, dropping units); a plain-array (non-`Distribution`)
    input follows NumPy's ordinary `subok` semantics unchanged.
  - `numpy.broadcast_arrays(*arrays, subok=...)` — as above, applied
    elementwise across mixed `Distribution`/plain-array arguments (S13).
  - `numpy.concatenate(seq, axis=0, out=None, ...)` — uses the common
    `n_samples` across the `Distribution` arguments in `seq`; if two
    `Distribution` arguments in `seq` have different `n_samples`, the
    helper cannot form a single common sample count and declines the call.
    Per `Distribution._not_implemented_or_raise`'s existing, unchanged rule
    (`core.py:345-353`): with every operand a `Distribution` (no
    non-`Distribution` `np.ndarray` subclass among `types`), declining
    returns `NotImplemented` all the way out of `__array_function__`, and
    NumPy's own dispatcher then raises the `TypeError` (the same
    "no implementation found" mechanism already verified for
    `may_share_memory` above) — see S34. For a consistent `n_samples`,
    ordinary (non-`Distribution`) array arguments are repeated across that
    sample count before concatenating, `axis` is interpreted against the
    logical shape, and the call returns a `Distribution`; an explicit
    `out=` is accepted and filled in place when it is itself a
    `Distribution` (S35) — a non-`Distribution` `out=` puts a
    non-`Distribution` `np.ndarray` among the operand `types` (since `seq`
    still holds `Distribution` arguments), so that combination *does* fall
    through to `Distribution._not_implemented_or_raise`'s `TypeError`
    branch (S31).
  - `numpy.may_share_memory` / `numpy.shares_memory` — verified by direct
    experiment that NumPy always routes these through
    `__array_function__` and raises `TypeError` for any operand type that
    returns `NotImplemented`. On `Distribution` operands they must return
    the same boolean NumPy would compute directly on the underlying
    storage arrays (a pointer/overlap check, unaffected by the structured
    sample-axis encoding) — they must never raise or return
    `NotImplemented`.

### Data Flow

1. Caller builds a `Distribution` from array-like samples (`Distribution(arr)`,
   `ds.normal(...)`, `arr << unit` on an existing `Distribution`, etc.).
   `__new__` normalizes the input, validates it is not scalar, resolves
   the concrete subclass, and stores the samples with the sample axis
   trailing.
2. Ordinary attribute/statistics access (`.distribution`, `.n_samples`,
   `.pdf_median()`, `.pdf_std()`, `.pdf_mean()`, `.astype(...)`, …) reads
   the stored array via the `distribution` property and reduces over its
   last axis.
3. NumPy operations (`np.sin(d)`, `d + other`, `d == 0`, `np.concatenate(...)`,
   `np.broadcast_to`/`np.broadcast_arrays`, `np.empty_like(d)`,
   `np.min(d)`, `np.may_share_memory(a, b)`, …) are intercepted by
   `__array_ufunc__`/`__array_function__`, translated to operations on the
   underlying sample arrays (with non-`Distribution` operands
   broadcast/repeated across the sample axis as needed), and the
   array-shaped results are rewrapped as `Distribution` before being
   returned; scalar and tuple/list results pass through their natural
   type/container, and pointer-overlap checks pass through to the plain
   boolean NumPy would compute on the raw storage.
4. `.view(...)` produces a new `Distribution` sharing storage with the
   original wherever the requested dtype/type keeps the sample axis
   trailing and contiguous.

### Interface Contract

```python
# astropy/uncertainty/core.py

class Distribution:
    _generated_subclasses: dict  # already present, keyed by sample-array type

    def __new__(cls, samples):
        # samples via numpy.asanyarray; an existing Distribution is unwrapped via .distribution
        # TypeError("Attempted to initialize a Distribution with a scalar ...") when samples.shape == ()
        # last axis of samples -> sample axis; remaining axes -> logical shape
        # subclass resolved/created from type(samples), cached in _generated_subclasses
        # storage shares memory via a safe trailing-sample view; copies only when
        # no safe view exists (e.g. negative last-axis strides); n_samples == 1
        # with a zero stride remains valid
        ...

    @property
    def n_samples(self) -> int: ...

    def _get_distribution_dtype(self, dtype, n_samples, itemsize=None): ...  # [INFERRED]

    def __array_function__(self, function, types, args, kwargs): ...

    def __array_ufunc__(self, function, method, *inputs, **kwargs): ...  # [INFERRED]

    def pdf_median(self, out=None): ...          # np.median(self.distribution, axis=-1, out=out)
    def pdf_std(self, dtype=None, out=None, ddof=0): ...  # np.std(self.distribution, axis=-1, dtype=dtype, out=out, ddof=ddof)

    @property
    def distribution(self): ...  # base version, core.py:182-184 — used by ScalarDistribution
                                  # (np.void-backed); n_samples must work through this path too

    # Unchanged, already implemented, depend on the above:
    # pdf_mean, pdf_var, pdf_mad, pdf_smad, pdf_percentiles, pdf_histogram,
    # __eq__, __ne__, _not_implemented_or_raise, dtype getter/setter, astype


class ScalarDistribution(Distribution, np.void):
    # Unchanged, already implemented (core.py:513-518) — a single structured
    # element returned by ArrayDistribution.__getitem__ (e.g. from unpacking
    # a 1-d Distribution); n_samples and the base distribution property above
    # must produce correct results for this class too (S36).
    pass


class ArrayDistribution(Distribution, np.ndarray):
    _samples_cls = np.ndarray  # already present

    @property
    def distribution(self): ...   # raw sample array, trailing sample axis, shares storage where possible
                                   # (overrides the base Distribution.distribution above)

    def view(self, dtype=None, type=None): ...
    # Result is always a Distribution.
    # ValueError("... can only be viewed ...") for an incompatible dtype reinterpretation.
    # ValueError("... last axis must be contiguous ...") when the sample axis
    #   is not contiguous but a dtype view requires it to be.

    # Unchanged, already implemented: __getitem__, __setitem__


# astropy/uncertainty/function_helpers.py
# Existing empty registries: FUNCTION_HELPERS, DISPATCHED_FUNCTIONS,
# DISTRIBUTION_SAFE_FUNCTIONS, and decorators function_helper / dispatched_function.
# Must gain entries (registry choice — FUNCTION_HELPERS vs DISPATCHED_FUNCTIONS
# vs DISTRIBUTION_SAFE_FUNCTIONS — is the implementing agent's judgment; only
# observable behavior is constrained) for:
#   numpy.empty_like(prototype, dtype=None, order="K", subok=True, shape=None)
#   numpy.broadcast_to(array, shape, subok=...)
#   numpy.broadcast_arrays(*arrays, subok=...)
#   numpy.concatenate(seq, axis=0, out=None, ...)
#   numpy.may_share_memory / numpy.shares_memory
```

## Acceptance Scenarios

Each scenario notes its test-coverage status: **existing** (an unmodified
test in `test_distribution.py`/`test_functions.py` already exercises it —
do not weaken or rewrite that test), **doctest** (pinned by
`docs/uncertainty/index.rst`, a non-blocking secondary check), or **new**
(no current test — the implementing agent must add one).

### Happy Path

- **S1** *(existing: `test_shape`, `test_size`, `test_n_samples`)* — Given
  `data`, a `(4, 10000)` array of normal samples, and
  `distr = Distribution(data * u.kpc)`, then `distr.shape == (4,)`,
  `distr.size == 4`, `distr.distribution.shape == (4, 10000)`,
  `distr.distribution.size == 40000`, and `distr.n_samples == 10000`.
- **S1b** *(new)* — Given a plain `(4, 10000)` ndarray of samples `arr`,
  when constructed via `Distribution(arr)`, then
  `type(Distribution(arr)) is NdarrayDistribution` (importable from
  `astropy.uncertainty.core`); given the same `arr` tagged with a unit
  (`arr << u.kpc`), the generated class is not importable (it only exists
  in `Distribution._generated_subclasses`), so instead:
  `type(Distribution(arr << u.kpc)).__name__ == "QuantityDistribution"`
  and repeated construction from `Quantity` samples returns the identical
  cached class object (`type(Distribution(arr << u.kpc)) is type(Distribution(arr << u.pc))`).
  *(No existing test asserts the concrete class name directly — `test_quantity_init`
  (S2) only checks `isinstance(pqd, Distribution)`/`isinstance(pqd, u.Quantity)`.)*
- **S2** *(existing: `test_quantity_init`)* — Given an integer-sample
  `Quantity` `pq = parr << u.ct`, when constructed via `Distribution(pq)`,
  then the result is both `Quantity` and `Distribution`, `.value` is
  itself a `Distribution`, and `.value.distribution` equals the original
  integer samples.
- **S3** *(existing: `test_quantity_init_with_distribution`)* — Given an
  existing `pd = Distribution(parr)`, when combined with a unit via
  `pd << u.ct`, then the resulting object's `.value.distribution` equals
  `pd.distribution.astype(float)`.
- **S4** *(existing: `test_pdf_median`)* — Given a `Distribution` built
  from normally-distributed `(4, 10000)` data with known per-row
  mean/std, when `.pdf_median()` is called, then the result matches
  `np.median(data, axis=-1)` (within tolerance), is a plain `Quantity`
  (not a `Distribution`), and `.pdf_median(out=x)` returns `x` populated
  with the result.
- **S5** *(existing: `test_pdf_std`)* — Given the same setup, when
  `.pdf_std()` (default `ddof=0`) and `.pdf_std(ddof=1, out=x)` are
  called, then results match `np.std(data, axis=-1, ddof=...)`, are plain
  `Quantity` (not `Distribution`), and `out=` identity holds.
- **S6** *(existing: `TestStructuredQuantityDistributionInit`)* — Given
  samples with a structured dtype (fields `"a"` (`f8`) and `"b"`
  (`(2,2)f8`)) tagged with a compound unit, when constructed via
  `Distribution(structured_samples << unit)`, then `.distribution` equals
  the original unit-tagged structured array and `.value.distribution`
  equals the raw structured array.
- **S7** *(existing: `test_distr_angle_view_as_quantity`)* — Given
  `ad = Angle(Distribution([2.,3.,4.]), "deg")`, when `.view(u.Quantity)`
  is called, then the result is a `Quantity` + `Distribution` but not an
  `Angle`; `.view(result.__class__)` and `.view(result.dtype, result.__class__)`
  reproduce the same class; and a no-argument `.view()` on that result
  (`qd4 = qd3.view()`) returns the same class and shares memory with it,
  asserted via `np.may_share_memory(qd4, qd3)` (this assertion is also the
  primary existing-test coverage for the `may_share_memory` contract in Key
  Components — the earlier views in this same test, `qd`/`qd2`/`qd3`, are
  checked by class/type and `assert_array_equal`, not `may_share_memory`).
- **S8** *(existing: `test_distr_view_different_dtype1`,
  `test_distr_view_different_dtype2`)* — Given `c = Distribution([2.0j, 3.0, 4.0j])`,
  when `.view("2f8")` is called, then the shape becomes `c.shape + (2,)`,
  memory is shared (`np.may_share_memory`), `.distribution` equals
  `np.moveaxis(c.distribution.view("2f8"), -2, -1)`, and viewing back via
  `.view("c16")` recovers the original `.distribution` while still
  sharing memory; the analogous `u4` <-> `4u1` round trip holds for
  `Distribution(np.array([[0x01020304, 0x05060708], [0x11121314, 0x15161718]], dtype="u4"))`.
- **S9** *(existing: `test_scalar_quantity_distribution`)* — Given
  `angles = Distribution([90.,30.,0.] * u.deg)`, when `np.sin(angles)` is
  applied, then the result is a `Distribution` and a `Quantity` equal to
  `Distribution(np.sin([90.,30.,0.] * u.deg))` — ufuncs apply sample-wise
  and rewrap the result.
- **S10** *(existing: `test_helper_poisson_samples`)* — Given
  `p_dist = ds.poisson(centerqcounts, n_samples=100)`, when `np.min(p_dist)`
  is called with no axis argument, then the result `p_min` is a scalar
  `Distribution` (`isinstance(p_min, Distribution)`, `p_min.shape == ()`)
  and `np.all(p_min >= 0)` evaluates true — i.e. both the `np.min` reduction
  and the subsequent `np.all`/`>=` comparison on its result must work
  end-to-end on `Distribution` operands without a registered `concatenate`/
  `broadcast_*`/`empty_like` helper being involved.
- **S11** *(existing: `test_concatenate`, and `TestQuantityDistributionConcatenation`
  which reruns it with `da`/`db`/`c` as `Quantity`-based `Distribution`s in
  m/km/Mm)* — Given `da` and `db[np.newaxis]` (both `Distribution`,
  `n_samples=4`, compatible logical shapes), when
  `np.concatenate((da, db[np.newaxis]), axis=0)` is called, then the result
  is a `Distribution` whose `.distribution` equals `np.concatenate` of the
  two underlying sample arrays along the same axis; when `da`/`db` carry
  units, ordinary `Quantity` unit-conversion rules apply to that
  concatenation (unaffected by the sample-axis handling).
- **S12** *(existing: `test_concatenate_not_all_distribution`, and its
  `Quantity` rerun in `TestQuantityDistributionConcatenation`)* — Given `c`
  (a plain array/`Quantity` with no sample axis) and `da` (`Distribution`,
  `n_samples=4`), when `np.concatenate((c, da), axis=1)` is called, then
  `c` is broadcast across `da.n_samples` samples before concatenation, and
  the result `isinstance(..., Distribution)` matches
  `np.concatenate((c_broadcast, da.distribution), axis=1)`.
- **S13** *(existing: `test_broadcast_arrays`, `test_broadcast_arrays_subok_false`,
  and their `Quantity` reruns in `TestQuantityDistributionBroadcast`)* —
  Given `da`, `db` (`Distribution`) and `c` (plain array) of
  broadcast-compatible logical shapes, when
  `np.broadcast_arrays(da, db, c, subok=True)` is called, then the
  `Distribution` inputs broadcast to `Distribution` outputs of the
  matching subclass and `c` broadcasts to a plain array matching
  `np.broadcast_to(c, da.shape, subok=True)`; with `subok=False`, the
  `Distribution` outputs' `.distribution` and `c`'s output downgrade to
  plain `np.ndarray`.
- **S14** *(existing: `test_broadcast_to`, and its `Quantity` rerun in
  `TestQuantityDistributionBroadcast`)* — Given `db` (`Distribution`) and a
  target logical shape equal to `da.shape`, when
  `np.broadcast_to(db, da.shape, subok=True)` is called, then the result
  is a `Distribution` of `db`'s subclass with `.shape == da.shape` and
  `.distribution == np.broadcast_to(db.distribution's base array, da.distribution.shape, subok=True)`.
- **S15** *(new)* — Given a `Distribution` `d`, when `np.empty_like(d)`
  and `np.empty_like(d, dtype=other_dtype, shape=other_logical_shape)`
  are called, then both results are `Distribution` instances of `d`'s
  type with `n_samples == d.n_samples`; the first has `d`'s logical shape
  and per-sample dtype, the second has `other_logical_shape` (sample axis
  appended automatically) and `other_dtype` per sample; when
  `np.empty_like(d, subok=False)` is called instead, the result is still a
  `Distribution` with `n_samples == d.n_samples`, but its `.distribution`
  is a plain `np.ndarray` (not `d.distribution`'s own class, e.g. not a
  `Quantity`).
- **S16** *(existing: `test_distr_angle`, `TestSetItemWithSelection.test_inplace_operation`)* —
  Given `ad = Angle(Distribution([2.,3.,4.]), "deg")`, when `ad += ad` is
  executed, then `ad` remains both `Angle` and `Distribution` and its
  `.distribution` equals the pre-computed `ad + ad` result; given
  `d = Distribution([90.,30.,0.])`, when `d[d > 50] *= -1.0` is executed,
  then only the selected elements are negated in place.
- **S17** *(existing: `TestComparison.test_distribution_can_be_compared_to_non_distribution`)* —
  Given `d = Distribution([90.,30.,0.])`, when `d == 0.0`, `d != 0.0`, or
  `d > 0.0` is evaluated, then the result equals
  `Distribution(op(d.distribution, 0.0))` — a `Distribution` of booleans,
  not a plain boolean array.
- **S18** *(existing: `test_distr_to`, `test_distr_to_value`)* — Given
  `distr = ds.normal(10 * u.cm, n_samples=100, std=1 * u.cm)`, when
  `.to(u.m)` and `.to_value(u.m)` are called, then
  `distr.pdf_mean().to(u.m)` matches `distr.to(u.m).pdf_mean()`, and
  `distr.pdf_mean().to_value(u.m)` matches `distr.to_value(u.m).pdf_mean()`.
- **S19** *(new; doctest: `docs/uncertainty/index.rst:60,119-126`)* — Given
  a `Distribution` built from `Quantity` samples, when `repr()`/`str()` is
  called, then the output contains the literal class name
  `QuantityDistribution` and the substring `with n_samples=N`; given a
  `Distribution` built from plain-array samples, the output contains
  `NdarrayDistribution` and `with n_samples=N`; `_repr_latex_()` contains
  `n_{\rm samp}=N` (`test_reprs` already asserts the `n_samples=N`
  substrings for the `Quantity` case — this scenario adds the class-name
  assertion and the plain-array case).
- **S20** *(new)* — Given `da`, `db` (`Distribution` operands, `n_samples=4`)
  in a `np.matmul`-compatible logical shape, when `np.matmul(da, db)` is
  called (no `axes=` keyword), then the result is a `Distribution` with
  `n_samples=4` whose `.distribution`, moved to expose the matmul core
  dimensions per sample, equals `np.matmul` applied independently to each
  sample slice of `da.distribution` and `db.distribution`.
- **S36** *(existing + new: `test_index_assignment_array`/`test_index_assignment_quantity`
  assert `isinstance(d1, Distribution)`/`isinstance(d2, Distribution)` only
  — the `n_samples`/`.distribution` assertions below are new)* — Given a
  `(2, 1000)`-sample `Distribution` `distr` (plain-array and
  `Quantity`-based variants), when unpacked via `d1, d2 = distr`, then
  `d1`/`d2` are each `Distribution` instances (existing coverage; backed by
  `ScalarDistribution`, the `np.void`-based scalar-element class at
  `core.py:513-518`, reached whenever `__getitem__` returns a single
  structured element) whose `.n_samples == 1000` and `.distribution` is the
  corresponding 1000-sample row of `distr.distribution` (new).
- **S37** *(existing: `test_array_repr_latex`)* — Given
  `distr = Distribution(np.random.randn(4, 1000))` (plain-array samples,
  on a NumPy version where `ndarray` itself has no `_repr_latex_`), when
  `distr._repr_latex_()` is called, then it returns `None`.

### Edge Cases

- **S21** *(existing: `TestGetSetItemAdvancedIndex.test_getitem` and its
  `Quantity`/structured-dtype subclasses)* — Given advanced (fancy)
  integer-array indices, including negative-index variants that select
  the same elements as their positive equivalents, when used to index a
  `Distribution` (plain, `Quantity`, and structured-dtype variants), then
  `d[item].distribution` equals `self.distribution[item]` and
  `d[item].shape == item[0].shape`.
- **S22** *(existing: `test_numpy_init_T`, `test_quantity_init_T` construct
  from a `.T`-transposed, non-contiguous-last-axis array;
  `TestStructuredDistribution.test_getitem` (`np.may_share_memory(d_i, self.d)`)
  already asserts memory sharing survives a `moveaxis`'d construction; plus
  new)* — Given input whose sample axis has positive but non-unit,
  non-contiguous strides (e.g. a transposed view), when constructed via
  `Distribution(...)`, then no copy is forced merely because the layout is
  non-contiguous, and `.n_samples`/`.distribution` remain correct (new:
  verify via `np.may_share_memory` between the input and `.distribution`
  directly at construction time, not just after a further `moveaxis`);
  given input whose last-axis strides are negative, a copy is made (new);
  a one-sample (`n_samples == 1`), zero-stride input remains constructible
  without error (new).
- **S38** *(existing: `TestStructuredDistribution.test_getitem`,
  `test_setitem_field`, and their `TestStructuredQuantityDistribution`
  reruns)* — Given `d`, a `Distribution` over samples with structured
  dtype fields `"a"` (`f8`) and `"b"` (`(2,2)f8`), when `d["a"]` or `d["b"]`
  is accessed, then the result is a `Distribution` sharing memory with `d`
  (`np.may_share_memory`) whose shape is `d.shape + dtype[item].shape` and
  whose `.distribution` equals the field's data with the sample axis moved
  to the end (`np.moveaxis(self.distribution[item], d.ndim, -1)`); when
  `d["b"] = 0.0` is assigned, then `d.distribution["b"]` becomes all zero
  (matching `np.zeros_like`); when a broadcastable plain field value is
  assigned instead (e.g. `d["b"] = [[-1.,-2.],[-3.,-4.]]`, a `Quantity` in
  the `TestStructuredQuantityDistribution` rerun), every sample's field
  value becomes that value (matching `np.full_like`); when a `Distribution`
  field value is assigned (e.g. `d["a"] = d["a"] * 2.0`), the field's
  stored data becomes exactly double its previous value.
- **S23** *(new)* — Given a generalized ufunc (e.g. `np.matmul`) invoked
  with the unsupported `axes=` keyword against `Distribution` operand(s),
  when the call is made, then it raises `NotImplementedError`.
- **S24** *(existing: `TestSetItemWithSelection.test_setitem`)* — Given
  `d = Distribution([90.,30.,0.])` (`n_samples=3`, a scalar distribution),
  when `d[d > 50] = 0.0` is executed, then `d` equals
  `Distribution([0.0, 30.0, 0.0])` — only the samples at the selected
  (boolean-`Distribution`-indexed) positions change.
- **S33** *(existing: `TestGetSetItemAdvancedIndex.test_setitem` and its
  `TestQuantityDistributionGetSetItemAdvancedIndex`/`TestStructuredAdvancedIndex`
  variants)* — Given `d`, a `Distribution` whose logical shape is `(3, 4)`
  with `n_samples == 5` (built from a `(3,4,5)` sample array), and a fancy
  index `item` selecting a subset of logical positions,
  when a *plain* value `0.0` is assigned via `d[item] = 0.0`, then every
  sample at every selected position becomes `0.0` — the plain scalar is
  treated as an `n_samples=1` `Distribution` and broadcasts against `d`'s
  actual `n_samples` at each selected position (this is the code path
  `core.py:628-634` actually implements: wrapping a non-`Distribution`
  assigned value into an `n_samples=1` `Distribution` before storing);
  given a pristine copy `d0 = d.copy()` taken before that assignment,
  when `d[item] = d0[item]` is executed (assigning a `Distribution` value,
  not a plain one), then `d.distribution` is restored to its original
  (pre-zeroing) values exactly.
- **S34** *(new, `[INFERRED]`)* — Given `da`, `db` (`Distribution`,
  `n_samples=4` and `n_samples=5` respectively, otherwise compatible
  logical shapes), when `np.concatenate((da, db), axis=0)` is called, then
  it does not silently pick one sample count — it raises `TypeError`: the
  concatenate helper declines (both operands are `Distribution`, so
  `Distribution._not_implemented_or_raise` returns `NotImplemented`
  rather than raising directly), and NumPy's own dispatcher then raises
  `TypeError` because no type in `types` implements the function for these
  arguments (the same mechanism already verified for `may_share_memory`).
- **S35** *(new, `[INFERRED]`)* — Given `da`, `db` (`Distribution`,
  matching `n_samples`, each with logical shape `(2, 3)`) and
  `out = Distribution(np.empty_like(np.concatenate((da.distribution, db.distribution), axis=0)))`
  — a `Distribution` whose logical shape, `(4, 3)`, matches what
  concatenating `da` and `db` along `axis=0` produces — when
  `np.concatenate((da, db), axis=0, out=out)` is called, then the call
  succeeds, `out` is filled with the concatenation result (`out.distribution`
  equals `np.concatenate((da.distribution, db.distribution), axis=0)`), and
  the function's return value is `out` (identity).
- **S40** *(existing: `TestStructuredDistribution.test_setitem_index_slice`
  and its `TestStructuredQuantityDistribution` rerun)* — Given `d`, a
  `Distribution` over structured-dtype samples, and `item` an integer index
  (`1`) or a slice (`slice(0, 2)`) into `d`'s logical shape, when a plain
  structured-tuple value (`(0.0, [[-1.,-2.],[-3.,-4.]])`, or the same tuple
  carrying units — `Mm,km` — against a `km,m`-unit `d` in the `Quantity`
  rerun, exercising unit conversion) is assigned via `d[item] = value`,
  then every sample at the selected logical position(s) takes that value;
  given a pristine copy `d0 = d.copy()` taken beforehand, when
  `d[item] = d0[item]` is executed, then `d.distribution` is restored to
  its original values exactly.

### Error Scenarios

- **S25** *(existing: `test_init_scalar`)* — Given `parr.ravel()[0]` (a 0-d
  scalar), when `Distribution(parr.ravel()[0])` is constructed, then it
  raises `TypeError` matching `"Attempted to initialize a Distribution with a scalar"`.
- **S26** *(existing: `test_distr_cannot_view_new_dtype`)* — Given
  `distr = Distribution([2.,3.,4.])`, when `distr.view(np.dtype("2i8"))`
  or `distr.view(np.dtype("2i8"), distr.__class__)` is called (and the
  same calls on `Angle(distr, "deg")`), then a `ValueError` matching
  `"can only be viewed"` is raised.
- **S27** *(existing: `test_distr_view_different_dtype2`)* — Given
  `uint8_2 = Distribution(uint32_array).view("4u1").T` (a view whose last
  axis is no longer contiguous), when `.view("u4")` is called on it, then
  a `ValueError` matching `"last axis must be contiguous"` is raised.
- **S28** *(existing: `test_distr_noq_to`, `test_distr_noq_to_value`)* —
  Given `distr = ds.normal(10, n_samples=100, std=1)` (plain-array
  samples, no unit), when `.to(u.m)` or `.to_value(u.m)` is called, then
  `AttributeError` is raised (an `NdarrayDistribution` has no `Quantity`
  conversion methods).
- **S29** *(existing: `test_distr_angle`)* — Given `ad = Angle(Distribution([2.,3.,4.]), "deg")`,
  when `ad *= ad` is executed, then `u.UnitTypeError` is raised (squaring
  an angle in place is not a valid `Angle` unit).
- **S30** *(new)* — Given a NumPy function call mixing a `Distribution`
  operand with a plain (non-`Distribution`) `np.ndarray`-subclass operand,
  where the registered helper/dispatcher for that function explicitly
  signals it cannot handle the given argument combination (raises
  `NotImplementedError` internally, per `function_helpers.py`'s own
  documented contract for `FUNCTION_HELPERS`/`DISPATCHED_FUNCTIONS`
  entries) — as opposed to the function simply having no registration at
  all, which is S10's path — when `__array_function__` is invoked, then it
  raises `TypeError` (via the existing, unchanged
  `Distribution._not_implemented_or_raise`); when no such non-`Distribution`
  `ndarray` subclass is present among the operands, `NotImplemented` is
  returned instead so another type can handle it.
- **S31** *(new, `[INFERRED]`)* — Given `np.concatenate((da, db), out=plain_ndarray)`
  where `da`/`db` are `Distribution` and `plain_ndarray` is a bare
  `np.ndarray`, when the call is made, then it raises `TypeError` (the
  same `_not_implemented_or_raise` path as S30, since a `Distribution` is
  present among the operands but the `out=` argument cannot be handled).
- **S32** *(existing: `TestComparison.test_distribution_comparison_defers_correctly`)* —
  Given `d = Distribution([90.,30.,0.])` and `other` whose class sets
  `__array_ufunc__ = None` and defines `__eq__`/`__ne__`/`__lt__`
  returning fixed strings, when `d == other`, `d != other`, or `d > other`
  is evaluated, then `Distribution`'s comparison defers (returns
  `NotImplemented` internally) and the *other* operand's method result
  (`"eq"`/`"ne"`/`"gt"`) is what the expression evaluates to.
- **S41** *(new, `[INFERRED]`)* — Given `d = Distribution(np.arange(12.).reshape(3, 4))`
  (per-sample dtype `float64`), when `d.dtype` is read, then it reports the
  *per-sample* dtype (`float64`), not `Distribution`'s internal structured
  storage dtype; when `d2 = d.astype(np.float32)` is called, then `d2` is a
  `Distribution` with `d2.dtype == np.float32`, `d2.shape == d.shape`,
  `d2.n_samples == d.n_samples`, and `d2.distribution` equal to
  `d.distribution.astype(np.float32)`; when `d.dtype = np.float32` is
  assigned in place, then `d.dtype == np.float32` and `d.n_samples` is
  unchanged. *(Exercises `Distribution._get_distribution_dtype`, called by
  the already-present, unchanged `dtype.setter`/`astype` — S3 only pins
  `ndarray.astype` on an already-unwrapped `.distribution` array, not
  `Distribution.astype` itself, so this scenario is the only coverage for
  that helper.)*
- **S39** *(existing: `TestGetSetItemAdvancedIndex.test_getitem_bad`)* —
  Given `d`, a `Distribution` whose logical shape is `(3, 4)` with
  `n_samples == 5` (built from a `(3,4,5)` sample array), when indexed with
  an out-of-range fancy index (e.g. `d[([0, 4],)]`, where `4` is out of
  bounds for a length-3 logical axis) or a fancy index with too many index
  arrays for `d`'s 2-d logical shape (e.g. `d[([0], [0], [0])]`), then
  `IndexError` is raised.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*. A green suite that passes for
> the wrong reason does not satisfy this contract — `/verify` will hunt for
> vacuous tests by asking, of each behavior, "what is the smallest change
> that breaks this, and would any test catch it?"

Treat `astropy/uncertainty/tests/test_distribution.py` and
`astropy/uncertainty/tests/test_functions.py` as **authoritative and
unmodifiable** ground truth: every scenario marked *(existing: ...)* above
is asserted by the named test(s) in one of those two files, though in some
cases (noted inline, e.g. S7, S10, S22, S36) the existing test covers part of
the scenario and a *(new)* addition in the same bullet covers the rest —
read each scenario's parenthetical carefully rather than assuming full
existing coverage from the *(existing: ...)* tag alone. Do not weaken,
skip, or rewrite the existing tests' assertions to make them pass — if one
of them seems wrong, that is a signal your implementation is wrong, not
the test. Scenarios (or scenario parts) marked *(new)* have no current
test; add them to a new file,
`astropy/uncertainty/tests/test_distribution_restore.py`, in the same
style (pytest, `numpy.testing.assert_array_equal`,
`astropy.tests.helper.assert_quantity_allclose`, `astropy.utils.NumpyRNGContext`
for seeded randomness). The scenario marked *(doctest)* (S19's class-name
assertion) is also covered by `docs/uncertainty/index.rst`; running that
file's doctests is a useful secondary check but not a substitute for a
pytest assertion in the new test file.

Do not change any public name, signature, file location, or the behavior
of the methods that are already implemented and unchanged in `core.py`
(`pdf_mean`, `pdf_var`, `pdf_mad`, `pdf_smad`, `pdf_percentiles`,
`pdf_histogram`, `__eq__`, `__ne__`, `_not_implemented_or_raise`,
`__getitem__`, `__setitem__`, `dtype`/`astype`, `_DistributionRepr`,
`ScalarDistribution`, `NdarrayDistribution`) or in `distributions.py`
(`normal`, `poisson`, `uniform`) — they call directly into the interfaces
this spec restores and are the fastest way to notice a regression.

Write tests to these principles (the same ones `/verify` scores against —
see `references/test-desiderata.md` and `references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects
  (shapes, values, types, exceptions), not internal storage-dtype layout;
  the suite must survive refactoring of how the sample axis is hidden
  inside the structured storage dtype.
- **Every test can fail** — no copy-pasted expected values, no asserting a
  constant, no tautologies (AP-2, AP-4).
- **Deterministic, isolated, readable** — seed randomness (the existing
  suite uses `astropy.utils.NumpyRNGContext`), no cross-test state, AAA
  structure with inline setup.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Every test function in `astropy/uncertainty/tests/test_distribution.py`
      and `astropy/uncertainty/tests/test_functions.py` passes, with its
      assertions unchanged from what is in the repository today.
- [ ] Every acceptance scenario (S1–S41, including S1b) maps to at least
      one test; the *(new)* scenarios and *(new)* scenario parts — S1b,
      S15 (all three calls), S19 (class-name assertion only), S20, S22
      (the direct-construction `may_share_memory`, negative-stride-copy,
      and zero-stride-`n_samples=1` parts), S23, S30, S31, S34, S35, S36
      (the `n_samples`/`.distribution` assertions only), S41 — are covered
      by tests added in `astropy/uncertainty/tests/test_distribution_restore.py`.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
      the smallest break of its behavior (thought-mutation), e.g. flipping
      `axis=-1` to `axis=0` in `pdf_median`/`pdf_std`, or returning a plain
      array instead of rewrapping as `Distribution` from `__array_function__`.
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
      first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings) in `astropy/uncertainty/core.py` or
      `astropy/uncertainty/function_helpers.py`.

## Trade-offs and Limitations

- Non-`axes=` generalized-ufunc support only needs to keep the sample axis
  trailing and outside the function's core dimensions (S20); it does not
  need to handle every NumPy generalized ufunc's numerical edge cases —
  only that the sample axis is threaded through correctly, which S20's
  `np.matmul` case demonstrates generically for any gufunc signature.
- The exact registry (`FUNCTION_HELPERS` vs. `DISPATCHED_FUNCTIONS` vs.
  `DISTRIBUTION_SAFE_FUNCTIONS`) used for each required `function_helpers.py`
  registration or safe-function delegation is the implementing agent's
  choice; this spec constrains only the observable behavior in the
  Interface Contract and Acceptance Scenarios above. Every NumPy function
  actually exercised by `Distribution` arguments in the two existing test
  files is named in this spec: `concatenate`, `broadcast_arrays`,
  `broadcast_to`, `may_share_memory`, `empty_like` (registered helpers,
  Key Components); `min`/`amin` and `all` (delegate to the default
  implementation via `DISTRIBUTION_SAFE_FUNCTIONS`, per the
  `__array_function__` bullet above and S10); comparison operators and
  arithmetic (ufunc-protocol, per the `__array_ufunc__` bullet). Neither
  `numpy.median` nor `numpy.percentile` is ever called with a `Distribution`
  argument in either test file — the already-implemented, unchanged
  `pdf_median`/`pdf_mad`/`pdf_percentiles` call them directly on the
  unwrapped `self.distribution` array (`core.py:429-431`, `core.py:469`,
  and the Interface Contract's `pdf_median` comment), so neither needs a
  `Distribution`-side registration. Nothing goal-related is fenced off.

## Open Questions

- [ ] None outstanding. (The naming of generated `Quantity`-based
      subclasses as `QuantityDistribution`, previously an open question
      here, is settled by `docs/uncertainty/index.rst` — see S19.)

## References

- In-repo docstring: `astropy/uncertainty/core.py`, `Distribution` class
  docstring, lines 36-55 (background: `https://docs.astropy.org/en/stable/uncertainty/`).
- `astropy/units/quantity_helper/function_helpers.py` — `FunctionAssigner`
  pattern reused by `astropy/uncertainty/function_helpers.py`.
- `docs/uncertainty/index.rst` — doctest-pinned repr/class-name examples.

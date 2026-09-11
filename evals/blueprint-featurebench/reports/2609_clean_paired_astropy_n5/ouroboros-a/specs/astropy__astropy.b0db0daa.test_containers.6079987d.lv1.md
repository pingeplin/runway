# 2609.0001 Uncertainty Distribution Interfaces

**Date:** 2026-09-10
**Status:** draft
**Author:** FeatureBench

## Context

`astropy.uncertainty` (package root `astropy/uncertainty/`) implements a
`Distribution` type: a value (scalar or array) that carries a Monte-Carlo
sample of possible values instead of a single number, so uncertainty
propagates through arithmetic and NumPy functions automatically. Every
`Distribution` stores its samples with the **sample axis** trailing the
storage; the **logical shape** (`.shape`) of a `Distribution` never
includes that axis — `.distribution.shape == .shape + (.n_samples,)`
always holds. Both terms are used consistently throughout this document.

The module is split across:

- `astropy/uncertainty/core.py` — the `Distribution` base class,
  `ScalarDistribution` (mixes in `np.void`), `ArrayDistribution` (mixes in
  `np.ndarray`), `_DistributionRepr`, and the concrete
  `NdarrayDistribution`. `Distribution._generated_subclasses` is a
  cache/registry, keyed by the sample array's type (e.g. `np.ndarray`,
  `Quantity`, `Angle`), of dynamically created `Distribution` subclasses
  (e.g. `QuantityDistribution`) that also inherit the sample class's own
  behavior. `astropy.units.Quantity` and its subclasses (`Angle`, etc.)
  have **no** knowledge of `Distribution` — every hybrid class a test
  exercises (`QuantityDistribution`, an `Angle`-and-`Distribution`
  hybrid) is produced purely by `Distribution.__new__`/`_generated_subclasses`
  inside this file.
- `astropy/uncertainty/function_helpers.py` — the registries
  (`DISTRIBUTION_SAFE_FUNCTIONS`, `FUNCTION_HELPERS`,
  `DISPATCHED_FUNCTIONS`, `UNSUPPORTED_FUNCTIONS`) that
  `Distribution.__array_function__` consults to decide how a given NumPy
  function should treat `Distribution` arguments.
- `astropy/uncertainty/distributions.py` — convenience constructors
  (`normal`, `poisson`, `uniform`) that call `Distribution(...)`,
  `.pdf_mean()`, `.pdf_std()`; out of scope to modify, but they exercise
  everything in this spec.
- `astropy/uncertainty/tests/test_distribution.py` and
  `astropy/uncertainty/tests/test_functions.py` — existing test suites
  that already assert most of the behavior this spec describes. **No
  existing test function's body may be changed** (see the Scenario
  Coverage Index for which scenarios have no current assertion and need
  a brand-new test instead); new test functions may be appended to these
  files or placed in a new file, at the implementing agent's discretion.

In the current state of the repository, the following members are
**entirely absent** from `core.py` (no stub, no docstring — the lines are
blank) even though other code in the same file already calls them:

- `Distribution.__new__` — `Distribution(...)` cannot construct anything.
- `Distribution.n_samples` (property) — read by the already-working
  `dtype` setter/`astype` (`core.py:193,198`) and by `_DistributionRepr`
  (`core.py:645,650,654,660`), but not defined.
- `Distribution._get_distribution_dtype` — called by the same
  already-working `dtype` setter/`astype`, but not defined.
- `Distribution.__array_function__` — no NumPy-function dispatch path.
- `ArrayDistribution.__array_ufunc__` (name fixed by the NumPy protocol;
  not previously declared anywhere) — no ufunc dispatch path, so
  arithmetic, `np.sin`, `np.equal` (used by the already-working `__eq__`),
  and reductions have nothing to route through.
- `ArrayDistribution.distribution` (property override) and
  `ArrayDistribution.view`.
- `Distribution.pdf_median` and `Distribution.pdf_std` — their siblings
  `pdf_mean`, `pdf_var`, `pdf_mad`, `pdf_smad`, `pdf_percentiles`,
  `pdf_histogram` are already implemented in `core.py` and depend on the
  same `self.distribution` property and the same "reduce over `axis=-1`,
  return a plain array/Quantity, not a `Distribution`" contract that
  `pdf_median`/`pdf_std` must follow.

`function_helpers.py` declares its four registries but they are all
empty — no NumPy function is currently registered for `Distribution`.

`ArrayDistribution.__getitem__`, `__setitem__`, `Distribution.__eq__`,
`__ne__`, `astype`, the `dtype` property, `_not_implemented_or_raise`,
and the five already-implemented `pdf_*` methods are present, must not
be modified, and must keep passing every existing test that exercises
them — they are the regression surface for this work.

## Motivation

None of the machinery listed above exists yet, so no `Distribution` can
currently be constructed, combined with anything, or summarized — every
test in `test_distribution.py` and `test_functions.py`, every helper in
`distributions.py`, and any other astropy code depending on
`astropy.uncertainty` is blocked until it is built. `pdf_median` and
`pdf_std` are two of the most common distribution summary statistics,
already documented and tested, and leaving them missing while every
sibling `pdf_*` method works is an inconsistent, half-implemented public
API. NumPy dispatch (`empty_like`, `broadcast_arrays`, `broadcast_to`,
`concatenate`, plus generic ufunc/gufunc support) is required for
`test_functions.py` to pass and for `Distribution` to be usable as a
drop-in array-like anywhere ordinary NumPy code calls these ubiquitous
functions.

## Proposed Solution

### Overview

Restore the missing construction, dispatch, and reduction machinery in
`astropy/uncertainty/core.py`, and populate `astropy/uncertainty/function_helpers.py`,
so that every existing test in the two existing test modules keeps
passing exactly as written, and the additional scenarios below (covering
behavior these tests do not pin down precisely) also pass via newly
added tests. Do not change the public names or signatures fixed by the
Interface Contract. Everything else — private helpers, the exact
registry contents, dtype-construction internals, the general algorithm
behind `view()`'s dtype reinterpretation — is implementation detail the
agent is free to design, subject to the concrete, test-grounded scenarios
below. Where this spec cannot derive a fully general rule without risking
contradiction of a concrete existing test (noted explicitly in Trade-offs),
the literal scenario is the authoritative contract, not any paraphrase of it.

### Key Components

- **`Distribution.__new__(cls, samples)`** — in this order: (1) if
  `samples` is already a `Distribution`, replace it with
  `samples.distribution`; (2) `samples = numpy.asanyarray(samples)`; (3)
  if `samples.ndim == 0`, raise `TypeError`; (4) resolve
  `samples_cls = type(samples)` against `Distribution._generated_subclasses`
  — on a cache hit, reuse the cached class; on a cache miss, create a new
  class combining `Distribution` array behavior with `samples_cls`'s own
  behavior (so the result is simultaneously `isinstance(result, Distribution)`
  and `isinstance(result, samples_cls)`), register it in
  `_generated_subclasses[samples_cls]`, and reuse that same class object
  (not a fresh one) for every later construction from the same
  `samples_cls`. Per the `Distribution` docstring (`core.py:51-53`),
  sample data is not copied unless a view is not possible, which the
  docstring says is "generally, only when the strides of the last axis
  are negative" — whether a transposed-but-positive-stride input (S19)
  is copied or viewed is not pinned further than that docstring's own
  hedge (see Trade-offs).
- **`Distribution.n_samples`** (property) — the fixed length of the
  trailing sample axis (`self.distribution.shape[-1]`).
- **`Distribution._get_distribution_dtype`** — builds the structured
  storage dtype (a `"samples"` field whose own dtype has a `"sample"`
  sub-field of length `n_samples`, matching the base `Distribution.distribution`
  property already implemented as `self["samples"]["sample"]`) for a
  given element dtype and sample count; used by the already-implemented
  `dtype` setter and `astype`. Its exact parameter list is the agent's
  choice as long as it satisfies the two call sites already present at
  `core.py:192-193` (`(dtype, self.n_samples, itemsize=...)`) and
  `core.py:198` (`(dtype, self.n_samples)`).
- **`Distribution.__array_function__(self, function, types, args, kwargs)`**
  — consults `function_helpers.DISTRIBUTION_SAFE_FUNCTIONS`,
  `.FUNCTION_HELPERS`, `.DISPATCHED_FUNCTIONS`, and `.UNSUPPORTED_FUNCTIONS`:
  - in `DISTRIBUTION_SAFE_FUNCTIONS` → defer to
    `super().__array_function__(function, types, args, kwargs)` unchanged
    — functions whose correctness already follows from a correctly
    implemented `__array_ufunc__`/`__new__` once they are registered here
    (registration is required even for these "already work" functions,
    since an unregistered function is indistinguishable from an
    unsupported one and falls through to `_not_implemented_or_raise`
    instead — see S37/S38); `numpy.may_share_memory`, `numpy.min`, and
    `numpy.all` must be registered here for the existing test suite to
    pass (S14, S17, S40);
  - in `FUNCTION_HELPERS` → convert `Distribution` arguments to their
    `.distribution` sample arrays, call `function` on the converted
    arguments, and wrap an array-shaped result back into a `Distribution`
    (scalar and tuple/list results handled per the shared rule below). If
    the registered helper itself raises `NotImplementedError` (its
    documented convention, per the module docstring, for "one of the
    arguments is a distribution when it should not be or vice versa"),
    `__array_function__` catches it and calls
    `self._not_implemented_or_raise(function, types)` instead of letting
    it propagate — this is what turns `numpy.concatenate`'s
    non-`Distribution` `out=` case into a `TypeError` (S26), since a
    plain `ndarray` `out=` is present among `types`;
  - in `DISPATCHED_FUNCTIONS` → call the registered implementation
    directly and return its result as-is;
  - in `UNSUPPORTED_FUNCTIONS`, or in none of the four registries → call
    `self._not_implemented_or_raise(function, types)` (already
    implemented: raises `TypeError` if a non-`Distribution` `ndarray`
    subclass is among `types`, else returns `NotImplemented`).
- **`ArrayDistribution.__array_ufunc__`** — makes elementwise operators
  and NumPy ufuncs operate sample-wise and return `Distribution` results.
  Every constructed `Distribution` is a (possibly 0-d) `ArrayDistribution`;
  `ScalarDistribution` (mixing in `np.void`) is reached only by indexing
  an `ArrayDistribution` down to a single structured element and is out
  of scope for ufunc/comparison dispatch (see Trade-offs).
- **`ArrayDistribution.distribution`** (property) and
  **`ArrayDistribution.view`** — array-subclass-specific overrides of the
  base `Distribution.distribution` property and of `numpy.ndarray.view`,
  needed because default `ndarray.view` does not know how to stay a
  `Distribution`. A single positional argument that is a class rather
  than a dtype (`d.view(SomeClass)`, e.g. `ad.view(u.Quantity)`) is
  treated as the `type=` argument. `view(type=cls)` resolves `cls`
  through `Distribution._generated_subclasses` the same way `__new__`
  does (creating the cache entry if absent), so `d.view(SomeQuantitySubclass)`
  itself is a `Distribution`, not a bare `SomeQuantitySubclass`.
- **`Distribution.pdf_median`** and **`Distribution.pdf_std`** — follow
  the exact pattern already used by `pdf_mean` (calls
  `self.distribution.mean(axis=-1, dtype=dtype, out=out)`) and `pdf_var`
  (calls `self.distribution.var(axis=-1, dtype=dtype, out=out, ddof=ddof)`):
  `pdf_median(self, out=None)` calls `numpy.median(self.distribution, axis=-1, out=out)`;
  `pdf_std(self, dtype=None, out=None, ddof=0)` calls
  `self.distribution.std(axis=-1, dtype=dtype, out=out, ddof=ddof)`.
- **`function_helpers.py` registrations** — register at least
  `numpy.empty_like`, `numpy.broadcast_arrays`, `numpy.broadcast_to`, and
  `numpy.concatenate` via the module's own `function_helper`/
  `dispatched_function` decorators (or direct dict/set assignment), and
  add `numpy.may_share_memory`, `numpy.min`, and `numpy.all` to
  `DISTRIBUTION_SAFE_FUNCTIONS`.

### Data Flow

1. A caller constructs `Distribution(samples)` (directly, or indirectly
   via e.g. `astropy.uncertainty.distributions.normal(...)`). `__new__`
   inspects `type(samples)`, resolves/generates the matching subclass,
   and returns an instance whose storage exposes the samples with the
   sample axis trailing.
2. Arithmetic or a NumPy ufunc is applied. NumPy routes the call through
   `ArrayDistribution.__array_ufunc__`, which unwraps `Distribution`
   operands to their sample arrays, applies the ufunc sample-wise, and
   re-wraps a shaped array result as a new `Distribution`.
3. A non-ufunc NumPy function is applied (e.g. `np.concatenate`,
   `np.broadcast_arrays`, `np.empty_like`). NumPy routes the call through
   `Distribution.__array_function__`, which dispatches per the registry
   rules in Key Components.
4. `.pdf_median()` / `.pdf_std()` (and the other `pdf_*` methods) never
   go through `__array_function__` — they are ordinary `Distribution`
   methods that read `self.distribution` directly, reduce over
   `axis=-1`, and return the result as-is: same type/units as the sample
   array, one fewer dimension, a plain scalar for a 0-d `Distribution`,
   never re-wrapped as a `Distribution`.

### Interface Contract

Exact signatures that must be implemented from scratch (none of the
members below currently exist in `core.py` in any form). This is the
complete, exhaustive list against which the Definition of Done checks
signatures — `_get_distribution_dtype` (Key Components) is deliberately
excluded, since its parameter list is the agent's choice, constrained
only by the two call sites already present at `core.py:192-193,198`:

```python
class Distribution:
    def __new__(cls, samples): ...
    @property
    def n_samples(self): ...
    def __array_function__(self, function, types, args, kwargs): ...
    def pdf_median(self, out=None): ...
    def pdf_std(self, dtype=None, out=None, ddof=0): ...

class ArrayDistribution(Distribution, np.ndarray):
    _samples_cls = np.ndarray

    @property
    def distribution(self): ...

    def view(self, dtype=None, type=None): ...

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs): ...
```

Behavioral requirements not tied to one specific method signature:

- NumPy ufunc `.reduce()` calls with no `axis` given act over all
  logical `Distribution` axes while retaining the sample axis (the
  result is itself a 0-d `Distribution`, never a plain scalar — see S14).
  `.accumulate()` is out of scope (see Trade-offs).
- Two `Distribution` operands can be combined by a ufunc when their
  `n_samples` match, or when one side has `n_samples == 1` (which
  broadcasts against any count — see S15 — mirroring the already-
  implemented `__setitem__`'s use of a 1-sample `Distribution` for
  scalar assignment, `core.py:628-633`); any other mismatch raises
  `ValueError` (see S39). `numpy.concatenate` follows the same rule for
  its `Distribution` arguments' sample counts.
- Generalized ufuncs preserve the sample axis around their core
  dimensions (see S24 for the positive case); passing the `axes=`
  keyword to a generalized ufunc call on a `Distribution` raises
  `NotImplementedError` (see S25).
- `numpy.empty_like` on a `Distribution` preserves the `Distribution`
  type and `n_samples`, honoring a requested `dtype=` for the
  non-sample-axis element type (see S28).
- `numpy.broadcast_arrays` on a mix of `Distribution` and ordinary array
  arguments: every `Distribution` input produces a same-type
  `Distribution` output broadcast to the common logical shape; every
  non-`Distribution` input produces an output of its own original type
  (no sample axis added) broadcast to that same logical shape.
  `subok=True`/`subok=False` controls only whether the *sample* array's
  own subclass metadata (e.g. `Quantity` units) is retained or decays to
  a plain `ndarray`/value — it does not change which arguments become
  `Distribution` results (see S9, S10).
- `numpy.concatenate` on a mix of `Distribution` and ordinary-shaped
  array arguments: ordinary (non-`Distribution`) arrays are repeated
  across the common `Distribution` sample count (added as a new trailing
  axis of that length) before concatenation; `axis=` is interpreted
  against the logical shape, not the raw storage shape (see S7, S8). If
  an `out=` argument is supplied, it must be a `Distribution` — passing
  a non-`Distribution` `out=` raises `TypeError` (see S26, and the
  `NotImplementedError`-to-`TypeError` conversion rule above); a
  `Distribution` `out=` is filled and returned by identity (`is`, see
  S27).
- Across all of the above, an array-valued NumPy result comes back as a
  `Distribution` with a trailing sample axis; a scalar-valued NumPy
  result stays a plain scalar (never a `Distribution`); a tuple/list
  result (e.g. `numpy.broadcast_arrays`) keeps its container type with
  each element wrapped/left bare per the same array-vs-scalar rule.

## Alternatives Considered

### Give `Distribution` a plain extra trailing ndarray dimension instead of a structured dtype

The already-implemented parts of `core.py` (`self["samples"]["sample"]`
in the base `distribution` property; `dtype`/`astype` referring to
`super().dtype["samples"]`) commit to a structured-dtype-based storage
scheme. Switching to a plain extra ndarray dimension would require
rewriting `__getitem__`/`__setitem__`/`dtype`/`astype`, which are
explicitly out of scope and already correct. Not chosen: it contradicts
working, in-scope code.

### Re-derive `pdf_median`/`pdf_std` from `pdf_percentiles`/`pdf_var`

`pdf_median` could be `self.pdf_percentiles(50)`; `pdf_std` could be
`self.pdf_var(...) ** 0.5`. Not chosen: `test_pdf_median`/`test_pdf_std`
assert an `out=` argument is honored and returned by identity, matching
the pattern already used by `pdf_mean`/`pdf_var` (which call
`numpy.mean`/`numpy.var` directly with `out=`); routing through
`pdf_percentiles`, which strips and re-adds units manually, is a
needless detour that risks losing the `out=` identity contract.

### Have functions absent from every registry fall through to `super().__array_function__` instead of `_not_implemented_or_raise`

Silently deferring to `ndarray`'s implementation for any unregistered
function would let genuinely nonsensical operations on distributions
(e.g. treating each per-sample element as if it were the whole value)
silently produce wrong numbers instead of failing loudly. Not chosen:
the already-implemented `_not_implemented_or_raise` exists precisely to
convert "no registered handling" into a `TypeError` whenever another
`ndarray` subclass is present to plausibly claim the operation instead,
which is the behavior S37 requires.

## Security Considerations

None — this is a pure numerical/array-protocol feature with no I/O,
network, deserialization, or credential handling involved.

## Acceptance Scenarios

"Distribution" below means any instance produced by `Distribution(...)`,
whether `NdarrayDistribution` or a generated subclass such as
`QuantityDistribution`. The Scenario Coverage Index table at the end of
this section is the single authoritative source for which existing test
covers each scenario, or whether a new test is required — if any prose
elsewhere in this document seems to suggest different coverage for a
given `S`-number, the table governs.

### Happy Path

- **S1:** Given a `Distribution` `distr` built from a `(4, 10000)`
  normal-sample `Quantity` array, then `distr.shape == (4,)` and
  `distr.distribution.shape == (4, 10000)`; given a plain (non-`Quantity`)
  NumPy array of shape `(4, 1000)`, `Distribution(...)` of it is an
  `NdarrayDistribution`, not a `Quantity`.
- **S2:** Given a `Quantity` array `samples` with unit `ct` and shape
  `(4, 1000)`, when `Distribution(samples)` is called, then the result is
  simultaneously an instance of `Distribution` and of `Quantity`, and its
  `.value` is itself a `Distribution` whose `.distribution` equals the
  original plain-array samples.
- **S3:** Given `Distribution` arrays `da`, `db` independently
  constructed from plain (non-`Quantity`) sample arrays, and a plain
  array `c`, when `bda, bdb, bdc = numpy.broadcast_arrays(da, db, c, subok=True)`
  is called, then `type(bda) is type(bdb) is type(da)` — i.e. repeated
  construction from the same sample type reuses one cached generated
  class, not a fresh one per construction.
- **S4:** Given an existing `Distribution` `pd`, when `pd << u.ct` is
  evaluated, then the result is a `Distribution`-and-`Quantity` whose
  `.value.distribution` equals `pd.distribution` cast to float.
- **S5:** Given a `Distribution` `distr` built from a `(4, 10000)` normal
  sample array, when `.pdf_median()` and `.pdf_std()` are called with no
  arguments, then each returns a plain `Quantity` (not a `Distribution`)
  of shape `(4,)` matching `numpy.median`/`numpy.std` of the raw sample
  array along `axis=-1`, within tolerance.
- **S6:** Given the same `distr`, when `.pdf_median(out=out)` /
  `.pdf_std(ddof=1, out=out)` are called with a pre-allocated `out`
  Quantity, then the method returns `out` itself (`is`) filled with the
  correct values, and `ddof` is honored by `pdf_std`.
- **S7:** Given `Distribution` arrays `da`, `db` built from ordinary
  arrays, when `numpy.concatenate((da, db[np.newaxis]), axis=0)` is
  called, then the result is a `Distribution` whose `.distribution`
  equals `numpy.concatenate` of the two raw sample arrays along
  `axis=0` (sample axis preserved, trailing, untouched).
- **S8:** Given a `Distribution` `da` with logical shape `(2, 3)` and
  `n_samples == 4`, and a plain array (or `Quantity`) `c` of shape
  `(2, 1)`, when `numpy.concatenate((c, da), axis=1)` is called, then the
  result is a `Distribution` with logical shape `(2, 4)` whose
  `.distribution` equals
  `numpy.concatenate((broadcast_to(c[..., np.newaxis], (2, 1, 4), subok=True), da.distribution), axis=1)`
  — holds for both the plain-array (`ArraySetup`) and `Quantity`-backed
  (`QuantitySetup`) variants, `subok=True` preserving `c`'s units in the
  latter.
- **S9:** Given `Distribution` arrays `da`, `db` and plain array `c` of
  compatible broadcast shapes, when
  `numpy.broadcast_arrays(da, db, c, subok=True)` is called, then `da`
  and `db` each produce a same-type `Distribution` output of the common
  logical shape, `c` produces an output of `type(c)` (not `Distribution`)
  of that same logical shape, and each result's `.distribution` (or
  itself, for `c`) equals broadcasting the corresponding raw array.
- **S10:** Given the same setup as S9 but `subok=False`, when
  `numpy.broadcast_arrays(da, db, c, subok=False)` is called, then `da`
  and `db` still each produce a `Distribution` output, but their
  `.distribution` decays to plain `numpy.ndarray` (losing e.g. `Quantity`
  units), and `c`'s output decays to plain `numpy.ndarray` too — numeric
  values still match broadcasting the raw arrays in every case.
- **S11:** Given a `Distribution` `db` and a target logical shape, when
  `numpy.broadcast_to(db, shape, subok=True)` is called, then the result
  is a `Distribution` of that `.shape` whose `.distribution` equals
  `numpy.broadcast_to` of the raw sample array to `shape + (db.n_samples,)`.
- **S12:** Given a `Distribution` `angles` built from `[90.0, 30.0, 0.0] * u.deg`,
  when `numpy.sin(angles)` is called, then the result is simultaneously a
  `Distribution` and a `u.Quantity` (elementwise `sin` applied
  sample-wise), equal to `Distribution(numpy.sin(angles.distribution))`.
  (Regression test for gh-12336.)
- **S13:** Given two `Distribution`s `d1`, `d2` (or a `Distribution` and a
  plain `Quantity`), when `d1 + d2` (or `d1 + quantity`) is evaluated,
  then the result is a `Distribution` whose `pdf_median()`/`pdf_var()`
  match the median/variance of the (unit-converted) elementwise sum of
  the underlying sample arrays.
- **S14:** Given a `Distribution` `p_dist`, when `numpy.min(p_dist)` is
  called with no `axis`, then the result is itself a 0-d `Distribution`
  (`isinstance(result, Distribution)`, `.shape == ()`), not a plain
  scalar — the sample axis is retained while every logical axis is
  reduced.
- **S15:** Given `Distribution`s `d1000` (`n_samples == 1000`) and `d1`
  (`n_samples == 1`) of the same logical shape, when `d1000 + d1` is
  evaluated, then the result has `n_samples == 1000` and its
  `.distribution` equals `d1000.distribution + d1.distribution` with
  `d1`'s single sample broadcast against each of `d1000`'s 1000 samples.
- **S16:** Given the `n_samples` property on a `Distribution` built from
  a `(4, 10000)` sample array, then `.n_samples == 10000`.
- **S17:** Given a `Distribution` `d1` and a view of it `d2` (e.g.
  `d2 = d1.view(...)`) that share underlying storage, when
  `numpy.may_share_memory(d1, d2)` is called, then it returns `True`.

### Edge Cases

- **S18:** Given a 1-D sample array (e.g. shape `(1000,)`), when
  `Distribution(samples)` is called, then the sole dimension is treated
  as the sample axis, producing a 0-d `ArrayDistribution`
  (`NdarrayDistribution`/`QuantityDistribution`, **not**
  `ScalarDistribution`), on which `.view(...)` and masked assignment
  (`d[d > 50] = ...`) work exactly as on a higher-dimensional
  `ArrayDistribution`. `ScalarDistribution` is reached only by indexing
  an `ArrayDistribution` down to a single structured element (e.g.
  `arr_distribution[3]`), never by direct construction —
  `ArrayDistribution.__getitem__`'s `isinstance(result, np.void)` branch
  (`core.py:608-609`) is the only path that produces one.
- **S19:** Given a `Distribution` `d` constructed from a transposed,
  non-contiguous-last-axis array (e.g. `parr_t.T`, or a `Quantity`
  built the same way), then construction succeeds (contrast with S35,
  where a genuinely 0-d array is rejected outright), producing a
  `Distribution` whose `.shape` and `.n_samples` match the transposed
  array's leading dimensions and trailing dimension respectively, and
  whose `.distribution` equals the transposed array. Whether
  `numpy.may_share_memory(d, parr_t.T)` is `True` or `False` is not
  pinned by this scenario (see Trade-offs) — only the resulting values
  are.
- **S20:** Given a `Distribution` `d`, when `d.view()` is called with no
  arguments, then the result's exact class is `d.__class__`, it is a new
  `Distribution` instance, and `numpy.may_share_memory(result, d)` is
  `True`.
- **S21:** Given a complex-valued `Distribution` `c` (built from 3
  complex128 samples, `.shape == ()`), when `c.view("2f8")` is called,
  then the result's `.shape` is `(2,)`, memory is shared with `c`, and
  `.distribution` equals `numpy.moveaxis(c.distribution.view("2f8"), -2, -1)`;
  viewing that result back as `"c16"` recovers the original
  `.distribution`.
- **S22:** Given a `Distribution` `uint32` built from a `(2, 2)` `uint32`
  array (logical shape `(2,)`, `n_samples == 2`), when `uint32.view("4u1")`
  is called, then the result's `.shape` is `(2, 4)`, memory is shared,
  and `.distribution` equals `numpy.moveaxis(uint32.distribution.view("4u1"), -2, -1)`;
  viewing that result back as `"u4"` (`uint8.view("u4")`, no transpose)
  recovers `uint32`'s `.distribution` and shares memory with it; but
  first transposing that `"4u1"` result (`uint8.T`) and then attempting
  `.view("u4")` raises `ValueError` with a message containing "last axis
  must be contiguous".
- **S23:** Given a `Distribution` `distr` with a structured element
  dtype (fields `"a"`, `"b"`), when `Distribution(structured_samples)` is
  constructed, then `distr.shape` excludes the sample axis, `distr.n_samples`
  equals the trailing dimension size, and `distr.distribution` equals
  the original structured sample array with the sample axis trailing.
- **S24:** Given a `Distribution` `d` with 2-D logical shape `(m, m)`
  (each logical element a square matrix, sample axis trailing beyond
  that), when `numpy.matmul(d, d)` is called with no `axes=`, then the
  result is a `Distribution` with logical shape `(m, m)` and the same
  `n_samples` as `d`, whose value for each sample equals the plain
  `numpy.matmul` of that sample's two `(m, m)` matrices.
- **S25:** Given the same `d` as S24, when `numpy.matmul(d, d, axes=[(-2, -1), (-2, -1), (-2, -1)])`
  is called (the `axes=` keyword to a generalized ufunc), then
  `NotImplementedError` is raised.
- **S26:** Given a `Distribution` `da` and a plain (non-`Distribution`)
  array `arr` of a matching logical shape, when
  `numpy.concatenate((da, da), axis=0, out=arr)` is called (a
  non-`Distribution` `out=`), then `TypeError` is raised — the
  registered `concatenate` helper raises `NotImplementedError` internally
  on seeing a non-`Distribution` `out=`, which `__array_function__`
  converts to `TypeError` via `_not_implemented_or_raise` because `arr`'s
  plain `ndarray` type is present among the call's argument types.
- **S27:** Given a preallocated `Distribution` `out` of the correct
  resulting shape/`n_samples`, when
  `numpy.concatenate((da, db), axis=0, out=out)` is called, then the
  return value is `out` itself (`is`), populated with the concatenated
  samples.
- **S28:** Given a `Distribution` `d`, when `numpy.empty_like(d)` is
  called, then `type(result) is type(d)`, `result.shape == d.shape`, and
  `result.n_samples == d.n_samples`; when called with an explicit
  `dtype="f4"`, `result.dtype == np.dtype("f4")` while `result.n_samples`
  is unchanged.
- **S29:** Given a `Distribution` `distr` (from 3 float64 samples,
  `.shape == ()`), when `distr.view(np.dtype("2i8"))` or
  `distr.view(np.dtype("2i8"), distr.__class__)` is called, then
  `ValueError` is raised with a message containing "can only be viewed".
  This holds for `Distribution` subclasses too (e.g. an `Angle`-backed
  distribution).
- **S30:** Given a `Distribution` `ad` that is also an `Angle`, when
  `ad.view(u.Quantity)` is called, then the result is `Quantity`-and-
  `Distribution` but not `Angle`; viewing that result's own class
  (`qd.__class__`) or `(qd.dtype, qd.__class__)` round-trips to an
  equal-samples `Distribution` of that same non-`Angle` type.
- **S31:** Given a `Distribution` `d` and a plain float `other` (no
  `__array_ufunc__` override), when `d == other`, `d != other`, or
  `d > other` is evaluated (parametrized over `operator.eq`, `.ne`, `.gt`),
  then the result equals `Distribution(op(d.distribution, other))`.
- **S32:** Given an `Angle`-backed `Distribution` `ad`, when `ad + ad` is
  evaluated, the result stays an `Angle`-and-`Distribution`; when
  `ad * ad` is evaluated, the result decays to a plain `Quantity`-and-
  `Distribution` (not `Angle`); when `ad += ad` is evaluated, `ad` is
  mutated in place and stays an `Angle`; when `ad *= ad` is evaluated,
  `astropy.units.UnitTypeError` is raised.
- **S33:** Given a `Distribution` `d`, when `d[d > 50] = 0.0` (masked
  assignment) or `d[d > 50] *= -1.0` (masked in-place op) is evaluated,
  then only the elements satisfying the mask are changed, matching the
  same operation performed with `d.distribution` and a per-sample mask.
- **S34:** Given advanced (fancy) integer-array indices, when a
  `Distribution` `d` (built over a plain array, a `Quantity`, or a
  structured dtype) is indexed as `d[idx]` or assigned `d[idx] = value`,
  then the result/effect matches applying the same index to
  `d.distribution` (sample axis excluded from the index).

### Error Scenarios

- **S35:** Given a genuinely scalar array (0-d, e.g. `parr.ravel()[0]`),
  when `Distribution(scalar)` is called, then `TypeError` is raised with
  a message matching "Attempted to initialize a Distribution with a
  scalar".
- **S36:** Given a `Distribution` `d` and an operand `other` whose class
  sets `__array_ufunc__ = None` and defines its own
  `__eq__`/`__ne__`/`__lt__`, when `d == other`, `d != other`, or
  `d > other` is evaluated, then Python defers to `other`'s comparison
  method (result is `other`'s return value, e.g. the string `"eq"`), not
  `Distribution`'s. This exercises the already-implemented
  `Distribution.__eq__`/`__ne__` cooperating with the ufunc dispatch this
  spec adds.
- **S37:** Given a `Distribution` `d` and a plain (non-`Distribution`)
  `ndarray` `arr`, when `numpy.dot(d, arr)` is called (a function
  registered in none of `DISTRIBUTION_SAFE_FUNCTIONS`, `FUNCTION_HELPERS`,
  or `DISPATCHED_FUNCTIONS` — matrix products of per-sample distributions
  are not given special meaning), then `TypeError` is raised, via
  `_not_implemented_or_raise`, specifically because a non-`Distribution`
  `ndarray` is among the argument types.
- **S38:** Given the same unregistered `numpy.dot` and a call with
  **only** `Distribution` arguments (no plain `ndarray`/`Quantity`
  co-argument) — i.e. directly invoking
  `d.__array_function__(numpy.dot, (type(d),), (d, d), {})` — then the
  return value is `NotImplemented`, not an exception, per
  `_not_implemented_or_raise`'s "no other `ndarray` subclass to defer to"
  branch.
- **S39:** Given two `Distribution`s with different `n_samples`, neither
  equal to `1`, when a ufunc (e.g. `d1 + d2`) is applied to them, then
  `ValueError` is raised.

### Additional Coverage

- **S40:** Given `p_min`, a 0-d boolean-valued `Distribution` produced by
  `p_dist >= 0` where every sample is non-negative, when `numpy.all(p_min >= 0)`
  is evaluated inside `assert np.all(p_min >= 0)`, then it does not raise
  and the assertion passes (this scenario does not pin whether
  `numpy.all`'s return value is a plain `bool` or a 0-d `Distribution` —
  only that dispatch succeeds and the truth-value check passes).
- **S41:** Given a `QuantityDistribution` `distr` built from
  `10 * u.cm` with `n_samples=100`, when `distr.to(u.m)` (which calls
  `distr.view(np.ndarray)` internally as part of `Quantity`'s own unit
  conversion) is evaluated, then the result is itself a `Distribution`
  (not a bare structured `ndarray`) that is also a `Quantity` in
  meters, whose `pdf_mean()` equals `distr.pdf_mean().to(u.m)`; the same
  holds for `.to_value(u.m)`; and calling `.to`/`.to_value` on a
  plain-array (non-`Quantity`) `Distribution` raises `AttributeError`
  (unchanged `Quantity`-only behavior, not something this spec adds).

### Scenario coverage index

| Scenario | Source |
|---|---|
| S1 | `TestDistributionStatistics.test_shape` (shape/`.distribution.shape` clause); new test required for the `NdarrayDistribution`-not-`Quantity` clause (`TestInit.test_numpy_init` exercises this construction but asserts nothing) |
| S2 | `TestInit.test_quantity_init` |
| S3 | `TestBroadcast.test_broadcast_arrays` (`type(bda) is type(bdb) is type(self.da)`) |
| S4 | `TestInit.test_quantity_init_with_distribution` |
| S5, S6 | `TestDistributionStatistics.test_pdf_median`, `.test_pdf_std` |
| S7 | `TestConcatenation.test_concatenate` (+ `TestQuantityDistributionConcatenation`) |
| S8 | `TestConcatenation.test_concatenate_not_all_distribution` (+ `TestQuantityDistributionConcatenation`) |
| S9 | `TestBroadcast.test_broadcast_arrays` (+ `TestQuantityDistributionBroadcast`) |
| S10 | `TestBroadcast.test_broadcast_arrays_subok_false` |
| S11 | `TestBroadcast.test_broadcast_to` |
| S12 | `test_scalar_quantity_distribution` |
| S13 | `TestDistributionStatistics.test_add_quantity`, `.test_add_distribution` |
| S14 | `test_helper_poisson_samples` |
| S15, S39 | new test required (n_samples broadcast/mismatch rule) |
| S16 | `TestDistributionStatistics.test_n_samples` |
| S17 | `test_distr_angle_view_as_quantity`, `test_distr_view_different_dtype1/2` (each asserts `may_share_memory(..., True)` on a view/source pair) |
| S18 | `test_distr_angle`, `test_distr_angle_view_as_quantity`, `test_distr_cannot_view_new_dtype`, `TestComparison`, `TestSetItemWithSelection` (constructor calls at `test_distribution.py:405,427,488,516,543,548`) + `ArrayDistribution.__getitem__` (`core.py:608-609`) |
| S19 | new test required — `TestInit.test_numpy_init_T`/`.test_quantity_init_T` exercise the same construction but assert nothing; add a new test (not an edit to these) with the shape/`n_samples`/value assertions this scenario requires |
| S20 | `test_distr_angle_view_as_quantity` ("Simple view with no arguments") |
| S21 | `test_distr_view_different_dtype1` |
| S22 | `test_distr_view_different_dtype2` |
| S23 | `TestStructuredAdvancedIndex.test_init` |
| S24 | new test required (positive gufunc core-dimension handling) |
| S25 | new test required (gufunc `axes=` rejection) |
| S26, S27 | new test required (`concatenate` `out=`) |
| S28 | new test required (`empty_like`) |
| S29 | `test_distr_cannot_view_new_dtype` |
| S30 | `test_distr_angle_view_as_quantity` |
| S31 | `TestComparison.test_distribution_can_be_compared_to_non_distribution` |
| S32 | `test_distr_angle` |
| S33 | `TestSetItemWithSelection.test_setitem`, `.test_inplace_operation` |
| S34 | `TestGetSetItemAdvancedIndex`, `TestQuantityDistributionGetSetItemAdvancedIndex`, `TestStructuredAdvancedIndex`, `TestStructuredDistribution`, `TestStructuredQuantityDistribution` |
| S35 | `test_init_scalar` |
| S36 | `TestComparison.test_distribution_comparison_defers_correctly` |
| S37, S38 | new test required (`numpy.dot` as an unregistered function) |
| S40 | `test_helper_poisson_samples` (`assert np.all(p_min >= 0)`) |
| S41 | `test_distr_to`, `test_distr_to_value`, `test_distr_noq_to`, `test_distr_noq_to_value` |

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*. A green suite that passes for
> the wrong reason does not satisfy this contract — `/verify` will hunt
> for vacuous tests by asking, of each behavior, "what is the smallest
> change that breaks this, and would any test catch it?"

Use the Scenario Coverage Index as the single source of truth for what
is already covered versus what needs a new test. Do not change any
existing test function's body in `test_distribution.py`/`test_functions.py`
to make them pass — if a test appears to require behavior that
contradicts this spec, re-read the test and the spec, not the other way
around. For every scenario the index marks "new test required" —
including S1's `NdarrayDistribution` clause, S19, S24, S25, S26, S27,
S28, S37, and S38 — add a brand-new test function (in these files or a
new file, at your discretion; never by editing `test_numpy_init`,
`test_numpy_init_T`, or any other existing test body), in the same
class-based, `ArraySetup`/`QuantitySetup`-parametrized style already used
in `test_functions.py`.

Implementation notes (not prescriptive, but consistent with what already
works in `core.py`):

- `core.py` already imports `normalize_axis_index`, `_parse_gufunc_signature`,
  and `DummyArray` (with a `NUMPY_LT_2_0` compatibility branch) at the
  top of the file but does not yet use them anywhere — they exist to
  support generalized-ufunc signature parsing, axis handling, and
  low-level stride manipulation inside the new `__array_ufunc__` and
  `view()` (relevant to S21/S22/S24/S25).
- `function_helpers.py` already provides `function_helper` and
  `dispatched_function` `FunctionAssigner` instances (bound to
  `FUNCTION_HELPERS`/`DISPATCHED_FUNCTIONS`) — use them, or direct
  dict/set assignment, to register the functions in Key Components. Any
  helper/dispatched function given a docstring is auto-added to
  `__all__` at the bottom of the file — keep that mechanism intact.
- Keep the SOLID/no-dead-code project conventions: no stub bodies, no
  speculative parameters beyond the given signatures, and do not weaken
  `_not_implemented_or_raise`'s existing `TypeError`/`NotImplemented`
  split (S37, S38 depend on it exactly as written).

Write tests to the project's `pytest` conventions (class-based fixtures
via `setup_class`, `assert_array_equal`/`assert_quantity_allclose` from
`numpy.testing`/`astropy.tests.helper`) and to these principles (the same
ones `/verify` scores against — see `references/test-desiderata.md` and
`references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects
  (`.distribution`, `.shape`, `.n_samples`, exception type/message), not
  internal dtype layout or private helper names.
- **Every test can fail** — no copy-pasted expected values, no asserting
  a constant, no tautologies (AP-2, AP-4).
- **Deterministic, isolated, readable** — the existing suite seeds
  randomness via `astropy.utils.NumpyRNGContext`; follow that pattern for
  any new randomized test.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Every existing test function in
      `astropy/uncertainty/tests/test_distribution.py` and
      `astropy/uncertainty/tests/test_functions.py` still has its
      original body and is green.
- [ ] Every acceptance scenario (S1…S41) maps to at least one test per
      the Scenario Coverage Index (existing or newly added).
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
      the smallest break of its behavior (thought-mutation), e.g.
      flipping `axis=-1` to `axis=0` in `pdf_median`/`pdf_std`, or
      dropping the `TypeError`/`NotImplemented` distinction in S37/S38.
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
      first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings) in `core.py` or `function_helpers.py`.
- [ ] `Distribution.__new__`, `Distribution.n_samples`,
      `Distribution.__array_function__`, `Distribution.pdf_median`,
      `Distribution.pdf_std`, `ArrayDistribution.distribution`,
      `ArrayDistribution.view`, and `ArrayDistribution.__array_ufunc__`
      match the Interface Contract's signatures — no renamed parameters,
      no added required arguments.

## Trade-offs and Limitations

- `distributions.py`'s stretch-goal exact-distribution tests
  (`test_helper_normal_exact`, `test_helper_poisson_exact`) are already
  `pytest.skip`-marked in the existing suite and are explicitly out of
  scope.
- **`view()`'s general dtype-reinterpretation rule is intentionally not
  stated as a formula.** S21 (complex128 → `"2f8"`, same total itemsize,
  0-d source) and S22 (`uint32` → `"4u1"` → `"u4"`, walking itemsize
  ratios across a real logical axis, plus the transposed-non-contiguous
  failure) do not reduce to one simple, verifiably-correct-in-both-cases
  statement; deriving one risks silently contradicting whichever concrete
  case it wasn't checked against. The four concrete view scenarios (S20,
  S21, S22, S29) are individually exact and are the full, authoritative
  contract for `view()`'s dtype-changing behavior — an implementation
  that satisfies them individually satisfies this spec even if no single
  general paragraph describes all of them at once.
- `ArrayDistribution.__array_ufunc__`/comparison dispatch on a bare
  `ScalarDistribution` instance (e.g. calling a ufunc directly on the
  single-element result of iterating a 1-D `Distribution`) is out of
  scope — no existing test performs a ufunc or comparison directly on
  such an object; only `isinstance`/type checks
  (`test_index_assignment_quantity`/`_array`) and structured-field
  indexing (`TestStructuredDistribution`, which goes through
  `ArrayDistribution.__getitem__`, not `ScalarDistribution`'s own
  protocol) are required to work.
- `numpy.ufunc.accumulate` (as opposed to `.reduce`) on a `Distribution`
  is out of scope — no existing test exercises it, and NumPy's own
  `accumulate` only supports a single integer `axis`, which does not
  extend naturally to "all logical axes" the way `.reduce()`'s axis-free
  call does.
- `numpy.dot` (S37/S38) is a concrete stand-in for "a function in none
  of the four registries"; the spec does not mandate that `dot`
  specifically stays unregistered forever, only that *some* function
  reachable this way behaves per S37/S38 — if a future change registers
  `numpy.dot` with real Distribution semantics, S37/S38 should be
  re-pointed at a different, still-unregistered function rather than
  deleted.

## Open Questions

- [ ] None outstanding. Registry membership for functions beyond those
      named in Key Components is left to the agent's judgment as long as
      S1–S41 pass and no existing test regresses.

## References

- `astropy/uncertainty/core.py` — target file for all class/method changes.
- `astropy/uncertainty/function_helpers.py` — target file for NumPy
  function registrations.
- `astropy/uncertainty/distributions.py` — downstream consumer, unchanged.
- `astropy/uncertainty/tests/test_distribution.py` — primary acceptance
  test source.
- `astropy/uncertainty/tests/test_functions.py` — NumPy dispatch
  acceptance test source.
- `astropy/units/quantity_helper/function_helpers.py` — sibling
  `FunctionAssigner`-based registry pattern for `Quantity`; structural
  reference only — `Distribution`'s `FUNCTION_HELPERS`/`DISPATCHED_FUNCTIONS`
  contract (documented at the top of `astropy/uncertainty/function_helpers.py`)
  has a different return shape (`args, kwargs, out` / a bare result, not
  `args, kwargs, unit, out`).

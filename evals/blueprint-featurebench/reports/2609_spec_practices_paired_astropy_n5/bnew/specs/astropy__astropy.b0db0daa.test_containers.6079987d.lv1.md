# 2609.0001 Uncertainty Distribution Interfaces

**Date:** 2026-09-18
**Status:** draft
**Author:** FeatureBench

## Context

`astropy/uncertainty/` implements `Distribution`, a value type that carries a
Monte-Carlo sample of possible values (the "trailing sample axis") instead of
a single number, so that arithmetic and NumPy functions propagate
uncertainty. `Distribution.__new__` dispatches to a dynamically generated
subclass keyed by the array-like type of the input samples — `ArrayDistribution`
(a `np.ndarray` mixin, generating e.g. `NdarrayDistribution`,
`QuantityDistribution`) for anything array-like, or `ScalarDistribution` (a
`np.void` mixin) for 0-d elements reached via indexing. The samples are
stored as a structured dtype with the sample axis folded into a hidden
field, so that ordinary NumPy machinery (shape, indexing, ufuncs) operates on
the *logical* shape (sample axis stripped) while `.distribution` exposes the
raw sample array.

Two files that back this mechanism have had a subset of their method bodies
stripped to blank lines, while everything else around them is intact:

- `astropy/uncertainty/core.py` — `Distribution.__new__`,
  `Distribution.__array_function__`, `Distribution.pdf_median`,
  `Distribution.pdf_std`, `ArrayDistribution.distribution`,
  `ArrayDistribution.view`, and the NumPy ufunc dispatch hook that makes
  arithmetic on `Distribution` instances work.
- `astropy/uncertainty/function_helpers.py` — the registry entries
  (`FUNCTION_HELPERS` / `DISPATCHED_FUNCTIONS` / `DISTRIBUTION_SAFE_FUNCTIONS`)
  that teach `np.concatenate`, `np.broadcast_arrays`, `np.broadcast_to`, and
  `np.empty_like` how to handle `Distribution` arguments.

Everything else in the subpackage — `pdf_mean`, `pdf_var`, `pdf_mad`,
`pdf_smad`, `pdf_percentiles`, `pdf_histogram`, `ArrayDistribution.__getitem__` /
`__setitem__`, the `dtype` property/setter, `astype`, the repr machinery in
`_DistributionRepr`, and the distribution-creation helpers in
`astropy/uncertainty/distributions.py` (`normal`, `uniform`, `poisson`) —
already has working bodies and is unaffected.

Note, however, that two names *called from that intact code* are themselves
inside the stripped regions and therefore have to come back with the exact
names the callers use:

- `n_samples` — read by `_DistributionRepr.__repr__` / `__str__` /
  `_repr_latex_` (`core.py:645`, `650`, `654`, `660`), by the `dtype` setter
  (`core.py:193`), and by acceptance scenarios S1, S3, S14, S18, S19, S28.
  No definition of it survives in `core.py`.
- `_get_distribution_dtype` — called as `self._get_distribution_dtype(dtype,
  self.n_samples, itemsize=...)` by the `dtype` setter (`core.py:192-193`)
  and as `self._get_distribution_dtype(dtype, self.n_samples)` by `astype`
  (`core.py:198`). No definition of it survives in `core.py`, so setting
  `.dtype` or calling `.astype(...)` on a `Distribution` raises
  `AttributeError` until the stripped region is restored.

## Motivation

`Distribution.__new__` is the sole constructor for every `Distribution`
subclass. With it stripped, `Distribution(...)` cannot produce an instance at
all, so every test in `astropy/uncertainty/tests/test_distribution.py` and
`astropy/uncertainty/tests/test_functions.py` errors before it can assert
anything — including tests for the already-implemented methods listed above.
Restoring `__new__`, the ufunc/`__array_function__` dispatch hooks, the two
missing `pdf_*` reductions, and the `n_samples` / `_get_distribution_dtype`
names the intact code calls makes the subpackage importable and usable
again and lets the existing (unmodified) test suite exercise the rest of the
package as intended.

## Proposed Solution

### Overview

Implement eight units of behavior in `core.py` — construction (`__new__`),
NumPy high-level function dispatch (`__array_function__`), NumPy ufunc
dispatch (the standard `__array_ufunc__` hook), sample-array access
(`ArrayDistribution.distribution`), type-preserving viewing
(`ArrayDistribution.view`), two reductions (`pdf_median`, `pdf_std`), and the
two names the intact code already calls (`n_samples`,
`_get_distribution_dtype`) — plus the `function_helpers.py` registry entries needed for
`np.concatenate`, `np.broadcast_arrays`, `np.broadcast_to`, and
`np.empty_like` to round-trip through `__array_function__` correctly.

### Key Components

- **`Distribution.__new__`** (`astropy/uncertainty/core.py`, blank region
  currently spanning lines 58–181) — selects/creates the concrete subclass
  for the input sample type via `Distribution._generated_subclasses`,
  constructs the structured-dtype backing store with the sample axis made
  trailing, and shares the input's storage via a view where the trailing
  axis layout allows it.
- **`Distribution.__array_function__`** (same blank region) — the
  `__array_function__` protocol entry point; consults
  `function_helpers.DISTRIBUTION_SAFE_FUNCTIONS`,
  `function_helpers.FUNCTION_HELPERS`, and
  `function_helpers.DISPATCHED_FUNCTIONS`, and falls back to
  `Distribution._not_implemented_or_raise` (already implemented at
  `core.py:339`) when nothing recognizes the function.
- **`__array_ufunc__`** (same blank region or the `ArrayDistribution` blank
  region at `core.py:527–591`) — the standard NumPy ufunc-override hook;
  unwraps `.distribution` from every `Distribution` input, broadcasts
  ordinary (non-Distribution) array inputs across the sample axis, invokes
  the ufunc, and rewraps array results.
- **`ArrayDistribution.distribution`** (inside the `ArrayDistribution` blank
  region, `core.py:527–591`) — property returning the raw sample-array view.
  The base `Distribution.distribution` at `core.py:182-184` is intact
  (`return self["samples"]["sample"]`, no docstring) and serves
  `ScalarDistribution`; `ArrayDistribution` needs its own override because
  `ArrayDistribution.__getitem__` routes the `"samples"` key straight back to
  `.distribution` (`core.py:592-596`), so the base version would recurse.
- **`Distribution.n_samples`** (blank region, alongside `dtype`/`astype`) —
  the number of samples per element, as a plain `int`; read by intact repr
  code and by most acceptance scenarios.
- **`Distribution._get_distribution_dtype`** (blank region) — builds the
  structured backing dtype; the name and call shape are fixed by the intact
  `dtype` setter and `astype` (see Interface Contract), not free for the
  implementing agent to choose.
- **`ArrayDistribution.view`** (`core.py:521` region) — override of
  `np.ndarray.view` that keeps the result a `Distribution` subclass.
- **`Distribution.pdf_median` / `Distribution.pdf_std`** (`core.py`, blank
  regions around lines 202–338 and 373–416, alongside the intact
  `pdf_mean`/`pdf_var`) — `numpy.median` / `numpy.std` applied along
  `axis=-1` of `.distribution`.
- **`function_helpers.py` registry entries** (blank region at lines 75–151)
  — helpers for `np.concatenate`, `np.broadcast_arrays`, `np.broadcast_to`,
  and `np.empty_like`, registered via the existing `function_helper` /
  `dispatched_function` `FunctionAssigner` decorators (`function_helpers.py:71-72`).

### Data Flow

1. `Distribution(samples)` → `__new__` inspects `type(samples)` (or, if
   `samples` is already a `Distribution`, its exposed `.distribution`),
   looks up or generates the matching subclass, and returns an instance
   whose logical shape excludes the trailing sample axis.
2. A NumPy high-level function (e.g. `np.concatenate`) called with a
   `Distribution` argument → NumPy's protocol calls `__array_function__` →
   the registry entry rewrites args/kwargs in terms of raw distribution
   arrays (aligning sample counts, broadcasting non-Distribution operands
   across samples), calls the plain NumPy function, and rewraps a
   shaped result as a `Distribution`; a scalar result is returned unwrapped;
   tuple/list results keep their container type.
3. A NumPy ufunc (e.g. `+`, `np.sin`) called with a `Distribution` operand →
   `__array_ufunc__` unwraps `.distribution` from each `Distribution` input,
   leaves ordinary array inputs to broadcast normally against the sample
   axis, calls the ufunc, and wraps a shaped array result back into a
   `Distribution` with the sample axis trailing.

### Interface Contract

The following signatures and docstrings are fixed by the calling test suite
and by the intact code in `core.py`, and must be implemented exactly as declared (bodies only — do not change
signatures, decorators, or class bases):

```python
# astropy/uncertainty/core.py

class Distribution:
    def __new__(cls, samples):
        """See docstring in core.py for full contract:
        - rejects 0-d (scalar) `samples` with TypeError
          ("Attempted to initialize a Distribution with a scalar")
        - dispatches to NdarrayDistribution / QuantityDistribution / other
          subclass based on type(samples), reusing subclasses across calls
        - reconstructs from an existing Distribution's exposed samples
        - shares storage via a view when the trailing-axis layout allows it,
          copies otherwise
        """

    def __array_function__(self, function, types, args, kwargs):
        """Standard __array_function__ protocol entry point; see docstring
        in core.py for dispatch-table and fallback semantics."""

    @property
    def n_samples(self):
        """Number of samples per element, as a plain int."""

    def _get_distribution_dtype(dtype, n_samples, itemsize=...):
        """Structured backing dtype for `n_samples` samples of `dtype`.

        The name and the two call shapes are fixed by the intact callers:
        - `self._get_distribution_dtype(dtype, self.n_samples, itemsize=...)`
          from the `dtype` setter (core.py:192-193)
        - `self._get_distribution_dtype(dtype, self.n_samples)`
          from `astype` (core.py:198)
        so `itemsize` needs a default, whose value is unconstrained.
        """

    def pdf_median(self, out=None):
        """numpy.median(self.distribution, axis=-1, out=out)."""

    def pdf_std(self, dtype=None, out=None, ddof=0):
        """numpy.std(self.distribution, axis=-1, dtype=dtype, out=out, ddof=ddof)."""


class ArrayDistribution(Distribution, np.ndarray):
    _samples_cls = np.ndarray

    @property
    def distribution(self):
        """Raw sample array, sample axis trailing; shares storage where
        a view is possible; preserves sample-array subclass metadata."""

    def view(self, dtype=None, type=None):
        """Like ndarray.view, but the result is always a Distribution
        subclass; raises ValueError for incompatible dtype reinterpretation."""
```

`_get_distribution_dtype` is the one entry above whose declaration is *not*
literal: whether it is an instance, class, or static method is the
implementing agent's choice, as long as both call sites above work (`__new__`
needs it before an instance exists, so a `classmethod`/`staticmethod` is the
natural fit). Every other signature in the block is literal.

The ufunc-override hook is not given a docstring in the interfaces above but
is required supporting code: it must follow the standard NumPy
`__array_ufunc__(self, ufunc, method, *inputs, **kwargs)` protocol signature
so that arithmetic, comparisons, and `np.sin`/`np.add.reduce`-style calls on
`Distribution` operate sample-wise (see Acceptance Scenarios S12–S13, S20).

`function_helpers.py` entries for `np.concatenate`, `np.broadcast_arrays`,
`np.broadcast_to`, and `np.empty_like` must be registered with the existing
`function_helper`/`dispatched_function` `FunctionAssigner` instances
(`function_helpers.py:71-72`) so `Distribution.__array_function__` can find
them by function identity.

## Out of Scope

- `pdf_mean`, `pdf_var`, `pdf_mad`, `pdf_smad`, `pdf_percentiles`,
  `pdf_histogram` — already implemented with working bodies; not touched by
  this change.
- `ArrayDistribution.__getitem__` / `__setitem__`, the `dtype`
  property/setter, `astype`, `_DistributionRepr` — already implemented;
  not touched by this change.
- `astropy/uncertainty/distributions.py` (`normal`, `uniform`, `poisson`) —
  already implemented; not touched by this change.
- Exact (closed-form, non-sampled) normal/Poisson distributions — an
  explicitly deferred stretch goal in the existing test suite
  (`test_helper_normal_exact`, `test_helper_poisson_exact` both call
  `pytest.skip(...)`); out of scope here too.
- Custom/non-trivial dispatch logic (a `FUNCTION_HELPERS`/`DISPATCHED_FUNCTIONS`
  entry that reshapes args or rewrites `out`) for any NumPy function other
  than `concatenate`, `broadcast_arrays`, `broadcast_to`, and `empty_like` —
  those four are the ones named by this change's behavioral requirements.
  This does **not** exempt other functions from working: `Distribution.__array_function__`
  intercepts every NumPy function called on a `Distribution` operand (not
  just these four), and the unmodified test suite already calls several
  others on `Distribution` instances — `np.may_share_memory` (S9, S11;
  `test_distribution.py:447,456,461,472,476,650`), `np.min` (S18b;
  `test_distribution.py:255-257`), `np.percentile`'s underlying array method
  (used internally by the intact `pdf_percentiles`, `core.py:469`). Where
  such a function needs no special argument handling, register it as a
  plain pass-through in `DISTRIBUTION_SAFE_FUNCTIONS` (as the sibling
  `astropy/units/quantity_helper/function_helpers.py:113` and
  `astropy/utils/masked/function_helpers.py:114-115` do for
  `np.may_share_memory`) — that is in scope because it is a prerequisite of
  an in-scope scenario and of keeping `pytest astropy/uncertainty/` green
  (Definition of Done). Only the *bespoke logic* is scoped to the four named
  functions; the *registration* surface is whatever the acceptance scenarios
  and the existing test suite require.

## Acceptance Scenarios

### Happy Path

- **S1:** Given a `(4, 1000)` plain `ndarray` (4 elements, 1000 samples
  each), when `Distribution(arr)` is called, then the result is an
  `NdarrayDistribution` that is both `isinstance(..., Distribution)` and
  `isinstance(..., np.ndarray)`, with `.shape == (4,)`,
  `.distribution.shape == (4, 1000)`, and `.n_samples == 1000`.
- **S2:** Given a `Quantity` array `pq = arr << u.ct`, when
  `Distribution(pq)` is called, then the result is simultaneously
  `isinstance(..., u.Quantity)` and `isinstance(..., Distribution)`,
  `.value` is itself a `Distribution`, and `.value.distribution` equals
  `arr`.
- **S3:** Given an existing `Distribution` `pd` built from a `(4, 1000)`
  integer array, when `qpd = pd << u.ct` reconstructs it through `__new__`,
  then `qpd` is a `Quantity` with `.unit == u.ct`,
  `qpd.value.distribution` equals `pd.distribution.astype(float)` (the
  int→float cast the unit attachment forces), and `qpd.n_samples == 1000`.
- **S3b:** Given the same existing `Distribution` `pd`, when
  `Distribution(pd)` is called directly, then the result's `.distribution`
  equals `pd.distribution` and its `.n_samples` is still 1000.
- **S4:** Given a `QuantityDistribution` built from a `(4, 10000)` array of
  known normal samples, when `.pdf_median()` is called, then the result
  approximately equals `np.median(data, axis=-1) * unit` (within the
  default tolerance of `astropy.tests.helper.assert_quantity_allclose`), is
  a `Quantity` but NOT a `Distribution`, and has shape `(4,)`.
- **S5:** Given the same distribution and a pre-allocated `Quantity` array
  `out`, when `.pdf_median(out=out)` is called, then the return value `is
  out` and its values equal the plain `.pdf_median()` result.
- **S6:** Given the same `(4, 10000)` distribution, when `.pdf_std()` is
  called, then the result approximately equals `np.std(data, axis=-1) *
  unit` (within the default tolerance of
  `astropy.tests.helper.assert_quantity_allclose`), is a `Quantity` but NOT
  a `Distribution`.
- **S7:** Given the same distribution, when `.pdf_std(ddof=1, out=out)` is
  called, then `out` is returned and equals `np.std(data, axis=-1, ddof=1) *
  unit`.
- **S8:** Given a `Distribution` built from a structured-dtype array
  (fields `"a"`: f8, `"b"`: (2,2)f8) of logical shape `(3, 4)` with 5
  samples, when `.distribution` is accessed, then it equals the original
  structured array of shape `(3, 4, 5)` with the same dtype.
- **S9:** Given a `Distribution` `qd3`, when `.view()` is called with no
  arguments, then the result's class is identical to `qd3`'s class and
  `np.may_share_memory(result, qd3)` is `True`.
- **S10:** Given `ad = Angle(Distribution([2., 3., 4.]), "deg")`, when
  `.view(u.Quantity)` is called, then the result is
  `isinstance(..., u.Quantity)` and `isinstance(..., Distribution)` but NOT
  `isinstance(..., Angle)`.
- **S11:** Given `c = Distribution([2.0j, 3.0, 4.0j])` (complex128
  samples), when `.view("2f8")` is called, then the result's shape is
  `c.shape + (2,)`, it shares memory with `c`, and `.distribution` equals
  `np.moveaxis(c.distribution.view("2f8"), -2, -1)`.
- **S12:** Given two independently built `Distribution`s with the same
  `n_samples` (`self.distr`, kpc; `another_distr`, pc; both shape `(4,)`),
  when `combined = self.distr + another_distr` is computed, then
  `combined.pdf_median()` equals `np.median(data_kpc + data_pc / 1000,
  axis=-1) * kpc` — i.e. sample index `i` of the result combines sample
  index `i` of each operand, not a cross product.
- **S13:** Given `self.distr` (shape `(4,)`, 10000 samples) and an
  ordinary (non-Distribution) `Quantity` array `[2000, 0, 0, 500] * u.pc`
  (no sample axis), when `self.distr + that_array` is computed, then the
  ordinary array's value is added once per element across all of that
  element's samples (`pdf_median()` shifts by the ordinary value;
  `pdf_var()` is unchanged from the original distribution's variance).
- **S14:** Given `da` (logical shape `(2, 3)`, `n_samples=4`) and
  `db[np.newaxis]` (logical shape `(1, 3)`, same `n_samples`), when
  `np.concatenate((da, db[np.newaxis]), axis=0)` is called, then the
  result's `.distribution` equals concatenating the raw distribution
  arrays along the same axis index (the sample axis is untouched), with
  logical shape `(3, 3)`.
- **S15:** Given an ordinary array `c` (shape `(2, 1)`, no sample axis) and
  `da` (logical shape `(2, 3)`, `n_samples=4`), when
  `np.concatenate((c, da), axis=1)` is called, then the result's
  `.distribution` equals concatenating `da`'s raw distribution array with
  `c` broadcast to `c.shape + (da.n_samples,)` (`c`'s value repeated across
  all samples), joined along axis 1.
- **S16:** Given `da`, `db`, `c` (mixed `Distribution` / plain-array
  types), when `np.broadcast_arrays(da, db, c, subok=True)` is called,
  then each output retains its own original type (`Distribution` outputs
  stay `type(da)` / `type(db)`; the plain-array output stays `type(c)`),
  and each output's values equal broadcasting the corresponding raw arrays
  to the common logical shape.
- **S17:** Given the same inputs as S16, when
  `np.broadcast_arrays(da, db, c, subok=False)` is called, then each
  `Distribution` output's `.distribution` is a plain `np.ndarray` (not a
  `Quantity` subclass), and the plain-array output is also a plain
  `np.ndarray` — matching NumPy's own `subok=False` semantics.
- **S18:** Given a `Distribution` `d` with `n_samples == N` and a requested
  `dtype`, when `np.empty_like(d, dtype=dtype)` is called, then the result
  is a `Distribution` of the same subclass, with the same logical shape,
  the same `n_samples == N`, and samples stored using `dtype`.
- **S18b:** Given `p_dist = ds.poisson(centerqcounts, n_samples=100)`
  (shape `(4,)`), when `np.min(p_dist)` is called, then the result is a
  scalar (`shape == ()`) `Distribution` — i.e. `np.min` reaches
  `Distribution.__array_function__` and is handled, not left to raise
  `TypeError`.

### Edge Cases

- **S19:** Given an array whose trailing axis has length 1 (one sample per
  element), when `Distribution(arr)` is constructed, then `.n_samples ==
  1` and ordinary operations (indexing, `pdf_median()`) succeed without a
  special-cased failure.
- **S20:** Given a generalized-ufunc call on `Distribution` operands that
  passes the `axes=` keyword, when the call is made, then a
  `NotImplementedError` is raised rather than silently mishandling the
  sample axis.

### Error Scenarios

- **S21:** Given a 0-d scalar input (e.g. `parr.ravel()[0]`), when
  `Distribution(scalar)` is called, then a `TypeError` is raised whose
  message matches `"Attempted to initialize a Distribution with a
  scalar"`.
- **S22:** Given `distr = Distribution([2.0, 3.0, 4.0])` (float64
  samples), when `.view(np.dtype("2i8"))` is called, then a `ValueError`
  is raised whose message matches `"can only be viewed"`.
- **S23:** Given a `Distribution` whose logical last axis has been made
  non-contiguous (e.g. `uint8.T` after `uint32.view("4u1")`), when
  `.view("u4")` is called on it, then a `ValueError` is raised whose
  message matches `"last axis must be contiguous"`.
- **S24:** Given a NumPy function unsupported for `Distribution`, called
  with a mix of a `Distribution` argument and a plain (non-Distribution)
  `ndarray`-subclass argument, when the function is invoked, then a
  `TypeError` is raised (via the existing `Distribution._not_implemented_or_raise`
  at `core.py:339`) rather than silently returning `NotImplemented`.

### Interaction With Already-Implemented Code

These scenarios assert that code left intact keeps working once the stripped
regions are restored; they require no edits to the intact code itself.

- **S25:** Given `d = Distribution(np.arange(60.).reshape(3, 4, 5))`
  (logical shape `(3, 4)`, 5 samples), when `d.astype("f4")` is called, then
  the result is a `Distribution` with `.shape == (3, 4)`,
  `.n_samples == 5`, `.dtype == np.dtype("f4")`, and `.distribution` equal to
  the original samples cast to `f4`.
- **S25b:** Given the same `d`, when `d.dtype = "f4"` is assigned, then the
  assignment succeeds and `d` still reports `.shape == (3, 4)` and
  `.n_samples == 5`.
- **S26:** Given `ad = Angle(Distribution([2., 3., 4.]), "deg")`, when
  `ad += ad` is executed, then `ad` is still both an `Angle` and a
  `Distribution` and `ad.distribution` equals `[4., 6., 8.] * u.deg`.
- **S27:** Given the same `ad`, when `ad *= ad` is executed, then a
  `u.UnitTypeError` is raised (deg² cannot be stored in an `Angle`) and no
  result is returned.
- **S28:** Given `distr = Distribution(np.random.randn(2, 1000) * u.kpc)`,
  when its two elements are unpacked (`d1q, d2q = distr`), then each element
  is an instance of `Distribution` with `.n_samples == 1000` — i.e. indexing
  down to a 0-d element yields a scalar distribution, not a bare `np.void`.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*. A green suite that passes for the
> wrong reason does not satisfy this contract.

The project's own test suite already encodes these scenarios —
`astropy/uncertainty/tests/test_distribution.py` and
`astropy/uncertainty/tests/test_functions.py` are unmodified and exercise
S1–S24 directly (e.g. `TestInit`, `TestDistributionStatistics::test_pdf_median`
/ `test_pdf_std`, `test_distr_view_different_dtype1/2`,
`test_distr_cannot_view_new_dtype`, `TestConcatenation`, `TestBroadcast`,
`test_init_scalar`, `test_distr_angle`, `test_index_assignment_quantity`).
Running `pytest astropy/uncertainty/` after
implementation is both the fastest feedback loop and the primary check —
every currently-erroring test in that directory is a scenario this spec
covers. Do not weaken, skip, or rewrite those tests to make them pass; treat
them as the acceptance oracle. `test_helper_poisson_samples`
(`test_distribution.py:247-259`) already covers S18b (`np.min`). Five
scenarios have no direct test in the two files above — S3b
(`Distribution(existing_distribution)` called directly), S18
(`np.empty_like`), S20 (gufunc `axes=`), and S25 / S25b (`astype` and the
`dtype` setter called on a `Distribution` rather than on its raw
`.distribution`) — so add a test for each under `astropy/uncertainty/tests/`,
written to the same conventions.

- **Behavioral over structural** — assert observable output (`.distribution`,
  `.shape`, `.n_samples`, types, values), not internal storage layout.
- **Every test can fail** — no copy-pasted expected values; derive expected
  values from `np.median`/`np.std`/`np.concatenate`/etc. applied to the raw
  arrays, as the existing tests do.
- **Deterministic, isolated** — reuse `NumpyRNGContext` (already used in
  `test_distribution.py`) for any test needing random samples.

## Definition of Done

- [ ] `pytest astropy/uncertainty/` is green.
- [ ] Every acceptance scenario (S1…S28, including S3b, S18b, and S25b) maps
      to at least one test.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
      the smallest break of its behavior (thought-mutation).
- [ ] Tests meet the Test Desiderata bar (Kent Beck's test-quality
      properties — Behavioral and Structure-insensitive take priority: a
      test asserts observable behavior and survives refactoring of
      internals); no anti-pattern violations (no copy-pasted expected
      values, no asserting a constant, no tautologies).
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings) in the filled-in regions of `core.py` and
      `function_helpers.py`.

## Trade-offs and Limitations

- The spec does not prescribe internal helper decomposition beyond the names
  the intact code already calls. `_get_distribution_dtype` is *not* free:
  `core.py:192-193` and `core.py:198` call it by that name with the
  signatures given in the Interface Contract, so an implementation that
  inlines the dtype construction into `__new__` and omits the helper leaves
  the `dtype` setter and `astype` raising `AttributeError` (S25). Any
  *additional* private helper is the implementing agent's choice.
- `__array_ufunc__`'s exact placement (`Distribution` vs. `ArrayDistribution`)
  is left to the implementing agent since both classes' bodies are blank in
  the affected regions; what matters is that the standard protocol method
  exists and produces the behavior in S12, S13, S20.

## Open Questions

Both items the spec-evaluator raised have been resolved at hand-off (no
reviewer was available to consult, so the decision is made here and recorded
for traceability rather than left blocking):

1. **Resolved — the `function_helpers.py` scope fence was too narrow, and
   has been corrected.** It no longer excludes `DISTRIBUTION_SAFE_FUNCTIONS`
   registrations; see the rewritten Out of Scope bullet. Rationale: Out of
   Scope must never exclude a prerequisite of an in-scope scenario (S9, S11,
   S18b) or of the Definition of Done (`pytest astropy/uncertainty/` green),
   and `Distribution.__array_function__` intercepts every NumPy function
   called on a `Distribution` operand, not only the four functions with
   bespoke logic — so the registration surface was always going to be wider
   than four entries regardless of scope wording.
2. **Resolved — S20's `NotImplementedError` for the gufunc `axes=` keyword
   is correct, kept as specified.** This is not an inference from sibling
   code (`Masked.__array_ufunc__` handling `axes=` is not evidence about
   `Distribution`, which has a different sample-axis-preservation
   requirement to satisfy for every gufunc call regardless of `axes`); it is
   restated directly from the authoritative source behavioral requirements
   for this change: "reject the unsupported `axes` keyword with
   NotImplementedError." No test in the repository currently exercises this
   path, so the implementing agent must add one (already listed under For
   the Implementing Agent).

## References

- `astropy/uncertainty/core.py` — classes and blank regions described above.
- `astropy/uncertainty/function_helpers.py` — registry and blank region
  described above.
- `astropy/uncertainty/distributions.py` — intact creator functions used by
  several scenarios' setup.
- `astropy/uncertainty/tests/test_distribution.py`,
  `astropy/uncertainty/tests/test_functions.py` — acceptance oracle.
- `astropy/units/quantity_helper/function_helpers.py` — the `FunctionAssigner`
  pattern reused by `function_helpers.py:71-72`.

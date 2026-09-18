# Verdict: Uncertainty Distribution Interfaces

**Test suite:** not run — no test environment available in this checkout (no
installed deps, no docker image). Everything below is a static read of the
diff against `astropy/uncertainty/core.py` / `function_helpers.py` and the
oracle tests `astropy/uncertainty/tests/test_distribution.py` /
`test_functions.py`.

**Diff scope check (pass):** only `astropy/uncertainty/core.py` and
`astropy/uncertainty/function_helpers.py` are modified. Every change lands
exactly inside the blanked-out line ranges the spec named (`core.py` 59-181,
201-338, 372-378, 387-394, 403-415, 528-591; `function_helpers.py` 74-151),
plus the sanctioned import-line extension at `core.py:25`. No
already-implemented method (`distribution`, `dtype` getter/setter, `astype`,
`__getitem__`, `__setitem__`, `pdf_mean/var/mad/smad/percentiles/histogram`,
`_not_implemented_or_raise`, `__eq__`, `__ne__`, `_DistributionRepr`) was
touched. `distributions.py` and `__init__.py` are untouched. No stray `pass`
or misuse of `NotImplementedError` — the only two raises are the gufunc
`axes=` rejection and `concatenate`'s non-Distribution-`out` rejection, both
spec-mandated.

## Overall verdict

**Meets the spec's definition of done, with one real gap:** the
`numpy.broadcast_to` dispatch-table entry the spec explicitly requires
(Key Components list, Definition-of-Done bullet) was never added. The
one oracle test that exercises it (`test_broadcast_to`, `subok=True`) will
still pass by accident (see the thought-mutation note below), so this will
not show up as a red test — but the required-and-untested `subok=False`
behavior is actually wrong, not just unverified. Everything else checked
(construction, ufunc dispatch, `view`, `pdf_median`/`pdf_std`, `concatenate`,
`broadcast_arrays`, `empty_like`) traces correctly against every scenario
below.

## Scenario coverage (S1-S32)

| # | Scenario | Test(s) | Code path | Verdict |
|---|---|---|---|---|
| S1 | Plain-array construction, shape/size/n_samples, `.T` non-contiguous input | `TestDistributionStatistics.test_shape/test_size/test_n_samples/test_n_distr`, `TestInit.test_numpy_init(_T)` | `Distribution.__new__` | covered |
| S2 | `Quantity` construction, `pqd.value` is `NdarrayDistribution` | `TestInit.test_quantity_init(_T)` | `__new__` + `ArrayDistribution.view` (`Quantity.value` → `self.view(np.ndarray)`) | covered |
| S3 | `pd << u.ct` → `Distribution`+`Quantity`, `.value.distribution == pd.distribution.astype(float)` | `test_quantity_init_with_distribution` | `astype` (unchanged) → `view(<Quantity subclass>)` | covered |
| S4 | `pdf_mean/median/std/var`, `out=` returned by identity, `ddof=1` | `TestDistributionStatistics.test_pdf_mean/_median/_std/_var`, `test_pdf_mad_smad` | `pdf_median`, `pdf_std` (new), `pdf_mean`/`pdf_var` (unchanged) | covered |
| S5 | Unit-converting add, `Distribution`+`Quantity` and `Distribution`+`Distribution` | `test_add_quantity`, `test_add_distribution` | `__array_ufunc__` | covered |
| S6 | `ds.normal/poisson/uniform` produce working Distributions | `test_helper_normal_samples` etc. | `__new__` (unmodified `distributions.py` calls `cls(samples, **kwargs)`) | covered |
| S7 | Iterating a shape-`(2,)` Distribution yields `ScalarDistribution`s | `test_index_assignment_quantity/_array` | `__getitem__` (unchanged) relies on `__new__`/dtype machinery | covered |
| S8 | `np.sin(Distribution(...*u.deg))` | `test_scalar_quantity_distribution` | `__array_ufunc__` | covered |
| S9 | `Angle+Angle` stays `Angle`, `Angle*Angle` decays to `Quantity`, `+=` writes through, `*=` raises `UnitTypeError` | `test_distr_angle` | `__array_ufunc__` (`out=` forwarded as unwrapped samples) | covered |
| S10 | `np.concatenate` logical-axis semantics, unit conversion | `TestConcatenation.test_concatenate` (+ Quantity variant) | `function_helpers.concatenate` | covered |
| S11 | `concatenate` with a plain-array + Distribution mix | `test_concatenate_not_all_distribution` | `function_helpers.concatenate` (`get_n_samples`, `np.broadcast_to` internal call) | covered |
| S12 | `broadcast_to`/`broadcast_arrays`, `subok=True` | `TestBroadcast.test_broadcast_to/test_broadcast_arrays` | **no registered `broadcast_to` helper** — falls through `__array_function__`'s final `else` to `super().__array_function__`; `broadcast_arrays` IS registered (`FUNCTION_HELPERS`) | covered, but see finding #1 |
| S13 | `broadcast_arrays(subok=False)` decays samples' class only | `test_broadcast_arrays_subok_false` | `function_helpers.broadcast_arrays` | covered |
| S14 | `view` same-itemsize sub-array growth / itemsize-consuming shrink, memory sharing | `test_distr_view_different_dtype1` | `ArrayDistribution.view` | covered (hand-traced byte-for-byte, see below) |
| S15 | `view` 4-byte split, `.T` non-contiguous → `ValueError` "last axis must be contiguous" | `test_distr_view_different_dtype2` | `ArrayDistribution.view` | covered |
| S16 | `Angle.view(Quantity)` decay, no-arg `.view()` shares memory | `test_distr_angle_view_as_quantity` | `ArrayDistribution.view` | covered |
| S17 | Structured-dtype field indexing, padded-storage memory sharing | `TestStructuredDistribution.test_getitem` (+Quantity variant) | `_get_distribution_dtype(itemsize=...)` inside `__new__`, consumed by unmodified `__getitem__` | covered |
| S18 | Advanced fancy-index get/set, malformed index → `IndexError` | `TestGetSetItemAdvancedIndex` (+Quantity/structured variants) | unmodified `__getitem__`/`__setitem__`, relies on `__new__` dtype contract | covered |
| S19 | Boolean-mask indexing read/modify/write | `TestSetItemWithSelection` | unmodified `__getitem__`/`__setitem__` + `__array_ufunc__` (`out=`) | covered |
| S20 | `repr`/`str`/`_repr_latex_` show `n_samples=` for `Quantity` distributions | `test_reprs` | `n_samples` (new) + `_DistributionRepr` (unchanged, wins MRO via `_get_distribution_cls`) | covered |
| S21 | `np.min(p_dist)` with no `axis` reduces all logical axes, keeps sample axis | `test_helper_poisson_samples` | `__array_ufunc__` (`method="reduce"`, `axis is None` → `tuple(range(inputs[0].ndim))`) | covered |
| S22 | 0-d input → `TypeError` "Attempted to initialize ... scalar" | `test_init_scalar` | `__new__` | covered |
| S23 | `view` to an itemsize with no logical axis to consume → `ValueError` "can only be viewed", including `type=<Distribution subclass>` paths | `test_distr_cannot_view_new_dtype` | `ArrayDistribution.view` | covered (hand-traced, see below) |
| S24 | Defers to `__array_ufunc__ = None` operand for `==`/`!=`/`>` | `TestComparison.test_distribution_comparison_defers_correctly` | `__eq__`/`__ne__` (unchanged) + absence of `__lt__`/`__gt__` on `Distribution` (new code doesn't add any) | covered |
| S25 | Helper `NotImplementedError` + plain-ndarray in `types` → `TypeError` | not oracle-covered | `_not_implemented_or_raise` (unchanged) fed by the `except NotImplementedError` in `__array_function__` | implemented, not test-covered (per spec) |
| S26 | Generalized ufunc with `axes=` → `NotImplementedError` | not oracle-covered | `__array_ufunc__` explicit `"axes" in kwargs` check | implemented, not test-covered (per spec) |
| S27 | `==`/`!=`/`>` against a non-Distribution produce boolean Distributions | `TestComparison.test_distribution_can_be_compared_to_non_distribution` | `__array_ufunc__` | covered |
| S28 | `.to()`/`.to_value()` round trips, `AttributeError` for unitless | `test_distr_to(_value)`, `test_distr_noq_to(_value)` | `ArrayDistribution.view` (via `Quantity._new_view`) | covered |
| S29 | Structured dtype + structured unit | `TestStructuredQuantityDistributionInit` | `__new__` + `_get_distribution_dtype` | covered |
| S30 | 1-D sample input ⇒ scalar distribution, not an error | `test_wrong_kw_fails` (uses `ds.normal`/etc. with scalar centre) | `__new__` (1-D input has `shape != ()`, so no `TypeError`) | covered |
| S31 | `pdf_histogram`/`pdf_percentiles`/`_repr_latex_() is None` for ndarray | `test_histogram`, `test_percentile`, `test_array_repr_latex` | unchanged methods, depend on `.distribution`/`.shape` from new `__new__` | covered |
| S32 | `.copy()` independence | used inside `TestGetSetItemAdvancedIndex.test_setitem` etc. | inherited `ndarray.copy()`, relies on dtype contract from `__new__` | covered |

## Anti-vacuity (thought-mutation) — headline findings

| Behavior | Smallest breaking mutation | Does a test actually fail? |
|---|---|---|
| `__new__` padded-storage view sharing (S17) | Change `itemsize=samples.strides[-1]` to `itemsize=None` (always pack tightly) | **Yes** — `TestStructuredDistribution.test_getitem` asserts `np.may_share_memory(d_i, self.d)`; tight packing would force a copy, since the field view's stride (40) no longer matches a padded slot. Real coverage, not vacuous. |
| `ArrayDistribution.view` itemsize-consuming shrink (S14/S15) | Drop the `.squeeze(-1)` / logical-axis-removal step, always leaving a trailing size-1 axis (plain `ndarray.view` behavior) | **Yes** — `test_distr_view_different_dtype1/2` compare shapes with `assert_array_equal`, which is shape-strict; a leftover `(…, 1)` axis mismatches the expected `(…, )`/`(…,2)` shape. Real coverage. |
| **`broadcast_to` dispatch (S12)** | Register an explicit, *wrong* `broadcast_to` FUNCTION_HELPERS entry that ignores `subok` and always keeps the plain-array/Distribution mix as ndarray | **No — this scenario is not actually exercised by a dedicated dispatch path at all.** Because a `Distribution`'s ndarray `.shape` already excludes the (dtype-embedded) sample axis, numpy's *default* `__array_function__` fallback (`super().__array_function__`, i.e. plain `ndarray` broadcasting via `np.nditer`) happens to reproduce the right shape/value for `subok=True` without any Distribution-specific code running. The test only checks the *outcome*, not that a helper fired, so it is covered-but-accidental: deleting the `broadcast_arrays` helper's *sibling* handling for `broadcast_to` was never actually present to delete. See Finding #1 below — this is a real implementation gap masked by a coincidence of the storage design, not a vacuous test in the traditional "asserts nothing" sense. |
| `pdf_median`/`pdf_std` (S4) | Swap `axis=-1` for `axis=0`, or drop `out=` forwarding | **Yes** — `test_pdf_median`/`test_pdf_std` compare against `np.median(data, axis=-1)`/`np.std(..., ddof=1)` and separately assert `result is out`. Real coverage. |

## Test Desiderata note

The tests are the pre-existing, unmodified oracle (`test_distribution.py`,
`test_functions.py`) — they were not authored by the implementing agent and
are out of scope to edit or re-grade. No desiderata scoring is offered here
since there is nothing the implementing agent controlled about them; the
relevant question was only whether the implementation is *actually exercised
by* them (see anti-vacuity table above), not whether the tests themselves
are well-written.

## Implementation-quality findings

### Finding 1 (required, not oracle-covered): `numpy.broadcast_to` has no dispatch-table entry
- **File:** `astropy/uncertainty/function_helpers.py`
- **What's missing:** the spec's Key Components section and Definition-of-Done
  both list `numpy.broadcast_to` as a required `FUNCTION_HELPERS`/
  `DISPATCHED_FUNCTIONS` entry, alongside `broadcast_arrays`/`concatenate`/
  `empty_like`. Only `broadcast_arrays`, `concatenate`, and `empty_like` were
  added; `broadcast_to` was not.
- **Why it still passes today:** `Distribution`'s exposed `.shape` already
  excludes the sample axis (it's folded into the structured storage dtype),
  so numpy's un-overridden default `__array_function__` fallback
  (`super().__array_function__` in the final `else` branch) happens to
  broadcast correctly for `subok=True` — which is the only case
  `TestBroadcast.test_broadcast_to` exercises.
- **Where it actually breaks:** `np.broadcast_to(a_distribution, shape, subok=False)`
  (explicitly named in the spec's "not oracle-covered but still required"
  list). With no registered helper, this falls to the same default fallback,
  which does `np.array(x, copy=False, subok=False)` — for `Distribution`,
  `subok=False` at that layer strips the **entire Distribution wrapper**,
  returning a bare `ndarray` with the raw structured dtype, not a
  `Distribution` at all. Contrast with `broadcast_arrays(subok=False)`
  (`test_broadcast_arrays_subok_false`), where `subok` is defined to affect
  only the *inner samples' class* while the outer result stays a
  `Distribution` — `broadcast_to` should behave the same way per the spec's
  "following subok for the type of the result" wording, read consistently
  with the sibling function.
- **Fix:** add a `@function_helper def broadcast_to(array, shape, subok=False):
  ...` entry mirroring `broadcast_arrays`'s subok handling (view the array's
  samples down to `np.ndarray` when `subok=False`, but always call the real
  `np.broadcast_to` with `subok=True` so the `Distribution` wrapper survives),
  matching the `Interface Contract` block in the spec.

### Finding 2 (cosmetic, non-blocking): broken f-string in `view`'s error message
- **File:** `astropy/uncertainty/core.py`, in `ArrayDistribution.view`'s final
  `else` branch:
  ```python
  raise ValueError(
      f"{self.__class__} can only be viewed with a dtype with "
      "itemsize {self.strides[-1]} or {self.dtype.itemsize}"
  )
  ```
  Only the first string literal is an f-string; the second is not, so the
  message renders literally as `... itemsize {self.strides[-1]} or
  {self.dtype.itemsize}` instead of interpolating the values. This does not
  affect test outcomes (`S23`/`S15` only match on the substrings `"can only
  be viewed"` / `"last axis must be contiguous"`), but it's a real bug in a
  user-facing diagnostic message. Fix: prefix the second string with `f`.

## Punch list for the implementing agent

1. **Required:** add a `numpy.broadcast_to` entry to `FUNCTION_HELPERS` (or
   `DISPATCHED_FUNCTIONS`) in `function_helpers.py`, handling `subok=False`
   the same way `broadcast_arrays` does — decay only the samples' class,
   keep the outer result a `Distribution`. Verify by hand:
   `type(np.broadcast_to(da, da.shape, subok=False))` should still be `type(da)`
   with `.distribution` decayed to plain `np.ndarray`/base class, not a bare
   `ndarray` result.
2. **Optional cleanup:** fix the missing `f` prefix on the second string in
   `ArrayDistribution.view`'s `"itemsize {self.strides[-1]} or
   {self.dtype.itemsize}"` error message so the values actually interpolate.

Everything else — construction (`__new__`, `_get_distribution_dtype`,
`_get_distribution_cls`), `__array_ufunc__` (sample-wise dispatch, `out=`
forwarding, axis-free reduce, gufunc core-dimension handling, `axes=`
rejection), `__array_function__` dispatch/rewrap rules, `ArrayDistribution.view`
(all dtype/type branches including the two pinned `ValueError` messages),
`pdf_median`, `pdf_std`, and the `concatenate`/`broadcast_arrays`/`empty_like`
dispatch-table entries — was hand-traced against every applicable acceptance
scenario and matches the spec's stated contract and mechanism hints exactly,
including the trickier byte-level cases (S14/S15/S23 padded-storage view
arithmetic).

# Verdict — 2609.0001 Restore RGBImageMapping Construction and Image Conversion

## Overall verdict: **MEETS** the spec's definition of done

Test suite status: **not run — no test environment** (no pytest/astropy install available in
this checkout; not treated as a blocker per operating rules). In lieu of the suite, every
scenario below was verified by loading `basic_rgb.py`, `interval.py`, `stretch.py`, and
`lupton_rgb.py` directly with `importlib` (bypassing the package `__init__` chain that needs
compiled C extensions not built here) and executing the exact inputs/assertions the spec and
the existing/new test files describe. This is supplementary confirmation, not a substitute for
running the real suite — re-run `pytest astropy/visualization/tests/test_interval.py
astropy/visualization/tests/test_stretch.py astropy/visualization/tests/test_lupton_rgb.py
astropy/visualization/tests/test_basic_rgb.py` in a real environment before merging.

No blocking defects were found. One test is weaker than it looks (non-blocking, see below) and
a few cosmetic issues exist in the restored files.

---

## Scenario coverage mapping

| # | Scenario | Test(s) | Code path |
|---|---|---|---|
| S1 | single interval reused, identity-shared | `test_basic_rgb.py::TestRGBImageMappingInit::test_single_interval_reused_for_all_channels` | `RGBImageMapping.__init__` |
| S2 | 3-element interval preserves position/identity | `...::test_three_intervals_preserve_position` | `RGBImageMapping.__init__` |
| S3 | defaults behave like explicit args | `...::test_defaults_match_explicit_construction` | `RGBImageMapping.__init__`, `make_rgb_image` |
| S4 | uint8 output shape/dtype | `...::TestMakeRGBImage::test_uint8_output` | `make_rgb_image` |
| S5 | float/float64 output in [0,1] | `...::test_float_output_in_unit_range` | `make_rgb_image`, `apply_mappings` |
| S6 | per-channel own normalization / vmax→1 | `...::test_per_channel_intervals_are_independent`, `...::test_vmax_maps_to_stretch_of_one` | `apply_mappings` |
| S7 | inputs not mutated | `...::test_inputs_not_mutated` | `apply_mappings` (via `BaseInterval.__call__`, `_prepare`) |
| S8 | `RGBImageMappingLupton.make_rgb_image` (inherited) runs without error | pre-existing `test_lupton_rgb.py::test_Asinh`, `test_AsinhZscale*`, `test_linear` | `RGBImageMapping.make_rgb_image` → `RGBImageMappingLupton.apply_mappings` → `LuptonAsinhStretch.__call__` → `_stretch_prepare` |
| S8b | `make_rgb_image` delegates through `self.apply_mappings` | `...::test_apply_mappings_is_used_not_inlined` | `make_rgb_image` |
| S8c | uint8 quantization uses full range, no wraparound | `...::test_uint8_quantization_uses_full_range` | `make_rgb_image` |
| S8d | `make_rgb` ≡ `RGBImageMapping(...).make_rgb_image(...)` | `...::test_make_rgb_matches_direct_mapping` | `make_rgb`, `make_rgb_image` |
| S9 | per-channel interval independence (identical raw pixels) | `...::test_per_channel_intervals_are_independent` | `apply_mappings` |
| S10 | masked/non-finite excluded, 4 data reps | pre-existing `test_interval.py::TestInterval*` (`TestIntervalList`, `TestInterval2D`, `TestIntervalMaskedArray`, `TestIntervalMaskedNDArray`) | `BaseInterval._process_values` |
| S10b | 5 data reps give identical sampled percentiles | pre-existing `test_interval.py::TestInterval::test_asymmetric_percentile_nsamples` (inherited into the 4 subclasses) | `_process_values`, `AsymmetricPercentileInterval.get_limits` |
| S11 | zscale on Gaussian data, atol=0.1 | pre-existing `test_interval.py::test_zscale` (case 1) | `ZScaleInterval.get_limits` |
| S12 | zscale with NaN excluded | pre-existing `test_zscale` (case 2) | `ZScaleInterval.get_limits`, `_process_values` |
| S12b | zscale on data smaller than n_samples | pre-existing `test_zscale` (case 3) | `ZScaleInterval.get_limits` |
| S13 | zscale fallback to plain min/max | pre-existing `test_interval.py::test_zscale_npoints` | `ZScaleInterval.get_limits` |
| S14 | stretch `out=None` returns independent copy | pre-existing `test_stretch.py::TestStretch::test_no_clip`, `test_round_trip` | `_prepare` |
| S15 | stretch `out=result` writes into and returns `out` | pre-existing `test_stretch.py::TestStretch::test_inplace` | `_prepare` |
| S16 | `CompositeStretch` order (`transform_1` = 2nd operand) | pre-existing `test_stretch.py` `RESULTS[LinearStretch(intercept=0.5) + LinearStretch(slope=0.5)]`, exercised by `test_no_clip`/`test_clip`/`test_round_trip`/`test_double_inverse` | `CompositeStretch.__call__` |
| S17 | `CompositeStretch` honors `out` | pre-existing `test_stretch.py::TestStretch::test_inplace` (same `RESULTS` entry) | `CompositeStretch.__call__` |
| S18 | interval count error | `test_basic_rgb.py::TestRGBImageMappingInit::test_interval_count_error` | `RGBImageMapping.__init__` |
| S19 | mismatched shapes error, message substring | `test_basic_rgb.py::TestMakeRGBImage::test_mismatched_shapes_error`; pre-existing `test_lupton_rgb.py::TestLuptonRgb::test_different_shapes_asserts` | `make_rgb_image` |
| S20 | invalid `output_dtype`, checked before mapping work | `test_basic_rgb.py::TestMakeRGBImage::test_output_dtype_error`, `test_output_dtype_error_before_shape_check` | `make_rgb_image` |

All 20 scenarios (including lettered sub-scenarios) map to at least one test. S8 and S10–S17 are
covered by pre-existing suites that the spec explicitly designates as ground truth and forbids
modifying; the new `test_basic_rgb.py` was not required to duplicate them and doesn't.

---

## Thought-mutation table (anti-vacuity)

| Scenario | Smallest break | Caught? |
|---|---|---|
| S1 | Make `__init__` copy the interval into 3 separate objects instead of reusing the same one | ✅ `is` identity assertions fail |
| S2 | Swap `intervals[1]`/`intervals[2]` assignment order | ✅ position assertions fail |
| S6/S9 | Swap which interval index maps to which channel (e.g. use `intervals[1]` for red) | ✅ `test_per_channel_intervals_are_independent` asserts exact per-channel values (0.5/0.25/0.125); a swap produces a different exact value |
| S7 | Have `apply_mappings` write into the caller's array in place | ✅ `test_inputs_not_mutated` compares against a pre-call copy |
| S8b | Inline the per-channel loop into `make_rgb_image` instead of calling `self.apply_mappings` | ✅ `test_apply_mappings_is_used_not_inlined` uses a subclass override with distinguishable constants; inlining would ignore them |
| S8c | Drop the `* np.iinfo(output_dtype).max` scaling before `.astype(uint8)` | ✅ endpoints would be 0/1 instead of 0/255 |
| S8d | Have `make_rgb` construct `RGBImageMapping` with different args than documented | ✅ direct equality check against the class path |
| S18 | Accept 2- or 4-element interval lists silently | ✅ `pytest.raises(ValueError)` |
| S19 | Skip the shape check | ✅ message-matching `pytest.raises` |
| S20 | Skip dtype validation, or check it after the shape check | ✅ both a bad-dtype test and an order-sensitive test (`test_output_dtype_error_before_shape_check`, which pairs a bad dtype with mismatched shapes and asserts the dtype error wins) |
| S16 | Swap `transform_1`/`transform_2` application order in `CompositeStretch.__call__` | ✅ (via pre-existing suite) `RESULTS` pins `[0.5, 0.625, 0.75, 0.875, 1.0]`; reversed order gives `[0.25, 0.375, 0.5, 0.625, 0.75]`, a different value at every point |
| S11 | Use random sampling instead of the deterministic `values[::stride][:n_samples]` stride, or omit a sigma-rejection iteration | ✅ verified numerically: the restored algorithm reproduces `vmin≈-9.612`, `vmax≈25.384` against the pinned `atol=0.1` (`-9.6`, `25.4`) — plausible-but-wrong variants (e.g. no sigma rejection at all) would land outside tolerance |
| **S5 (weak)** | Drop `clip=True` from both `self.intervals[i](img, clip=True)` and `self.stretch(img, clip=True, ...)` in the base `apply_mappings` | ❌ **not caught**. `test_float_output_in_unit_range` uses `RGBImageMapping()` defaults (`ManualInterval(vmin=0, vmax=None)`) over `rng.random((10,12))` data, which is already in `[0,1)`. Verified directly: monkeypatching `apply_mappings` to call with `clip=False` still produces output in `[0, 1]` for this fixture, so the test cannot distinguish "clips because told to" from "happens to stay in range." Non-blocking (S4/S8c and the per-channel test still exercise clipping-adjacent paths, and the production code does pass `clip=True` correctly), but this specific test doesn't pin the clip contract. **Fix:** use data that exceeds the interval's `[vmin, vmax]` (e.g. values `> 1` with `vmax=1`, or a fixed `ManualInterval(vmin=0, vmax=0.5)` over the same random data) so an unclipped run would produce values outside `[0, 1]`. |
| S3 (weak by spec design) | Change the default `interval`/`stretch` construction while keeping both the implicit and explicit paths consistent | ❌ not caught, but the spec explicitly sanctions this weakness (mutable default args make object-identity assertions meaningless) and asks for a behavior-equivalence test instead — this is an accepted, documented trade-off, not a defect. |

All other scenarios pass their thought-mutation check: the acting test would fail if the
behavior broke in the smallest plausible way.

---

## Test Desiderata scoring (`test_basic_rgb.py`)

Scored against the 12 properties, priority order (Behavioral, Structure-insensitive, Readable,
Specific, Deterministic, Isolated):

| Property | Score | Notes |
|---|---|---|
| Behavioral ⭐ | ✅ | Every test asserts on `make_rgb_image`/`__init__` outputs (shape, dtype, values, exceptions) — no internal-state peeking except the two `self.intervals[i] is ...` identity checks the spec itself requires (S1/S2 contractually pin identity). |
| Structure-insensitive ⭐ | ✅ | No mocking, no call-order assertions. `test_apply_mappings_is_used_not_inlined` overrides a public, documented extension point rather than spying on internals — legitimate per spec (this is the documented extension mechanism). |
| Readable | ✅ | AAA structure, inline fixtures, `# S<n>` comments tie each test back to the spec scenario. |
| Specific | ✅ | One behavioral variant per test; failure would point at a specific scenario. |
| Deterministic | ✅ | `np.random.default_rng(seed)` used throughout; no unseeded randomness. |
| Isolated | ✅ | `setup_method` builds fresh fixtures per test; no shared mutable state across tests. |
| Fast | ✅ | Pure in-memory numpy ops on small arrays. |
| Automated | ✅ | Standard pytest, no manual steps. |
| Composable | ✅ | No ordering dependencies observed. |
| Predictive | ⚠️ | Mostly high — see S5 finding above; one test (`test_float_output_in_unit_range`) would pass even if clipping were silently dropped. |
| Inspiring | ✅ | Green suite would credibly mean the restoration works, modulo the one S5 gap. |

No AP-1 (structure-sensitive), AP-2 (no-assertion), AP-3 (non-deterministic), or AP-4
(copy-paste expected values) violations. `test_per_channel_intervals_are_independent` and
`test_uint8_quantization_uses_full_range` derive their expected values from the interval/stretch
math by hand (e.g. `0.5/1`, `0.5/2`, `0.5/4`), not from running the code and pasting the output —
consistent with AP-4's fix guidance. No AP-5 (mocking), AP-6 (over-DRY helpers), AP-7
(test-per-method structure — tests are organized by behavior, e.g.
`test_per_channel_intervals_are_independent` spans construction + mapping), or AP-8 (unclear
names) violations found.

---

## Implementation-quality flags (all non-blocking)

- `astropy/visualization/interval.py`: ~13 trailing blank lines at end of file, and doubled
  blank lines around `_process_values`/before `ZScaleInterval` — leftovers from the original
  strip-and-restore, cosmetic only.
- `astropy/visualization/interval.py::ZScaleInterval.get_limits`: several comments restate what
  the following line does (`# Sample the image`, `# Fit a line to the sorted array of samples`,
  `# Bad pixels mask used and updated at each iteration`, `# Kernel used to dilate the bad
  pixels mask`, `# Detect and reject pixels further than k*sigma from the fitted line`,
  `# Convolve with a kernel of length ngrow`). None are wrong, just restate-the-what; could be
  trimmed but don't block.
- `astropy/visualization/interval.py::ZScaleInterval.get_limits`: `fit` is only assigned inside
  the `for` loop body; if `max_iterations=0` were passed (not a default and not exercised by any
  scenario or test), `ngoodpix >= minpix` would be true immediately and `fit` would be
  referenced unbound, raising `UnboundLocalError` instead of falling back to plain min/max. Spec's
  Open Question 4 explicitly says not to add speculative handling beyond what's tested — flagged
  as an observation only, not a defect against this spec.
- No stubs, hard-coded returns unrelated to real logic, dead code, or stale docstrings found in
  `basic_rgb.py`, `interval.py`, or `stretch.py`. `lupton_rgb.py` has exactly the one permitted
  import line added and is otherwise byte-identical to before.

---

## Punch list (in case of revision)

1. **(Non-blocking, recommended)** Strengthen `test_float_output_in_unit_range` (S5) in
   `astropy/visualization/tests/test_basic_rgb.py` so it can actually detect a dropped
   `clip=True`: use an interval whose `[vmin, vmax]` is narrower than the data range (e.g.
   `ManualInterval(vmin=0.2, vmax=0.6)` over `rng.random((10,12))`, or add values `>1`/`<0` to
   the fixture) so an unclipped run would produce output outside `[0, 1]` and the existing
   `rgb.min() >= 0` / `rgb.max() <= 1` assertions become discriminating.
2. **(Cosmetic, optional)** Trim the trailing/doubled blank lines in `interval.py` left over
   from the strip-and-restore, and consider condensing the restate-the-what comments in
   `ZScaleInterval.get_limits`.

Nothing above blocks the verdict — item 1 is the only one with real leverage (a currently-silent
gap in S5's clip guarantee), and it is a strict improvement to an already-passing test, not a
missing behavior.

# 2609.0001 Restore RGBImageMapping Construction and Image Conversion

**Date:** 2026-09-10
**Status:** draft
**Author:** EP Lin

## Context

`astropy.visualization` provides a pipeline for turning three aligned
single-band images (red, green, blue) into a combined RGB image, built from
three modules:

- `astropy/visualization/interval.py` — `BaseInterval` subclasses compute
  `(vmin, vmax)` limits from raw data (`ManualInterval`, `MinMaxInterval`,
  `ZScaleInterval`, etc.).
- `astropy/visualization/stretch.py` — `BaseStretch` subclasses remap
  already-normalized `[0, 1]` values through a curve (`LinearStretch`,
  `LogStretch`, `CompositeStretch` via `stretch_a + stretch_b`, etc.).
- `astropy/visualization/basic_rgb.py` — `RGBImageMapping` ties one interval
  per channel and one shared stretch together; `make_rgb()` is the public
  wrapper around it. `astropy/visualization/lupton_rgb.py` builds
  `RGBImageMappingLupton` (a `RGBImageMapping` subclass, importable as
  `astropy.visualization.lupton_rgb.RGBImageMappingLupton`) and
  `make_lupton_rgb()` on the same interval/stretch machinery.

In the current working tree, nine method/function definitions — full
signature, docstring, and body, not just the body — have been deleted
across three files, and one import line has been blanked in a fourth
file:

- `astropy/visualization/basic_rgb.py` — the `RGBImageMapping` class
  (`__all__ = ["make_rgb"]`; the class itself is not exported) currently
  has only its class-level docstring; `__init__`, `make_rgb_image`,
  `apply_mappings`, `_convert_images_to_float`, and
  `_convert_images_to_uint` (5 definitions) do not exist at all (lines
  36–155 are blank). The module-level `make_rgb()` function and the
  `_OUTPUT_IMAGE_FORMATS = [float, np.float64, np.uint8]` constant are
  intact and unchanged.
- `astropy/visualization/interval.py` — `BaseInterval._process_values`
  (a `@staticmethod` every `get_limits()` depends on) and
  `ZScaleInterval.get_limits` (2 definitions) do not exist (lines 52–76
  and 321–336 are blank). `BaseInterval.__call__` and every other
  interval class are intact.
- `astropy/visualization/stretch.py` — the module-level `_prepare()`
  helper (used by nearly every `BaseStretch.__call__`) and
  `CompositeStretch.__call__` (2 definitions) do not exist (lines 40–54
  are blank, and the `CompositeStretch` class body is empty after its
  docstring, line 987 onward). Every other stretch class is intact.
- `astropy/visualization/lupton_rgb.py` — the line
  `from astropy.visualization.stretch import _prepare as _stretch_prepare`
  has been removed (line 16 is now blank), leaving `_stretch_prepare`
  undefined at the point `LuptonAsinhStretch.__call__` uses it. This is
  the only change in this file; `RGBImageMappingLupton.apply_mappings`
  (signature `(self, image_r, image_g, image_b)`) and `make_lupton_rgb`
  are intact and unchanged.
- `astropy/visualization/tests/test_basic_rgb.py` has been deleted from
  the working tree, but it is present, unmodified, at the current git
  HEAD commit (`b0db0daa`) in this repository — confirmed via `git show
  HEAD:astropy/visualization/tests/test_basic_rgb.py`. Only the working
  copy is gone; git history still has it.
- `astropy/visualization/tests/test_interval.py`,
  `test_stretch.py`, `test_lupton_rgb.py`, and `test_norm.py` are
  present, unmodified, and already exercise parts of this pipeline (see
  Motivation); `test_histogram.py` does not reference any interval or
  stretch class and is unaffected.

**On using git history:** the four source files above are `git status`
`M` (modified in the working tree, not deleted), so `git show HEAD --
<path>` reflects their exact pre-deletion implementation, and `git
checkout HEAD -- <path>` restores any of them verbatim. **This is an
acceptable and expected implementation strategy** — the point of this
spec is to define correct, testable behavior, not to force
reinvention of code that is one command away in the same repository.
Every description in Key Components and the Interface Contract below is
written to be sufficient on its own, so the restoration is correct
whether or not the implementing agent's environment has this git
history available; where it is available, using it is simply the
fastest way to satisfy this spec, not a shortcut around it.

`RGBImageMapping` (via `make_rgb`) and `RGBImageMappingLupton` (via
`make_lupton_rgb`) are both reachable from `astropy.visualization`
(`from .basic_rgb import *` and an explicit `lupton_rgb` import in
`astropy/visualization/__init__.py`), so `astropy.visualization` currently
imports without error but every RGB-conversion code path is either
missing (`AttributeError`) or broken (`NameError`/`TypeError`).

## Motivation

Right now:

- Any use of `RGBImageMapping(interval=..., stretch=...)` (including
  `make_rgb`, which calls it exactly this way) fails immediately with
  `TypeError: RGBImageMapping() takes no arguments` (the default
  `object.__init__` is reached instead, since `RGBImageMapping.__init__`
  does not exist and takes no keyword arguments). `RGBImageMappingLupton`
  (`lupton_rgb.py`) calls `super().__init__(interval=..., stretch=...)`
  by keyword from its own `__init__`, so **every** test in
  `test_lupton_rgb.py::TestLuptonRgb` that constructs one — `test_Asinh`,
  `test_AsinhZscale`, `test_AsinhZscaleIntensity`,
  `test_AsinhZscaleIntensityBW`, `test_AsinhZscale_pedestal_array`,
  `test_AsinhZscale_pedestal_float`, the two `LinearMapping`-flavored
  cases, `test_different_shapes_asserts`, and `test_make_rgb` — fails
  with this same `TypeError` at construction, before any of them can
  reach the separate `NameError: _stretch_prepare` problem described
  below. The four `AsinhZscale*` tests have an additional dependency:
  `LuptonAsinhZscaleStretch.__init__` calls `ZScaleInterval().get_limits(
  image)` directly, so they also depend on Key Component 2 below.
- `astropy/visualization/tests/test_interval.py::test_zscale` and
  `::test_zscale_npoints` fail (`ZScaleInterval.get_limits` does not
  exist). In the same file, `BaseInterval._process_values` (used by
  `MinMaxInterval.get_limits`, `PercentileInterval.get_limits`,
  `AsymmetricPercentileInterval.get_limits`, and `SymmetricInterval
  .get_limits` when no explicit `radius` is given) does not exist, so
  the data-inspecting cases in `TestInterval` and its four subclasses
  (`TestIntervalList`, `TestInterval2D`, `TestIntervalMaskedArray`,
  `TestIntervalMaskedNDArray`) fail: `test_manual_defaults`,
  `test_manual_defaults_with_nan`, `test_minmax`, `test_percentile`,
  `test_asymmetric_percentile`, `test_asymmetric_percentile_nsamples`,
  and `test_symmetric_interval_auto`, plus the module-level
  `test_integers`. `test_manual`, `test_manual_zero_limit`, and
  `test_symmetric_interval_manual` **currently pass** in all five
  classes, because `ManualInterval.get_limits` short-circuits before
  calling `_process_values` when both `vmin` and `vmax` are already
  given, and `SymmetricInterval.get_limits` short-circuits the same way
  when `radius` is given — restoring `_process_values` must not change
  that these three keep passing.
  `astropy/visualization/tests/test_norm.py` (which drives these same
  interval/stretch classes through `ImageNormalize`) fails for the same
  reason wherever it hits a data-inspecting case.
- Every parametrized case in `astropy/visualization/tests/test_stretch.py
  ::TestStretch` (`test_no_clip`, `test_clip`, `test_clip_ndimensional`,
  `test_inplace`, `test_round_trip`, `test_inplace_roundtrip`,
  `test_double_inverse`), plus `test_clip_invalid` and
  `test_linearstretch_clip`, fail because the module-level `_prepare()`
  helper does not exist. Once `_prepare` is restored, all of those pass
  for every entry in `TestStretch`'s `RESULTS` table (there is exactly
  one `CompositeStretch` entry in that table:
  `LinearStretch(intercept=0.5) + LinearStretch(slope=0.5)`) **except**
  that one composite entry under `test_inplace` and
  `test_inplace_roundtrip` specifically — those two pass `out=` and fail
  with `TypeError: __call__() got an unexpected keyword argument 'out'`
  because `CompositeStretch` has no `__call__` override to accept it (it
  currently falls back to the inherited
  `CompositeTransform.__call__(self, values, clip=True)`, which forwards
  `clip` correctly but has no `out` parameter at all).
  (`test_no_clip`/`test_clip`/`test_round_trip`/`test_double_inverse` on
  that same composite entry pass with no `CompositeStretch` change
  whatsoever, once `_prepare` works, since none of them pass `out=`.)
- `astropy/visualization/tests/test_lupton_rgb.py::TestLuptonRgb
  ::test_Asinh` (and any other test that actually calls a
  `LuptonAsinhStretch` instance) fails with `NameError: name
  '_stretch_prepare' is not defined`.

Restoring the nine missing definitions and the one import unblocks all of
the above without modifying any of those four already-existing test
files, and restores the deleted `test_basic_rgb.py` coverage.

## Proposed Solution

### Overview

Recreate the nine missing definitions and the one import so the
interval → stretch → per-channel-mapping → dtype-conversion pipeline works
end to end, and recreate `astropy/visualization/tests/test_basic_rgb.py`.
Do not change any public signature, class name, `__all__` list, or
module-level constant in any of the four source files — this is a
restoration, not a redesign.

### Key Components

The following six items are the **only** things that need to change (5 +
2 + 2 = 9 definitions, plus 1 import). None of these nine definitions has
a surviving docstring or signature in the working tree — the
descriptions below and the Interface Contract section are a complete
enough specification on their own; git history (see the Context note
above) additionally has the exact pre-deletion code if available in your
environment.

1. **`BaseInterval._process_values(values)`** (`interval.py`, `@staticmethod`,
   used by every `get_limits()`) — flatten `values` into a 1D array. Use
   `astropy.utils.masked.get_data_and_mask` to split `values` into
   `(data, mask)`; keep only entries where `data` is finite
   (`np.isfinite`) *and*, if `mask` is not `None`, unmasked. Return that
   filtered 1D array.
2. **`ZScaleInterval.get_limits(values)`** (`interval.py`) — IRAF-zscale:
   a. `values = self._process_values(values)`.
   b. Sample: `stride = max(1, values.size // self.n_samples)`; take
      `values[::stride][:self.n_samples]`, sorted ascending — call this
      `samples`, with `npix = len(samples)`, `vmin = samples[0]`,
      `vmax = samples[-1]` as the starting fallback values.
   c. Iteratively (up to `self.max_iterations` times) fit a line
      `y = slope * x + intercept` to `samples` by weighted least squares
      (`np.polyfit(x, samples, deg=1, w=(~badpix).astype(int))` where `x
      = np.arange(npix)`), then flag samples more than `self.krej` sigma
      (std of the unflagged residuals) from the fit as `badpix`, dilating
      the bad-pixel mask by a kernel of width `max(1, int(npix * 0.01))`
      each iteration. Stop early if the good-pixel count stops shrinking
      or drops below `minpix = max(self.min_npixels, int(npix *
      self.max_reject))`.
   d. If the final good-pixel count is `>= minpix`, derive
      `slope` from the last fit (divided by `self.contrast` if
      `self.contrast > 0`), and set `vmin = max(vmin, median -
      (center_pixel - 1) * slope)`, `vmax = min(vmax, median + (npix -
      center_pixel) * slope)` where `center_pixel = (npix - 1) // 2` and
      `median = np.median(samples)`. Otherwise (good-pixel count below
      `minpix`), leave `vmin`/`vmax` as the raw sampled min/max from step
      (b) — this is the only path exercised by S14 below.
   e. Return `(vmin, vmax)`.
3. **`_prepare(values, clip=True, out=None)`** (`stretch.py`, module-private,
   used by nearly every `BaseStretch.__call__`) — if `clip` is true:
   `return np.clip(values, 0.0, 1.0, out=out)`. If `clip` is false and
   `out` is `None`: return an independent copy of `values` (mutating the
   result must not affect the caller's `values`). If `clip` is false and
   `out` is given: copy `values` into `out` and return `out`.
4. **`CompositeStretch.__call__(self, values, clip=True, out=None)`**
   (`stretch.py`) — apply `self.transform_1` then `self.transform_2` in
   order, threading both `clip` and `out` through both calls, so the
   second call's return value (which is `out` itself when `out` was
   given) is the final result: conceptually
   `self.transform_2(self.transform_1(values, clip=clip, out=out), clip=clip, out=out)`.
5. **`RGBImageMapping.__init__` / `.make_rgb_image` / `.apply_mappings` /
   `._convert_images_to_float` / `._convert_images_to_uint`**
   (`basic_rgb.py`) — see Interface Contract below.
6. **`lupton_rgb.py` import** — restore the line
   `from astropy.visualization.stretch import _prepare as _stretch_prepare`
   (it must bind the name `_stretch_prepare`, exactly as
   `LuptonAsinhStretch.__call__` already references it). No other change
   in this file.

### Data Flow

1. `RGBImageMapping(interval=..., stretch=...)` normalizes `interval` into
   a 3-element list (`self.intervals`) and stores `stretch` (`self.stretch`).
2. `make_rgb_image(image_r, image_g, image_b, output_dtype=...)` validates
   `output_dtype` and that the three input shapes match.
3. It calls `self.apply_mappings(image_r, image_g, image_b)`, which
   independently normalizes and stretches each channel into `[0, 1]`
   (for stretches whose output stays within `[0, 1]` on `[0, 1]`-clipped
   input — see the note on stretch range in the Interface Contract)
   using that channel's interval and the shared stretch, returning an
   array of shape `(3, N, M)` (this exact shape is a hard contract:
   `RGBImageMappingLupton.apply_mappings`, unchanged in `lupton_rgb.py`,
   overrides this method and returns the same shape, and the inherited
   `make_rgb_image` must consume either implementation identically).
   The three input arrays passed to `apply_mappings`/`make_rgb_image`
   must be unchanged after the call returns (it must copy, not mutate,
   each channel) — see S23.
4. `make_rgb_image` dispatches on `output_dtype`: if
   `np.issubdtype(output_dtype, np.floating)`, call
   `self._convert_images_to_float(image_rgb, output_dtype)`; if
   `np.issubdtype(output_dtype, np.unsignedinteger)`, call
   `self._convert_images_to_uint(image_rgb, output_dtype)`. It then
   stacks the three `(N, M)` channels along a new **last** axis
   (`np.dstack`-style) to produce shape `(N, M, 3)` and returns that.
5. `make_rgb()` (already implemented, unchanged) builds an
   `RGBImageMapping` and calls `make_rgb_image` on it, optionally saving
   to a file via `matplotlib.image.imsave` (unchanged, optional
   dependency).

### Interface Contract

`RGBImageMapping` in `astropy/visualization/basic_rgb.py`, importable as
`from astropy.visualization.basic_rgb import RGBImageMapping`, must match
this exactly (parameter names, order, and defaults are mandatory):

```python
class RGBImageMapping:
    def __init__(
        self,
        interval=ManualInterval(vmin=0, vmax=None),
        stretch=LinearStretch(),
    ):
        """
        interval : a BaseInterval instance, or an array-like of exactly 3
            BaseInterval instances (one per R, G, B, stored as
            `self.intervals`). A single instance is expanded to a
            3-element list reusing that same object for all three
            channels.
        stretch : a BaseStretch instance, shared across all three
            channels, stored as `self.stretch`.

        Raises
        ------
        ValueError
            If `interval` is array-like but does not have exactly 3
            elements. The message must contain "3 instances for
            interval." (case-sensitive substring match).
        """

    def make_rgb_image(self, image_r, image_g, image_b, output_dtype=np.uint8):
        """
        image_r, image_g, image_b : ndarray, same shape (NxM). May be int
            or float dtype on input (for the base RGBImageMapping path;
            RGBImageMappingLupton's overridden apply_mappings is not
            required to support integer input — see S11).
        output_dtype : one of [float, np.float64, np.uint8].

        Returns
        -------
        RGBimage : ndarray, shape (N, M, 3), dtype == output_dtype.
            For a stretch whose output stays within [0, 1] when called
            with clip=False on [0, 1]-clipped input (true of
            LinearStretch and LogStretch, the two stretches used
            throughout this spec's scenarios; NOT guaranteed for a
            stretch like ContrastBiasStretch whose documented range is
            outside [0, 1] — such stretches are out of scope for the
            range guarantee below, matching the pre-deletion code, which
            applies no final clip after the stretch):
              - float output values lie in [0, 1].
              - np.uint8 output values lie in [0, 255], each
                channel-and-pixel value equal to
                `np.uint8(np.floor(normalized_value * 255))`, where
                `normalized_value` is that same pixel's value in the
                [0, 1] float64 output for identical inputs/interval/
                stretch (so a normalized value of exactly 1.0 maps to
                255, and 0.0 maps to 0).
            NaN-valued input pixels: out of scope for this restoration
            (the pre-deletion code applies no NaN guard in
            apply_mappings or the dtype converters; a NaN input pixel
            produces NaN in the float path and an implementation-defined
            uint8 value on that path, matching pre-deletion behavior).

        Raises
        ------
        ValueError
            If output_dtype is not one of [float, np.float64, np.uint8].
            The message must contain "'output_dtype' must be one"
            (case-sensitive substring match).
        ValueError
            If image_r/image_g/image_b shapes do not all match. The
            message must contain "shapes must match" (case-sensitive
            substring match).
        """

    def apply_mappings(self, image_r, image_g, image_b):
        """
        Returns a (3, N, M) array: for channel i, look up
        `vmin, vmax = self.intervals[i].get_limits(image)`, copy that
        channel to an independent float array, apply
        `(image - vmin) / (vmax - vmin)` (no zero-division guard — if
        `vmin == vmax`, this intentionally produces inf/nan/RuntimeWarning
        via `np.true_divide`, matching plain floating-point division
        semantics rather than the guarded behavior of
        `BaseInterval.__call__`; see S19), clip to [0, 1], then apply
        `self.stretch(image, out=image, clip=False)`. Must not mutate the
        caller's original image_r/image_g/image_b arrays (see S23).
        """

    def _convert_images_to_float(self, image_rgb, output_dtype):
        """Cast the already-[0, 1]-normalized (3, N, M) array to
        output_dtype unchanged (no scaling)."""

    def _convert_images_to_uint(self, image_rgb, output_dtype):
        """Multiply the normalized (3, N, M) array by
        `float(np.iinfo(output_dtype).max)`, then cast to output_dtype."""
```

## Alternatives Considered

### Rewrite the pipeline with a new API

Rejected: `RGBImageMappingLupton` in `lupton_rgb.py` subclasses
`RGBImageMapping`, overriding `__init__`, `intensity`, and
`apply_mappings`, and is otherwise unchanged in this working tree. Its
`__init__` calls `super().__init__(interval=..., stretch=...)` **by
keyword** — which is exactly why the parameter names in the Interface
Contract below are mandatory, not just their order/defaults. It also
depends on `self.intervals`, `self.stretch`, and the exact
`apply_mappings`/`make_rgb_image` shapes described below. Changing the
base class's shape would force changes in `lupton_rgb.py` beyond the one
blanked import, which is out of scope — this is a restoration, not a
redesign. The Interface Contract above also fixes the exact
`RGBImageMapping.__init__`/`make_rgb_image` signature as a hard
requirement, so an alternative API is not an option.

## Security Considerations

None. Pure numerical array processing; the only I/O is the already-present,
unchanged, optional `matplotlib.image.imsave` file-write path in
`make_rgb`/`make_lupton_rgb`, gated by an explicit `filename` argument.

## Acceptance Scenarios

All fixture data and reference numbers below are taken verbatim from
`astropy/visualization/tests/test_basic_rgb.py` as it exists at git HEAD
— they are not estimates. See the Test Coverage Map at the end of this
section for exactly which test (restored-verbatim, existing-unmodified,
or net-new) each scenario ID maps to.

**Shared fixture** (module-level in `test_basic_rgb.py`, referred to below
as *the Gaussian fixture*): `SHAPE = (85, 75)`; `_grid = np.indices(SHAPE)`
so `_grid[0]` ranges over axis 0 (0..84) and `_grid[1]` ranges over axis 1
(0..74); four Gaussian blobs at `_points = [[15,15],[50,45],[30,30],
[45,15]]` (each `[a, b]` is `(axis-0 index, axis-1 index)`, matching
`_grid[0]`/`_grid[1]`) with peak values `_values = [1000, 5500, 600,
20000]` and widths `_stddevs = [1.5, 2.0, 1.0, 2.5]`; for each blob, the
**peak-amplitude** (not area-normalized) Gaussian is
`gaussian = np.exp(-((_grid[0]-a)**2/(2*std**2) + (_grid[1]-b)**2/(2*std**2)))`
(so `gaussian` peaks at exactly `1.0` at pixel `[a, b]` and decays with
no further scaling); each blob's red/green/blue contribution uses color
indices `_g_r = [1.0, -1.0, 1.0, 1.0]` and `_r_i = [2.0, -0.5, 2.5, 1.0]`:
`IMAGER += v * 10**(0.4*ri) * gaussian`, `IMAGEG += v * 10**(0.4*gr) *
gaussian`, `IMAGEB += v * gaussian`, accumulated over all four blobs;
then `rng = np.random.default_rng(0)` adds `rng.normal(0, 2, SHAPE)` to
`IMAGER`, then a **second, independent** `rng.normal(0, 2, SHAPE)` call
to `IMAGEG`, then a **third** to `IMAGEB`, in that order (order matters
for reproducibility of a single shared `rng` instance across three
sequential calls). `IX = IY = 16` is the pixel index used for
single-pixel checks below, i.e. `result[IX, IY, :]` == `result[16, 16,
:]`, indexing axis 0 then axis 1, consistent with `_grid`/`_points`
above.

### Happy Path

- **S1:** Given the Gaussian fixture and `RGBImageMapping(stretch=
  LinearStretch(), interval=[ManualInterval(vmin=0, vmax=5e4),
  ManualInterval(vmin=0, vmax=5e4), ManualInterval(vmin=0, vmax=4e4)])`,
  when `.make_rgb_image(IMAGER, IMAGEG, IMAGEB, output_dtype=np.float64)`
  is called, then the result has shape `(85, 75, 3)`, dtype `float64`,
  per-channel `(min, max)` of exactly `(0.0, 1.0)`, `(0.0, 1.0)`,
  `(0.0, 0.5000598388671327)`, and `result[16, 16, :]` equals
  `[0.08093024185629245, 0.032216094791227695, 0.016040737174622725]`
  (`rtol=1e-6`).
- **S2:** Given the same fixture, interval list, and default `stretch`
  (`LinearStretch()`, the default), when driven through
  `astropy.visualization.basic_rgb.make_rgb(IMAGER, IMAGEG, IMAGEB,
  interval=interval, output_dtype=np.float64)` instead of constructing
  `RGBImageMapping` directly, then the result equals S1's result exactly
  — same per-channel min/max and same `[16, 16, :]` triplet — showing
  `make_rgb` is a thin wrapper.
- **S3:** Given the same fixture and interval list as S1/S2 but
  `stretch=LogStretch(a=1500.0)`, when `make_rgb(...)` is called with
  `output_dtype=np.float64`, then per-channel max is `(1.0, 1.0,
  0.9053360156408082)` and `result[16, 16, :]` equals
  `[0.6572779418489928, 0.5330153105260111, 0.4404384627801792]`
  (`rtol=1e-6`) — distinct from S1's values, confirming the stretch is
  actually applied per channel after interval normalization.
- **S4:** Given the exact setup and fixture of S1 (`ManualInterval` list,
  `LinearStretch`), when `make_rgb_image(..., output_dtype=np.uint8)` is
  called instead of `np.float64`, then `result.dtype == np.uint8`, every
  value lies in `[0, 255]`, and the whole `(85, 75, 3)` array equals
  `(float64_reference * 255).astype(np.uint8)` where `float64_reference`
  is S1's exact float64 result — in particular `result[:, :, 0].max() ==
  255` and `result[:, :, 0].min() == 0`.
- **S5:** Given the exact setup and fixture of S1, when
  `make_rgb_image(..., output_dtype=float)` (the builtin, not
  `np.float64`) is called, then the result equals S1's result exactly
  (same values, `np.issubdtype(result.dtype, float)` is true) — confirms
  both members of `_OUTPUT_IMAGE_FORMATS` that are floating-point
  dispatch to the same conversion path.
- **S6:** Given the Gaussian fixture and a single `ManualInterval(vmin=
  None, vmax=None)` (not a 3-list) passed as `interval` to `make_rgb`
  with default `stretch=LinearStretch()`, when called, then construction
  succeeds without raising (the single interval object is reused for all
  three channels, each independently computing its own image's actual
  min/max since both bounds are `None`), all three channel maxima are
  exactly `1.0`, and `result[16, 16, :]` equals
  `[0.08069534125307666, 0.032196043103128555, 0.032466842729915714]`
  (`rtol=1e-6`) — distinct from S1 because each channel now auto-scales
  to its own max instead of the fixed per-channel max in S1.
- **S7:** Given the same auto-scaling interval as S6 combined with
  `stretch=LogStretch(a=1500.0)`, when `make_rgb(...)` is called, then all
  three channel maxima are still exactly `1.0` but `result[16, 16, :]`
  equals `[0.6568837677677257, 0.5329319103684619, 0.5340539629318083]`
  (`rtol=1e-6`) — distinct from both S6 (different stretch) and S3
  (different interval), confirming stretch is applied after auto-scaled
  normalization.
- **S8:** Given a single `ManualInterval(vmin=0.0, vmax=5e4)` (one fixed
  pair reused for all 3 channels via the single-instance expansion) with
  `image_r == image_g == image_b == IMAGER` (the grayscale case) and
  `stretch=LinearStretch()`, when `make_rgb(...)` is called, then all
  three output channels are numerically identical to each other: max
  `1.0` for all three, and `result[16, 16, :]` equals
  `[0.08093024185629245, 0.08093024185629245, 0.08093024185629245]`.
- **S9:** Given the same setup as S8 but `stretch=LogStretch(a=1500.0)`,
  when `make_rgb(...)` is called, then all three channels are again
  identical to each other, with max `1.0` for all three and
  `result[16, 16, :]` equal to `[0.6572779418489928,
  0.6572779418489928, 0.6572779418489928]`.
- **S10:** Given `RGBImageMappingLupton(interval=ManualInterval(vmin=0,
  vmax=None), stretch=lupton_rgb.LuptonAsinhStretch(stretch=5, Q=20))`
  (importable as `astropy.visualization.lupton_rgb
  .RGBImageMappingLupton`) built over three same-shape `(85, 75)` images
  constructed the same way as `test_lupton_rgb.py::TestLuptonRgb
  .setup_method`'s fixture (Gaussian blobs convolved with a PSF plus
  noise — reuse that existing fixture logic, do not modify
  `test_lupton_rgb.py` itself), when `.make_rgb_image(image_r, image_g,
  image_b)` is called, then it returns an array of shape `(85, 75, 3)`
  and dtype `np.uint8`, without raising `NameError` or `AttributeError`.
  Note: `test_lupton_rgb.py::TestLuptonRgb::test_Asinh` already calls
  this same code path but asserts nothing about its result (only that it
  doesn't raise) — S10's shape/dtype assertions require a *new* test;
  restoring `test_lupton_rgb.py`'s existing behavior alone does not cover
  them.
- **S11:** Given S1's exact setup (fixture, interval list, `LinearStretch`)
  but with `IMAGER`, `IMAGEG`, `IMAGEB` each cast to `np.int32` before the
  call, when `RGBImageMapping(...).make_rgb_image(image_r_int, image_g_int,
  image_b_int, output_dtype=np.float64)` is called, then it succeeds (no
  `TypeError` from in-place float operations on an integer input array)
  and the result equals, elementwise, `RGBImageMapping(...)
  .make_rgb_image(image_r_int.astype(np.float64), image_g_int.astype(
  np.float64), image_b_int.astype(np.float64), output_dtype=np.float64)`
  (`rtol=1e-12`) — i.e. integer input is equivalent to pre-casting to
  float before the call. This scenario binds only the base
  `RGBImageMapping` path; `RGBImageMappingLupton.apply_mappings` (in
  `lupton_rgb.py`, unchanged) is not required to support integer input,
  since its `np.multiply(image_rgb, fInorm, out=image_rgb)` step would
  raise a casting error on an integer output array, and fixing that is
  out of scope (it is not one of the nine deleted definitions).

### Edge Cases

- **S12:** Given `np.random.seed(42); data = np.random.randn(100, 100) * 5
  + 10`, when `ZScaleInterval().get_limits(data)` is called, then it
  returns `(vmin, vmax)` with `vmin ≈ -9.6` and `vmax ≈ 25.4`
  (`atol=0.1`) — existing test:
  `test_interval.py::test_zscale` (first block).
- **S13:** Given `data = list(range(1000)) + [np.nan]`, when
  `ZScaleInterval().get_limits(data)` is called, then the NaN is excluded
  from consideration (via `_process_values`'s `np.isfinite` filter) and
  it returns `vmin ≈ 0`, `vmax ≈ 999` (`atol=0.1`) — existing test:
  `test_interval.py::test_zscale` (second block). This is the
  discriminator for `_process_values`'s `np.isfinite` filter: dropping it
  changes `samples.sort()` to error or silently include the NaN,
  breaking this result.
- **S14:** Given `data = np.arange(4).reshape((2, 2))` and
  `ZScaleInterval(min_npixels=5)`, when `.get_limits(data)` is called,
  then because the sample size (4) is below `min_npixels` (5), the
  iterative fit is skipped and it returns exactly `(vmin, vmax) == (0,
  3)` (the raw sampled min/max) — existing test:
  `test_interval.py::test_zscale_npoints`.
- **S15:** Given `data = np.concatenate((np.linspace(-20.0, 60.0, 100),
  np.full(100, 1e6)))` wrapped either as `np.ma.MaskedArray(data, data >
  1000)` (`TestIntervalMaskedArray`) or as `astropy.utils.masked.Masked(
  data, data > 1000)` (`TestIntervalMaskedNDArray` — the variant that
  exercises `get_data_and_mask`, the function Key Component 1 uses to
  split data from mask) — either way masking out the 100 outlier `1e6`
  entries, when `MinMaxInterval().get_limits(data)` (or
  `ManualInterval()`, `PercentileInterval(...)`, etc. — any
  `BaseInterval` subclass relying on `_process_values`) is called, then
  the masked entries are excluded and the result matches the same call
  on `np.linspace(-20.0, 60.0, 100)` alone (`vmin=-20.0, vmax=60.0` for
  `MinMaxInterval`) — existing tests:
  `test_interval.py::TestIntervalMaskedArray` and
  `::TestIntervalMaskedNDArray`, which run every `TestInterval` case
  (`test_manual`, `test_minmax`, `test_percentile`, etc.) against exactly
  this masked fixture. This is the discriminator for
  `_process_values`'s mask filter specifically (S13 above is the
  discriminator for its `np.isfinite` filter; `test_interval.py
  ::TestInterval::test_manual_defaults_with_nan` exists but calls
  `get_limits` on the pristine, non-NaN `self.data` attribute rather than
  the locally NaN-mutated `data` variable, so it does not discriminate
  either filter and is not cited as coverage for anything in this spec).
- **S16:** Given `stretch = SqrtStretch()` and `values = [-1.0, 0.0, 0.5,
  1.0, 1.5]`, when called with the default `clip=True`, then the `-1.0`
  and `1.5` are first clipped to `0.0`/`1.0` by `_prepare` *before* the
  sqrt, giving `[0.0, 0.0, 0.70710678, 1.0, 1.0]`; when called with
  `clip=False` on the same input, then no pre-clip happens, `sqrt(-1.0)`
  is `NaN`, giving `[nan, 0.0, 0.70710678, 1.0, 1.2247448]` — existing
  test: `test_stretch.py::test_clip_invalid`. This is the discriminating
  case for `_prepare`'s `clip` branch: swapping the `if clip` /`else`
  body in `_prepare` flips both of these results.
- **S17:** Given `stretch_1 = LinearStretch(slope=0.5)` and `stretch_2 =
  LinearStretch(intercept=0.5)` combined as `composite = LinearStretch(
  intercept=0.5) + LinearStretch(slope=0.5)` (i.e. `composite.transform_1
  is stretch_1`, `composite.transform_2 is stretch_2`, applying
  `stretch_1` then `stretch_2`), when `composite(np.array([0.00, 0.25,
  0.50, 0.75, 1.00]), clip=False)` is called, then the result is
  `[0.5, 0.625, 0.75, 0.875, 1.0]` (`atol=1e-6`) — existing tests:
  `test_stretch.py::TestStretch::test_no_clip`, `test_clip`,
  `test_round_trip`, `test_double_inverse` for this `RESULTS` entry. Note:
  this scenario already passes once `_prepare` is restored, with no
  `CompositeStretch.__call__` override needed, because
  `CompositeStretch` currently inherits `CompositeTransform.__call__`
  which forwards `clip` correctly — it is not, by itself, evidence that
  `CompositeStretch.__call__` has been restored (see S18).
- **S18:** Given the same `composite` stretch from S17, a source array
  `data_in = np.array([0.00, 0.25, 0.50, 0.75, 1.00])`, and a preallocated
  `result = np.zeros(5)`, when `composite(data_in, out=result,
  clip=False)` is called, then it must not raise `TypeError` (which it
  does today, since the inherited `CompositeTransform.__call__` has no
  `out` parameter), `result` receives `[0.5, 0.625, 0.75, 0.875, 1.0]`,
  and `data_in` is left unmodified — existing tests:
  `test_stretch.py::TestStretch::test_inplace`,
  `test_inplace_roundtrip` for this `RESULTS` entry. This is the
  discriminating scenario that requires `CompositeStretch.__call__` to
  exist and thread `out` through both sub-transforms.
- **S19:** Given `img = np.array([[4.0, 5.0, 6.0]])` (used for all three
  channels) and `RGBImageMapping(interval=ManualInterval(vmin=5, vmax=5),
  stretch=LinearStretch())` (a degenerate interval where `vmin == vmax`),
  when `.apply_mappings(img, img, img)` is called inside
  `pytest.warns(RuntimeWarning)` (the division below raises
  `RuntimeWarning: invalid value encountered`/`divide by zero`, and this
  repository's `pyproject.toml` sets `filterwarnings = ["error", ...]`,
  so the test must expect the warning explicitly or it errors instead of
  passing), then each of the three returned `(1, 3)` channels equals
  `[0.0, nan, 1.0]`: `(4-5)/(5-5) = -inf` and `(6-5)/(5-5) = +inf` are
  each then clipped to `[0, 1]` (giving `0.0` and `1.0` respectively),
  while `(5-5)/(5-5) = nan` survives the clip unchanged (`np.clip` does
  not alter `nan`), and `LinearStretch(clip=False)` (slope=1,
  intercept=0) passes all three through unchanged. This is the
  discriminator for `apply_mappings`'s division being **unguarded**: an
  implementation that adds a `vmax - vmin != 0` guard (matching
  `BaseInterval.__call__`'s guarded behavior, which this restoration
  intentionally does not replicate here) turns the middle value into
  `0.0` instead of `nan`, giving `[0.0, 0.0, 1.0]` and failing this
  scenario's `nan`-at-index-1 assertion (use `np.testing.assert_equal`,
  which treats `nan == nan` as equal, unlike a plain `==`). This is a new
  test; no existing or restorable file covers it.

### Error Scenarios

- **S20:** Given `RGBImageMapping(interval=[ManualInterval(vmin=0,
  vmax=1), ManualInterval(vmin=0, vmax=1)])` (a 2-element list), when the
  constructor runs, then it raises `ValueError` matching `"3 instances for
  interval."` — restorable test:
  `test_basic_rgb.py::test_incorrect_interval_length`.
- **S21:** Given the Gaussian fixture with `image_r` reshaped to
  `(75, 85)` (dimensions swapped relative to `image_g`/`image_b`'s
  `(85, 75)`), when `make_rgb(image_r, image_g, image_b, stretch=
  LogStretch(a=1500.0))` is called, then it raises `ValueError` matching
  `"shapes must match"` — restorable test:
  `test_basic_rgb.py::test_different_shapes_asserts`.
- **S22:** Given `output_dtype` set to each of `bool`, `str`, `np.int64`,
  `np.cdouble`, and the string literal `"str"` in turn, when
  `make_rgb(IMAGER, IMAGEG, IMAGEB, interval=[...], stretch=
  LogStretch(a=1500.0), output_dtype=output_dtype)` is called for each,
  then every case raises `ValueError` matching `"'output_dtype' must be
  one"` — restorable test: `test_basic_rgb.py::test_invalid_output_dtype`
  (parametrized over `INCORRECT_OUTPUT_TYPES`).

### Invariants

- **S23:** Given the exact setup of S1, when `make_rgb_image(IMAGER,
  IMAGEG, IMAGEB, output_dtype=np.float64)` is called, then `IMAGER`,
  `IMAGEG`, and `IMAGEB` are bit-identical (`np.array_equal`) to copies
  taken immediately before the call — `apply_mappings` must copy each
  channel, not mutate it in place. This is a new test; no existing or
  restorable file covers it.
- **S24:** Given `stretch = SqrtStretch()` and `data = np.array([0.0,
  0.25, 0.5, 0.75, 1.0])`, when `stretch(data, clip=False)` is called
  (no `out` argument), then the returned array is a different object
  from `data`, and `data` itself is unchanged after the call
  (`np.array_equal(data, [0.0, 0.25, 0.5, 0.75, 1.0])` still holds) —
  this pins `_prepare`'s "independent copy when `out is None`" branch.
  This is a new test; no existing or restorable file covers it (the
  existing `test_stretch.py::TestStretch::test_inplace` only exercises
  the `out is not None` branch).

### Test Coverage Map

| Scenario | Test home |
|---|---|
| S1, S2, S3, S6, S7, S8, S9 | Restore `test_basic_rgb.py` verbatim from git HEAD (`test_image_mapping`, `test_linear`, `test_log`, `test_linear_min_max`, `test_log_min_max`, `test_linear_bw`, `test_log_bw`) |
| S4, S5 | Restoring `test_basic_rgb.py`'s `test_int8`/`test_float64` verbatim covers the dtype check only; add new assertions (in that file or a new one) for the exact-value checks in S4/S5 |
| S10 | New test (do not modify `test_lupton_rgb.py`) |
| S11, S19, S23, S24 | New tests |
| S12, S13, S14 | Existing, unmodified: `test_interval.py::test_zscale`, `::test_zscale_npoints` |
| S15 | Existing, unmodified: `test_interval.py::TestIntervalMaskedArray`, `::TestIntervalMaskedNDArray` |
| S16 | Existing, unmodified: `test_stretch.py::test_clip_invalid` |
| S17 | Existing, unmodified: `test_stretch.py::TestStretch::test_no_clip`/`test_clip`/`test_round_trip`/`test_double_inverse` |
| S18 | Existing, unmodified: `test_stretch.py::TestStretch::test_inplace`/`test_inplace_roundtrip` |
| S20, S21, S22 | Restore `test_basic_rgb.py` verbatim from git HEAD (`test_incorrect_interval_length`, `test_different_shapes_asserts`, `test_invalid_output_dtype`) |

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that would *fail if the behavior were wrong*. A green suite that passes for the wrong reason does not satisfy this contract — `/verify` will hunt for vacuous tests by asking, of each behavior, "what is the smallest change that breaks this, and would any test catch it?"

Restore the six Key Components items (9 definitions + 1 import). The
`RGBImageMapping` signatures in the Interface Contract section are
mandatory and exact — match parameter names, order, and defaults
character for character. `apply_mappings`, `_convert_images_to_float`,
and `_convert_images_to_uint`'s *external behavior* (return shape,
no-mutation guarantee, scaling formula) is also mandatory, since
`RGBImageMappingLupton` in `lupton_rgb.py` depends on it, but their
internal structure is yours to choose. Using `git show HEAD -- <path>` /
`git checkout HEAD -- <path>` on any of the four source files, if that
history is available in your environment, is an acceptable way to recover
the exact pre-deletion code — see the Context note on git history.

Follow the Test Coverage Map above: restore `astropy/visualization/tests
/test_basic_rgb.py` (via `git checkout HEAD -- astropy/visualization/
tests/test_basic_rgb.py` if available, or recreated from the fixture and
values given verbatim in the Acceptance Scenarios section otherwise), add
the new tests it calls out (S4/S5's exact-value assertions, S10, S11,
S19, S23, S24), and do **not** modify `test_interval.py`, `test_stretch.py`,
`test_lupton_rgb.py`, or `test_norm.py` — they are unmodified and already
cover S12–S18 and part of S10. Run them as-is; if your implementation
doesn't make them pass unmodified, the implementation is wrong, not the
tests.

Write any new tests to the project's conventions (pytest, `numpy.testing
.assert_allclose` for numeric comparisons, `pytest.raises(..., match=...)`
for errors) and to these principles (the same ones `/verify` scores
against — see `references/test-desiderata.md` and
`references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects
  (returned arrays, dtypes, exceptions), not internals; the suite must
  survive refactoring of `apply_mappings`'s internal structure.
- **Every test can fail** — no copy-pasted expected values without a
  traceable source (the values in this spec all trace to `git show
  HEAD:astropy/visualization/tests/test_basic_rgb.py` or an already-
  existing test file, cited scenario by scenario above), no asserting a
  constant unless it's a genuine invariant (e.g. dtype/shape checks), no
  tautologies (AP-2, AP-4).
- **Deterministic, isolated, readable** — seed any randomness
  (`np.random.seed`/`np.random.default_rng` with a fixed seed, as the
  cited fixtures already do), no cross-test shared mutable state, AAA
  structure with inline setup.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] The full `astropy/visualization/tests/` suite is green, including
  `test_interval.py`, `test_stretch.py`, `test_lupton_rgb.py`, and
  `test_norm.py` run unmodified.
- [ ] Every acceptance scenario (S1…S24) maps to at least one test, per
  the Test Coverage Map.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
  the smallest break of its behavior (thought-mutation), e.g.: swapping
  the `if clip` / `else` branch in `_prepare` must break S16; dropping
  the `np.isfinite` filter in `_process_values` must break S13; dropping
  its mask filter must break S15; removing the `* 255` scale in
  `_convert_images_to_uint` must break S4; adding a `vmax - vmin != 0`
  guard to `apply_mappings` turns S19's `nan` (at the pixel equal to
  `vmin`) into `0.0`, breaking it; omitting `out` support in
  `CompositeStretch.__call__` must break S18 without breaking S17;
  mutating the input in `apply_mappings` or in `_prepare`'s no-`out`
  branch must break S23/S24 respectively.
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
  first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale
  docstrings) remain in `basic_rgb.py`, `interval.py`, `stretch.py`, or
  `lupton_rgb.py`.

## Trade-offs and Limitations

- `ZScaleInterval.get_limits`'s k-sigma rejection loop is iterative and
  its exact fitted slope depends on floating-point order of operations;
  the tolerances in S12–S13 (`atol=0.1`) and the exact-match case in S14
  (fallback path, no fit involved) are chosen to allow minor
  implementation variation in the iterative branch while still catching a
  materially wrong algorithm.
- S19 locks in an inconsistency that already exists between
  `apply_mappings` (unguarded division) and `BaseInterval.__call__`
  (guarded division) in the pre-deletion code. This spec restores that
  inconsistency as-is rather than resolving it, since resolving it would
  be a behavior change beyond the scope of a restoration.
- The range guarantee in the Interface Contract (`make_rgb_image`'s float
  output in `[0, 1]`, uint8 output in `[0, 255]`) is scoped to stretches
  that don't leave `[0, 1]` on already-clipped input, matching every
  stretch actually used in this spec's scenarios (`LinearStretch`,
  `LogStretch`) and the pre-deletion code's behavior (no final clip after
  the stretch). A stretch like `ContrastBiasStretch` that documents a
  wider range is out of scope for that guarantee.
- Integer-dtype input is required to work for the base `RGBImageMapping`
  path (S11) but explicitly not for `RGBImageMappingLupton` — see S11's
  final sentence.

## Open Questions

None open. Three scope decisions came up while writing this spec and were
resolved by the author rather than left for a reviewer, since no
implementation choice should hinge on them being revisited later:

- [x] Is restoring the four source files (or the deleted test file) from
  git history an acceptable implementation path? — **Yes.** See the
  Context section, "On using git history."
- [x] Must `RGBImageMappingLupton` accept integer-dtype input the same
  way the base `RGBImageMapping` does? — **No**, explicitly out of
  scope; see S11's final sentence and Trade-offs.
- [x] What should happen when a stretch's output leaves `[0, 1]` on
  already-clipped input (e.g. `ContrastBiasStretch`)? — **Out of scope**
  for the range guarantee; see the Interface Contract's `make_rgb_image`
  Returns note and Trade-offs.

## References

- `astropy/visualization/basic_rgb.py`, `interval.py`, `stretch.py`,
  `lupton_rgb.py`, `transform.py` (current working tree).
- `astropy/visualization/tests/test_basic_rgb.py` at git HEAD
  (`b0db0daa`) — the pre-deletion oracle for S1–S9, S20–S22.
- `astropy/visualization/tests/test_interval.py`, `test_stretch.py`,
  `test_lupton_rgb.py`, `test_norm.py` (existing, unmodified) — the
  oracle for part of S10, and all of S12–S18.
- Lupton et al. 2004, https://ui.adsabs.harvard.edu/abs/2004PASP..116..133L
  (referenced by `lupton_rgb.py`'s existing docstrings).

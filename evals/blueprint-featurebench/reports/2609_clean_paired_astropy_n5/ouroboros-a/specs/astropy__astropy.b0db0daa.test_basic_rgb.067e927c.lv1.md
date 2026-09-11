# 2609.0001 Restore RGBImageMapping Construction and Image Conversion

**Date:** 2026-09-10
**Status:** draft
**Author:** FeatureBench

## Context

`astropy/visualization/basic_rgb.py` defines `RGBImageMapping`, the class that
turns three aligned red/green/blue arrays into a single RGB image by
normalizing each channel through an interval (value-range selection) and a
stretch (nonlinear remapping onto `[0, 1]`). `astropy/visualization/lupton_rgb.py`
depends on it directly: `RGBImageMappingLupton(RGBImageMapping)` calls
`super().__init__(interval=interval, stretch=stretch)`, reads
`self.intervals[i].get_limits(img)` for each band, and overrides
`apply_mappings(...)`. The convenience function `make_rgb(...)` at the bottom
of `basic_rgb.py` already builds an `RGBImageMapping` and calls
`.make_rgb_image(...)` on it — it is the module's only `__all__` export.

In the current tree, `RGBImageMapping` has only its class docstring — `__init__`,
`make_rgb_image`, and every other method are missing. Because `__init__` is
missing, `RGBImageMappingLupton.__init__`'s call to
`super().__init__(interval=interval, stretch=stretch)` currently resolves to
`object.__init__`, which rejects keyword arguments, so it raises `TypeError`
before an `RGBImageMappingLupton` can even be constructed. `make_rgb`,
`make_lupton_rgb`, and any direct use of `RGBImageMapping` are all currently
broken as a result. Two supporting pieces the mapping depends on are also
missing their bodies:

- `astropy/visualization/interval.py`: `BaseInterval` is missing the
  `_process_values` helper that every concrete interval's `get_limits` calls
  (`ManualInterval`, `MinMaxInterval`, `AsymmetricPercentileInterval`,
  `SymmetricInterval` all reference `self._process_values(values)`, which
  does not exist), and `ZScaleInterval` is missing its `get_limits` body
  entirely (only `__init__` is present).
- `astropy/visualization/stretch.py`: the module-level `_prepare(values, clip,
  out)` helper that `LinearStretch`, `SqrtStretch`, `PowerStretch`,
  `LogStretch`, `AsinhStretch`, `SinhStretch`, `HistEqStretch`,
  `ContrastBiasStretch`, and others all call is missing, and
  `CompositeStretch` (declared as `class CompositeStretch(CompositeTransform,
  BaseStretch)`) has no `__call__` override, so it falls back to the
  inherited `CompositeTransform.__call__(self, values, clip=True)`
  (`astropy/visualization/transform.py:36`), which has no `out` parameter at
  all — dropping the `out` keyword that `BaseStretch.__call__` and every
  stretch test expect.

Three pre-existing test suites already exercise these code paths and
currently fail because of the missing bodies above:
`astropy/visualization/tests/test_interval.py` (e.g. `TestInterval.test_minmax`,
`test_zscale`, `test_zscale_npoints`), `astropy/visualization/tests/test_stretch.py`
(the `CompositeStretch` entry in its `RESULTS` dict, used throughout
`TestStretch`), and `astropy/visualization/tests/test_lupton_rgb.py` (e.g.
`test_different_shapes_asserts`, which calls `lupton_rgb.make_lupton_rgb(...)`
and asserts `pytest.raises(ValueError, match=r"shapes must match")` — this
exercises the base `RGBImageMapping.make_rgb_image`, since
`RGBImageMappingLupton` does not override it). A hidden
`test_basic_rgb.py` will separately exercise `RGBImageMapping` directly.

## Motivation

Without a working `RGBImageMapping`, the whole basic-RGB pipeline
(`make_rgb`) and the Lupton RGB pipeline (`make_lupton_rgb`, whose
`RGBImageMappingLupton` subclasses `RGBImageMapping`) are unusable, and three
pre-existing test suites fail on `AttributeError`/`TypeError` for reasons
that trace back to these same seven missing callables (listed in full under
Overview). Restoring `RGBImageMapping.__init__` and `make_rgb_image` requires
restoring `_process_values`, `ZScaleInterval.get_limits`, `_prepare`, and
`CompositeStretch.__call__` first, since `make_rgb_image` cannot normalize a
channel without them.

## Proposed Solution

### Overview

Restore the seven missing callables listed below so `RGBImageMapping` can be
constructed and used end to end, and so the interval/stretch machinery it
depends on behaves exactly as their existing docstrings and existing test
suites already describe. No public signature changes: every restored method
keeps the signature already declared in its docstring or already exercised
by existing tests.

### Key Components

- **`BaseInterval._process_values(self, values)`** (`astropy/visualization/interval.py`)
  — shared preprocessing used by every concrete interval's `get_limits`.
  Accepts array-like, list, N-D array, `numpy.ma.MaskedArray`, or
  `astropy.utils.masked.Masked` input (via `astropy.utils.masked.get_data_and_mask`,
  already imported at the top of the file) and returns a flattened 1-D
  `ndarray` containing only unmasked, finite values.
- **`ZScaleInterval.get_limits(self, values)`** (`astropy/visualization/interval.py`)
  — implements IRAF's zscale algorithm using the six `__init__` parameters
  already stored on `self` (`n_samples`, `contrast`, `max_reject`,
  `min_npixels`, `krej`, `max_iterations`), preprocessing input with
  `self._process_values`. Falls back to the plain min/max of the
  (sub-sampled) processed data whenever the iterative line fit cannot retain
  enough good points — see the Interface Contract below for the precise
  fallback condition.
- **`_prepare(values, clip=True, out=None)`** (`astropy/visualization/stretch.py`,
  module-level) — shared entry point every concrete stretch's `__call__`
  already invokes as its first line. Produces the array each stretch mutates
  in place afterward, without mutating the caller's original array when
  `out` is not given.
- **`CompositeStretch.__call__(self, values, clip=True, out=None)`**
  (`astropy/visualization/stretch.py`) — applies `self.transform_1` then
  `self.transform_2` (attributes already set by the inherited
  `CompositeTransform.__init__`), forwarding `clip` and `out` to both so a
  composite stretch is usable anywhere a single stretch is (including inside
  `RGBImageMapping`).
- **`RGBImageMapping.__init__`** (`astropy/visualization/basic_rgb.py`) —
  stores `self.intervals` (always a 3-element list, one `BaseInterval` per
  R/G/B channel) and `self.stretch` (one `BaseStretch` shared by all three
  channels), per the interface contract below.
- **`RGBImageMapping.apply_mappings(self, image_r, image_g, image_b)`** —
  the per-channel normalization step `make_rgb_image` calls internally.
  **Required name and signature**: `RGBImageMappingLupton.apply_mappings` in
  `astropy/visualization/lupton_rgb.py:584` already overrides a method by
  this exact name on this exact base class — renaming it breaks that
  override. Its required behavior:
  - For each channel `i` in `(r, g, b)`, call `self.intervals[i](image_i,
    clip=True)` (that channel's own interval, invoked with `clip=True`, so
    it derives `(vmin, vmax)` via `get_limits` on that channel alone,
    normalizes, and clips to `[0, 1]`).
  - Pass each clipped, normalized channel through `self.stretch(..., clip=True)`
    (the one stretch object shared by all three channels, also invoked with
    `clip=True` so its output is guaranteed to land in `[0, 1]` even for a
    stretch whose raw formula can leave that range, e.g.
    `ContrastBiasStretch`).
  - Do not mutate the caller's `image_r`/`image_g`/`image_b` arrays.
  - Return the three normalized channel arrays (any container
    `make_rgb_image` can turn into a `(3, N, M)` array — see Data Flow step
    6).
- **`RGBImageMapping.make_rgb_image`** — validates `output_dtype` against the
  module-level `_OUTPUT_IMAGE_FORMATS = [float, np.float64, np.uint8]`
  constant already defined at `basic_rgb.py:13` (currently unused because
  the method that reads it is missing), validates that the three inputs
  share one shape, delegates per-channel normalization to
  `self.apply_mappings(...)`, converts the normalized `[0, 1]` triplet to
  `output_dtype`, and stacks the three channels into one `NxMx3` array.

### Data Flow

1. Caller constructs `RGBImageMapping(interval=..., stretch=...)` (or accepts
   the defaults `ManualInterval(vmin=0, vmax=None)` / `LinearStretch()`).
   `__init__` normalizes `interval` into `self.intervals`, a 3-element list.
2. Caller calls `.make_rgb_image(image_r, image_g, image_b, output_dtype=...)`.
3. `make_rgb_image` coerces each input via `np.asarray(...)`, then validates
   `output_dtype` is one of `_OUTPUT_IMAGE_FORMATS` (raising `ValueError`
   whose message contains `"output_dtype"` otherwise) and that
   `image_r.shape == image_g.shape == image_b.shape` (raising `ValueError`
   whose message contains `"shapes must match"` otherwise).
4. `make_rgb_image` calls `self.apply_mappings(image_r, image_g, image_b)`,
   which applies each channel's own interval (`clip=True`) followed by the
   shared stretch (`clip=True`) as described under Key Components, so the
   result is guaranteed to lie in `[0, 1]` regardless of which interval or
   stretch was configured.
5. `make_rgb_image` converts the three normalized-to-`[0, 1]` arrays to
   `output_dtype`: for `float`/`np.float64`, cast directly (values remain in
   `[0, 1]`); for `np.uint8`, multiply by `np.iinfo(np.uint8).max` (255) and
   `.astype(np.uint8)` (truncating, not rounding).
6. `make_rgb_image` stacks the three channel arrays along a new last axis
   (`np.dstack` or equivalent) into shape `(N, M, 3)` and returns it. This
   step must accept whatever `apply_mappings` returns as long as it is
   `np.asarray`-able to shape `(3, N, M)` — `RGBImageMappingLupton.apply_mappings`
   (`lupton_rgb.py:664`) already returns exactly `np.asarray(image_rgb)` of
   that shape via a base-class-inherited `make_rgb_image` call
   (`lupton_rgb.py:751`), so the two methods must stay compatible even
   though this spec only prescribes the base class's own `apply_mappings`.
7. `make_rgb(...)` (already implemented, unchanged) builds an
   `RGBImageMapping` and calls step 2–6 on the caller's behalf, optionally
   writing the result to `filename` via `matplotlib.image.imsave`.

### Interface Contract

The two signatures below are the authoritative interface — match them
exactly (defaults included):

```python
# astropy/visualization/basic_rgb.py
class RGBImageMapping:
    def __init__(self, interval=ManualInterval(vmin=0, vmax=None), stretch=LinearStretch()):
        """
        `interval` accepts exactly two forms:
          (a) a single BaseInterval instance -> self.intervals becomes
              [interval, interval, interval] (the SAME object reused three
              times: self.intervals[0] is self.intervals[1] is
              self.intervals[2]).
          (b) a sequence (anything with len()) of BaseInterval instances ->
              if len() != 3, raise ValueError; otherwise self.intervals is
              that sequence's three (possibly distinct) objects, in order,
              as a list.
        `stretch` is stored as self.stretch, as-is, shared by all three
        channels.
        """

    def make_rgb_image(self, image_r, image_g, image_b, output_dtype=np.uint8):
        """
        Raises ValueError, with a message containing "output_dtype", if
        output_dtype is not one of _OUTPUT_IMAGE_FORMATS ([float, np.float64,
        np.uint8]).
        Raises ValueError, with a message containing "shapes must match", if
        image_r/image_g/image_b (after np.asarray(...) coercion) do not all
        have the same .shape.
        Returns an (N, M, 3) ndarray, dtype == output_dtype:
          - output_dtype is float or np.float64 -> values in [0.0, 1.0]
            (guaranteed by apply_mappings calling both the interval and the
            stretch with clip=True -- see Key Components).
          - output_dtype is np.uint8 -> each normalized-to-[0,1] value is
            multiplied by 255 and truncated via .astype(np.uint8) (not
            rounded), so a normalized value of 1.0 maps to 255 and a
            normalized value of 0.0 maps to 0.
        Does not modify image_r, image_g, or image_b in place.
        """
```

Supporting internals restored alongside these two methods (signatures already
fixed by existing callers/docstrings — do not rename):

```python
# astropy/visualization/interval.py
class BaseInterval(BaseTransform):
    def _process_values(self, values):
        """Returns a flattened 1-D ndarray of finite, unmasked values."""

class ZScaleInterval(BaseInterval):
    def get_limits(self, values):
        """
        Uses self.n_samples, self.contrast, self.max_reject, self.min_npixels,
        self.krej, self.max_iterations (already set in __init__).

        Let `minpix = max(self.min_npixels, int(npix * self.max_reject))`
        where `npix` is the size of the (sub-sampled) processed data. If the
        iterative sigma-rejection line fit ends with fewer than `minpix`
        surviving ("good") points -- whether because npix itself is small
        (min_npixels-dominated, see S13) or because rejection removed too
        many points (max_reject-dominated, see S14) -- return
        (min(sampled_data), max(sampled_data)) instead of a fitted range.
        """

# astropy/visualization/stretch.py
def _prepare(values, clip=True, out=None):
    """
    clip=True  -> returns np.clip(values, 0.0, 1.0, out=out).
    clip=False, out=None -> returns an independent, writable float copy of
        values (the caller's original array/list is left untouched).
    clip=False, out given -> writes values into out and returns out.
    """

class CompositeStretch(CompositeTransform, BaseStretch):
    def __call__(self, values, clip=True, out=None):
        """
        Applies self.transform_1 then self.transform_2, forwarding clip and
        out to both, matching BaseStretch.__call__'s (values, clip=True,
        out=None) signature. Scope limit: this restoration does not add an
        `invalid` keyword to CompositeStretch (unlike SqrtStretch,
        PowerStretch, LogStretch); see Open Questions for the resulting
        compatibility note.
        """
```

## Alternatives Considered

### Reimplement `apply_mappings` logic inline inside `make_rgb_image`

Rejected: `RGBImageMappingLupton.apply_mappings` in `lupton_rgb.py` already
overrides a method by this name on `RGBImageMapping` and is called nowhere
except (implicitly) from `make_rgb_image`. Not naming the base method
`apply_mappings` would break that override contract and force changes to
`lupton_rgb.py`, which is out of scope for this restoration.

### Give each channel its own independent stretch

Rejected: the existing `RGBImageMapping` docstring and `RGBImageMappingLupton.__init__`
(`stretch=LuptonAsinhStretch(...)`, a single shared object passed to
`super().__init__`) both establish a single shared `stretch` across all three
channels — only `interval` varies per channel.

## Acceptance Scenarios

### Happy Path

- **S1:** Given no arguments, when `RGBImageMapping()` is constructed, then
  `self.intervals` is a 3-element list where every element is the same
  `ManualInterval(vmin=0, vmax=None)` instance, and `self.stretch` is a
  `LinearStretch()` instance.
- **S2:** Given a single `BaseInterval` instance (e.g. `MinMaxInterval()`),
  when `RGBImageMapping(interval=MinMaxInterval())` is constructed, then
  `self.intervals` is a 3-element list and `self.intervals[0] is
  self.intervals[1] is self.intervals[2]` (the same object reused).
- **S3:** Given a 3-element array-like of distinct `BaseInterval` instances
  (e.g. `[ManualInterval(0, 1), ManualInterval(0, 2), ManualInterval(0, 3)]`),
  when `RGBImageMapping(interval=that_list)` is constructed, then
  `self.intervals` holds those three distinct objects in order.
- **S4:** Given `image_r = image_g = image_b = np.array([[0., 10., 20.],
  [30., 40., 50.]])` and a default-constructed `RGBImageMapping()`, when
  `.make_rgb_image(image_r, image_g, image_b)` is called with no
  `output_dtype`, then the result has shape `(2, 3, 3)`, dtype `uint8`, and
  every channel equals `[[0, 51, 102], [153, 204, 255]]` (the default
  `ManualInterval(vmin=0, vmax=None)` normalizes each channel by its own
  data max of `50`, `LinearStretch()` is the identity, and `0, 0.2, 0.4,
  0.6, 0.8, 1.0` scaled by 255 and truncated give exactly `0, 51, 102, 153,
  204, 255`).
- **S5:** Given the same inputs as S4, when
  `.make_rgb_image(image_r, image_g, image_b, output_dtype=float)` (and
  separately `output_dtype=np.float64`) is called, then the result dtype is
  that float type, shape `(2, 3, 3)`, and every channel equals
  `[[0.0, 0.2, 0.4], [0.6, 0.8, 1.0]]` (`assert_allclose`).
- **S6:** Given a single input array `image = np.array([[20., 20.], [20.,
  20.]])` passed as `image_r = image_g = image_b = image`, and
  `RGBImageMapping(interval=[ManualInterval(0, 20), ManualInterval(0, 50),
  ManualInterval(0, 100)])`, when `.make_rgb_image(image_r, image_g,
  image_b)` is called, then the three output channels differ even though
  the three inputs are identical: the red channel is all `255`
  (`20/20 = 1.0`), the green channel is all `102` (`20/50 = 0.4`), and the
  blue channel is all `51` (`20/100 = 0.2`) — proving each channel is
  normalized by its own interval, not a shared one.
- **S7:** Given `image_r`, `image_g`, `image_b` from S4 and copies of each
  taken before the call, when `.make_rgb_image(image_r, image_g, image_b)`
  is called, then `image_r`, `image_g`, `image_b` compare equal
  (`assert_array_equal`) to their pre-call copies afterward (inputs are not
  mutated).
- **S8:** Given a `ZScaleInterval()` and 2-D data `np.random.seed(42);
  np.random.randn(100, 100) * 5 + 10`, when `.get_limits(data)` is called,
  then it returns `(vmin, vmax)` with `vmin ≈ -9.6` and `vmax ≈ 25.4`
  (`atol=0.1`), matching `astropy/visualization/tests/test_interval.py::test_zscale`.
- **S9:** Given `ZScaleInterval()` and `data = list(range(1000)) + [np.nan]`,
  when `.get_limits(data)` is called, then it returns `vmin ≈ 0` and
  `vmax ≈ 999` (`atol=0.1`) — the `NaN` is dropped by preprocessing rather
  than propagating.
- **S10:** Given a `CompositeStretch` built as `LinearStretch(intercept=0.5) +
  LinearStretch(slope=0.5)` and `DATA = np.array([0.00, 0.25, 0.50, 0.75,
  1.00])` (an ndarray, matching `test_stretch.py:23`'s `DATA` — a Python
  list would make the "distinct object"/"unmutated" checks below pass
  trivially, since `np.asarray` of a list always copies), when called as
  `result = stretch(DATA, clip=False)`, then `result` equals
  `[0.5, 0.625, 0.75, 0.875, 1.0]` (slope applied before intercept),
  matching the `RESULTS` entry in `astropy/visualization/tests/test_stretch.py`;
  `result` is also a distinct object from `DATA` (`result is not DATA`), and
  `DATA` itself still equals `[0.00, 0.25, 0.50, 0.75, 1.00]` after the call
  (no in-place mutation of the input when `out` is not given).
- **S11:** Given that same `CompositeStretch` and a preallocated `out` array,
  when called as `stretch(data_in, out=result, clip=False)`, then `result`
  holds the composite output and `data_in` is unchanged — the same contract
  `TestStretch.test_inplace` already asserts for every non-composite stretch
  in `RESULTS`.
- **S12:** Given `image_r`, `image_g`, `image_b` from S4, when
  `make_rgb(image_r, image_g, image_b)` (the module-level convenience
  function, `filename=None`) is called, then its return value equals, byte
  for byte, `RGBImageMapping().make_rgb_image(image_r, image_g, image_b)`
  (both default to `ManualInterval(vmin=0, vmax=None)` /
  `LinearStretch()` / `output_dtype=np.uint8`, so this equals S4's
  `[[0, 51, 102], [153, 204, 255]]` per channel).

### Edge Cases

- **S13:** Given `ZScaleInterval(min_npixels=5)` and `data =
  np.arange(4).reshape((2, 2))` (4 points, below `min_npixels`), when
  `.get_limits(data)` is called, then it returns `(0, 3)` — the plain
  min/max of the data — matching
  `test_interval.py::test_zscale_npoints`.
- **S14:** Given `ZScaleInterval(max_reject=1.0)` — so
  `minpix = max(self.min_npixels, int(npix * 1.0)) = npix`, meaning *any*
  single rejected point forces the fallback, independent of
  `min_npixels`'s default of `5` — and `data = np.concatenate([
  np.linspace(0.0, 1.0, 99), [1000.0]])` (99 points on a line plus one
  extreme outlier, 100 points total, well under `n_samples`'s default of
  1000 so no sub-sampling occurs), when `.get_limits(data)` is called, then
  it returns exactly `(0.0, 1000.0)` — `min(data)` and `max(data)` — because
  the line fit necessarily rejects at least the outlier, so `ngoodpix <
  minpix (== 100)` and the fallback applies. (Add this case to
  `astropy/visualization/tests/test_interval.py`, alongside the existing
  `test_zscale`/`test_zscale_npoints` it complements.)
- **S15:** Given the same unmasked reference data as
  `TestInterval.data = np.linspace(-20.0, 60.0, 100)` in `test_interval.py`,
  reshaped to 2-D, converted to a plain Python list, wrapped in a
  `numpy.ma.MaskedArray` with extra out-of-range values masked out, and
  wrapped in an `astropy.utils.masked.Masked` array with the same extra
  values masked out (mirroring `TestIntervalList`, `TestInterval2D`,
  `TestIntervalMaskedArray`, `TestIntervalMaskedNDArray` in
  `test_interval.py`) — when `.get_limits(...)` is called on each of these
  four representations with each of `MinMaxInterval()`,
  `AsymmetricPercentileInterval(10.5, 70.5)`, `SymmetricInterval()`, and
  `ManualInterval()` (all of which route through `_process_values`; a
  `ManualInterval` with both `vmin` and `vmax` given does not and is out of
  scope for this scenario) — then all four representations return the same
  `(vmin, vmax)` for a given interval, matching the values already asserted
  elsewhere in `test_interval.py` for this reference data:
  `MinMaxInterval()` → `(-20.0, 60.0)`,
  `AsymmetricPercentileInterval(10.5, 70.5)` → `(-11.6, 36.4)`,
  `SymmetricInterval()` → `(-60.0, 60.0)`,
  `ManualInterval()` → `(-20.0, 60.0)`.
- **S16:** Given `image_r = image_g = image_b = np.array([[0, 10, 20], [30,
  40, 50]], dtype=np.int64)` (same values as S4, integer dtype) and a
  default-constructed `RGBImageMapping()`, when
  `.make_rgb_image(image_r, image_g, image_b)` is called with default
  `output_dtype=np.uint8`, then it succeeds and returns the same
  `[[0, 51, 102], [153, 204, 255]]` per-channel result as S4 (integer input
  is accepted, not just float).
- **S17:** Given `image_r = image_g = image_b = np.full((3, 3), 7.0)` (a
  constant-valued channel) and `RGBImageMapping(interval=MinMaxInterval())`,
  when `.make_rgb_image(image_r, image_g, image_b)` is called, then it
  returns an all-zero `uint8` array of shape `(3, 3, 3)` with no `NaN`/`inf`
  and no divide-by-zero warning raised: `MinMaxInterval().get_limits(...)`
  returns `(7.0, 7.0)`, so `vmax == vmin` and `BaseInterval.__call__`'s
  `if (vmax - vmin) != 0` guard skips the division, leaving every value at
  `0` — mirroring the guard `test_interval.py::test_constant_data` already
  covers for `MinMaxInterval` directly. (Note: this scenario intentionally
  uses `MinMaxInterval`, not the default `ManualInterval(vmin=0,
  vmax=None)` — with the default, `vmin=0` is fixed while `vmax` resolves
  to the data's own max of `7.0`, so `vmax - vmin = 7 ≠ 0` and every pixel
  would normalize to `1.0`/`255` instead.)
- **S18:** Given a subclass of `RGBImageMapping` whose `apply_mappings`
  override returns `np.asarray([np.full((2, 3), 0.0), np.full((2, 3), 0.5),
  np.full((2, 3), 1.0)])` (shape `(3, 2, 3)`, mirroring
  `RGBImageMappingLupton.apply_mappings`'s plain-`ndarray` return type
  rather than a 3-element Python list), when that subclass's (inherited)
  `make_rgb_image` is called with default `output_dtype=np.uint8`, then it
  returns a `(2, 3, 3)` `uint8` array where `result[..., 0]` is all `0`,
  `result[..., 1]` is all `127` (`0.5 * 255 = 127.5`, truncated), and
  `result[..., 2]` is all `255` — i.e. the base `make_rgb_image`'s
  post-`apply_mappings` conversion/stacking step does not assume a
  Python-list return type, and channel order (`r`, `g`, `b` →
  `result[..., 0]`, `result[..., 1]`, `result[..., 2]`) is preserved.
- **S19:** Given `RGBImageMapping(interval=ManualInterval(vmin=0, vmax=20))`
  and `image_r = image_g = image_b = np.array([[-10., 10., 30.]])` (one
  value below the interval, one exactly at its midpoint, one above), when
  `.make_rgb_image(image_r, image_g, image_b)` is called, then every
  channel equals `[[0, 127, 255]]`: `-10` normalizes to `-0.5`, clipped to
  `0.0`; `10` normalizes to exactly `0.5`, which truncates to `127` (not
  `128`) under `.astype(np.uint8)`; `30` normalizes to `1.5`, clipped to
  `1.0`, giving `255`. This pins both the clip-to-`[0,1]` behavior and the
  truncate-not-round quantization rule with a single scenario.
- **S20:** Given `RGBImageMapping(stretch=SqrtStretch())` and the same
  inputs as S4, when `.make_rgb_image(image_r, image_g, image_b)` is
  called, then every channel equals `[[0, 114, 161], [197, 228, 255]]`
  (`sqrt(0.2)*255 ≈ 114.0`, `sqrt(0.4)*255 ≈ 161.3`, `sqrt(0.6)*255 ≈
  197.5`, `sqrt(0.8)*255 ≈ 228.1`, each truncated) — this is only reachable
  if the interval is applied *before* the stretch (applying `SqrtStretch`
  first, before the interval has normalized to `[0, 1]`, or applying it to
  the raw pixel values `0..50`, produces a materially different, easily
  distinguished result).
- **S21:** Given `RGBImageMapping(interval=ManualInterval(vmin=0, vmax=4),
  stretch=ContrastBiasStretch(contrast=2.0, bias=0.4))` and `image_r =
  image_g = image_b = np.array([[0., 1., 2., 3., 4.]])`, when
  `.make_rgb_image(image_r, image_g, image_b, output_dtype=float)` is
  called, then every channel equals `[[0.0, 0.2, 0.7, 1.0, 1.0]]`
  (`assert_allclose`). Reasoning: the interval normalizes the five pixels
  to `[0, 0.25, 0.5, 0.75, 1.0]`; `ContrastBiasStretch(2.0, 0.4)`'s raw
  (unclipped) formula `(x - 0.4) * 2.0 + 0.5` gives
  `[-0.3, 0.2, 0.7, 1.2, 1.7]` (matching the un-clipped `RESULTS` entry in
  `test_stretch.py`), but `apply_mappings` invokes the stretch with
  `clip=True`, so the actual output is the clipped
  `[0.0, 0.2, 0.7, 1.0, 1.0]` — measurably different from the unclipped
  values at indices 3 (`1.0` vs `1.2`) and 4 (`1.0` vs `1.7`), so a
  `clip=False` bug is caught. `output_dtype=float` is
  used deliberately here rather than the default `uint8`: at index 1, the
  normalized value is `0.5 + 2 * (0.25 - 0.4)`, which is not exactly `0.2`
  in IEEE double precision (it evaluates to a value fractionally below
  `0.2`), so `0.2 * 255 = 51` would be right at a truncation boundary that a
  `uint8` assertion could get wrong by one count for reasons unrelated to
  the behavior under test; asserting the float value with `assert_allclose`
  avoids that trap.

### Error Scenarios

- **S22:** Given a 2-element (or 4-element) array-like `interval` argument,
  when `RGBImageMapping(interval=that_array_like)` is constructed, then it
  raises `ValueError`.
- **S23:** Given `image_r`, `image_g`, `image_b` where at least one has a
  different `.shape` from the others, when `.make_rgb_image(...)` is
  called, then it raises `ValueError` whose message contains the substring
  `"shapes must match"` (before any partial output is computed/returned) —
  this exact substring is already asserted by
  `test_lupton_rgb.py::test_different_shapes_asserts` via
  `lupton_rgb.make_lupton_rgb(...)`, which calls this same base
  `make_rgb_image`.
- **S24:** Given a valid, equal-shape triplet of images, when
  `.make_rgb_image(..., output_dtype=np.int32)` (or any type outside
  `_OUTPUT_IMAGE_FORMATS`) is called, then it raises `ValueError` whose
  message contains the substring `"output_dtype"`.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that would *fail if the behavior were wrong*. A green suite that passes for the wrong reason does not satisfy this contract — `/verify` will hunt for vacuous tests by asking, of each behavior, "what is the smallest change that breaks this, and would any test catch it?"

Concretely:

- Implement the seven restored callables (`RGBImageMapping.__init__`,
  `RGBImageMapping.apply_mappings`, `RGBImageMapping.make_rgb_image`,
  `BaseInterval._process_values`, `ZScaleInterval.get_limits`, `_prepare`,
  `CompositeStretch.__call__`) in their existing files at their existing
  locations — do not move or rename them, since `lupton_rgb.py` and the
  pre-existing `test_interval.py`/`test_stretch.py`/`test_lupton_rgb.py`
  already call them by name.
- Do not touch `make_rgb`, `RGBImageMappingLupton`, `make_lupton_rgb`, or any
  already-complete stretch/interval class (`ManualInterval`, `MinMaxInterval`,
  `AsymmetricPercentileInterval`, `PercentileInterval`, `SymmetricInterval`,
  `LinearStretch`, `SqrtStretch`, `SqrtStretch`, `ContrastBiasStretch`, etc.)
  beyond what's needed to unblock them via the restored helpers — their
  bodies are already correct and already tested.
- Run the existing `astropy/visualization/tests/test_interval.py`,
  `astropy/visualization/tests/test_stretch.py`, and
  `astropy/visualization/tests/test_lupton_rgb.py` suites as a correctness
  check (S8, S9, S10, S11, S13, S15, S23 mirror cases already in those
  files) — but do not weaken or edit those tests to make them pass. S14 is
  new but belongs alongside them in `test_interval.py`.
- Add `astropy/visualization/tests/test_basic_rgb.py` covering S1–S7, S12,
  S16–S22, S24 at minimum, following the AAA style and parametrization
  patterns already used in `test_interval.py`/`test_stretch.py`.

Write tests to the project's conventions and to these principles (the same ones `/verify` scores against — see `references/test-desiderata.md` and `references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects (returned array shape/dtype/values, raised exceptions), not internals; the suite must survive refactoring `apply_mappings`'s internals.
- **Every test can fail** — no copy-pasted expected values, no asserting a constant, no tautologies (AP-2, AP-4). Compute expected values independently of the implementation under test where feasible (by hand, as most scenarios above do, or via `np.clip`/manual normalization, as `test_stretch.py`'s `RESULTS` dict does).
- **Deterministic, isolated, readable** — seed any randomness (`np.random.seed(...)`, matching S8's existing convention), no cross-test state, AAA structure with inline setup.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Test suite is green, including the pre-existing `test_interval.py`, `test_stretch.py`, and `test_lupton_rgb.py`.
- [ ] Every acceptance scenario (S1…S24) maps to at least one test.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under the smallest break of its behavior (thought-mutation), e.g. swapping which interval index maps to which channel, forgetting to reuse the single interval instance across channels, applying `stretch` before `interval` (S20), rounding instead of truncating the uint8 conversion (S19), or calling the stretch/interval with `clip=False` (S21).
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code — including `_OUTPUT_IMAGE_FORMATS` staying unused if the implementer hard-codes its own list — or stale docstrings).

## Trade-offs and Limitations

- `ZScaleInterval.get_limits`'s iterative sigma-rejection fit is a
  well-known published algorithm (IRAF zscale / STScI numdisplay, credited
  in the class docstring); this spec pins its externally observable
  behavior via S8/S9/S13/S14 rather than prescribing the fit's internal
  steps.
- `CompositeStretch` does not accept or forward the `invalid` keyword that
  `SqrtStretch`, `PowerStretch`, and `LogStretch` support — this
  restoration only gives `CompositeStretch.__call__` the `(values,
  clip=True, out=None)` signature `BaseStretch.__call__` already declares.
  Adding `invalid` support to composites is out of scope here; see Open
  Questions for the resulting compatibility note.
- Non-finite (`NaN`/`inf`) values inside the *image* arrays passed to
  `make_rgb_image` (as opposed to inside interval-limit computation, which
  already drops them via `_process_values`) are out of scope: this spec
  does not pin what byte a `NaN` pixel produces after normalization and
  `uint8` conversion.
- The `_prepare(values, clip=True, out=<given>)` combination (clip *and* an
  explicit output buffer together) is pinned in the Interface Contract
  (`np.clip(values, 0.0, 1.0, out=out)`) but has no dedicated scenario above
  — `S10`/`S11` exercise `clip=False`, and `S4`–`S7`/`S15`–`S21` exercise
  `clip=True` only via `apply_mappings`, which never passes `out`. This
  combination is, however, exactly what `astropy/visualization/mpl_normalize.py:205`
  calls in production (`self.stretch(values, out=values, clip=False, ...)`
  is the `clip=False` sibling; the `clip=True, out=given` path is reachable
  the same way with `clip=True`). Treated as a known gap rather than blocking
  this restoration, since no scenario in this feature's own contract
  exercises it directly.

## Open Questions

- [ ] `mpl_normalize.py:204` dispatches special `invalid`-value handling on
      `self.stretch._supports_invalid_kw`. Because `CompositeStretch` never
      overrides `_supports_invalid_kw` and this restoration does not change
      that, `SqrtStretch() + LinearStretch()` (for example) silently loses
      `invalid` handling relative to using `SqrtStretch()` alone. Whether
      `CompositeStretch` should eventually report `_supports_invalid_kw`
      based on its two transforms is unresolved and left as a follow-up;
      this spec does not require a fix or a scenario for it here.

## References

- `astropy/visualization/basic_rgb.py` — `RGBImageMapping`, `make_rgb`, `_OUTPUT_IMAGE_FORMATS`.
- `astropy/visualization/lupton_rgb.py` — `RGBImageMappingLupton` (consumer of `self.intervals`, `self.stretch`, `apply_mappings`), `make_lupton_rgb`.
- `astropy/visualization/interval.py` — `BaseInterval`, `ZScaleInterval`, and sibling interval classes whose `get_limits` already call `self._process_values`.
- `astropy/visualization/stretch.py` — `_prepare`, `CompositeStretch`, and sibling stretch classes whose `__call__` already call `_prepare`.
- `astropy/visualization/mpl_normalize.py` — another consumer of `BaseStretch._supports_invalid_kw`, relevant to the `CompositeStretch` limitation noted under Open Questions.
- `astropy/visualization/tests/test_interval.py`, `astropy/visualization/tests/test_stretch.py`, `astropy/visualization/tests/test_lupton_rgb.py` — pre-existing suites whose failures motivate S8–S11, S13, S15, S23, and whose sibling S14 belongs alongside them.

# 2609.0001 Restore RGBImageMapping Construction and Image Conversion

**Date:** 2026-09-18
**Status:** draft
**Author:** FeatureBench

## Context

`astropy/visualization/basic_rgb.py` defines `RGBImageMapping`, the class that
turns three aligned single-band images (red, green, blue) into one combined
RGB image by applying a per-channel `~astropy.visualization.BaseInterval`
(normalization) and a shared `~astropy.visualization.BaseStretch` (tone
mapping). The module-level `make_rgb()` convenience function
(`astropy/visualization/basic_rgb.py:156-217`) already exists and is fully
implemented — it just constructs an `RGBImageMapping` and calls
`make_rgb_image` on it.

Right now the `RGBImageMapping` class body
(`astropy/visualization/basic_rgb.py:18-34`) is empty except for its
docstring: `__init__` and `make_rgb_image` are missing entirely, along with
whatever private helper(s) `make_rgb_image` needs to apply the interval and
stretch per channel. This is not an isolated gap:

- `astropy/visualization/lupton_rgb.py:532-664` defines
  `RGBImageMappingLupton(RGBImageMapping)`, which calls
  `super().__init__(interval=interval, stretch=stretch)` and then, in its own
  `apply_mappings` override, reads `self.intervals[i].get_limits(img)` for
  `i in range(3)`. This means the restored `RGBImageMapping.__init__` **must**
  store the per-channel intervals on `self.intervals` as a 3-element
  list/sequence, and `make_rgb_image` **must** delegate the per-channel
  normalize+stretch step to a method named `apply_mappings(image_r, image_g,
  image_b)` — that is the exact seam `RGBImageMappingLupton` already
  overrides. Any other attribute name or seam breaks the existing Lupton
  subclass and every test in `astropy/visualization/tests/test_lupton_rgb.py`.
- `astropy/visualization/interval.py`'s `BaseInterval` class
  (`interval.py:27-127`) is missing its `_process_values` method, called by
  `ManualInterval.get_limits`, `MinMaxInterval.get_limits`,
  `AsymmetricPercentileInterval.get_limits`, and `SymmetricInterval.get_limits`
  (each already calls `self._process_values(values)`). `ZScaleInterval`
  (`interval.py:267-320`) has its `__init__` (storing `n_samples`, `contrast`,
  `max_reject`, `min_npixels`, `krej`, `max_iterations`) but is missing
  `get_limits` entirely.
- `astropy/visualization/stretch.py` is missing the module-level `_prepare`
  helper that every stretch's `__call__` uses (e.g. `LinearStretch.__call__`
  at `stretch.py:146` does `values = _prepare(values, clip=clip, out=out)`),
  and `CompositeStretch` (`stretch.py:976-987`, subclass of
  `CompositeTransform` and `BaseStretch`) is missing its `__call__` override.

`RGBImageMapping.make_rgb_image` cannot run end to end without all of the
above. Three of the four supporting helpers already have an oracle in the
existing (intact) test files — `_process_values` in
`astropy/visualization/tests/test_interval.py`, `ZScaleInterval.get_limits`
in the same file (with exact expected numerics), and `_prepare` in
`astropy/visualization/tests/test_stretch.py`. `CompositeStretch.__call__`
has **no** existing test, so S10 below is its only coverage. This spec's job
is to restore the RGB-mapping-specific pieces (`RGBImageMapping.__init__`,
`RGBImageMapping.make_rgb_image`, and the `apply_mappings` seam) plus the four
supporting helpers above, since `make_rgb_image` cannot be verified without
them.

## Motivation

`make_rgb()`, `make_lupton_rgb()`, and every doc example in
`docs/visualization/rgb.rst` are currently broken because their shared
foundation, `RGBImageMapping`, has no body. Restoring it un-breaks both the
plain (`make_rgb`) and Lupton (`make_lupton_rgb`) RGB pipelines in one place,
since both are thin wrappers around `RGBImageMapping` /
`RGBImageMappingLupton`.

## Proposed Solution

### Overview

Implement `RGBImageMapping.__init__` to normalize the `interval` argument
into a 3-element indexable sequence (`self.intervals`) and store the shared `stretch`
(`self.stretch`). Implement `RGBImageMapping.make_rgb_image` to validate its
inputs, apply the per-channel interval+stretch mapping (via an
`apply_mappings` method, so `RGBImageMappingLupton` can override just that
step), stack the three normalized channels, and convert to the requested
output dtype. Restore the four supporting helpers
(`BaseInterval._process_values`, `ZScaleInterval.get_limits`,
`stretch._prepare`, `CompositeStretch.__call__`) that this path depends on.

### Key Components

- **`RGBImageMapping.__init__`**
  (`astropy/visualization/basic_rgb.py`) — accepts `interval` (a single
  `BaseInterval` instance or an array-like of exactly 3) and `stretch` (a
  single `BaseStretch`, shared across channels). Normalizes `interval` into
  `self.intervals`, an indexable sequence of exactly 3 intervals in R, G, B
  order (a single instance is repeated 3 times; a 3-element array-like may be
  kept as passed); stores `stretch` as `self.stretch`.
- **`RGBImageMapping.make_rgb_image`**
  (`astropy/visualization/basic_rgb.py`) — validates `image_r`/`image_g`/
  `image_b` share one shape and `output_dtype` is one of
  `_OUTPUT_IMAGE_FORMATS` (`basic_rgb.py:13`, i.e. `[float, np.float64,
  np.uint8]`); obtains the three normalized channels (via `apply_mappings`);
  stacks them along a new last axis; converts to `output_dtype`. The
  shape-mismatch `ValueError` message must contain the substring `shapes must
  match` — the existing test `test_different_shapes_asserts`
  (`tests/test_lupton_rgb.py:343-347`) reaches this method through
  `make_lupton_rgb` (which performs no shape check of its own) and asserts
  `pytest.raises(ValueError, match=r"shapes must match")`. The already-present
  legacy `Mapping.make_rgb_image` (`lupton_rgb.py:107-117`) is the reference
  for both the message text (`"The image shapes must match. r: {}, g: {} b:
  {}"`) and the `np.dstack(...).astype(dtype)` stacking pattern.
- **`RGBImageMapping.apply_mappings`** (new method,
  `astropy/visualization/basic_rgb.py`) — for each channel `i`, derives that
  channel's `(vmin, vmax)` from `self.intervals[i]`, normalizes the channel to
  `[0, 1]` and clips it to that range, applies `self.stretch`, and returns the
  three mapped channels without mutating the caller's input arrays. Returns a
  sequence of three `(N, M)` float arrays in R, G, B order; the Lupton
  override returns an ndarray of shape `(3, N, M)`
  (`lupton_rgb.py:664`), so `make_rgb_image` must accept that form too (both
  work with `np.dstack`). This is the exact method
  `RGBImageMappingLupton.apply_mappings`
  (`astropy/visualization/lupton_rgb.py:584`) already overrides — the base
  implementation must use this name and this per-channel/independent
  algorithm (as opposed to the Lupton subclass's cross-channel algorithm).
- **`BaseInterval._process_values`**
  (`astropy/visualization/interval.py`) — turns the input into a flattened
  array of finite, unmasked values (using
  `astropy.utils.masked.get_data_and_mask`, already imported at
  `interval.py:12`), for the four `get_limits` implementations that already
  call it. Its oracle is the existing `test_interval.py`:
  `test_manual_defaults_with_nan`, `test_integers`, and the
  `TestIntervalList` / `TestInterval2D` / `TestIntervalMaskedArray` /
  `TestIntervalMaskedNDArray` re-runs of `TestInterval` — i.e. it must accept
  lists, 2-D arrays, `np.ma.MaskedArray`, and `Masked` ndarrays, and drop NaN
  and masked entries.
- **`ZScaleInterval.get_limits`**
  (`astropy/visualization/interval.py`) — implements IRAF zscale sampling,
  iterative sigma-rejection fitting, and contrast scaling per the
  already-present docstring (`interval.py:267-303`) and `__init__` parameters
  (`n_samples`, `contrast`, `max_reject`, `min_npixels`, `krej`,
  `max_iterations`), falling back to the sampled data's min/max when the fit
  isn't usable. The existing `test_zscale` and `test_zscale_npoints`
  (`test_interval.py:125-158`) assert exact numeric limits: they are the
  oracle, and the restored implementation must reproduce those numbers rather
  than re-derive a variant algorithm.
- **`stretch._prepare`** (module-level helper,
  `astropy/visualization/stretch.py`) — the shared preprocessing every
  stretch's `__call__` already invokes as `_prepare(values, clip=clip,
  out=out)`, honoring `clip` and `out` per each stretch's existing docstring
  (e.g. `LinearStretch`, `stretch.py:96-151`). Its oracle is the existing
  `TestStretch` in `test_stretch.py` (list input, 2-D input via `reshape`,
  `out=` in-place writes with `clip=False`, and `clip=True` behavior) plus
  `test_clip_invalid` and `test_linearstretch_clip`. Note
  `lupton_rgb.py:450` also calls it (imported as `_stretch_prepare`), so the
  Lupton stretches depend on it as well.
- **`CompositeStretch.__call__`**
  (`astropy/visualization/stretch.py:976`) — applies `self.transform_1` first
  and then `self.transform_2` (attributes already set by the inherited
  `CompositeTransform.__init__`, `astropy/visualization/transform.py:31-34`),
  threading `clip` and `out` through both calls the same way
  `CompositeTransform.__call__` (`transform.py:36-37`) threads `clip`. Because
  `BaseStretch.__add__` is `CompositeStretch(other, self)`
  (`stretch.py:66-67`), `stretch_a + stretch_b` puts `stretch_b` in
  `transform_1` — so the composite applies **`stretch_b` first, then
  `stretch_a`**.

### Data Flow

1. Caller constructs `RGBImageMapping(interval=..., stretch=...)` (directly,
   or indirectly via `make_rgb()` at `basic_rgb.py:209` or
   `RGBImageMappingLupton.__init__` at `lupton_rgb.py:552-558`).
2. `__init__` expands `interval` to `self.intervals` (length 3) and stores
   `self.stretch`.
3. Caller calls `make_rgb_image(image_r, image_g, image_b, output_dtype=...)`.
4. `make_rgb_image` validates shapes match and `output_dtype` is supported.
5. `make_rgb_image` calls `self.apply_mappings(image_r, image_g, image_b)`,
   which for each channel `i` calls `self.intervals[i].get_limits(image_i)`
   (or the interval's own `__call__`, which uses `get_limits` internally) to
   normalize+clip to `[0, 1]`, then applies `self.stretch` to the normalized
   channel.
6. `make_rgb_image` stacks the three mapped channels into one `NxMx3` array
   and converts to `output_dtype` — scaling by the dtype's max and quantizing
   for `np.uint8`, or leaving the `[0, 1]` float values as-is (cast to dtype)
   for `float`/`np.float64`.
7. Result is returned to the caller (and, for `make_rgb()`, optionally
   written to disk via `matplotlib.image.imsave`, `basic_rgb.py:212-215` —
   already implemented, unaffected by this spec).

### Interface Contract

```python
# astropy/visualization/basic_rgb.py

class RGBImageMapping:
    def __init__(
        self,
        interval=ManualInterval(vmin=0, vmax=None),
        stretch=LinearStretch(),
    ):
        """
        interval : BaseInterval instance, or array-like of exactly 3
            BaseInterval instances (one per R, G, B channel).
        stretch : BaseStretch instance, shared across all 3 channels.

        Raises
        ------
        ValueError
            If `interval` is array-like but does not contain exactly 3
            elements.

        Post-conditions
        ----------------
        self.intervals : indexable sequence of length 3; self.intervals[i] is
            the interval object for channel i (the identical object repeated
            3 times if a single instance was passed).
        self.stretch : the stretch object as passed.
        """

    def make_rgb_image(self, image_r, image_g, image_b, output_dtype=np.uint8):
        """
        Raises
        ------
        ValueError
            If output_dtype not in [float, np.float64, np.uint8].
        ValueError
            If image_r/image_g/image_b shapes do not all match. The message
            must contain the substring "shapes must match" (an existing test
            matches on it; see Key Components).

        Returns
        -------
        ndarray, shape (N, M, 3), dtype output_dtype.
        For float/np.float64: values in [0, 1].
        For np.uint8: values in [0, 255].
        """

    def apply_mappings(self, image_r, image_g, image_b):
        """
        Returns
        -------
        A sequence of 3 channel arrays (R, G, B order), each the same shape
        as the inputs, with float values in [0, 1]. Callers must tolerate
        either a list of 3 (N, M) arrays or a single (3, N, M) ndarray — the
        Lupton subclass's override returns the latter.

        Post-conditions
        ----------------
        image_r, image_g, image_b are not modified in place.
        """
```

The `[0, 1]` output range assumes the configured stretch maps `[0, 1]` onto
`[0, 1]`, which is what `BaseStretch` documents (`stretch.py:56-59`) and what
every stretch in `stretch.py` does under its default `clip=True`. Stretches
that deliberately leave the unit range are outside this contract.

Existing, already-implemented callers that this contract must not break:

- `make_rgb()` (`basic_rgb.py:156-217`) — constructs `RGBImageMapping` and
  calls `make_rgb_image`.
- `RGBImageMappingLupton.__init__` (`lupton_rgb.py:552-558`) — calls
  `super().__init__(interval=interval, stretch=stretch)`, then sets
  `self._pixmax = 1.0`.
- `RGBImageMappingLupton.apply_mappings` (`lupton_rgb.py:584-664`) — reads
  `self.intervals[i].get_limits(img)` for `i in range(3)` and reads
  `self.stretch`; overrides the per-channel step that
  `RGBImageMapping.make_rgb_image` must call by the name `apply_mappings`.
- `make_lupton_rgb()` (`lupton_rgb.py:667-758`) — constructs
  `RGBImageMappingLupton` and calls `make_rgb_image` with the same signature.

## Out of Scope

- Changing `make_rgb()` or `make_lupton_rgb()` themselves — both are already
  fully implemented and are only exercised here as regression checks on the
  restored base class.
- `RGBImageMappingLupton.apply_mappings`, `LuptonAsinhStretch`,
  `LuptonAsinhZscaleStretch`, `Mapping`/`LinearMapping`/`AsinhMapping`/
  `AsinhZScaleMapping`, and `compute_intensity` in `lupton_rgb.py` — already
  fully implemented.
- Restoring `get_limits`/`_process_values` behavior for interval subclasses
  other than `ManualInterval`, `MinMaxInterval`,
  `AsymmetricPercentileInterval`/`PercentileInterval`, `SymmetricInterval`,
  and `ZScaleInterval` beyond what `_process_values` already provides them —
  their individual algorithms (percentile math, symmetric radius math) are
  unaffected by this change and out of scope to re-derive.
- Restoring every individual stretch's `__call__` body (`SqrtStretch`,
  `LogStretch`, `AsinhStretch`, etc.) beyond the shared `_prepare` helper they
  call — each stretch's own math is unaffected by this change.
- Saturated-pixel handling, file-writing formats other than what
  `matplotlib.image.imsave` already supports, and any new output dtype
  beyond `[float, np.float64, np.uint8]` — not requested and not implied by
  the existing `_OUTPUT_IMAGE_FORMATS` constant.

## Alternatives Considered

### Give `RGBImageMapping` and `RGBImageMappingLupton` independent, unrelated implementations of `make_rgb_image`

Would avoid the `apply_mappings` seam requirement, but `RGBImageMappingLupton`
already inherits from `RGBImageMapping` and already overrides
`apply_mappings` while relying on the inherited `make_rgb_image` — duplicating
`make_rgb_image` would diverge from the class hierarchy already committed to
in `lupton_rgb.py` and double the surface area to keep in sync.

### Store per-channel intervals as `self.interval` (singular, matching the constructor kwarg name)

Rejected: `RGBImageMappingLupton.apply_mappings` already indexes
`self.intervals[i]` (plural). Using any other attribute name breaks the
existing subclass without modifying it, which is out of scope.

## Acceptance Scenarios

Scenarios S4–S8, S10, S15, and S18 share one fixture, referred to below as
**the standard triplet** (S9, S16, and S17 define their own):

```python
image_r = np.array([[0.0,  3.0], [ 6.0, 10.0]])   # channel max 10
image_g = np.array([[0.0,  5.0], [10.0, 20.0]])   # channel max 20
image_b = np.array([[0.0, 10.0], [25.0, 40.0]])   # channel max 40
```

With the default `ManualInterval(vmin=0, vmax=None)` and `LinearStretch()`,
each channel normalizes to `pixel / channel_max`, so every channel contains an
exact `0.0` and an exact `1.0` after mapping.

### Happy Path

- **S1:** Given no arguments, when `RGBImageMapping()` is constructed, then
  `self.intervals` has length 3, all three elements are the same object
  (`self.intervals[0] is self.intervals[1] is self.intervals[2]`), that object
  is a `ManualInterval` with `vmin == 0` and `vmax is None`, and
  `self.stretch` is a `LinearStretch` instance.
- **S2:** Given a single `BaseInterval` instance (e.g.
  `ManualInterval(vmin=0, vmax=1)`) passed as `interval`, when
  `RGBImageMapping(interval=...)` is constructed, then `self.intervals` has
  length 3 and `self.intervals[i] is` that interval object for `i` in 0, 1, 2.
- **S3:** Given an array-like of exactly 3 distinct `BaseInterval` instances,
  when `RGBImageMapping(interval=[i0, i1, i2])` is constructed, then
  `self.intervals[0] is i0`, `self.intervals[1] is i1`, and
  `self.intervals[2] is i2` (each channel keeps its own interval, in order).
- **S4:** Given the standard triplet and the default interval/stretch, when
  `make_rgb_image(image_r, image_g, image_b)` is called with no
  `output_dtype` override, then the result is a `(2, 2, 3)` `np.uint8` array
  in which every channel's zero-valued pixel is `0`, every channel's
  maximum-valued pixel is `255`, and the values within each channel are
  non-decreasing in the input value.
- **S5:** Given the standard triplet, when `make_rgb_image(...,
  output_dtype=float)` is called, then the result is a `(2, 2, 3)` float array
  equal (within `1e-12`) to each channel divided by that channel's maximum —
  e.g. `result[0, 1, 0] == 0.3` (red `3.0 / 10.0`) and `result[1, 0, 2] ==
  0.625` (blue `25.0 / 40.0`). The same holds for
  `output_dtype=np.float64`.

- **S18:** Given the standard triplet, when the public
  `make_rgb(image_r, image_g, image_b, output_dtype=float)` is called with no
  `filename`, then its return value equals
  `RGBImageMapping().make_rgb_image(image_r, image_g, image_b,
  output_dtype=float)` element for element — the already-implemented
  convenience wrapper works again once the class body is restored.

### Edge Cases

- **S6:** Given the standard triplet cast to an integer dtype (`np.int32`) —
  `make_rgb`'s docstring promises "The input images can be int or float"
  (`basic_rgb.py:169-170`) — when `make_rgb_image(..., output_dtype=float)` is
  called, then the result equals the result of the same call on the
  `np.float64` copies of those arrays; in particular `result[0, 1, 0]` is
  `0.3`, not `0.0`, so integer truncation during normalization fails the test.
- **S7:** Given the standard triplet, when `make_rgb_image` is called, then
  `image_r`, `image_g`, and `image_b` are unchanged in both value and dtype
  after the call (no in-place mutation of caller data).
- **S8:** Given an `RGBImageMappingLupton` instance (constructed via
  `lupton_rgb.RGBImageMappingLupton(interval=ManualInterval(vmin=0, vmax=None),
  stretch=lupton_rgb.LuptonAsinhStretch(5, 8))`), when `make_rgb_image` is
  called on the standard triplet, then the result is a `(2, 2, 3)` `np.uint8`
  array containing at least two distinct values (not uniformly zero) — i.e.
  the restored base class drives the Lupton subclass's `apply_mappings`
  override end to end. The whole of the existing
  `tests/test_lupton_rgb.py` must also pass unchanged.
- **S9:** Given `ZScaleInterval()` as the shared interval and three copies of
  a deterministic 2-D ramp (`np.arange(1000.0).reshape(40, 25)`), when
  `make_rgb_image(..., output_dtype=float)` is called, then each output
  channel equals `np.clip((ramp - vmin) / (vmax - vmin), 0, 1)` where `vmin,
  vmax = ZScaleInterval().get_limits(ramp)` — exercising the restored
  `ZScaleInterval.get_limits` through the RGB pipeline without re-deriving the
  zscale numerics.
- **S10:** Given `composite = SqrtStretch() + LinearStretch(slope=0.5)` as the
  shared stretch and the standard triplet, when `make_rgb_image(...,
  output_dtype=float)` is called, then each output channel equals
  `np.sqrt(0.5 * normalized)` — the `LinearStretch` runs first and the
  `SqrtStretch` second, because `BaseStretch.__add__` places the right-hand
  operand in `transform_1` (`stretch.py:66-67`). The opposite order would give
  `0.5 * np.sqrt(normalized)`, which differs for every value in `(0, 1)`.
- **S15:** Given the standard triplet and a default `RGBImageMapping()`, when
  `make_rgb_image(..., output_dtype=float)` is called twice — once with the
  standard `image_g`, once with `image_g * 0.5` and the other two channels
  unchanged — then the red plane `result[..., 0]` and the blue plane
  `result[..., 2]` are identical between the two results: each band is mapped
  independently of the other bands.
- **S16:** Given `interval=[ManualInterval(0, 10), ManualInterval(0, 20),
  ManualInterval(0, 40)]` and the same ramp `np.array([[0.0, 10.0], [20.0,
  40.0]])` passed as all three channels, when `make_rgb_image(...,
  output_dtype=float)` is called, then the red channel is `clip(ramp/10, 0,
  1)`, the green channel is `clip(ramp/20, 0, 1)`, and the blue channel is
  `ramp/40` — each channel uses its own interval, in R, G, B order.
- **S17:** Given `interval=ManualInterval(vmin=10, vmax=20)` and
  `np.array([[-5.0, 10.0], [15.0, 40.0]])` passed as all three channels, when
  `make_rgb_image(..., output_dtype=float)` is called, then every channel
  equals `[[0.0, 0.0], [0.5, 1.0]]` — values below `vmin` clip to `0.0`,
  values above `vmax` clip to `1.0`, and values between scale linearly (the
  class docstring's "optional clipping and applying a scaling function").

### Error Scenarios

- **S11:** Given an array-like `interval` with 2 elements, when
  `RGBImageMapping(interval=[i0, i1])` is constructed, then a `ValueError` is
  raised.
- **S12:** Given an array-like `interval` with 4 elements, when
  `RGBImageMapping(interval=[i0, i1, i2, i3])` is constructed, then a
  `ValueError` is raised.
- **S13:** Given `image_r` with shape `(3, 4)` and `image_g`/`image_b` with
  shape `(4, 3)`, when `make_rgb_image` is called, then a `ValueError` whose
  message contains `shapes must match` is raised (the existing
  `test_different_shapes_asserts` matches on that substring).
- **S14:** Given `output_dtype=np.int16` (not in `[float, np.float64,
  np.uint8]`), when `make_rgb_image(..., output_dtype=np.int16)` is called,
  then a `ValueError` is raised.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*. A green suite that passes for the
> wrong reason does not satisfy this contract — `/verify` will hunt for
> vacuous tests by asking, of each behavior, "what is the smallest change
> that breaks this, and would any test catch it?"

Implement however you work best — blueprint does not prescribe order,
cadence, or commit structure. Only the result is checked. New tests for the
RGB scenarios go in `astropy/visualization/tests/test_basic_rgb.py`, which
does not exist yet and is yours to create; `RGBImageMapping` is reachable as
`from astropy.visualization.basic_rgb import RGBImageMapping` (the module's
`__all__` lists only `make_rgb`). Write tests to the
project's conventions (see `astropy/visualization/tests/test_interval.py`,
`astropy/visualization/tests/test_stretch.py`, and
`astropy/visualization/tests/test_lupton_rgb.py` for this module's existing
style) and to these principles (the same ones `/verify` scores against — see
`references/test-desiderata.md` and `references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects (shapes,
  dtypes, value ranges, raised exceptions), not internals; the suite must
  survive refactoring.
- **Every test can fail** — no copy-pasted expected values, no asserting a
  constant, no tautologies (AP-2, AP-4).
- **Deterministic, isolated, readable** — the scenarios above use fixed
  arrays rather than random data; if you do introduce randomness, seed it
  (`np.random.seed(...)`), keep no cross-test state, and use AAA structure
  with inline setup.
- **The existing tests are the oracle for the four helpers** — `test_zscale`,
  `test_zscale_npoints`, the `TestInterval*` classes, and `TestStretch` assert
  exact numerics for `ZScaleInterval.get_limits`, `_process_values`, and
  `_prepare`. A correct restoration satisfies those assertions as they stand —
  a helper that only passes once those tests are changed is the wrong helper.

Do not modify `RGBImageMappingLupton`, `make_rgb`, or `make_lupton_rgb` — S8
exists specifically to confirm the restored base class keeps them working
as-is.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Test suite is green, including the new `test_basic_rgb.py` and the
      existing, unmodified `test_interval.py`, `test_stretch.py`, and
      `test_lupton_rgb.py`.
- [ ] Every acceptance scenario (S1…S18) maps to at least one test.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under the
      smallest break of its behavior (thought-mutation).
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
      first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings).

## Trade-offs and Limitations

- The exact numeric fallback rule for `ZScaleInterval.get_limits` ("falling
  back to the sampled data limits when the fit is not usable") is inherited
  as-is from the existing docstring and IRAF zscale algorithm; this spec does
  not re-derive or change that algorithm's numerics.
- `float` and `np.float64` are treated as equivalent output dtypes per the
  existing `_OUTPUT_IMAGE_FORMATS` constant (`basic_rgb.py:13`); this spec
  does not introduce additional float precision options.
- **Degenerate channel (`vmax == vmin`), unspecified.** No scenario pins the
  result when an interval returns equal limits for a channel (e.g. an
  all-zero channel under the default `ManualInterval(vmin=0, vmax=None)`),
  because the reviewer found no existing test or docstring that fixes it.
  `BaseInterval.__call__` (`interval.py:121-122`) skips the division when
  `vmax - vmin == 0`; mirroring that guard is the reviewer's assumed-safe
  default, but it is a judgment call, not a contract clause.
- **Exact `ValueError` message for a 1-or-3 interval violation (S11/S12),
  unspecified.** Only the `ValueError` type is contractual. The codebase's
  idiom for the same check is `"please provide 1 or 3 values for minimum."`
  (`lupton_rgb.py:84` and `:739`); wording the RGB message by direct
  substitution on that idiom — `"please provide 1 or 3 instances for
  interval."` — is the reviewer's recommendation, since
  a caller matching on a substring is more likely to match that phrasing than
  a novel one. The shape-mismatch message is different: `shapes must match` is
  contractual, because an existing test matches on it.
- Existing NumPy rounding behavior for `np.uint8` output (truncation vs.
  rounding of mid-tone values) is not pinned by any scenario; S4 asserts only
  the exact endpoints (`0` and `255`) and monotonicity, which hold under
  either rule.

## References

- `astropy/visualization/basic_rgb.py`
- `astropy/visualization/lupton_rgb.py`
- `astropy/visualization/interval.py`
- `astropy/visualization/stretch.py`
- `astropy/visualization/transform.py`
- `astropy/visualization/tests/test_lupton_rgb.py`
- `astropy/visualization/tests/test_interval.py`
- `astropy/visualization/tests/test_stretch.py`
- `docs/visualization/rgb.rst`

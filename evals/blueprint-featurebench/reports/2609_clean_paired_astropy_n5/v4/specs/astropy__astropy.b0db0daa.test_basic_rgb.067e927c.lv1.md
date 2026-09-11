# 2609.0001 Restore RGBImageMapping Construction and Image Conversion

**Date:** 2026-09-10
**Status:** draft
**Author:** FeatureBench

## Context

`astropy.visualization.basic_rgb` provides `RGBImageMapping`, the class that
turns three co-aligned single-band images into one RGB composite by applying
a per-channel `~astropy.visualization.BaseInterval` (normalization) followed
by a shared `~astropy.visualization.BaseStretch`. It is the base class behind
two public entry points:

- `astropy.visualization.basic_rgb.make_rgb` (module-level convenience
  function, already present and unmodified) constructs an `RGBImageMapping`
  and calls `.make_rgb_image(...)` on it.
- `astropy.visualization.lupton_rgb.RGBImageMappingLupton` (already present),
  which subclasses `RGBImageMapping`, overrides `__init__` (delegating to
  `super().__init__(interval=..., stretch=...)` at
  `astropy/visualization/lupton_rgb.py:557`), `intensity`, and
  `apply_mappings` — but *not* `make_rgb_image`. It relies on the inherited
  `make_rgb_image` and on two attributes set by the base `__init__`:
  `self.intervals` (a 3-element list) and `self.stretch`. `make_lupton_rgb`
  in `astropy/visualization/lupton_rgb.py:751` depends on this chain working
  and calls `lup_map.make_rgb_image(image_r, image_g, image_b,
  output_dtype=output_dtype)`.

In the current checkout, the entire body of `RGBImageMapping` in
`astropy/visualization/basic_rgb.py` between the class docstring
(ends line 34) and the module-level `make_rgb` function (starts line 156) has
been removed. That means **`__init__`, `apply_mappings`, and
`make_rgb_image` are all missing** — `apply_mappings` is easy to overlook
because `RGBImageMappingLupton` defines its own override
(`astropy/visualization/lupton_rgb.py:584`), but the base class needs its own
version for `make_rgb` / `RGBImageMapping` to work at all. Four further
pieces of supporting infrastructure that this pipeline depends on are also
missing:

- `astropy/visualization/interval.py`: `BaseInterval` calls
  `self._process_values(values)` from `ManualInterval.get_limits`,
  `MinMaxInterval.get_limits`, `AsymmetricPercentileInterval.get_limits`, and
  `SymmetricInterval.get_limits`, but no `_process_values` method exists
  anywhere in the file. `ZScaleInterval.__init__` is present but
  `ZScaleInterval.get_limits` is entirely missing.
- `astropy/visualization/stretch.py`: every concrete stretch's `__call__`
  (e.g. `LinearStretch`, `SqrtStretch`, `PowerStretch`, `LogStretch`,
  `AsinhStretch`, ...) calls a module-level `_prepare(values, clip=clip,
  out=out)` helper that does not exist in the file. `CompositeStretch`
  (`astropy/visualization/stretch.py:976`) has a docstring but no `__call__`
  override, so it currently falls back to
  `CompositeTransform.__call__` (`astropy/visualization/transform.py:36`),
  which does not accept an `out` keyword — this breaks the `out=`-based
  in-place tests in `astropy/visualization/tests/test_stretch.py` for any
  stretch built with `+` (e.g.
  `LinearStretch(intercept=0.5) + LinearStretch(slope=0.5)`, exercised by
  `TestStretch.test_inplace` at
  `astropy/visualization/tests/test_stretch.py:70`).
- `astropy/visualization/lupton_rgb.py`: `LuptonAsinhStretch.__call__`
  (`astropy/visualization/lupton_rgb.py:450`) calls
  `_stretch_prepare(values, clip=clip, out=out)`, but **the import that binds
  that name has been removed too** — lines 15–16 of that file are blank,
  between `from astropy.visualization.stretch import BaseStretch` (line 14)
  and `from .basic_rgb import RGBImageMapping` (line 17), and a repo-wide
  grep for `_stretch_prepare` finds only the call site at line 450 with no
  definition or import. Every Lupton test that renders an image through a
  Lupton stretch (`test_Asinh`, `test_AsinhZscale*`, `test_make_rgb`) raises
  `NameError` on this line no matter what is done in `basic_rgb.py`, so
  restoring this one import line is in scope for this spec. (`test_linear`
  passes a plain `LinearStretch`, so it goes through `stretch._prepare`
  instead and is unaffected by this particular gap.)

`astropy/visualization/tests/test_interval.py` and
`astropy/visualization/tests/test_stretch.py` already exist and exercise
this supporting behavior end to end (`_process_values` and
`ZScaleInterval.get_limits` via `TestInterval`/`test_zscale`/
`test_zscale_npoints`; `_prepare` and `CompositeStretch` via `TestStretch`).
They currently fail or error because the underlying methods are missing.
`astropy/visualization/tests/test_lupton_rgb.py` also currently fails
because it depends on `RGBImageMapping.__init__`/`make_rgb_image` through
`RGBImageMappingLupton`, and on the missing `_stretch_prepare` binding.
Caveat for scenario design: apart from the error-path tests, the Lupton
rendering tests (`test_Asinh`, `test_AsinhZscale*`, `test_linear`) call
`make_rgb_image` and assert *nothing* about the result, so they detect
crashes but not wrong values.

## Motivation

Without a working `RGBImageMapping.__init__`, `.apply_mappings`, and
`.make_rgb_image`, both public RGB-composite entry points (`make_rgb` and
`make_lupton_rgb`) are unusable, and the existing interval/stretch/lupton_rgb
test suites fail. Restoring this pipeline — the class construction, the
per-channel mapping, the image conversion, and the supporting primitives it
transitively depends on (`BaseInterval._process_values`,
`ZScaleInterval.get_limits`, `stretch._prepare`, `CompositeStretch.__call__`,
and the `_stretch_prepare` import in `lupton_rgb.py`) — makes the documented
RGB workflow in `docs/visualization/rgb.rst` work again and unblocks the
existing test suites without touching anything unrelated.

## Proposed Solution

### Overview

Restore behavior only; do not change any public signature, file layout, or
`__all__` export that already exists in `astropy/visualization/basic_rgb.py`,
`interval.py`, or `stretch.py`. Fill in:

1. `RGBImageMapping.__init__` — normalize the `interval` argument into a
   3-element `self.intervals` list and store `self.stretch`.
2. `RGBImageMapping.apply_mappings` — the per-channel interval-then-stretch
   step, as an **overridable method** (this is the extension point
   `RGBImageMappingLupton` replaces).
3. `RGBImageMapping.make_rgb_image` — validate `output_dtype` and shapes,
   delegate the per-channel work to `self.apply_mappings(...)`, stack into an
   `NxMx3` array, and convert to the requested output dtype.
4. `BaseInterval._process_values` (`astropy/visualization/interval.py`) — the
   shared preprocessing step used by `ManualInterval`, `MinMaxInterval`,
   `AsymmetricPercentileInterval`, and `SymmetricInterval`.
5. `ZScaleInterval.get_limits` (`astropy/visualization/interval.py`) — IRAF
   zscale algorithm honoring the parameters already stored on `self` by
   `__init__` (`n_samples`, `contrast`, `max_reject`, `min_npixels`, `krej`,
   `max_iterations`).
6. `_prepare` (module-level helper in `astropy/visualization/stretch.py`) —
   the shared `clip`/`out` handling used by every concrete stretch's
   `__call__`.
7. `CompositeStretch.__call__` (`astropy/visualization/stretch.py`) — apply
   `transform_1` then `transform_2` with `clip`/`out` semantics matching
   every other stretch.
8. The single missing import line in `astropy/visualization/lupton_rgb.py`
   that binds `_stretch_prepare` (used at line 450) to `stretch._prepare`.
   This is the **only** edit permitted in `lupton_rgb.py`.

None of these eight items are independently optional: `make_rgb_image` cannot
run end to end without a working interval `__call__` chain (which needs
`_process_values` for every non-`ManualInterval`-with-both-limits case) and a
working stretch `__call__` chain (which needs `_prepare`);
`RGBImageMappingLupton`/`make_lupton_rgb` need `ZScaleInterval.get_limits`
for its `AsinhZScaleMapping`/`LuptonAsinhZscaleStretch` paths and need
`_stretch_prepare` bound for any Lupton stretch to evaluate at all; and
without `make_rgb_image` dispatching through `self.apply_mappings(...)`,
`RGBImageMappingLupton`'s override is silently bypassed and
`make_lupton_rgb` stops implementing the Lupton algorithm.

### Key Components

- **`RGBImageMapping.__init__`**
  (`astropy/visualization/basic_rgb.py`) — Accepts `interval` (a single
  `BaseInterval` instance or an array-like of exactly 3) and `stretch` (a
  single `BaseStretch`, shared across channels). Stores the per-channel
  intervals as `self.intervals` (a plain 3-element list — this exact
  attribute name is required because `RGBImageMappingLupton.apply_mappings`
  reads `self.intervals[i].get_limits(img)` at
  `astropy/visualization/lupton_rgb.py:635`) and the shared stretch as
  `self.stretch` (read by the same method at line 642 as `self.stretch(Int,
  clip=False)`). When a single `BaseInterval` instance is given, the *same*
  object is reused for all three list entries (not three separate copies).

- **`RGBImageMapping.apply_mappings`**
  (`astropy/visualization/basic_rgb.py`) — Signature
  `apply_mappings(self, image_r, image_g, image_b)`, identical to the
  override at `astropy/visualization/lupton_rgb.py:584`. Returns the three
  channels normalized into `[0, 1]`, in R, G, B order, as a 3-element
  sequence of `NxM` arrays (the Lupton override returns a `3xNxM` ndarray —
  `make_rgb_image` must accept either). Channel `i` is normalized by
  `self.intervals[i](img, clip=True)` and then stretched by
  `self.stretch(..., clip=True)`; both steps clip, so the result is
  guaranteed to lie in `[0, 1]` (S5 and the non-wrapping uint8 conversion
  both depend on that guarantee). This method exists as a separate,
  overridable method — not inlined into `make_rgb_image` — because it is the
  documented extension point the Lupton subclass replaces.

- **`RGBImageMapping.make_rgb_image`**
  (`astropy/visualization/basic_rgb.py`) — Validates that `output_dtype` is
  one of `_OUTPUT_IMAGE_FORMATS` (`[float, np.float64, np.uint8]`, already
  defined at module scope) and that `image_r`, `image_g`, `image_b` share
  one shape, raising `ValueError` otherwise. Obtains the three
  independently-normalized channels by calling
  `self.apply_mappings(image_r, image_g, image_b)` — **via `self`, so that a
  subclass override is used** — stacks them into one `NxMx3` array in R, G,
  B order along the last axis, and converts to `output_dtype`. It must not
  reimplement the interval/stretch loop inline: doing so would silently
  bypass `RGBImageMappingLupton.apply_mappings` and make `make_lupton_rgb`
  return plain per-band normalization instead of the Lupton composite.

- **`BaseInterval._process_values`**
  (`astropy/visualization/interval.py`) — Turns whatever `get_limits`
  receives (list, tuple, ndarray of any dimensionality, `np.ma.MaskedArray`,
  or `astropy.utils.masked.Masked`) into a flat 1-D **`np.ndarray`**
  containing only finite, unmasked values, in their original order, ready
  for `np.min`/`np.max`/`np.percentile`/zscale sampling. Three constraints
  are pinned by existing code and tests:
  - It must return an object with `.size` that `np.random.choice` accepts,
    because `AsymmetricPercentileInterval.get_limits`
    (`astropy/visualization/interval.py:205-206`) calls
    `values.size` and `np.random.choice(values, self.n_samples)` on the
    result — so a plain Python list is not acceptable.
  - It must strip the mask, not merely carry it: `TestIntervalMaskedArray`
    and `TestIntervalMaskedNDArray` in
    `astropy/visualization/tests/test_interval.py` append 100 masked `1e6`
    values to the 100-element base data and still expect the *unmasked*
    limits (e.g. `test_minmax` → `(-20.0, +60.0)`).
  - Order and content must be identical across all five data
    representations: `test_asymmetric_percentile_nsamples` runs under
    `NumpyRNGContext(12345)` and asserts the *same* sampled percentiles
    (`-14.367676767676768`, `40.266666666666666`) for the plain, list, 2-D,
    `MaskedArray`, and `Masked` variants, which only holds if
    `_process_values` yields the same 100 values in the same order for all
    of them.
  `astropy.utils.masked.get_data_and_mask` is already imported at
  `astropy/visualization/interval.py:12` and is otherwise unused in the
  file — that is the intended mechanism for handling both
  `np.ma.MaskedArray` and `Masked` uniformly.

- **`ZScaleInterval.get_limits`**
  (`astropy/visualization/interval.py`) — Implements IRAF's zscale
  algorithm: sample up to `self.n_samples` points from the (processed,
  flattened) data, sort them, iteratively sigma-reject a linear fit with
  rejection threshold `self.krej` for up to `self.max_iterations`
  iterations, and derive `vmin`/`vmax` from the fitted slope scaled by
  `self.contrast`. Falls back to returning the sampled data's raw
  `(min, max)` when the fit isn't usable — specifically when fewer than
  `self.min_npixels` points remain after rejection, or when more than
  `self.max_reject * npixels` points would need to be rejected.
  **Follow the reference implementation already cited in the class docstring**
  (`astropy/visualization/interval.py:271-272`, the stsci.numdisplay
  `zscale.py`), including its *deterministic* stride-based subsampling —
  `stride = max(1, size // n_samples)`, then `values[::stride][:n_samples]`
  — rather than random sampling. S11's `atol=0.1` on 10 000 Gaussian points
  subsampled to 1 000 is tight enough that a different sampling scheme, or
  an omitted step of the sigma-rejection loop, can land outside tolerance;
  S12/S12b/S13 use perfectly linear data or the fallback path and so will
  *not* catch such a deviation. S11 is the only scenario that discriminates
  here.

- **`_prepare`** (module-level function, `astropy/visualization/stretch.py`)
  — Signature `_prepare(values, clip=True, out=None)`, matching the 13 call
  sites already in the file (e.g. `astropy/visualization/stretch.py:147`).
  It returns the array that the caller then mutates in place, so it must
  satisfy exactly three observable properties:
  1. When `out` is `None`, the returned array is an independent, writable
     copy — mutating it must never change the caller's `values`. (Pinned by
     `TestStretch.test_no_clip`/`test_round_trip`, which reuse one
     module-level `DATA` array across every parametrized stretch and would
     drift if any call mutated it.)
  2. When `out` is provided, the returned array **is** `out`, so that the
     caller's in-place writes land in `out` and `out` holds the final
     result. (Pinned by `TestStretch.test_inplace`, which passes
     `out=np.zeros(DATA.shape)`, ignores the return value, and asserts on
     `result`; it also asserts `data_in` is unchanged, so `values` itself
     must not be written to.)
  3. When `clip=True`, the values are clipped to `[0, 1]` before the caller's
     transform runs; when `clip=False` they are passed through unclipped
     (`ContrastBiasStretch` at `astropy/visualization/stretch.py:914` relies
     on `clip=False` here and clips only afterwards).
  No error type is pinned for a non-writable or non-floating `out`; nothing
  in the repo exercises that path for stretches (`test_integers` in
  `astropy/visualization/tests/test_interval.py` pins that `TypeError` for
  `BaseInterval.__call__` only, which is already implemented). Do not
  invent an error path here, and do not force a dtype conversion beyond what
  these three properties require.

- **`CompositeStretch.__call__`**
  (`astropy/visualization/stretch.py`) — Signature
  `__call__(self, values, clip=True, out=None)`. `self.transform_1` is
  applied first, then `self.transform_2` is applied to that result, both
  with the given `clip` — the same order as the inherited
  `CompositeTransform.__call__` (`astropy/visualization/transform.py:37`),
  which this override exists solely to extend with `out` support. The
  composite honors `out` the same way every other stretch does (write into
  `out` when provided and return it; otherwise return a fresh array;
  `out=None` must not mutate the input).
  Note on operand order: `BaseStretch.__add__`
  (`astropy/visualization/stretch.py:66-67`) returns
  `CompositeStretch(other, self)`, so for `A + B` the *second* operand `B`
  becomes `transform_1` and is applied first.

- **`_stretch_prepare` import** (`astropy/visualization/lupton_rgb.py`) — Add
  the one import that binds the name used at
  `astropy/visualization/lupton_rgb.py:450` to the `stretch` module helper
  restored above (the alias name `_stretch_prepare` is fixed by that call
  site and must not change). Place it with the other `astropy.visualization`
  imports at the top of the file (the blank lines 15–16). This is the only
  change permitted in `lupton_rgb.py`.

### Data Flow

`make_rgb_image(image_r, image_g, image_b, output_dtype=np.uint8)`:

1. Validate `output_dtype in _OUTPUT_IMAGE_FORMATS`; raise `ValueError` if
   not. The message names `output_dtype` and lists the permitted formats.
2. Coerce each input with `np.asarray`, then validate
   `image_r.shape == image_g.shape == image_b.shape`; raise `ValueError` if
   not. The message must contain the substring `shapes must match` — reuse
   the wording already used by the sibling implementation at
   `astropy/visualization/lupton_rgb.py:112`
   (`"The image shapes must match. r: {}, g: {} b: {}"`), because
   `TestLuptonRgb.test_different_shapes_asserts` matches on it (S19).
3. Call `self.apply_mappings(image_r, image_g, image_b)` — through `self`,
   so a subclass override wins — and receive the three `[0, 1]`-normalized
   channels back (a 3-element sequence of `NxM` arrays, or an equivalent
   `3xNxM` array).
   The base implementation of `apply_mappings` does, for channel `i` in
   `0, 1, 2`: `img = self.intervals[i](img, clip=True)` followed by
   `self.stretch(img, clip=True, out=img)`. The three caller-supplied input
   arrays (`image_r`, `image_g`, `image_b`) are left unmodified by this step:
   `BaseInterval.__call__` with `out=None` already allocates via
   `np.subtract(values, vmin)` (`astropy/visualization/interval.py:113`), and
   `_prepare` guarantees the stretch does not write into its input.
4. Stack the three resulting `[0, 1]` channels along a new last axis (R, G,
   B order) into one `NxMx3` array — e.g. `np.dstack` on a 3-element
   sequence of `NxM` channels.
5. Convert to `output_dtype`:
   - `float` / `np.float64`: return the stacked `[0, 1]` array as that
     dtype.
   - `np.uint8`: multiply the normalized `[0, 1]` values by
     `np.iinfo(output_dtype).max` and cast with `.astype(output_dtype)`,
     returning an `NxMx3` array of dtype `np.uint8`. This follows the
     in-package precedent in `astropy/visualization/lupton_rgb.py:77`
     (`self._uint8Max = float(np.iinfo(np.uint8).max)`) and `:117`
     (`.astype(np.uint8)`), so the two RGB implementations quantize
     identically. Because step 3 guarantees `[0, 1]`, this cannot wrap
     around: `0.0 → 0` and `1.0 → 255`.

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
        interval : BaseInterval instance or array-like of exactly 3 BaseInterval instances
        stretch  : BaseStretch instance, shared across all 3 channels
        Sets self.intervals (list of 3) and self.stretch.
        Raises ValueError if `interval` is array-like but len(interval) != 3.
        Message convention: mirror `Mapping.__init__`
        (astropy/visualization/lupton_rgb.py:84), which raises
        "please provide 1 or 3 values for minimum." -- i.e. state the same
        thing for `interval`.
        """

    def apply_mappings(self, image_r, image_g, image_b):
        """
        Overridable per-channel mapping step. Same signature as
        RGBImageMappingLupton.apply_mappings (lupton_rgb.py:584).
        Returns the 3 channels normalized to [0, 1] in R, G, B order
        (3-element sequence of NxM arrays; a 3xNxM array is also acceptable,
        since the Lupton override returns one).
        Base behavior: self.intervals[i](img, clip=True), then
        self.stretch(..., clip=True, out=...).
        Must not mutate image_r/image_g/image_b.
        """

    def make_rgb_image(self, image_r, image_g, image_b, output_dtype=np.uint8):
        """
        Returns an NxMx3 ndarray (dtype == output_dtype).
        MUST obtain the channels via self.apply_mappings(...) so subclass
        overrides take effect.
        Raises ValueError if output_dtype not in [float, np.float64, np.uint8].
        Raises ValueError (message containing "shapes must match") if
        image_r/image_g/image_b shapes don't match.
        """
```

```python
# astropy/visualization/lupton_rgb.py -- the only permitted change here:
# bind the name already used at line 450 to the restored stretch helper.
from astropy.visualization.stretch import _prepare as _stretch_prepare
```

This is the full public surface this spec restores. `make_rgb`
(`astropy/visualization/basic_rgb.py`, already implemented) and
`RGBImageMappingLupton`/`make_lupton_rgb`
(`astropy/visualization/lupton_rgb.py`, already implemented apart from the
missing import above) are consumers of this contract and must not otherwise
change.

## Alternatives Considered

### Inline the per-channel interval+stretch loop directly inside `make_rgb_image`

Rejected — `RGBImageMappingLupton` (`astropy/visualization/lupton_rgb.py:584`)
overrides `apply_mappings` and does *not* override `make_rgb_image`, so the
Lupton algorithm reaches the output only if the base `make_rgb_image`
dispatches through `self.apply_mappings(...)`. Inlining would leave
`make_lupton_rgb` silently producing plain per-band normalization while
still returning a plausible-looking `NxMx3` uint8 image. Note that no
existing test in `astropy/visualization/tests/test_lupton_rgb.py` asserts on
Lupton pixel *values* (the rendering tests only check that the call
completes), so this regression would not be caught by the existing suite —
S8b exists specifically to catch it.

### Give `RGBImageMapping` a bespoke normalization routine instead of reusing `interval.__call__`/`stretch.__call__`

Rejected — `RGBImageMappingLupton.apply_mappings` already calls
`self.intervals[i].get_limits(...)` and `self.stretch(...)` directly, so the
base class's per-channel step must be built from those same two objects, or
the two classes' outputs would diverge for equivalent inputs.

## Acceptance Scenarios

### Happy Path

- **S1:** Given a single `BaseInterval` instance (e.g.
  `ManualInterval(vmin=0, vmax=1)`) and a `BaseStretch` instance passed to
  `RGBImageMapping(interval=..., stretch=...)`, when the instance is
  constructed, then `mapping.intervals` is a list of exactly 3 elements, all
  three are the same object as the one passed in (`mapping.intervals[0] is
  mapping.intervals[1] is mapping.intervals[2] is interval`), and
  `mapping.stretch is stretch`.
- **S2:** Given an array-like of exactly 3 distinct `BaseInterval` instances
  passed as `interval`, when `RGBImageMapping(interval=[i0, i1, i2])` is
  constructed, then `mapping.intervals` has length 3 and preserves position
  and identity: `mapping.intervals[0] is i0`, `[1] is i1`, `[2] is i2` (each
  channel keeps its own interval).
- **S3:** Given `RGBImageMapping()` constructed with no arguments, when
  inspected, then it behaves as if constructed with
  `interval=ManualInterval(vmin=0, vmax=None)` and `stretch=LinearStretch()`
  (i.e. `make_rgb_image` on data with only non-negative values and default
  args produces the same result as an explicit
  `RGBImageMapping(interval=ManualInterval(vmin=0, vmax=None),
  stretch=LinearStretch())`). Note that these defaults are evaluated once at
  import time (mutable default arguments, matching the existing signature of
  `make_rgb` at `astropy/visualization/basic_rgb.py:160-161`), so two
  default-constructed mappings share the *same* interval and stretch
  objects; tests must assert on behavior, not on object distinctness.
- **S4:** Given three equal-shape 2-D arrays with distinct values and a
  default-constructed `RGBImageMapping`, when
  `make_rgb_image(image_r, image_g, image_b)` is called with the default
  `output_dtype=np.uint8`, then it returns an `ndarray` of shape
  `image_r.shape + (3,)` and dtype `np.uint8`.
- **S5:** Given the same setup as S4, when `make_rgb_image(..., output_dtype=float)`
  and `make_rgb_image(..., output_dtype=np.float64)` are called, then both
  return an array of shape `image_r.shape + (3,)` with all values within
  `[0, 1]`.
- **S6:** Given an `RGBImageMapping` constructed with a 3-element list of
  `ManualInterval`s with different `vmin`/`vmax` per channel, when
  `make_rgb_image` is called on three images where each channel's values sit
  entirely inside its own interval's `[vmin, vmax]`, then each output
  channel reflects that channel's own normalization (e.g. a pixel at its
  channel's `vmax` normalizes to the stretch's output for input `1.0`,
  independent of what the other two channels' intervals are).
- **S7:** Given `image_r`, `image_g`, `image_b` passed into `make_rgb_image`,
  when the call returns, then the three original input arrays are
  numerically unchanged (compare against a pre-call copy) — the method does
  not mutate its inputs in place.
- **S8:** Given `RGBImageMappingLupton` (`astropy/visualization/lupton_rgb.py`)
  constructed with a `ManualInterval` and a `LuptonAsinhStretch`, when
  `.make_rgb_image(...)` (inherited from `RGBImageMapping`, not overridden by
  the subclass) is called on three equal-shape images, then it returns an
  `NxMx3` array without error — i.e. the base class's `make_rgb_image`
  correctly drives a subclass that overrides `apply_mappings`/`intensity`,
  and `_stretch_prepare` resolves inside `LuptonAsinhStretch.__call__`
  instead of raising `NameError`.
- **S8b:** Given a minimal subclass of `RGBImageMapping` whose
  `apply_mappings(image_r, image_g, image_b)` ignores its arguments and
  returns three known constant `NxM` arrays (e.g. all-`0.25`, all-`0.5`,
  all-`0.75`), when `make_rgb_image(...)` is called on that subclass with
  `output_dtype=float`, then the returned `NxMx3` array contains exactly
  those constants in R, G, B order along the last axis. This fails if
  `make_rgb_image` computes the channels itself instead of delegating to
  `self.apply_mappings(...)`, which no existing test would otherwise catch
  (see Alternatives Considered).
- **S8c:** Given the same subclass as S8b but returning all-`0.0`,
  all-`0.5`, and all-`1.0` channels and called with `output_dtype=np.uint8`,
  when `make_rgb_image(...)` is called, then the R channel is exactly `0`,
  the B channel is exactly `255`, and the G channel is within 1 of
  `0.5 * 255` — i.e. the full uint8 range is used, the mapping is
  monotonic, and nothing wraps around. (The interior value follows from the
  quantization rule pinned in Data Flow step 5; only the endpoints are
  asserted exactly, so the scenario stays robust to the truncate-vs-round
  boundary convention — see Trade-offs.)
- **S8d:** Given three equal-shape images, when the module-level
  `make_rgb(image_r, image_g, image_b, interval=..., stretch=...,
  output_dtype=...)` (`astropy/visualization/basic_rgb.py:156`, already
  implemented and unchanged) is called, then it returns exactly what
  `RGBImageMapping(interval=..., stretch=...).make_rgb_image(image_r,
  image_g, image_b, output_dtype=...)` returns — confirming the restored
  `__init__`/`make_rgb_image` signatures match how the existing public entry
  point already calls them at `astropy/visualization/basic_rgb.py:209-210`.

### Edge Cases

- **S9:** Given `interval` as an array-like of exactly 3 `BaseInterval`
  instances, when `make_rgb_image` is called, then each channel is mapped by
  its own interval (`self.intervals[0]` for red, `[1]` for green, `[2]` for
  blue) — verified by giving each channel a different `vmax` and confirming
  the resulting channels are not identical even when the raw pixel values
  are identical across channels.
- **S10:** Given `BaseInterval._process_values` is exercised indirectly via
  `ManualInterval().get_limits(...)`/`MinMaxInterval().get_limits(...)` on a
  Python list, a 2-D ndarray, an `np.ma.MaskedArray`, and an
  `astropy.utils.masked.Masked` array (all four already covered by
  `TestInterval`/`TestIntervalList`/`TestInterval2D`/
  `TestIntervalMaskedArray`/`TestIntervalMaskedNDArray` in
  `astropy/visualization/tests/test_interval.py`), when `get_limits` is
  called, then masked entries and non-finite (NaN/inf) entries are excluded
  from the returned min/max, matching the values already asserted in that
  test file for each interval type.
- **S10b:** Given `AsymmetricPercentileInterval(10.5, 70.5, n_samples=20)`
  under `NumpyRNGContext(12345)` (as in
  `test_asymmetric_percentile_nsamples`), when `get_limits` is called on each
  of the five equivalent data representations — plain 1-D ndarray, Python
  list, `(100, 1)` 2-D ndarray, `np.ma.MaskedArray` with 100 extra masked
  `1e6` values, and the `Masked` equivalent — then all five return the same
  `(vmin, vmax)` (`-14.367676767676768`, `40.266666666666666`). This holds
  only if `_process_values` yields the same 100 surviving values **in the
  same order** for every representation, and returns something
  `np.random.choice` accepts (i.e. a 1-D `ndarray`, not a list).
- **S11:** Given `ZScaleInterval()` on `np.random.seed(42); data =
  np.random.randn(100, 100) * 5 + 10` (as in
  `astropy/visualization/tests/test_interval.py::test_zscale`), when
  `get_limits(data)` is called, then it returns `vmin ≈ -9.6` and
  `vmax ≈ 25.4` (`atol=0.1`).
- **S12:** Given `ZScaleInterval()` on `list(range(1000)) + [np.nan]` (as in
  the same test), when `get_limits(data)` is called, then it returns
  `vmin ≈ 0` and `vmax ≈ 999` (`atol=0.1`) — the NaN is excluded rather than
  propagating.
- **S12b:** Given `ZScaleInterval()` on `list(range(100))` (the third case in
  `astropy/visualization/tests/test_interval.py::test_zscale`), when
  `get_limits(data)` is called, then it returns `vmin ≈ 0` and `vmax ≈ 99`
  (`atol=0.1`) — i.e. a dataset smaller than the default `n_samples=1000` is
  used whole, without sampling.
- **S13:** Given `ZScaleInterval(min_npixels=5)` on `np.arange(4).reshape((2,
  2))` (as in `test_zscale_npoints`), when `get_limits(data)` is called,
  then it falls back to the plain data min/max: `vmin == 0`, `vmax == 3`,
  because fewer than `min_npixels` points remain for a rejection fit.
- **S14:** Given any concrete stretch (e.g. `LinearStretch()`, `SqrtStretch()`),
  when called with `out=None`, then mutating the returned array afterward
  does not change the original input array passed in (independent, writable
  output) — matching `TestStretch.test_round_trip`/`test_no_clip` in
  `astropy/visualization/tests/test_stretch.py`, which reuse the same
  `DATA` array across many stretch calls and require it stay unmodified.
- **S15:** Given a stretch called with an explicit `out=result` array, when
  the call returns, then `result` contains the transformed values and is
  the same object returned by `__call__` — matching
  `TestStretch.test_inplace` (`astropy/visualization/tests/test_stretch.py:70`).
- **S16:** Given `LinearStretch(intercept=0.5) + LinearStretch(slope=0.5)`
  (a `CompositeStretch`), when called on
  `DATA = np.array([0.00, 0.25, 0.50, 0.75, 1.00])` with `clip=False`, then
  it returns `[0.5, 0.625, 0.75, 0.875, 1.0]` (`atol=1e-6`) — `transform_1`
  is applied before `transform_2`, and because `BaseStretch.__add__` builds
  `CompositeStretch(other, self)`
  (`astropy/visualization/stretch.py:66-67`), `transform_1` here is
  `LinearStretch(slope=0.5)` (the *second* operand of `+`) and `transform_2`
  is `LinearStretch(intercept=0.5)`. Applying them in the reverse order
  would give `[0.25, 0.375, 0.5, 0.625, 0.75]`, so this scenario detects an
  order swap. This exact case is parametrized into
  `TestStretch.test_no_clip`, `test_clip`, `test_inplace`,
  `test_round_trip`, `test_inplace_roundtrip`, and `test_double_inverse` via
  the module-level `RESULTS` dict in
  `astropy/visualization/tests/test_stretch.py`.
- **S17:** Given the same `CompositeStretch` as S16, when called with an
  explicit `out=result` array (as in `TestStretch.test_inplace`), then it
  writes into `result` rather than raising `TypeError` for missing `out`
  support.

### Error Scenarios

- **S18:** Given `interval` passed as an array-like with 2 elements (or 4),
  when `RGBImageMapping(interval=[i0, i1])` is constructed, then it raises
  `ValueError` whose message says 1 or 3 values are required for `interval`
  (mirroring `Mapping.__init__`'s
  `"please provide 1 or 3 values for minimum."` at
  `astropy/visualization/lupton_rgb.py:84`).
- **S19:** Given `image_r`, `image_g`, `image_b` with mismatched shapes (e.g.
  `image_r.reshape(h, w)` transposed relative to the others — mirroring
  `TestLuptonRgb.test_different_shapes_asserts` in
  `astropy/visualization/tests/test_lupton_rgb.py:343`), when
  `make_rgb_image` is called, then it raises `ValueError` whose message
  matches `r"shapes must match"` (this exact message substring is asserted
  by the existing lupton_rgb test, which exercises this base-class method
  through `RGBImageMappingLupton`).
- **S20:** Given `output_dtype` set to something not in `[float, np.float64,
  np.uint8]` (e.g. `np.int32` or `str`), when `make_rgb_image(..., output_dtype=...)`
  is called, then it raises `ValueError` whose message names `output_dtype`.
  The check must run before any mapping work, so it also raises for
  otherwise-valid images.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that would *fail if the behavior were wrong*. A green suite that passes for the wrong reason does not satisfy this contract — `/verify` will hunt for vacuous tests by asking, of each behavior, "what is the smallest change that breaks this, and would any test catch it?"

Concretely, in this repository:

- Implement in `astropy/visualization/basic_rgb.py`:
  `RGBImageMapping.__init__`, `RGBImageMapping.apply_mappings`, and
  `RGBImageMapping.make_rgb_image`, matching the Interface Contract above
  exactly (same parameter names/defaults — other code, including `make_rgb`
  in the same file and `RGBImageMappingLupton` in
  `astropy/visualization/lupton_rgb.py`, already calls these with keyword and
  positional arguments in the shapes shown). `make_rgb_image` must reach the
  per-channel work through `self.apply_mappings(...)`; do not inline it.
- Implement in `astropy/visualization/interval.py`: `BaseInterval._process_values`
  and `ZScaleInterval.get_limits`. Do not change any other method in this
  file — `ManualInterval`, `MinMaxInterval`, `AsymmetricPercentileInterval`,
  `PercentileInterval`, `SymmetricInterval`, and `BaseInterval.__call__` are
  already complete and already call `self._process_values(...)`.
- Implement in `astropy/visualization/stretch.py`: the module-level
  `_prepare(values, clip=..., out=...)` helper and
  `CompositeStretch.__call__`. Do not change any concrete stretch's
  `__call__` body — they already call `_prepare(values, clip=clip, out=out)`
  and only need that function to exist with matching semantics.
- In `astropy/visualization/lupton_rgb.py`, make **exactly one** change: add
  `from astropy.visualization.stretch import _prepare as _stretch_prepare`
  near the existing imports (lines 14–17). Every other line of that file —
  including `RGBImageMappingLupton.apply_mappings` and the `Mapping` classes
  — is already correct and must not change.
- Do not modify `astropy/visualization/transform.py` or any test file — they
  are the ground truth for several scenarios above (S8, S19 via
  `test_lupton_rgb.py`; S10–S13 including S10b/S12b via `test_interval.py`;
  S14–S17 via `test_stretch.py`).
- Run the existing suites as you go:
  `pytest astropy/visualization/tests/test_interval.py
  astropy/visualization/tests/test_stretch.py
  astropy/visualization/tests/test_lupton_rgb.py` — these must pass
  unmodified. A `test_basic_rgb.py` covering `RGBImageMapping` directly does
  not yet exist in this checkout; create
  `astropy/visualization/tests/test_basic_rgb.py` covering S1–S9 (including
  S8b, S8c, S8d), S18, and S20 at minimum. Note that S8b/S8c/S8d have no existing coverage anywhere and
  the existing Lupton rendering tests assert nothing about pixel values, so
  those scenarios need new tests to be non-vacuous.

Write tests to the project's conventions (see the existing parametrized
style in `astropy/visualization/tests/test_interval.py` and
`test_stretch.py`) and to these principles (the same ones `/verify` scores
against — see `references/test-desiderata.md` and `references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects (returned
  arrays, dtypes, shapes, raised exceptions), not internals like private
  attribute layouts beyond what's contractually required (`self.intervals`,
  `self.stretch`).
- **Every test can fail** — no copy-pasted expected values, no asserting a
  constant, no tautologies (AP-2, AP-4). Use the concrete numeric
  expectations already present in `test_interval.py`/`test_stretch.py`
  where scenarios reference them.
- **Deterministic, isolated, readable** — seed `np.random` where randomness
  is involved (as the existing zscale tests already do), no cross-test
  state, AAA structure with inline setup.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Test suite is green, including the previously-failing
      `astropy/visualization/tests/test_interval.py`,
      `astropy/visualization/tests/test_stretch.py`, and
      `astropy/visualization/tests/test_lupton_rgb.py`.
- [ ] `RGBImageMapping.make_rgb_image` obtains its channels via
      `self.apply_mappings(...)`, and `RGBImageMapping.apply_mappings` exists
      as an overridable base method (S8b).
- [ ] `_stretch_prepare` is bound in `astropy/visualization/lupton_rgb.py`,
      and that file is unchanged apart from that one added import.
- [ ] Every acceptance scenario (S1…S20, including the lettered
      sub-scenarios S8b, S8c, S8d, S10b, S12b) maps to at least one test.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under the
      smallest break of its behavior (thought-mutation), e.g. swapping
      `self.intervals[0]`/`[1]`, inlining `apply_mappings` into
      `make_rgb_image`, dropping the finite/unmasked filter in
      `_process_values`, or returning the caller's own array from `_prepare`
      instead of a copy.
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
      first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings) in `basic_rgb.py`, `interval.py`, or `stretch.py`.

## Trade-offs and Limitations

- The uint8 quantization rule is pinned in Data Flow step 5 (scale by
  `np.iinfo(output_dtype).max`, then `.astype(output_dtype)`), following the
  in-package precedent at `astropy/visualization/lupton_rgb.py:77` and
  `:117`. No test in this checkout pins an exact interior per-pixel uint8
  value, so the truncate-vs-round convention at fractional boundaries (e.g.
  `0.5 * 255 = 127.5` → `127` under `.astype`) is a documented consequence
  of that rule rather than an independently verified requirement. S8c
  therefore asserts the endpoints exactly and the interior only to within
  1 count. Accepted limitation: if a future consumer needs bit-exact
  interior values, that convention must be pinned by a new test.
- `ZScaleInterval.get_limits`'s sigma-rejection fit is a numerical
  algorithm with several interacting parameters (`contrast`, `krej`,
  `max_iterations`, `max_reject`, `min_npixels`, `n_samples`); this spec
  pins its behavior only at the four points already covered by
  `astropy/visualization/tests/test_interval.py` (S11, S12, S12b, S13).
  That is enough to detect a broken or missing implementation, but note the
  asymmetry: S12/S12b/S13 pass for almost any reasonable algorithm, while
  S11's `atol=0.1` effectively requires following the cited stsci.numdisplay
  reference algorithm (sampling scheme included, see Key Components). The
  agent should port that reference rather than invent an equivalent-looking
  rejection loop; only exact IRAF *bit*-level reproduction is out of scope.
- Exact exception *messages* are pinned only where an existing test matches
  on them (`shapes must match`, S19). For the `interval`-count and
  `output_dtype` errors the spec pins the exception type and requires the
  message to name the offending parameter, following the repo's existing
  phrasing conventions; the precise wording is left open because nothing in
  this checkout constrains it.

## Open Questions

This spec was written and reviewed non-interactively, so the following were
resolved by the reviewer from evidence in the checkout rather than by asking
a human. They are recorded here because each was a genuine fork.

1. **Should `make_rgb_image` inline the per-channel loop or delegate to an
   overridable `apply_mappings`?** Resolved: delegate. Evidence:
   `RGBImageMappingLupton` overrides `apply_mappings`
   (`astropy/visualization/lupton_rgb.py:584`) and does not override
   `make_rgb_image`, so delegation is the only way the Lupton algorithm can
   reach output. See Alternatives Considered and S8b.
2. **Is `lupton_rgb.py` really off-limits?** Resolved: no — its
   `_stretch_prepare` import is missing (used at line 450, defined nowhere),
   so exactly one import line must be added there. Everything else in the
   file stays as-is.
3. **Does `_prepare` need to validate `out` and raise `TypeError`?**
   Resolved: no. The `TypeError` for non-float `out` belongs to
   `BaseInterval.__call__` (`astropy/visualization/interval.py:115-118`,
   pinned by `test_integers`), which is already implemented. No stretch test
   exercises an invalid `out`, so no such error path is required — inventing
   one would be an unverified requirement.
4. **What does `_process_values` return for input that is entirely
   non-finite or fully masked?** Unresolved and out of scope: no test or
   caller in this checkout exercises it, and `np.min` on an empty array
   would raise. Accepted limitation — the implementing agent should not add
   speculative handling; whatever falls out of the natural implementation is
   acceptable, and no scenario asserts on it.

## References

- `astropy/visualization/basic_rgb.py` — `RGBImageMapping`, `make_rgb`
- `astropy/visualization/lupton_rgb.py` — `RGBImageMappingLupton`
  (`apply_mappings` override at line 584), `make_lupton_rgb` (consumers of
  this contract, already implemented); also the missing `_stretch_prepare`
  import used at line 450, and the `Mapping` class whose
  `make_rgb_image`/`__init__` (lines 84, 112, 117) supply the error-message
  and uint8-quantization conventions this spec reuses
- `astropy/visualization/interval.py` — `BaseInterval`, `ZScaleInterval`
- https://github.com/spacetelescope/stsci.numdisplay/blob/master/lib/stsci/numdisplay/zscale.py
  — the zscale reference implementation already cited in the
  `ZScaleInterval` docstring (`astropy/visualization/interval.py:271-272`);
  port this for `get_limits`
- `astropy/visualization/stretch.py` — `BaseStretch`, `CompositeStretch`
- `astropy/visualization/transform.py` — `CompositeTransform` (base
  `__call__`/`__init__` that `CompositeStretch` extends)
- `astropy/visualization/tests/test_interval.py`,
  `astropy/visualization/tests/test_stretch.py`,
  `astropy/visualization/tests/test_lupton_rgb.py` — existing ground-truth
  tests this restoration must keep green
- `docs/visualization/rgb.rst` — documented user-facing workflow this
  pipeline supports

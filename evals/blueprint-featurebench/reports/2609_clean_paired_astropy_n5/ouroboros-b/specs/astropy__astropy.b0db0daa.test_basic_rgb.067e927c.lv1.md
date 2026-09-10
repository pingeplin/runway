# 2609.0001 Restore RGB Image Mapping Construction and Conversion

**Date:** 2026-09-10
**Status:** draft
**Author:** FeatureBench

## Context

`astropy.visualization` builds RGB composite images from three aligned,
same-shape single-band arrays. There are two code paths that produce an
RGB image, sharing one base class:

- `astropy/visualization/basic_rgb.py` — `RGBImageMapping` and its
  `make_rgb()` convenience function: a simple per-channel scheme where
  each channel is normalized and stretched independently, no
  cross-channel coupling.
- `astropy/visualization/lupton_rgb.py` — `RGBImageMappingLupton(RGBImageMapping)`
  and `make_lupton_rgb()`: the Lupton et al. (2004) scheme, which
  couples the three channels through a shared intensity.

`RGBImageMapping`'s entire class body — everything in
`astropy/visualization/basic_rgb.py` between the class docstring (lines
19–34) and the `make_rgb()` function (line 156 onward) — is currently
blank. No method exists: `__init__`, the per-channel mapping hook, and
`make_rgb_image` are all missing. The **only** surviving text that
describes the class's contract is the class docstring itself (interval/
stretch parameter description) and `make_rgb()`'s own docstring
(`basic_rgb.py:165-208`, which documents the wrapper function's
parameters, `Returns`, and DS9-comparison `Notes`) — there is no
surviving `__init__` or `make_rgb_image` docstring anywhere in the file
to read back.

Four more callables these methods need are also blank:

- `astropy/visualization/stretch.py`: the module-level `_prepare(values,
  clip=True, out=None)` helper. Every concrete stretch's `__call__`
  (`LinearStretch`, `SqrtStretch`, `LogStretch`, …) already calls
  `_prepare(...)` as its first line, but the function itself does not
  exist. `CompositeStretch.__call__` (used whenever two transforms are
  combined with `+`) is also missing — the class has only a docstring.
- `astropy/visualization/interval.py`: `BaseInterval._process_values`,
  called by `ManualInterval.get_limits`, `MinMaxInterval.get_limits`,
  `AsymmetricPercentileInterval.get_limits`, and
  `SymmetricInterval.get_limits`, does not exist. `ZScaleInterval.get_limits`
  is entirely missing (only `__init__` is present).

In total this spec restores **seven missing methods/functions across
three files** (`_prepare`, `CompositeStretch.__call__`,
`BaseInterval._process_values`, `ZScaleInterval.get_limits`,
`RGBImageMapping.__init__`, `RGBImageMapping.apply_mappings`, and
`RGBImageMapping.make_rgb_image`), **plus one missing import
binding** in a fourth file (below).

Because `_prepare` and `_process_values` are shared helpers, every
existing stretch and interval class is broken today, not just the RGB
path: `astropy/visualization/tests/test_stretch.py`,
`astropy/visualization/tests/test_interval.py`,
`astropy/visualization/tests/test_norm.py`, and
`astropy/visualization/scripts/tests/test_fits2bitmap.py` all fail, and
the doctests in `docs/visualization/normalization.rst` (run by pytest via
`doctest_plus`/`--doctest-rst`, configured in `pyproject.toml`) fail too.

A more subtle break sits in `lupton_rgb.py`: `LuptonAsinhStretch.__call__`
(`lupton_rgb.py:450`) calls `_stretch_prepare(values, clip=clip, out=out)`,
but no name `_stretch_prepare` is imported or defined anywhere in that
file — the binding (originally an aliased import of `stretch.py`'s
`_prepare`) was stripped along with everything else, leaving two blank
lines between the `BaseStretch` import (`lupton_rgb.py:14`) and the
`RGBImageMapping` import (`:17`). Every test that constructs a
`LuptonAsinhStretch`/`LuptonAsinhZscaleStretch` or calls `make_lupton_rgb`
with default arguments currently raises `NameError`, independent of
anything restored in `basic_rgb.py`. This one-line binding is therefore
in scope even though the rest of `lupton_rgb.py`'s algorithms are intact
and must not be changed.

`RGBImageMappingLupton` calls `super().__init__(interval=interval,
stretch=stretch)`, then reads `self.intervals[i].get_limits(img)` (a
list of exactly 3 interval instances — plural attribute name
`intervals`) and calls `self.stretch(Int, clip=False)` directly
(`lupton_rgb.py:635,642`). It overrides `apply_mappings(self, image_r,
image_g, image_b)` and `intensity(self, image_r, image_g, image_b)`
while inheriting `make_rgb_image` unmodified. This means the base
class's internals are not a free implementation choice: Lupton's working
algorithm already depends on specific attribute and method names on
`RGBImageMapping`, and on `make_rgb_image` dispatching to
`apply_mappings` polymorphically rather than inlining the per-channel
logic.

## Motivation

`astropy/visualization/tests/test_basic_rgb.py` does not exist in this
checkout — it is a held-out test that will be run against this code
after restoration, with no further guidance available at that point.
The ground truth available now is: (a) the class docstring and
`make_rgb()`'s docstring in `basic_rgb.py`, (b) `docs/visualization/rgb.rst`'s
worked examples, (c) the already-working call sites in `lupton_rgb.py`
that pin attribute/method names and the `"shapes must match"` error
wording, and (d) the existing (currently failing) test suites
`test_interval.py`, `test_stretch.py`, `test_norm.py`,
`test_fits2bitmap.py`, and `test_lupton_rgb.py` plus the
`normalization.rst` doctests, which exercise the stubbed helpers and
therefore double as executable specifications for their exact numeric
and dtype behavior. Getting the attribute names, error messages, dtype
handling, or numeric semantics wrong will silently break
`lupton_rgb.py`, `mpl_normalize.py`'s `ImageNormalize` (and everything
built on it, including `fits2bitmap`), or the documentation build, even
though none of those files are the direct target of this restoration.

## Proposed Solution

### Overview

Fill in the seven missing methods/functions plus the one missing import
binding (see Context), so that: (1) every existing stretch/interval/
normalize/fits2bitmap test and doctest that is not itself specific to
`ZScaleInterval` or `CompositeStretch` passes again (they already
exercise `_prepare` and `_process_values` transitively); (2)
`ZScaleInterval.get_limits` and `CompositeStretch.__call__` behave per
their docstrings and the numeric expectations in
`test_interval.py`/`test_stretch.py`/`normalization.rst`; (3)
`RGBImageMapping.__init__`, its per-channel mapping hook, and
`make_rgb_image` behave per the class/`make_rgb()` docstrings, `rgb.rst`,
and keep `test_lupton_rgb.py` green through inheritance once the
`_stretch_prepare` binding is restored.

### Key Components

- **`astropy/visualization/stretch.py::_prepare(values, clip=True, out=None)`**
  — module-level helper. When `out is None`, returns an independent,
  writable **float** copy of `values`
  (`np.array(values, dtype=float, copy=True)` or equivalent) — concrete
  stretch `__call__` bodies do in-place float math via
  `np.multiply(..., out=values)`, `np.sqrt(values, out=values)`, etc.
  (`stretch.py:146-156`, `:230-236`), so the returned array must always
  be float regardless of the input dtype; this is unrelated to, and does
  not contradict, `_process_values`'s dtype-preserving behavior below —
  the two functions have different jobs (one prepares values for
  in-place math, the other summarizes a dataset's limits). When `out` is
  given, fills it in place via `out[:] = values` (this must work
  correctly even when `values is out`, the aliasing pattern
  `mpl_normalize.py:204-207`'s `ImageNormalize.__call__` uses:
  `self.stretch(values, out=values, clip=False)`), raising `TypeError`
  if `out` is not a floating-point array (mirroring the existing check
  in `BaseInterval.__call__` at `interval.py:115-118`). When `clip` is
  true, clips the *domain* to `[0, 1]` **before** returning — i.e.
  before the stretch's own math runs on it, not just on the output;
  `test_clip_invalid` (`test_stretch.py:111-118`) pins this exactly:
  `SqrtStretch()([-1, 0, 0.5, 1, 1.5])` (default `clip=True`) returns
  `[0.0, 0.0, 0.707…, 1.0, 1.0]` — the `-1` is clipped to `0` *before*
  `sqrt`, not after (`sqrt(-1)` would be `nan`).

- **`astropy/visualization/stretch.py::CompositeStretch.__call__(self, values, clip=True, out=None)`**
  — applies `self.transform_1` then `self.transform_2` in sequence,
  threading `clip` and `out` through both calls
  (`self.transform_2(self.transform_1(values, clip=clip, out=out), clip=clip, out=out)`).
  `BaseStretch.__add__` (`self + other`) builds `CompositeStretch(other,
  self)`, so `transform_1` is the right-hand operand and runs first — the
  `test_stretch.py` fixture `LinearStretch(intercept=0.5) +
  LinearStretch(slope=0.5)` confirms this ordering (see S5). `transform_1`
  is not always a `BaseStretch`: `docs/visualization/normalization.rst`'s
  `SqrtStretch() + PercentileInterval(90.)` example builds
  `CompositeStretch(PercentileInterval(90.), SqrtStretch())`, so
  `transform_1` there is a `BaseInterval`. `BaseInterval.__call__` and
  `BaseStretch.__call__` share the same `(values, clip=True, out=None)`
  shape, so `CompositeStretch.__call__` must call both transforms with
  only `clip`/`out` — never assume a `transform_1`-specific keyword like
  `invalid` exists. **Decision:** `CompositeStretch` does not accept or
  forward an `invalid` keyword and does not override
  `_supports_invalid_kw` (it stays `False`, inherited from `BaseStretch`
  via `CompositeTransform`/`BaseTransform`, neither of which defines
  it). No oracle (test, doctest, or docs example) exercises `invalid`
  with a composite stretch. Consequently, `ImageNormalize(stretch=<a
  composite>, ...)` takes the `else` branch at `mpl_normalize.py:206-207`
  and never passes `invalid` through, so out-of-range values produce
  `NaN` from a composite even where the same non-composite stretch,
  called with `invalid=...`, would substitute a finite value (S17 pins
  this explicitly).

- **`astropy/visualization/interval.py::BaseInterval._process_values(values)`**
  — turns arbitrary array-like/possibly-masked input into a 1-D array of
  finite, unmasked values, **preserving the input's dtype** (no forced
  float cast): split data/mask via `astropy.utils.masked.get_data_and_mask`,
  flatten, drop masked entries, drop non-finite entries (`np.isfinite`
  is `False` for both `NaN` and `Inf`). Dtype preservation is pinned by
  `docs/visualization/normalization.rst`: `MinMaxInterval().get_limits([1,
  3, 4, 5, 6])` returns `(np.int64(1), np.int64(6))`, not
  `np.float64(1.0)`. **Unmasked-mask handling:** `get_data_and_mask` on
  an `np.ma.MaskedArray`/`Masked` instance that has *no* masked entries
  returns a mask that may be `None`, `np.ma.nomask` (a 0-d/scalar
  `False`), or a full-size all-`False` boolean array depending on input
  type — treat `None` and any mask that does not have the same size as
  the flattened data as "nothing is masked" (skip the drop step, or
  broadcast before indexing) rather than boolean-indexing the flattened
  data with a scalar/mismatched-size mask, which raises `IndexError`
  (S16 pins this).

- **`astropy/visualization/interval.py::ZScaleInterval.get_limits(self, values)`**
  — implements the IRAF zscale algorithm per the class's existing
  docstring (`interval.py:267-320`): preprocess `values` via
  `self._process_values`; if fewer than `self.n_samples` points remain,
  use all of them, otherwise take an evenly-strided **deterministic**
  sample of `self.n_samples` points (not a random sample —
  `test_zscale` seeds only `np.random.seed(42)` for generating the
  *input data*, not for a sampler, and asserts results with `atol=0.1`;
  a deterministic evenly-strided sample matches the documented IRAF
  algorithm and makes that tolerance meaningful); sort the sample; fit a
  line to sorted-value-vs-index with iterative sigma rejection
  (`self.krej` sigma, up to `self.max_iterations` iterations, stopping
  early once fewer than `self.min_npixels` points remain or a rejection
  iteration removes no additional points); if the sampled data has fewer
  than `self.min_npixels` points, or more than `self.max_reject *
  len(sample)` points were rejected during fitting, or the fit's slope
  is non-positive/degenerate, fall back to returning `(sample.min(),
  sample.max())`; otherwise derive `z1`/`z2` from the fitted median,
  slope, and `self.contrast` per the standard zscale formula (`z1 =
  median - (npoints/2 - 1) * slope/contrast`, `z2 = median + (npoints -
  npoints/2 - 1) * slope/contrast`), clipped to the sampled data's own
  min/max. Must reproduce the values already asserted in `test_zscale`
  and `test_zscale_npoints`.

- **`astropy/visualization/lupton_rgb.py`: restore the missing
  `_stretch_prepare` binding** — add back the import that
  `LuptonAsinhStretch.__call__` (`lupton_rgb.py:450`) needs, e.g.
  `from astropy.visualization.stretch import _prepare as _stretch_prepare`,
  in the blank lines between the existing imports at `lupton_rgb.py:14`
  and `:17`. This is the **only** change in scope inside `lupton_rgb.py`
  — no algorithm, class, or public behavior in that file changes.

- **`astropy/visualization/basic_rgb.py::RGBImageMapping.__init__(self, interval=ManualInterval(vmin=0, vmax=None), stretch=LinearStretch())`**
  — stores the shared stretch on `self.stretch`. Normalizes `interval`
  to a 3-element list on `self.intervals` (attribute name is
  load-bearing, see Context): if `interval` has no `len()`, reuse the
  same single instance for all three entries (`self.intervals =
  [interval] * 3`); if it does have a `len()`, require `len(interval) ==
  3` and use it directly (element-wise, not copied), else raise
  `ValueError`. No error-message wording for this `ValueError` is
  recoverable from this checkout (the constructor body is entirely
  blank), so use the wording of the closest working precedent in the
  same codebase — `lupton_rgb.py:739`'s equivalent check on `minimum`
  raises `ValueError("please provide 1 or 3 values for minimum.")` — and
  raise `ValueError("please provide 1 or 3 values for interval.")`; S20
  asserts this substring.

- **`astropy/visualization/basic_rgb.py::RGBImageMapping.apply_mappings(self, image_r, image_g, image_b)`**
  — the per-channel mapping hook that `make_rgb_image` must call
  polymorphically (not inline the logic in `make_rgb_image`), because
  `RGBImageMappingLupton` overrides this method and relies on
  `make_rgb_image` dispatching to it. Default (base-class) behavior, for
  each of the three `(image, interval)` pairs zipped from
  `(image_r, image_g, image_b)` and `self.intervals`: normalize+clip the
  channel to `[0, 1]` via `interval(image, clip=True)` (per
  `BaseInterval.__call__`, this always allocates a new array via
  `np.subtract` when no `out` is given, so the source `image` array is
  never mutated), then apply `self.stretch(..., clip=True)`. Returns the
  three mapped, same-shape channel arrays (list or stacked array; must
  be consumable by `np.dstack`).

- **`astropy/visualization/basic_rgb.py::RGBImageMapping.make_rgb_image(self, image_r, image_g, image_b, output_dtype=np.uint8)`**
  — validates `output_dtype in _OUTPUT_IMAGE_FORMATS` (the module
  already defines `_OUTPUT_IMAGE_FORMATS = [float, np.float64,
  np.uint8]` at `basic_rgb.py:13`), else `ValueError`; validates
  `image_r.shape == image_g.shape == image_b.shape` (`np.asarray` each
  first so plain lists/int arrays are accepted), else `ValueError` whose
  message contains the substring `"shapes must match"` (required —
  `test_lupton_rgb.py::test_different_shapes_asserts` calls
  `make_lupton_rgb` with mismatched shapes and asserts
  `pytest.raises(ValueError, match=r"shapes must match")`, and that call
  reaches this inherited method unmodified through
  `RGBImageMappingLupton`); calls `self.apply_mappings(image_r, image_g,
  image_b)` to get three `[0, 1]`-normalized channel arrays; `np.dstack`s
  them into an `(N, M, 3)` array; converts to `output_dtype`:
  - `float`/`np.float64`: cast the stacked `[0, 1]` array to that dtype,
    values unchanged (NaN, if present in the input, propagates to NaN
    in the output at that pixel — only the interval's *limit
    computation* filters NaN via `_process_values`, not the per-pixel
    transform).
  - `np.uint8`: scale to the full `uint8` range and **truncate** —
    `(stacked * 255).astype(np.uint8)` — under `np.errstate(invalid="ignore")`
    so a NaN pixel does not raise/warn (mirrors the existing precedent
    in `lupton_rgb.py:184-198`, which wraps its own `.astype(np.uint8)`
    the same way; `pyproject.toml` turns warnings into errors, so an
    unguarded cast of NaN would fail the test suite). Truncation (not
    rounding) is the committed rule — matches the sibling converter's
    `c * pixmax / …` then `.astype(np.uint8)` behavior in
    `lupton_rgb.py:198`, which truncates: a normalized `0.5` must convert
    to `127`, not `128`.

### Data Flow

1. Caller constructs `RGBImageMapping(interval=..., stretch=...)`
   (directly, via `make_rgb()` in the same module, or via
   `RGBImageMappingLupton`/`make_lupton_rgb()` in `lupton_rgb.py`).
2. Caller calls `make_rgb_image(image_r, image_g, image_b,
   output_dtype=...)`.
3. `make_rgb_image` validates `output_dtype` and shapes, then delegates
   the per-channel transform to `self.apply_mappings(...)` — the
   polymorphic seam Lupton overrides.
4. `apply_mappings` (base version) uses `self.intervals[i]` to normalize
   +clip each channel to `[0, 1]`, then applies `self.stretch` to each.
5. `make_rgb_image` stacks the three `[0, 1]` channels into `(N, M, 3)`
   and converts to the requested `output_dtype`.

### Interface Contract

```python
# astropy/visualization/stretch.py
def _prepare(values, clip=True, out=None): ...  # -> ndarray (float, writable)

class CompositeStretch(CompositeTransform, BaseStretch):
    def __call__(self, values, clip=True, out=None): ...  # -> ndarray
    # no `invalid` kwarg; _supports_invalid_kw stays False (inherited)

# astropy/visualization/interval.py
class BaseInterval(BaseTransform):
    @staticmethod
    def _process_values(values): ...  # -> 1-D ndarray, finite, unmasked, dtype preserved

class ZScaleInterval(BaseInterval):
    def get_limits(self, values): ...  # -> (vmin: float, vmax: float)

# astropy/visualization/lupton_rgb.py  (one-line import fix only)
from astropy.visualization.stretch import _prepare as _stretch_prepare

# astropy/visualization/basic_rgb.py
class RGBImageMapping:
    def __init__(self, interval=ManualInterval(vmin=0, vmax=None), stretch=LinearStretch()):
        # self.intervals: list[BaseInterval] of length 3
        # self.stretch: BaseStretch
        # raises ValueError("please provide 1 or 3 values for interval.")
        #   if interval is array-like with len() != 3
        ...

    def apply_mappings(self, image_r, image_g, image_b): ...
        # -> sequence of 3 ndarrays, each shape == image_r.shape, values in [0, 1]

    def make_rgb_image(self, image_r, image_g, image_b, output_dtype=np.uint8): ...
        # -> ndarray, shape (N, M, 3), dtype == output_dtype
        # raises ValueError if output_dtype not in _OUTPUT_IMAGE_FORMATS
        # raises ValueError (message contains "shapes must match") on shape mismatch
```

No public name, signature, or default value changes from what is already
written in `basic_rgb.py`, `interval.py`, and `stretch.py`; the only
change to `lupton_rgb.py` is restoring the single stripped import
binding above.

## Alternatives Considered

### Inline the per-channel loop directly in `make_rgb_image`

Simpler to write, but breaks `RGBImageMappingLupton`, which overrides
`apply_mappings` and relies on `make_rgb_image` calling it
polymorphically. Rejected — this is a hard constraint from existing,
unmodifiable code.

### Random sampling in `ZScaleInterval.get_limits` (mirroring `AsymmetricPercentileInterval`)

`AsymmetricPercentileInterval` uses `np.random.choice` for its optional
sampling. Rejected for `ZScaleInterval` specifically: `test_zscale`
seeds only `np.random.seed(42)` for generating the *input data*, not for
the sampler, and asserts results with `atol=0.1`. A random sampler
reseeded implicitly by that same call would be coupled to sampling
implementation details not fixed by the test; a deterministic
evenly-strided sample makes the test's tolerance meaningful and matches
the documented IRAF zscale algorithm, which samples evenly, not
randomly.

### Round instead of truncate for uint8 quantization

No available oracle pins this directly for `basic_rgb.py`, but the
sibling converter in the same feature family (`lupton_rgb.py:179-198`)
truncates via `.astype(np.uint8)` after scaling, and rounding would
silently diverge from that established codebase convention. Rejected in
favor of truncation, made explicit and tested (S9) rather than left
implicit.

### Forward `invalid` through `CompositeStretch`

Would make composite stretches behave more like their single-stretch
components under `ImageNormalize`'s `invalid=` option. Rejected for this
restoration: no test, doctest, or documentation example in the repo
exercises `invalid` on a composite stretch, so adding support would be
unverifiable scope beyond what any oracle requires, and the simpler
"inherit `False`" behavior is a smaller, more conservative surface to
restore correctly.

## Acceptance Scenarios

### Happy Path

- **S1:** Given `RGBImageMapping()` (all defaults) and
  `image_r = image_g = image_b = np.array([[0.0, 5.0], [10.0, 2.5]])`,
  when `make_rgb_image(image_r, image_g, image_b, output_dtype=np.uint8)`
  is called, then the result has shape `(2, 2, 3)`, dtype `np.uint8`, and
  every channel's plane equals `[[0, 127], [255, 63]]` exactly (default
  `ManualInterval(vmin=0, vmax=None)` computes `vmax=10` from the data,
  normalizes to `[0, 0.5, 1.0, 0.25]`, default `LinearStretch()` is
  identity, and `*255` truncated gives `0, 127, 255, 63`).
- **S2:** Given `RGBImageMapping(interval=ManualInterval(vmin=0,
  vmax=100))` (a single interval instance) constructed once, then
  `self.intervals` is a list of length 3 and all three entries are the
  *same* object (`is` identity) as the constructor argument.
- **S3:** Given `RGBImageMapping(interval=[ManualInterval(vmin=0, vmax=10), ManualInterval(vmin=0, vmax=100), ManualInterval(vmin=0, vmax=1000)])`
  and three `2×2` channels that are each a **constant array equal to
  `5.0`** (the same value in all three channels), when
  `make_rgb_image(..., output_dtype=float)` is called, then the red
  plane equals `0.5` everywhere, the green plane equals `0.05`
  everywhere, and the blue plane equals `0.005` everywhere (within float
  tolerance) — three distinct values from one shared input value, which
  can only happen if each channel used its own interval; an
  implementation that shared a single interval across all three channels
  would produce the same value in all three planes and fail this
  scenario.
- **S4:** Given `RGBImageMapping(interval=ManualInterval(vmin=0, vmax=4),
  stretch=LinearStretch())` and
  `image_r = image_g = image_b = np.array([[0.0, 1.0, 2.0], [3.0, 4.0, 4.0]])`,
  when `make_rgb_image(..., output_dtype=float)` and
  `make_rgb_image(..., output_dtype=np.float64)` are each called, then
  both results equal `np.dstack([[[0, 0.25, 0.5], [0.75, 1.0, 1.0]]] * 3)`
  exactly (within float tolerance) and both have `dtype` matching the
  requested `output_dtype`.
- **S5:** Given `RGBImageMapping(interval=ManualInterval(vmin=0, vmax=1), stretch=LinearStretch(intercept=0.5) + LinearStretch(slope=0.5))`
  (a `CompositeStretch` built via `+`, the exact fixture used in
  `test_stretch.py`'s `RESULTS`) and
  `image_r = image_g = image_b = np.array([[0.0, 0.25, 0.5, 0.75, 1.0]])`,
  when `make_rgb_image(..., output_dtype=float)` is called, then every
  channel equals `[[0.5, 0.625, 0.75, 0.875, 1.0]]` — `LinearStretch(slope=0.5)`
  applied first, then `LinearStretch(intercept=0.5)`, matching
  `test_stretch.py`'s `RESULTS[LinearStretch(intercept=0.5) +
  LinearStretch(slope=0.5)]` reproduced through the RGB path.
- **S6:** Given a channel built as
  `np.random.default_rng(0).normal(10, 5, size=(50, 50))` (same array
  reused for R, G, B), when `make_rgb_image(..., output_dtype=float)` is
  called once with `RGBImageMapping(interval=ZScaleInterval())` and once
  with `RGBImageMapping(interval=MinMaxInterval())`, then both results
  are fully finite (`np.isfinite(result).all()`) and the two results are
  **not** equal (`not np.allclose(rgb_zscale, rgb_minmax)`) — for
  normally-distributed data `ZScaleInterval` clips a substantial
  fraction of pixels while `MinMaxInterval` clips none, so the two must
  differ; this demonstrates `ZScaleInterval` actually integrates through
  `apply_mappings` rather than being silently ignored (exact
  `ZScaleInterval` numeric behavior is pinned separately by S18's
  regression oracle).
- **S7:** Given `interval=ManualInterval(vmin=0, vmax=1)`,
  `stretch=LinearStretch()`, and matching-shape channels, when
  `make_rgb(image_r, image_g, image_b, interval=interval,
  stretch=stretch, output_dtype=float)` (the module's only public name,
  `basic_rgb.py:15`) is called, then it returns an array equal to
  `RGBImageMapping(interval=interval, stretch=stretch).make_rgb_image(image_r, image_g, image_b, output_dtype=float)`.
- **S8:** Given `HAS_MATPLOTLIB` is true (skip otherwise, mirroring
  `test_lupton_rgb.py::test_make_rgb`'s guard), when
  `make_rgb(image_r, image_g, image_b, filename=str(tmp_path / "out.png"))`
  is called, then `tmp_path / "out.png"` exists after the call and can be
  read back as a valid image (e.g. via `matplotlib.image.imread`).

### Edge Cases

- **S9:** Given normalized channel value `0.5` exactly (e.g.
  `ManualInterval(vmin=0, vmax=2)` on input `1.0`) and
  `output_dtype=np.uint8`, when `make_rgb_image` is called, then the
  output pixel is `127`, not `128` — pins truncation over rounding.
- **S10:** Given all three input channels are constant arrays with value
  `c = 5` (so, with the default `ManualInterval(vmin=0, vmax=None)`,
  `vmax` is computed as `5` from the data and `vmin=0`, so `vmin !=
  vmax`), when `make_rgb_image` is called with `output_dtype=float` and
  separately with `output_dtype=np.uint8`, then every pixel is `1.0` and
  `255` respectively.
- **S11:** Given all three input channels are constant arrays with value
  `c = 0` (so `vmin == vmax == 0`, the zero-range case
  `BaseInterval.__call__`'s `if (vmax - vmin) != 0:` guard at
  `interval.py:121` exists for), when `make_rgb_image` is called with
  `output_dtype=float` and separately with `output_dtype=np.uint8`, then
  it does not raise `ZeroDivisionError` and every pixel is `0.0` and `0`
  respectively.
- **S12:** Given a channel array containing one `NaN` pixel among
  otherwise-finite values and `RGBImageMapping()` (default
  `ManualInterval(vmin=0, vmax=None)`, so `vmax` is derived from the
  channel's own finite data via `_process_values`, ignoring the `NaN`),
  when `make_rgb_image(..., output_dtype=float)` is called, then it does
  not raise, the non-`NaN` output pixels equal the values obtained from
  computing `vmax` over the finite data only, and the output pixel at
  the `NaN` input position is `NaN`. When the same call is made with
  `output_dtype=np.uint8` instead, then it does not raise and does not
  emit a warning (the cast runs under `np.errstate(invalid="ignore")`
  per the `lupton_rgb.py:184-198` precedent); the numeric uint8 value at
  the `NaN` pixel is not asserted.
- **S13:** Given three `np.uint8`-dtype channels (e.g.
  `np.array([[0, 64], [128, 255]], dtype=np.uint8)` for each of R, G, B)
  and `RGBImageMapping()` (default interval derives `vmin=0, vmax=255`
  from the data), when `make_rgb_image(..., output_dtype=float)` is
  called, then the result equals
  `np.dstack([[[0.0, 64/255], [128/255, 1.0]]] * 3)` within float
  tolerance — proving integer input is promoted to exact fractional
  values, not integer-truncated.
- **S14:** Given a call to `make_rgb_image`, when it returns, then the
  original `image_r`/`image_g`/`image_b` arrays passed in are
  bit-for-bit unchanged (assert equality against a pre-call copy) —
  covers "input channel arrays are not modified."
- **S15:** Given `image_r`, `image_g`, `image_b` are passed as plain
  Python nested lists (not `ndarray`) of matching shape, when
  `make_rgb_image` is called, then it succeeds and returns an `ndarray`
  of the requested `output_dtype`.
- **S16:** Given `MinMaxInterval()` and an **unmasked**
  `np.ma.MaskedArray` input, e.g. `np.ma.array([1, 3, 4, 5, 6])` (no
  element actually masked — `get_data_and_mask` may return a scalar
  `np.ma.nomask` for this case rather than a full boolean array), when
  `get_limits(...)` is called, then it returns `(1, 6)` and does not
  raise `IndexError`.
- **S17:** Given `SqrtStretch()([-1.0], clip=False, invalid=-99.0)`
  returns `[-99.0]` (the non-composite baseline — `SqrtStretch`
  supports `invalid`), when the same normalized value `-1.0` instead
  flows through `ImageNormalize(stretch=SqrtStretch() + LinearStretch(),
  vmin=0, vmax=1, clip=False, invalid=-99.0)` on an input that maps to
  `-1.0` pre-stretch, then the result at that pixel is `NaN`, not
  `-99.0` — pins that `CompositeStretch` does not forward `invalid`
  (§Alternatives Considered).
- **S18 (regression oracle):** `astropy/visualization/tests/test_interval.py`,
  `astropy/visualization/tests/test_stretch.py`,
  `astropy/visualization/tests/test_norm.py`, and
  `astropy/visualization/scripts/tests/test_fits2bitmap.py`, run as-is,
  pass in full. Between them these already assert: `_prepare`'s
  clip-before-stretch behavior (`test_clip_invalid`); `out`-array
  in-place semantics including `out is values` self-aliasing
  (`test_inplace`, `test_inplace_roundtrip`, and
  `ImageNormalize.__call__`'s `self.stretch(values, out=values, ...)`
  pattern exercised by `test_norm.py` and, end-to-end through
  `simple_norm`/`imsave`, by `test_fits2bitmap.py::test_orientation`);
  `_process_values`'s mask-dropping (`TestIntervalMaskedArray`,
  `TestIntervalMaskedNDArray`) and NaN-**and**-Inf-dropping
  (`test_zscale`'s `list(range(1000)) + [np.nan]` case, and
  `test_norm.py::test_invalid_data`'s array with both `np.nan` and
  `np.inf`, asserting `(vmin, vmax) == (1.65, 22.35)` for
  `PercentileInterval(85.)`); and `ZScaleInterval.get_limits`'s numeric
  output and fallback branch (`test_zscale`, `test_zscale_npoints`).
- **S19 (regression oracle):** the doctests in
  `docs/visualization/normalization.rst` pass under pytest's
  `--doctest-rst` (configured in `pyproject.toml`). These pin, among
  other things, `_process_values` preserving input dtype
  (`MinMaxInterval().get_limits([1, 3, 4, 5, 6]) ==
  (np.int64(1), np.int64(6))`) and `CompositeStretch` working when
  `transform_1` is a `BaseInterval` rather than a `BaseStretch`
  (`SqrtStretch() + PercentileInterval(90.)`).

### Error Scenarios

- **S20:** Given `RGBImageMapping(interval=[ManualInterval(), ManualInterval()])`
  (array-like of length 2), when constructed, then `ValueError` is
  raised with a message containing the substring `"1 or 3 values"` (see
  Key Components for the exact committed wording).
- **S21:** Given `RGBImageMapping()` and three matching-shape channels,
  when `make_rgb_image(..., output_dtype=np.int16)` (not in
  `_OUTPUT_IMAGE_FORMATS`) is called, then `ValueError` is raised.
- **S22:** Given `RGBImageMapping()` and `image_r.shape != image_g.shape`
  (e.g. `(10, 5)` vs `(5, 10)`), when `make_rgb_image` is called, then
  `ValueError` is raised with a message containing `"shapes must match"`.
- **S23 (regression oracle):** `astropy/visualization/tests/test_lupton_rgb.py`,
  run as-is, passes in full — this requires the `_stretch_prepare`
  import fix (see Key Components) as a prerequisite, since every test
  that constructs a `LuptonAsinhStretch`/`LuptonAsinhZscaleStretch` or
  calls `make_lupton_rgb` currently raises `NameError` before reaching
  any assertion. Includes `test_different_shapes_asserts`
  (`pytest.raises(ValueError, match=r"shapes must match")` via
  `make_lupton_rgb` → inherited `RGBImageMapping.make_rgb_image`) and
  `test_incorrect_input_compute_intensity_asserts`.
- **S24:** Given `LuptonAsinhStretch(stretch=5, Q=8)([0.0, 0.5, 1.0],
  clip=False)` (the smallest reproduction of the `_stretch_prepare`
  gap), when called, then it returns three finite float values and does
  not raise `NameError`.
- **S25:** Given `SqrtStretch()` and an integer input array
  `np.array([0, 1, 4], dtype=np.int64)`, when called with `clip=False`,
  then it returns a floating-point array equal to `[0.0, 1.0, 2.0]`
  without raising (an implementation of `_prepare` that copies `values`
  without casting to a float dtype makes `np.sqrt(values, out=values)`
  raise a numpy casting error on an integer array) — pins that `_prepare`
  always returns a float-capable array regardless of input dtype.
- **S26:** Given `LinearStretch()` and `out = np.zeros(5, dtype=int)`,
  when called as `LinearStretch()(np.array([0.0, 0.25, 0.5, 0.75, 1.0]),
  out=out)`, then `TypeError` is raised (mirroring
  `BaseInterval.__call__`'s identical check for non-floating-point
  `out`) — pins that `_prepare` validates `out`'s dtype rather than
  silently truncating into it.

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*. A green suite that passes for
> the wrong reason does not satisfy this contract — `/verify` will hunt for
> vacuous tests by asking, of each behavior, "what is the smallest change
> that breaks this, and would any test catch it?"

Start by running `astropy/visualization/tests/test_interval.py`,
`astropy/visualization/tests/test_stretch.py`,
`astropy/visualization/tests/test_norm.py`,
`astropy/visualization/scripts/tests/test_fits2bitmap.py`, and
`astropy/visualization/tests/test_lupton_rgb.py`, plus
`pytest --doctest-rst docs/visualization/normalization.rst`, to see the
current failures — they are regression oracles (S18, S19, S23), not just
references, and they pin exact numeric, dtype, and string-matching
behavior for `_prepare`, `_process_values`, `ZScaleInterval.get_limits`,
`CompositeStretch`, and the shape-mismatch error message. Do not change
their assertions to make them pass; make the implementation match them.
`test_lupton_rgb.py` and `test_fits2bitmap.py` will keep failing with
`NameError`/errors until the one-line `_stretch_prepare` import is
restored in `lupton_rgb.py` (see Key Components) — that fix is in scope
even though the rest of that file is untouched.

New tests should go in a new
`astropy/visualization/tests/test_rgb_mapping.py` (not
`test_basic_rgb.py` — that filename is reserved for the held-out oracle
test that will be dropped into this checkout after restoration; creating
a file at that path would collide with it) covering S1–S17 and S20–S22
(the `RGBImageMapping`/`make_rgb` scenarios) plus S24–S26 (the
`stretch.py`-level scenarios — they don't touch the RGB path, but the
same file is the natural home for every new test this restoration adds).
Implement however you work best — blueprint does not
prescribe order, cadence, or commit structure. Only the result is
checked. Write tests to the project's conventions (this codebase uses
plain `pytest` functions/classes and
`numpy.testing.assert_allclose`/`assert_equal`, see the existing test
files above for style) and to these principles (the same ones `/verify`
scores against — see `references/test-desiderata.md` and
`references/anti-patterns.md`):

- **Behavioral over structural** — assert observable output/effects
  (shapes, dtypes, exact pixel values, raised exceptions, source-array
  identity/equality), not internals; the suite must survive refactoring
  `apply_mappings`'s internal implementation as long as the polymorphic
  seam and `self.intervals`/`self.stretch` attribute names stay intact
  (those are pinned by `lupton_rgb.py`, not optional).
- **Every test can fail** — no copy-pasted expected values, no asserting
  a constant, no tautologies (AP-2, AP-4). Prefer exact expected arrays
  (as in S1, S4, S5, S9, S13) over loose bounds checks, and prefer inputs
  where a plausible-but-wrong implementation (e.g. a shared interval
  instead of per-channel ones, as in S3) produces a different, wrong
  answer rather than coincidentally the same answer.
- **Deterministic, isolated, readable** — seed any RNG used to build test
  fixtures (e.g. `np.random.default_rng(0)`), no cross-test state, AAA
  structure with inline setup.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] Test suite is green, including the pre-existing
      `test_interval.py`, `test_stretch.py`, `test_norm.py`,
      `test_fits2bitmap.py`, and `test_lupton_rgb.py` (S18, S23) with no
      assertions altered, and the `normalization.rst` doctests (S19).
- [ ] Every acceptance scenario (S1–S26) maps to at least one test.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
      the smallest break of its behavior (thought-mutation), e.g.
      swapping `self.intervals[i]` for a single shared interval, calling
      the per-channel logic inline instead of through `apply_mappings`,
      or rounding instead of truncating in the uint8 conversion, must
      break at least one test.
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
      first); no AP-1…AP-8 violations.
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings) — the class docstring in `basic_rgb.py` and the
      docstrings in `interval.py`/`stretch.py` remain accurate to the
      finished implementation.

## Trade-offs and Limitations

- `ZScaleInterval.get_limits`'s iterative-rejection fit (line-fitting
  method, exact rejection bookkeeping) is specified at the level of the
  standard IRAF zscale algorithm and the two existing tests (`test_zscale`,
  `test_zscale_npoints`); those tests use `atol=0.1`, so minor
  differences in fitting method (e.g. unweighted vs. iteratively
  reweighted linear fit) that stay within that tolerance are acceptable.
- The exact numeric uint8 value produced for a `NaN` input pixel (S12)
  is left unspecified — only "does not raise/warn" is required — because
  no available oracle pins it and `np.errstate(invalid="ignore")` makes
  the cast's NaN-to-uint8 result implementation/platform-dependent.
- `CompositeStretch` does not support the `invalid` keyword (S17,
  §Alternatives Considered); this is a scope decision made against the
  absence of any oracle requiring it, not a technical limitation — it
  could be added later if a concrete use case needs it.
- The exact wording of `RGBImageMapping.__init__`'s `ValueError` for a
  wrong-length `interval` is not recoverable from this checkout (the
  constructor body is entirely blank); S20 asserts only the substring
  `"1 or 3 values"`, matching the committed wording's shared
  sub-string with the `lupton_rgb.py:739` precedent it was modeled on.

## Open Questions

- [ ] None — all scope was resolved against the surviving docstrings,
      `docs/visualization/rgb.rst` and `docs/visualization/normalization.rst`,
      the existing test suites (including `test_norm.py`,
      `test_fits2bitmap.py`, and the `normalization.rst` doctests), and
      the working `lupton_rgb.py`/`mpl_normalize.py` call sites
      (including the stripped `_stretch_prepare` binding) during spec
      authoring. The one behavior-change question raised during review
      (whether `CompositeStretch` should forward `invalid`) was resolved
      against the absence of any supporting oracle — see §Alternatives
      Considered and §Trade-offs and Limitations.

## References

- `astropy/visualization/basic_rgb.py` — class docstring for
  `RGBImageMapping`, `make_rgb()` and its docstring.
- `astropy/visualization/lupton_rgb.py` — `RGBImageMappingLupton`,
  `make_lupton_rgb`, `compute_intensity`, `LuptonAsinhStretch` (working
  code that pins base class attribute/method names and needs the
  `_stretch_prepare` import restored).
- `astropy/visualization/mpl_normalize.py` — `ImageNormalize.__call__`
  (pins `_prepare`'s `out=values` self-aliasing behavior and the
  `_supports_invalid_kw` branch).
- `astropy/visualization/interval.py` — `BaseInterval`, `ManualInterval`,
  `ZScaleInterval` (docstring at line 267).
- `astropy/visualization/stretch.py` — `BaseStretch`, `LinearStretch`,
  `CompositeStretch`.
- `astropy/visualization/tests/test_interval.py`,
  `astropy/visualization/tests/test_stretch.py`,
  `astropy/visualization/tests/test_norm.py`,
  `astropy/visualization/scripts/tests/test_fits2bitmap.py`,
  `astropy/visualization/tests/test_lupton_rgb.py` — regression oracles.
- `docs/visualization/rgb.rst`, `docs/visualization/normalization.rst` —
  user-facing usage examples and doctest oracles.

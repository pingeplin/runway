# Implementation brief: restore `RGBImageMapping` and its dependency chain

## Context

Repo root for this task is the current working directory (there is no
`/testbed` in this checkout — despite what the task template says, work
directly in `astropy/` under the cwd). The target class `RGBImageMapping`
lives in `astropy/visualization/basic_rgb.py`. Its `__init__` and
`make_rgb_image` bodies are currently **completely empty** (only the
docstring remains, lines 18–156 of that file contain nothing but blank
lines after the class docstring).

`RGBImageMapping` does not stand alone. Two of its direct dependencies —
`astropy/visualization/interval.py` and `astropy/visualization/stretch.py`
— also have missing pieces that `RGBImageMapping` (and, transitively, most
of the stretch/interval test suite) requires to run at all. You must
restore all of them together or `make_rgb_image` will raise
`AttributeError`/`NameError` the moment it touches an interval or stretch.
Concretely, five gaps need to be filled, across four files:

1. `astropy/visualization/basic_rgb.py` — `RGBImageMapping.__init__`,
   `RGBImageMapping.make_rgb_image`, and a per-channel mapping helper.
2. `astropy/visualization/interval.py` — `BaseInterval._process_values`
   (called but never defined) and `ZScaleInterval.get_limits` (missing
   entirely).
3. `astropy/visualization/stretch.py` — module-level `_prepare()` helper
   (called by ~15 `__call__` implementations but never defined) and
   `CompositeStretch.__call__` (needs an override; the inherited one from
   `CompositeTransform` doesn't support `out`).
4. `astropy/visualization/lupton_rgb.py` — a one-line import fix (a
   missing `_prepare` import under a local alias) that, once restored,
   unlocks an existing, complete test file
   (`test_lupton_rgb.py`) as a real regression suite for the
   `RGBImageMapping` base class. Details in section 4 below.

Existing tests you can and should run to validate your work (do not edit
these files — they already exist and are complete):
- `astropy/visualization/tests/test_interval.py`
- `astropy/visualization/tests/test_stretch.py`
- `astropy/visualization/tests/test_lupton_rgb.py`

There is no `test_basic_rgb.py` in the repo — the grading harness supplies
its own hidden test for `RGBImageMapping`. Match the interface contract
below exactly; do not rename methods/attributes it relies on.

A sibling class, `RGBImageMappingLupton` in
`astropy/visualization/lupton_rgb.py` (line 532), **already subclasses**
`RGBImageMapping` and gives you a hard behavioral contract for the base
class's public surface — read it before writing code:

```python
class RGBImageMappingLupton(RGBImageMapping):
    def __init__(self, interval=ManualInterval(vmin=0, vmax=None),
                 stretch=LuptonAsinhStretch(stretch=5, Q=8)):
        super().__init__(interval=interval, stretch=stretch)
        self._pixmax = 1.0
    ...
    def apply_mappings(self, image_r, image_g, image_b):
        ...
        for i, img in enumerate(image_rgb):
            vmin, _ = self.intervals[i].get_limits(img)   # <- self.intervals (list of 3)
            ...
        Int = self.intensity(*image_rgb)
        fI = self.stretch(Int, clip=False)                # <- self.stretch (callable)
        ...
        return np.asarray(image_rgb)                      # shape (3, ...), values in [0,1]-ish
```

This tells you, unambiguously:
- `RGBImageMapping.__init__` must accept `interval=` and `stretch=` keyword
  args and store them as `self.intervals` (a **list of exactly 3**
  interval objects) and `self.stretch` (a single stretch object, shared).
- The base class must define a method named `apply_mappings(self, image_r,
  image_g, image_b)` that `make_rgb_image` calls internally — subclasses
  override just this one method to swap in different combination logic
  while reusing `__init__` and `make_rgb_image` unchanged. `apply_mappings`
  returns the three normalized-to-[0,1] channel images as
  `np.asarray([...])` of shape `(3, N, M)`, matching Lupton's override
  exactly (see section 1 below for the exact contract).

## 1. `astropy/visualization/basic_rgb.py`

File currently imports (already present, do not change):
```python
from astropy.visualization.interval import ManualInterval
from astropy.visualization.stretch import LinearStretch
_OUTPUT_IMAGE_FORMATS = [float, np.float64, np.uint8]
```

### `RGBImageMapping.__init__(self, interval=ManualInterval(vmin=0, vmax=None), stretch=LinearStretch())`

- Store `stretch` as `self.stretch`.
- Normalize `interval` into `self.intervals`, a list of exactly 3 entries:
  - If `interval` is a single `BaseInterval` instance (no `len()`), expand
    it to `[interval, interval, interval]` — reuse the **same object** in
    all three slots (matches the docstring: "the same interval object is
    reused in all three entries"). Use a `try: len(interval) / except
    TypeError:` guard (same idiom already used in
    `lupton_rgb.Mapping.__init__` for its `minimum` parameter — see line
    ~78 of `lupton_rgb.py`) rather than `isinstance` checks, since
    `BaseInterval` instances are not `Sized`.
  - If `interval` is array-like, it must contain **exactly 3** elements;
    otherwise raise `ValueError` (message should mention needing 1 or 3
    intervals — follow the same phrasing style as
    `lupton_rgb.Mapping.__init__`'s `"please provide 1 or 3 values for
    minimum."`).
  - Store the (possibly expanded) 3-element list as `self.intervals`.

### `apply_mappings(self, image_r, image_g, image_b)` (new helper method, not in the interface spec by name but required by the contract above)

For each of the 3 channel arrays, in order `[image_r, image_g, image_b]`:
- Apply `self.intervals[i](channel, clip=True)` — this is `BaseInterval.__call__`
  (already implemented at `interval.py:77`), which derives the channel's
  own limits via `get_limits`, normalizes to `[0, 1]`, and clips. Called
  with `out=None` (the default), it returns a **new** array, so the
  caller's input channel is never mutated — this satisfies "Input channel
  arrays are not modified."
- Apply `self.stretch(normalized_channel, clip=True)` — the same shared
  stretch instance for all 3 channels.
- Return `np.asarray([result_r, result_g, result_b])`, shape `(3, N, M)`.
  Match `RGBImageMappingLupton.apply_mappings`'s return convention exactly
  (it returns `np.asarray(image_rgb)`) so that `make_rgb_image`'s dtype
  conversion step (below) works identically regardless of which
  `apply_mappings` override produced the data — don't return a plain
  Python list from the base version and an ndarray from the override.

### `make_rgb_image(self, image_r, image_g, image_b, output_dtype=np.uint8)`

1. Validate `output_dtype in _OUTPUT_IMAGE_FORMATS` (the module-level list
   already defined: `[float, np.float64, np.uint8]`); raise `ValueError`
   naming the allowed formats if not.
2. Convert inputs with `np.asarray` and check
   `image_r.shape == image_g.shape == image_b.shape`; raise `ValueError`
   with a message naming all three shapes if they differ (follow the style
   already used in `lupton_rgb.Mapping.make_rgb_image`: `"The image shapes
   must match. r: {}, g: {} b: {}"`).
3. Call `image_rgb = self.apply_mappings(image_r, image_g, image_b)` to
   get the `(3, N, M)` array of normalized `[0, 1]` channel images.
4. Convert to `output_dtype`:
   - `float` / `np.float64`: `image_rgb.astype(output_dtype)`, values stay
     in `[0, 1]`.
   - `np.uint8`: scale by `np.iinfo(np.uint8).max` (255) then cast —
     `(image_rgb * np.iinfo(np.uint8).max).astype(np.uint8)` — truncating,
     not rounding (this matches the existing sibling implementation
     `Mapping.map_intensity_to_uint8`/`_convert_images_to_uint8` in
     `lupton_rgb.py`, which also just clips then `.astype(np.uint8)`
     without rounding). This is the "scales and quantizes" step
     ("Conversion to uint8 scales and quantizes the normalized values").
5. `np.dstack` the result into an `NxMx3` array and return it —
   `np.dstack(image_rgb)` works directly on the `(3, N, M)` array from
   step 3/4 (dstack iterates a 3D array along its first axis).

Do not touch `make_rgb()` at the bottom of the file (lines 156–216) — it
already correctly delegates to `RGBImageMapping` and needs no changes.

## 2. `astropy/visualization/interval.py`

### `BaseInterval._process_values(self, values)` — currently completely
missing, but called from `ManualInterval.get_limits` (line 154),
`MinMaxInterval.get_limits` (line 167), `AsymmetricPercentileInterval.get_limits`
(line 201), and `SymmetricInterval.get_limits` (line 259). Add it to
`BaseInterval` (there is dead blank space for it between the abstract
`get_limits` method, ending line 52, and `__call__`, starting line 77).

Required behavior ("returns flattened finite, unmasked data" per spec),
and must satisfy `astropy/visualization/tests/test_interval.py`'s
`TestIntervalMaskedArray`/`TestIntervalMaskedNDArray`/`TestInterval2D`/
`TestIntervalList` subclasses (same `TestInterval` cases run against
`np.ma.MaskedArray`, `astropy.utils.masked.Masked`, 2D arrays, and plain
Python lists):

```python
def _process_values(self, values):
    data, mask = get_data_and_mask(values)   # already imported at top of file
    data = np.ravel(np.asarray(data))
    if mask is not None:
        data = data[~np.ravel(mask)]
    return data[np.isfinite(data)]
```
(`get_data_and_mask` is already imported at the top of `interval.py` from
`astropy.utils.masked` — it returns `(data, None)` for plain arrays/lists
and `(unmasked_data, mask)` for `MaskedArray`/`Masked` inputs.

**Order matters**: call `get_data_and_mask` on the *raw* input, before any
`np.asarray`/`np.ravel`. `np.asarray(masked_array)` silently drops the
mask (returns the base-class `.data` with no `mask` attribute), so if you
convert to a plain ndarray first, `get_data_and_mask` will see a plain
array and return `mask=None`, and the masked-out sentinel values (e.g.
`1e6` in `TestIntervalMaskedArray`) will leak into the result. Verify:
`python -c "import numpy as np; m=np.ma.MaskedArray([1,2,3],mask=[0,1,0]); print(hasattr(np.asarray(m),'mask'))"`
prints `False`. Get the data/mask apart first, *then* ravel/asarray.)

### `ZScaleInterval.get_limits(self, values)` — the whole method is
missing (the class body ends right after `__init__`, line ~319, with
nothing else). This is IRAF's zscale algorithm (the class docstring
already cites the reference implementation at
`stsci.numdisplay/zscale.py`). Implement the standard algorithm:

1. `values = self._process_values(values)`.
2. If `values.size < self.min_npixels`, return
   `(np.min(values), np.max(values))` directly (fallback — this is
   covered by `test_zscale_npoints` in `test_interval.py`, which
   constructs `ZScaleInterval(min_npixels=5)` over only 4 pixels and
   expects `vmin == 0, vmax == 3` for `data = np.arange(4).reshape((2,2))`).
3. Stride-sample the **unsorted** flattened data (not the sorted data —
   sampling after sorting biases the sample toward one end of the range):
   `stride = int(max(1, values.size / self.n_samples))`,
   `sample = values[::stride][: self.n_samples]`, then sort `sample` in
   place (`sample.sort()` / `np.sort`). Let `npix = len(sample)`.
4. Iterative sigma-clipped linear fit of `sample` value vs. rank index
   `x = np.arange(npix)`, for up to `self.max_iterations` iterations:
   - Start with a "good" mask of all `True` (no points rejected).
   - Each iteration, fit a line to the currently-good points:
     `coeffs = np.polyfit(x[good], sample[good], deg=1)` (or an
     equivalent weighted fit over the full `x`/`sample` with a 0/1 weight
     array for rejected points — either is fine as long as rejected
     points don't influence the fit).
   - Compute residuals `sample - (coeffs[0] * x + coeffs[1])` over all
     `npix` points, and their standard deviation over the currently-good
     residuals.
   - Reject points with `abs(residual) > self.krej * std`.
   - **Dilate** the newly-rejected mask by `ngrow = max(1, int(npix *
     0.01))` pixels on each side before combining it into `good` (e.g.
     via `np.convolve(bad_mask.astype(int), np.ones(ngrow), mode="same")
     > 0`) — this growing step is part of the standard zscale algorithm
     and is easy to accidentally skip; skipping it changes the final
     slope enough to miss the `atol=0.1` tolerance in `test_zscale`.
   - Track `ngoodpix = good.sum()`. Stop iterating early once `ngoodpix`
     stops decreasing (converged), or once `ngoodpix` drops below
     `minpix = max(self.min_npixels, int(npix * self.max_reject))`.
   - Keep the fitted slope (`coeffs[0]`) as `zslope`.
5. If the final `ngoodpix < minpix` (fit never converged to enough good
   pixels), fall back to the min/max of the **sample** (not the full
   original `values` array) — this is the "falling back to the sampled
   data limits when the fit is not usable" behavior called out in the
   task spec: `return sample.min(), sample.max()`.
6. Otherwise:
   - If `self.contrast > 0`, divide `zslope` by `self.contrast`.
   - `median = np.median(sample)`, `center_pixel = (npix - 1) // 2`.
   - `vmin = max(sample.min(), median - (center_pixel - 1) * zslope)`.
   - `vmax = min(sample.max(), median + (npix - center_pixel) * zslope)`.
7. Return `(vmin, vmax)` as plain floats.

This is the standard IRAF zscale algorithm (as cited in the class
docstring). The specific numeric choices above (unsorted stride-sampling
before sorting, `polyfit`-style line fit, `ngrow` mask dilation via
convolution, the early-stop condition, and the `center_pixel` formula for
the final `vmin`/`vmax`) all affect the final answer at the level of
precision `test_zscale` checks (`atol=0.1`) — don't substitute a
simplified sigma-clip that skips the dilation step.

Validate directly against the existing tests in
`astropy/visualization/tests/test_interval.py::test_zscale` and
`::test_zscale_npoints` — they are not hidden, run them:
```
pytest astropy/visualization/tests/test_interval.py -k zscale -v
```
`test_zscale` checks three cases (Gaussian random data, `range(1000) +
[nan]`, and `range(100)`) with `atol=0.1`, so your fit routine's numeric
details must match the standard algorithm closely, not just the general
shape.

## 3. `astropy/visualization/stretch.py`

### Module-level `_prepare(values, clip=True, out=None)` — called by
essentially every concrete stretch's `__call__` (e.g. `LinearStretch` at
line 147, `SqrtStretch` at line 230, and a dozen more through line 960)
but never defined. There is dead blank space for it between the `_logn`
helper (ends line 34) and `class BaseStretch` (line 55) — put it there,
as a module-level function (not a method), matching how it's called:
`_prepare(values, clip=clip, out=out)`, unqualified.

Required behavior ("honors `clip` and `out`; without an output it returns
independent writable data"), confirmed by
`test_stretch.py::TestStretch::test_inplace` (writes into a separate
`out` array and asserts the original input `data_in` is untouched
afterward):

```python
def _prepare(values, clip=True, out=None):
    if clip:
        return np.clip(values, 0.0, 1.0, out=out)
    if out is None:
        return np.array(values, copy=True, dtype=float)
    out[:] = values
    return out
```

Callers rely on the returned array being safe to mutate in place (they
immediately do things like `np.multiply(values, self.slope, out=values)`
on the result), so it must never alias the caller's original input array
when `out` is not supplied.

### `CompositeStretch.__call__` — the class (line 976) currently has only
a docstring, no `__call__` override, so it falls back to
`CompositeTransform.__call__` (in `astropy/visualization/transform.py:36`),
which has signature `(self, values, clip=True)` — **no `out` parameter**.
Since `BaseStretch.__call__`'s contract includes `out`, and
`test_stretch.py` parametrizes `test_inplace`/`test_inplace_roundtrip`
over composite stretches too (e.g.
`LinearStretch(intercept=0.5) + LinearStretch(slope=0.5)` is in the
`RESULTS` dict tested by every parametrized test in that file), you must
add an explicit override:

```python
def __call__(self, values, clip=True, out=None):
    return self.transform_2(
        self.transform_1(values, clip=clip, out=out), clip=clip, out=out
    )
```

Do not touch `CompositeTransform.inverse` or `CompositeStretch`'s
inheritance from it — the existing `inverse` property (returns
`self.__class__(transform_2.inverse, transform_1.inverse)`) already works
correctly once `__call__` is fixed, since `self.__class__` resolves to
`CompositeStretch`.

## 4. `astropy/visualization/lupton_rgb.py` — one-line import fix

`LuptonAsinhStretch.__call__` (line ~450) calls
`_stretch_prepare(values, clip=clip, out=out)` — same call signature as
the `_prepare()` helper you're adding to `stretch.py` in step 3 above —
but `_stretch_prepare` is never imported or defined anywhere in
`lupton_rgb.py`. The current import at the top of the file is:

```python
from astropy.visualization.stretch import BaseStretch
```

This is almost certainly where `, _prepare as _stretch_prepare` was
stripped when `_prepare` was removed from `stretch.py`. Restore it:

```python
from astropy.visualization.stretch import BaseStretch, _prepare as _stretch_prepare
```

This is low-risk (one import line) and high-value: it unblocks
`astropy/visualization/tests/test_lupton_rgb.py`, an existing, complete
12KB test file that exercises `RGBImageMappingLupton` — a real subclass
of the `RGBImageMapping` base class you're restoring — through its
`make_rgb_image` (inherited unchanged from the base class),
`__init__` (also inherited unchanged), and dtype conversion. That's the
closest available proxy in this repo to the hidden `test_basic_rgb.py`
the grading harness will run, since `test_basic_rgb.py` itself doesn't
exist in this checkout. Treat `test_lupton_rgb.py` passing as a strong
signal that your `basic_rgb.py` changes are correct, not just your
`lupton_rgb.py` one-liner.

## Verification checklist

1. `pytest astropy/visualization/tests/test_interval.py -v` — all pass,
   especially the `zscale` tests and the masked/2D/list variants of
   `TestInterval`.
2. `pytest astropy/visualization/tests/test_stretch.py -v` — all pass,
   especially `test_inplace`, `test_inplace_roundtrip`, and the composite
   stretch (`LinearStretch(...) + LinearStretch(...)`) cases.
3. `pytest astropy/visualization/tests/test_lupton_rgb.py -v` — all pass
   (skip only the two tests that call `pytest.skip(...)` themselves:
   `test_make_rgb_saturated_fix` and `test_saturated`, both unrelated to
   this work). In particular `test_Asinh`, `test_AsinhZscale*`,
   `test_linear`, `test_make_rgb`, and `test_different_shapes_asserts`
   (checks the `ValueError` "shapes must match" message from your
   `make_rgb_image` shape check) all drive the base `RGBImageMapping`
   code you're restoring end-to-end.
4. Manually exercise the restored `RGBImageMapping`, e.g.:
   ```python
   import numpy as np
   from astropy.visualization.basic_rgb import RGBImageMapping
   from astropy.visualization.interval import ManualInterval, ZScaleInterval
   from astropy.visualization.stretch import LinearStretch

   r = np.random.rand(10, 10) * 100
   g = np.random.rand(10, 10) * 100
   b = np.random.rand(10, 10) * 100

   m = RGBImageMapping()  # defaults
   img = m.make_rgb_image(r, g, b)
   assert img.shape == (10, 10, 3) and img.dtype == np.uint8

   img_f = m.make_rgb_image(r, g, b, output_dtype=float)
   assert img_f.dtype == float and img_f.min() >= 0 and img_f.max() <= 1

   m3 = RGBImageMapping(interval=[ZScaleInterval(), ManualInterval(0, 50), ZScaleInterval()])
   m3.make_rgb_image(r, g, b)

   try:
       RGBImageMapping(interval=[ManualInterval()] * 2)
       assert False, "should have raised"
   except ValueError:
       pass

   try:
       m.make_rgb_image(r, g, b[:5])
       assert False, "should have raised"
   except ValueError:
       pass
   ```

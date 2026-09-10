# 2609.0001 Uncertainty Distribution Interfaces

**Date:** 2026-09-10
**Status:** draft
**Author:** EP Lin

## Context

`astropy.uncertainty` (package root: `astropy/uncertainty/`) implements a
Monte-Carlo style representation of a value-with-uncertainty: a
`Distribution` whose array holds many samples of the quantity being
represented, stored along a trailing "sample" axis. `Distribution` is a
mixin combined with a concrete array class — `np.ndarray` (via
`ArrayDistribution` → `NdarrayDistribution`) or `np.void` (via
`ScalarDistribution`) — and, through a dynamic-subclass mechanism, with
arbitrary `numpy.ndarray` subclasses such as `astropy.units.Quantity`
(`QuantityDistribution`) or `astropy.coordinates.Angle`. Instances behave
like ordinary NumPy-compatible arrays under `numpy` ufuncs and array
functions, except that the *logical* shape excludes the trailing sample
axis, which every operation must thread through correctly.

In the working copy, `astropy/uncertainty/core.py` and
`astropy/uncertainty/function_helpers.py` have had several
methods/functions removed *entirely* — `def` line, docstring, and body all
replaced with blank lines — while every other method/function in the same
files was left untouched. (The Interface Contract below shows short,
one-line pseudo-docstrings for the missing members; those are this spec's
own shorthand for what each member does, not the literal text to restore —
recover the real signatures and docstrings from the pre-crop source, per
the next paragraph, rather than pasting the contract's shorthand in as the
implementation.) This repository's own git history still has the
pre-crop version at `HEAD` (`git show HEAD:astropy/uncertainty/core.py`,
`git show HEAD:astropy/uncertainty/function_helpers.py`), which this spec
uses as ground truth. Every factual claim below — exact exception types
and message substrings, which branch a given `view()` call takes, memory
sharing, gufunc behavior — was verified in this environment by temporarily
restoring the pre-crop files, stubbing `astropy.stats` (its compiled
`_stats` extension isn't built in this sandbox; the stub only provides a
no-op `histogram` and has no bearing on the behavior specified here), and
exercising the result with `python -c` snippets against NumPy 2.5, then
restoring the cropped working-tree files exactly (confirmed byte-identical
via `diff`) before continuing. Where this document and a **named,
line-numbered existing test or an explicitly reproduced `python -c`
verification** might seem to disagree, treat that as a bug in this spec to
flag during implementation, not as license to reinterpret an Acceptance
Scenario or the Definition of Done — those two sections are the normative
contract; prose elsewhere in this document exists only to explain *why*.

Concretely, the following are currently missing their implementation (diff
of working tree against `HEAD`):

In `astropy/uncertainty/core.py`:
- `Distribution.__new__(cls, samples)`
- `Distribution._get_distribution_cls(cls, samples_cls)` (classmethod)
- `Distribution._get_distribution_dtype(cls, dtype, n_samples, itemsize=None)` (classmethod)
- `Distribution.__array_ufunc__(self, ufunc, method, *inputs, **kwargs)`
- `Distribution.__array_function__(self, function, types, args, kwargs)`
- `Distribution._result_as_distribution(self, result, out, ncore_out=None, axis=None)`
- `Distribution.n_samples` (property)
- `Distribution.pdf_std(self, dtype=None, out=None, ddof=0)`
- `Distribution.pdf_median(self, out=None)`
- `ArrayDistribution.view(self, dtype=None, type=None)`
- `ArrayDistribution.distribution` (property)

In `astropy/uncertainty/function_helpers.py` (registered via the intact
`@function_helper` decorator into `FUNCTION_HELPERS`, unless noted):
- `is_distribution(x)` (plain helper, not registered)
- `get_n_samples(*arrays)` (plain helper, not registered)
- `empty_like(prototype, dtype=None, *args, **kwargs)`
- `broadcast_arrays(*args, subok=False)`
- `concatenate(arrays, axis=0, out=None, dtype=None, casting="same_kind")`

Everything else in both files is intact and **must not be modified**,
including: `ScalarDistribution`, `_DistributionRepr`, `NdarrayDistribution`,
`ArrayDistribution.__getitem__`/`__setitem__`, `Distribution.dtype`
getter/setter, `Distribution.astype`, `Distribution.pdf_mean`/`pdf_var`/
`pdf_mad`/`pdf_smad`/`pdf_percentiles`/`pdf_histogram`,
`Distribution.__eq__`/`__ne__`/`_not_implemented_or_raise`, the
`FunctionAssigner` plumbing, `DISPATCHED_FUNCTIONS`/`UNSUPPORTED_FUNCTIONS`
(declared and exported for documentation purposes but **not consulted** by
`__array_function__`, which only ever checks `FUNCTION_HELPERS` — confirmed
by grep of the pre-crop source), and the `__all__` construction at the
bottom of `function_helpers.py` — which computes `__all__` from
`helper.__doc__` (i.e. from the restored docstrings), so restoring a
helper without its real upstream docstring silently shrinks
`function_helpers.__all__`; check it matches `git show
HEAD:astropy/uncertainty/function_helpers.py`'s `__all__` as part of
Definition of Done. Several of these intact call sites depend on exact
names/signatures of the missing pieces (see Interface Contract), so those
names and signatures are fixed by the surrounding code, not free design
choices.

The package's two pre-existing test modules,
`astropy/uncertainty/tests/test_distribution.py` and
`astropy/uncertainty/tests/test_functions.py`, are untouched and already
exercise a majority of the missing behavior end-to-end (`test_distribution.py`
imports `Angle` from `astropy.coordinates` at module scope, but nothing
deeper into coordinates). A third test module,
`astropy/uncertainty/tests/test_containers.py` (which tests `Distribution`
interoperating with `SkyCoord` and representation/differential classes),
has been deleted from the working tree. **Restoring `test_containers.py`
is out of scope for this spec.** This is a deliberate scope call, not an
oversight: see Trade-offs and Limitations for exactly what coverage gap it
leaves and why the residual risk is acceptable. The implementing agent
should treat `test_distribution.py` and `test_functions.py` as the
authoritative, must-pass regression suite, and should assume a test
environment where `astropy.stats`'s compiled extension and `scipy` are
both available (unlike this spec-writing sandbox) — see Definition of
Done.

## Motivation

Without these implementations, `Distribution` cannot be constructed,
cannot participate in NumPy ufunc/array-function dispatch, and its two
core summary statistics (`pdf_median`, `pdf_std`) are missing. Every
existing test in `test_distribution.py` and `test_functions.py` that
constructs a `Distribution`, calls a NumPy function on one, or calls
`pdf_median`/`pdf_std`/`pdf_mad`/`pdf_smad` (which call `pdf_median`
internally) will fail or error. Restoring these pieces exactly as designed
is required for the module to be usable at all, and for downstream code
(`astropy.units.Quantity`, and — outside this spec's test scope —
`astropy.coordinates`) that passes `Distribution`/`QuantityDistribution`
objects through its own `__array_function__`/`__array_ufunc__` machinery
to keep working.

## Proposed Solution

### Overview

Restore the missing method/function bodies so that: (1) `Distribution(...)`
constructs the correct concrete subclass from any array-like whose
trailing axis is the sample axis, sharing storage with a view whenever the
sample-axis layout permits it; (2) NumPy ufuncs and a curated set of NumPy
array functions dispatch through `__array_ufunc__`/`__array_function__` to
operate on the underlying "unwrapped" sample arrays and re-wrap array
results as `Distribution`; and (3) `pdf_median`/`pdf_std` reduce over the
trailing sample axis using `numpy.median`/`numpy.std`. This is a
restoration of a specific, already-designed implementation, not a free
redesign.

### Key Components

**Storage.** A `Distribution`'s underlying `ndarray`/`void` storage uses a
structured dtype built by `_get_distribution_dtype(dtype, n_samples,
itemsize=None)`:

```
sample_dtype = np.dtype({"names": ["sample"], "formats": [dtype],
                          "itemsize": itemsize or dtype.itemsize})
result_dtype = np.dtype([("samples", sample_dtype, (n_samples,))])
```

unless the incoming `dtype` already has `dtype.names == ("samples",)`, in
which case it is returned unchanged (this early-return has no named
in-scope caller — see Trade-offs). `itemsize`, when given larger than
`dtype.itemsize`, represents a per-sample byte stride larger than one
element — needed when samples are non-contiguous (e.g. a field selected
out of a structured array; see S27). This exact construction is what the
intact `Distribution.dtype` getter (`super().dtype["samples"].base["sample"]`),
`Distribution.n_samples` (`super().dtype["samples"].shape[0]`), and the
base `Distribution.distribution` fallback (`self["samples"]["sample"]`,
used only by `ScalarDistribution`) all depend on.

**Why the structured dtype matters for dispatch.** Because the sample axis
lives inside the per-element dtype rather than as a real trailing ndarray
axis, plain shape/identity NumPy functions that never inspect dtype
contents (`numpy.broadcast_to`, `numpy.reshape`, `numpy.transpose`, ...)
work correctly on a `Distribution` with zero `Distribution`-specific code
— NumPy's own default `__array_function__` handling, reached through the
pass-through branch described below, is sufficient (S28 exercises this).
Numeric ufunc operations, by contrast, go through `.distribution` (via
`__array_ufunc__`), which returns a genuine `ndarray`/subclass with a real
trailing sample axis, so ordinary NumPy broadcasting rules apply,
including a length-1 sample axis broadcasting against a longer one.

**Subclass registry** (`Distribution._get_distribution_cls`). Maps a
concrete samples class (e.g. `np.ndarray`, `Quantity`, `Angle`) to a
generated `Distribution` subclass, memoized in the class attribute
`Distribution._generated_subclasses` (a plain `dict`, declared at
`core.py:57` and pre-seeded for `np.ndarray` → `NdarrayDistribution` at
the bottom of the module, both intact). If `samples_cls` is already a
`Distribution` subclass, it is returned as-is. Otherwise,
`samples_cls.__mro__` is walked to find the first already-registered
entry; an unregistered, non-matching class falls back to
`NdarrayDistribution`. Newly generated classes are built as
`type(name, (_DistributionRepr, samples_cls) + base_cls.__mro__[2:],
{"_samples_cls": samples_cls})` so `_DistributionRepr` (repr/str/
`_repr_latex_`, intact) stays the first base. The MRO-walk mechanism
itself is exercised in-scope: registering `Quantity` (any
`QuantityDistribution` construction, S2) and registering `Angle` (S24)
both walk the MRO to `np.ndarray`'s entry. What is **not** exercised
in-scope is a *subclass of an already-registered non-ndarray class*
reusing that class's entry — e.g. `astropy.coordinates.Longitude` (a
subclass of `Angle`) generating its own `Distribution` subclass derived
from `Angle`'s registered entry — which only `test_containers.py` (out of
scope) covers; see Trade-offs.

**Sample-wise ufunc dispatch** (`Distribution.__array_ufunc__`). Unwraps
`Distribution` inputs to their `.distribution` arrays. Any other input
with a non-empty `.shape` gets a trailing axis of length 1 appended so it
broadcasts against samples (a true scalar with no `.shape` passes through
unchanged) — this is how `d - d.pdf_median()` (S7) and a `Distribution`
with `n_samples=1` broadcasting against one with more samples both work.
`out=` is forwarded by unwrapping any `Distribution` output to its
`.distribution`; **a non-`Distribution` `out` is not supported** — the
shared `_result_as_distribution` helper (see below) asserts `isinstance(out,
Distribution)`, so passing a plain `ndarray` as `out` raises a bare
`AssertionError` (verified: `numpy.add(d1, d2, out=plain_ndarray)` raises
`AssertionError` with no message; this is an existing upstream limitation,
not a designed error path, and disappears entirely if tests are run with
Python's `-O` flag — do not build a test that depends on `-O` being off).
For reductions/accumulations (`method in {"reduce", "accumulate",
"reduceat"}`) with no explicit `axis` keyword (`kwargs.get("axis")` is
`None`, which also covers an explicit `axis=None`), the operation is
forced over every *logical* axis of the first (`Distribution`) input:
`kwargs["axis"] = tuple(range(inputs[0].ndim))`, where `inputs[0].ndim` is
the `Distribution`'s own pre-unwrap `ndim` (sample axis excluded) — the
sample axis, being outside that range, is left untouched (S8). For
generalized ufuncs (`ufunc.signature` is set — e.g. `numpy.vecdot`, whose
signature is `"(n),(n)->()"`), core dimensions are parsed with the private
`_parse_gufunc_signature` (imported at the top of `core.py`, intact) and
each input's sample axis is moved from its trailing position to just
before that input's core dimensions before the real ufunc is called, then
moved back into the result (S9). The `axes` keyword is explicitly
unsupported for gufunc calls and raises `NotImplementedError` with message
`"Distribution does not yet support gufunc calls with 'axes'."` (verified
via `numpy.matmul(d, d, axes=[(-2, -1), (-2, -1), (-2, -1)])`; S20). Note
that some real NumPy gufuncs are **not** supported and are explicitly out
of scope: `numpy.linalg.det` and other `numpy.linalg.*` wrapper functions
dispatch through `__array_function__` and call their underlying gufunc
directly on the *structured* storage rather than through
`__array_ufunc__`, so they fail with a dtype-casting `TypeError` (verified:
`numpy.linalg.det(d)` raises `numpy.exceptions._UFuncNoLoopError`/
`TypeError`-family "Cannot cast ufunc 'det' input..."); `numpy.matmul`'s
public signature contains optional (`?`) core dimensions that
`_parse_gufunc_signature` cannot parse and raises a plain `ValueError`
before ever reaching the sample-axis logic. `numpy.vecdot` is the
verified, in-scope example of a working generalized ufunc call.

**Array-function dispatch** (`Distribution.__array_function__`). Exactly
two branches:
1. `function in FUNCTION_HELPERS` — look up the helper, call `args,
   kwargs, out = function_helper(*args, **kwargs)` (catching
   `NotImplementedError` raised by the helper and converting it via the
   intact `self._not_implemented_or_raise(function, types)`), then call
   `super().__array_function__(function, types, args, kwargs)`. If the
   helper returned `out is True`, return that call's result as-is,
   **skipping** the result-rewrapping step (used by `broadcast_arrays`,
   whose result is already correctly typed); otherwise continue to
   result-rewrapping below.
2. `function not in FUNCTION_HELPERS` — the **pass-through branch**:
   return `super().__array_function__(function, types, args, kwargs)`
   directly, with the *original*, un-transformed `args`/`kwargs`. This
   relies entirely on the structured-dtype trick described above and
   needs no `Distribution`-specific code of its own — it is what makes
   `numpy.broadcast_to(d, shape, subok=True)` work with no
   `FUNCTION_HELPERS` entry (verified against
   `test_functions.py::TestBroadcast::test_broadcast_to`, S28).

In both branches, a `result is NotImplemented` from the inner call is
returned as-is (lets another type's dispatch protocol take over).

**Result rewrapping** (`Distribution._result_as_distribution(self, result,
out, ncore_out=None, axis=None)`). Shared by both `__array_ufunc__` and
`__array_function__`. A `tuple`/`list` result is rewrapped element-wise,
preserving the container type via `getattr(result, "_make", result.__class__)`
(this branch exists for `numpy.linalg` functions that return named tuples
— since `numpy.linalg.*` is explicitly out of scope here, per the ufunc
section above, this branch has **no verified in-scope trigger**; it is
required for correctness of the restored code but is exempt from
Definition of Done's scenario-coverage requirement — see Trade-offs). A
shaped, non-`Distribution` array result becomes `Distribution(result)`
(after moving the gufunc core-dimension axis back into place, when
`ncore_out`/`axis` are given); a scalar (no `.shape` attribute, or an
empty `.shape`) or already-`Distribution` result is returned unchanged; a
supplied `out` is asserted to be a `Distribution` (see the `AssertionError`
note above) and returned as-is.

**View support.** `ArrayDistribution.view(dtype=None, type=None)` always
returns a `Distribution` subclass, computed in two steps.

*Step A — argument normalization (always applied, never returns on its
own):*

| # | Condition | Normalization |
|---|---|---|
| A1 | `type is None` and `dtype` is itself an `ndarray` subclass (a `builtins.type` — `core.py` imports the `builtins` module specifically so this isn't shadowed by the `type` parameter) | treat as `type=dtype`, `dtype=None` |
| A2 | (after A1) `type` is now set, whether from the caller or from A1 | replace it with `_get_distribution_cls(type)`, generating/deriving a subclass if not already registered |

A1/A2 run unconditionally before Step B; they only rewrite `dtype`/`type`,
they never raise or return. This is what lets `distr.view(np.dtype("2i8"),
distr.__class__)` still reach Step B's `ValueError` below (`type` was
already set, so only A2 applies) and what lets `ad.view(qd.dtype,
qd.__class__)` reach Step B's branch 4 with a real `type` in hand.

*Step B — dtype dispatch (first match wins, each row returns):*

| # | Condition | Result |
|---|---|---|
| 1 | `dtype is None` | `super().view(type=type)` |
| 2 | `np.dtype(dtype) == self.dtype` (no real dtype change) | `super().view(type=type)` |
| 3 | `dtype.names == ("samples",)` (caller passes the structured dtype explicitly) | `super().view(dtype, type)` — raw pass-through |
| 4 | `dtype.shape == ()` (a plain scalar dtype, not a sub-array dtype like `"2f8"`) and `dtype.itemsize == self.dtype.itemsize` | rebuild the structured `"samples"` dtype around `dtype` via `_get_distribution_dtype(dtype, self.n_samples, itemsize=super().dtype["samples"].base.itemsize)`, then `super().view(new_dtype, type)` — same-size scalar reinterpretation, e.g. `float64` ↔ `int64` |
| 5 | `dtype.itemsize == self.dtype.itemsize` (element itemsize match — covers sub-array dtypes like `"2f8"`/`"4u1"` whose *total* itemsize equals the current element's) | `distr = self.distribution; distr_view = distr.view(dtype, samples_cls); Distribution(np.moveaxis(distr_view, distr.ndim - 1, -1))` |
| 6 | `dtype.itemsize == super().dtype["samples"].base.itemsize` (the current per-sample byte stride; only differs from row 5 when samples are non-contiguous, e.g. a selected structured field) | `distr = np.moveaxis(self.distribution, -1, -2); Distribution(distr.view(dtype, samples_cls).squeeze(-1))` |
| 7 | none of the above | `raise ValueError` containing the substring `"can only be viewed"` |

Both S10 (`complex128` → `"2f8"`) and S11 (`uint32` → `"4u1"`) take Step B
row **5**, not row 6 — for an ordinary, contiguous `Distribution` the
per-sample stride always equals the element itemsize, so row 6 is only
reachable when they differ (non-contiguous samples), which none of this
spec's in-scope scenarios exercise (this is a narrower, honestly-stated
version of the same gap noted for tuple/list result rewrapping). The
`ValueError` message body in the pre-crop source is
`f"{self.__class__} can only be viewed with a dtype with " "itemsize
{self.strides[-1]} or {self.dtype.itemsize}"` — note only the first half
is an f-string; the second half's `{...}` are **not** substituted, a
pre-existing upstream cosmetic bug that must be reproduced verbatim, not
fixed (S16 and existing tests only assert the `"can only be viewed"`
substring). Separately, Step B row 5/6's inner `distr.view(dtype,
samples_cls)` call can itself raise NumPy's own `ValueError` (message
containing `"last axis must be contiguous"`) when the logical last axis
of `.distribution` is itself non-contiguous (e.g. after `.T`); this is
NumPy's error, not something this implementation constructs, and needs no
special handling beyond letting the call raise it naturally (S17).
`.distribution` builds its result from `super().view(np.ndarray)` — going
through `super()`, **not** `self[...]`, because `ArrayDistribution.__getitem__`'s
`item == "samples"` branch (intact, `core.py:592-601`) delegates back into
`.distribution`, so implementing `.distribution` via
`self["samples"]["sample"]` would recurse — then indexes down to the
`"sample"` field, views that as `self._samples_cls`, and calls
`__array_finalize__(self)` on it so subclass metadata (e.g. `Quantity`
units) is restored.

**NumPy free functions** (`function_helpers.empty_like`,
`.broadcast_arrays`, `.concatenate`). `empty_like` rebuilds the structured
dtype for the (possibly overridden) element dtype at the prototype's
`n_samples` via `_get_distribution_dtype` and returns `(prototype, dtype)
+ args, kwargs, None`, so the plain-array `numpy.empty_like` result is
wrapped as `Distribution` by the normal result-rewrapping step (S12).
`broadcast_arrays` optionally strips `Distribution`-ness from inputs when
`subok=False` (view as plain `ndarray`, or `np.array(...)` for
non-array-likes) before delegating to `numpy.broadcast_arrays(...,
subok=True)` — the *structured* storage must broadcast with `subok=True`
regardless of the caller's `subok`, or the structured-dtype trick breaks;
the caller-visible `subok` only controls whether the *result* stays a
`Distribution` subclass (returns `args, {"subok": True}, True`, S13).
`concatenate` determines the common `n_samples` from the first
`Distribution` among `arrays` and `out` (`get_n_samples`, raising
`RuntimeError` if none is found at all — not reachable from
`__array_function__`, which only calls the helper when a `Distribution` is
already among the dispatching `types`), unwraps `Distribution` array
arguments to `.distribution`, and broadcasts ordinary shaped arrays to
`shape + (n_samples,)` via `np.broadcast_to(array[..., np.newaxis], ...,
subok=True)` (S14). A negative `axis` is shifted one further negative
(`axis - 1`) to account for the extra trailing sample axis — verified:
concatenating two `Distribution`s of logical shape `(3, 4)`/`(3, 2)` along
`axis=-1` gives logical shape `(3, 6)` (S25). An explicit `out` must be a
`Distribution` (its `.distribution` is passed through as the real `out`);
a non-`Distribution` `out` raises `NotImplementedError` from inside the
helper, which propagates through `Distribution.__array_function__` to
`_not_implemented_or_raise`, which — because a plain `numpy.ndarray` `out`
is among the dispatching `types` — raises `TypeError` (S21; verified
message in this environment: `"the Distribution implementation cannot
handle <built-in function concatenate> with the given arguments."` — the
`{function}` portion of this f-string is **not** guaranteed stable across
NumPy versions, since NumPy's array-function-dispatch decorator can wrap a
function as either a plain Python function or leave it as a C built-in
depending on the function and NumPy version; assert only the
version-independent substrings `"cannot handle"` and `"with the given
arguments"`, not the full text). Two `concatenate` inputs are explicitly
**out of scope** and left unspecified by this spec: NumPy's `axis=None`
flatten mode (the `axis - 1` shift has no defined meaning there), and two
`Distribution`s with *differing* `n_samples` (`get_n_samples` only reads
the first `Distribution` it finds, so a mismatch surfaces only as
whatever error the subsequent real `numpy.concatenate` call happens to
raise on the mismatched trailing axis — not a designed, asserted error).
Neither needs a scenario or a test under this spec.

### Data Flow

1. A user calls `Distribution(samples)` (or internal code returns a plain
   array that needs rewrapping). `__new__` normalizes `samples`:
   - If `samples` is already a `Distribution`, it is replaced by
     `samples.distribution` (S3).
   - Else if `samples` is not an `ndarray` at all (e.g. a Python scalar, a
     list, or a NumPy scalar such as `arr[0]` pulled by integer-indexing a
     1-D array — indexing yields a `numpy.generic`, not an `ndarray`), or
     it *is* an `ndarray` but its trailing-axis stride is smaller than its
     dtype's itemsize **and** its trailing axis is not length 1
     (`samples.strides[-1] < samples.dtype.itemsize and samples.shape[-1:]
     != (1,)`), it is copied via `np.asanyarray(samples, order="C")`. The
     length-1 carve-out matters because a length-1 trailing axis
     legitimately has `strides[-1] == 0` yet is perfectly safe to view
     (S18); a genuine negative trailing stride (e.g. `a[:, ::-1]`) fails
     this condition and is copied (S19).
   - If the (now-`ndarray`) result has `shape == ()`, raise
     `TypeError("Attempted to initialize a Distribution with a scalar")`.
     **This check only fires for inputs that reach it as an `ndarray`
     already, or that get converted to one by the `asanyarray` step
     above** (a Python float, or a NumPy scalar from integer indexing —
     this is what `test_init_scalar` actually exercises). A pre-existing
     **0-d `ndarray`** passed directly (e.g. `Distribution(np.array(1.0))`)
     is `isinstance(samples, np.ndarray)` already, so it skips the
     `asanyarray` copy and goes straight to the `samples.strides[-1]`
     check above — but a 0-d array's `.strides` is `()`, so that indexing
     raises `IndexError: tuple index out of range` instead of reaching the
     `TypeError` branch at all (verified). This is a pre-existing quirk of
     the ground-truth implementation, not something to "fix"; S15 is
     scoped to the two inputs that are actually attested to raise
     `TypeError` by the existing test.
   - Otherwise, `__new__` builds the structured "samples"/"sample" dtype
     via `_get_distribution_dtype`, reinterprets the trailing axis into
     that dtype (a plain `.view()` when the trailing axis is already
     contiguous at the element itemsize; `DummyArray`/`__array_interface__`
     stride tricks otherwise, e.g. for `parr_t.T`), and views the result
     as the subclass returned by `_get_distribution_cls(type(samples))`,
     finalizing (`__array_finalize__`) against the original `samples`
     object.
2. A NumPy ufunc or array function is invoked on one or more `Distribution`
   operands. NumPy's dispatch protocol calls `Distribution.__array_ufunc__`
   or `Distribution.__array_function__` — the two protocols are
   independent and a single public NumPy function can trigger only one of
   them (see the `numpy.linalg.det` vs `numpy.vecdot` contrast in Key
   Components).
3. The dispatch method unwraps `Distribution` operands to their
   `.distribution` arrays (ufunc path), or hands off to a
   `FUNCTION_HELPERS` entry that does the equivalent transformation plus
   any function-specific reshaping, or falls straight through on the
   untouched structured storage (array-function pass-through branch),
   calls the real NumPy ufunc/function, and passes the raw result through
   `_result_as_distribution` to rewrap it.
4. `pdf_median`/`pdf_std` read `self.distribution` and call
   `numpy.median`/`.std` with `axis=-1`.

### Interface Contract

```python
# astropy/uncertainty/core.py

class Distribution:
    _generated_subclasses: dict  # already declared; keyed by samples class

    def __new__(cls, samples):
        """
        Returns a Distribution subclass instance (NdarrayDistribution,
        QuantityDistribution, etc., chosen by type(samples)).
        Raises TypeError("Attempted to initialize a Distribution with a
        scalar") for a scalar input that is not already an ndarray (see
        Data Flow step 1 for the pre-existing IndexError quirk on a
        pre-built 0-d ndarray).
        If samples is already a Distribution, reconstructs from
        samples.distribution.
        Shares storage with `samples` via a view whenever the trailing
        axis has a positive stride >= itemsize, or is length 1 (stride
        may be 0); copies (np.asanyarray(samples, order="C")) otherwise,
        including for negative trailing strides.
        """

    @classmethod
    def _get_distribution_cls(cls, samples_cls): ...  # -> Distribution subclass

    @classmethod
    def _get_distribution_dtype(cls, dtype, n_samples, itemsize=None): ...
        # -> np.dtype([("samples",
        #      np.dtype({"names": ["sample"], "formats": [dtype],
        #                "itemsize": itemsize or dtype.itemsize}),
        #      (n_samples,))])
        # unless dtype.names == ("samples",) already, in which case dtype
        # is returned unchanged.

    @property
    def n_samples(self) -> int: ...  # super().dtype["samples"].shape[0]

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs): ...
    def __array_function__(self, function, types, args, kwargs): ...
    def _result_as_distribution(self, result, out, ncore_out=None, axis=None): ...

    def pdf_median(self, out=None):
        """numpy.median(self.distribution, axis=-1, out=out)"""

    def pdf_std(self, dtype=None, out=None, ddof=0):
        """self.distribution.std(axis=-1, dtype=dtype, out=out, ddof=ddof)"""


class ArrayDistribution(Distribution, np.ndarray):
    _samples_cls = np.ndarray

    @property
    def distribution(self): ...  # array of type self._samples_cls, trailing
        # sample axis, built from super().view(np.ndarray) (NOT self[...])

    def view(self, dtype=None, type=None): ...  # always returns a
        # Distribution subclass; see the branch table above; raises
        # ValueError containing "can only be viewed" for an incompatible
        # reinterpretation itemsize
```

```python
# astropy/uncertainty/function_helpers.py

def is_distribution(x) -> bool: ...
def get_n_samples(*arrays) -> int: ...  # RuntimeError if none found

@function_helper
def empty_like(prototype, dtype=None, *args, **kwargs): ...
    # -> ((prototype, dtype) + args, kwargs, None)

@function_helper
def broadcast_arrays(*args, subok=False): ...
    # -> (args, {"subok": True}, True)

@function_helper
def concatenate(arrays, axis=0, out=None, dtype=None, casting="same_kind"): ...
    # -> ((converted_arrays,), kwargs, out)
    # NotImplementedError if out is given and is not a Distribution
```

Fixed constraints inherited from intact code (violating these breaks call
sites that are out of scope to change):
- `Distribution.dtype` getter/setter (`core.py:186-195`, intact) call
  `self._get_distribution_dtype(dtype, self.n_samples,
  itemsize=super().dtype["samples"].base.itemsize)` — the classmethod
  signature `(cls, dtype, n_samples, itemsize=None)` must match exactly.
- `Distribution.astype` (intact) calls
  `self._get_distribution_dtype(dtype, self.n_samples)`.
- `ArrayDistribution.__getitem__`/`__setitem__` (intact, `core.py:592-635`)
  compare a string item against the literal `"samples"` and, on match,
  delegate to `self.distribution` — so `.distribution` must not itself be
  implemented via `self["samples"]["sample"]` (that path is only correct
  for the base `Distribution.distribution` fallback used by
  `ScalarDistribution`, which does not override `__getitem__`).
- `Distribution.pdf_mad` (intact) calls `np.abs(self - median)` where
  `median` is a plain (non-`Distribution`) array missing the sample axis,
  then reads `.distribution` off the result — `__array_ufunc__` must
  therefore correctly broadcast a `Distribution` against a plain shaped
  array missing the sample axis (S7).
- The bottom of `core.py` (intact) does
  `Distribution._generated_subclasses[np.ndarray] = NdarrayDistribution`
  after the class bodies — `_get_distribution_cls` must read from this
  same dict via `cls._generated_subclasses.get(...)`.

## Alternatives Considered

### Reimplement sample storage as a plain trailing ndarray axis (no structured dtype)

Simpler conceptually, but incompatible with intact code
(`Distribution.dtype`, `ArrayDistribution.__getitem__`/`__setitem__`,
`ScalarDistribution` via `np.void`) that already assumes the
`"samples"`/`"sample"` structured-dtype layout, and would break the
zero-cost pass-through for shape-only NumPy functions described in Key
Components. Rejected: would require rewriting code declared out of scope.

### Always copy on construction instead of viewing when possible

Simpler, avoids the `DummyArray`/`__array_interface__` stride-trickery
branch entirely. Rejected: existing tests assert shared storage directly
(the `np.may_share_memory` assertions in
`test_distr_view_different_dtype1`/`2` and
`TestStructuredDistribution::test_getitem`), and the intact `Distribution`
**class** docstring (`core.py:48-53` — `__new__` itself has no docstring
in the cropped working tree) explicitly promises "the data will not be
copied unless it is not possible to take a view (generally, only when the
strides of the last axis are negative)" — the parenthetical directly
backs S19's negative-stride copy behavior.

## Acceptance Scenarios

### Happy Path
- **S1:** Given a 2D `numpy.ndarray` `a` of shape `(3, 10)`, when
  `Distribution(a)` is constructed, then the result is an instance of
  `NdarrayDistribution` and `Distribution`, has `.shape == (3,)`,
  `.n_samples == 10`, and `.distribution` elementwise equal to `a`. *(No
  existing named test asserts all of this together —
  `test_distribution.py::TestInit::test_numpy_init` calls `Distribution(self.parr)`
  with no assertions at all, and `TestDistributionStatistics::test_shape`/
  `test_n_samples` operate on a `Quantity`-backed distribution. Add a
  direct test with these exact assertions.)*
- **S2:** Given a `Quantity` `q = a << u.ct` with `a` as in S1, when
  `Distribution(q)` is constructed, then the result is an instance of
  `Distribution` and `Quantity`, `.value` is itself a `Distribution`, and
  `.value.distribution` is elementwise equal to `a`. *(Covered by
  `test_distribution.py::TestInit::test_quantity_init`.)*
- **S3:** Given `d = Distribution(a)` from S1, when `Distribution(d)` is
  constructed, then the result's `.distribution` is elementwise equal to
  `d.distribution` and the result is again an instance of
  `NdarrayDistribution`. *(Not covered by an existing named test —
  verified empirically here; add a direct test.)*
- **S4:** Given `d = Distribution(a)` with normally-distributed samples,
  when `d.pdf_median()` is called, then the result equals
  `numpy.median(a, axis=-1)` and has shape `(3,)`; when called with
  `out=arr` where `arr = numpy.zeros(3)`, then the return value `is arr`
  and its values equal `numpy.median(a, axis=-1)`. *(Covered by
  `test_distribution.py::TestDistributionStatistics::test_pdf_median`,
  lines 152-168.)*
- **S5:** Given `d = Distribution(a)`, when `d.pdf_std(ddof=1)` is called,
  then the result equals `numpy.std(a, axis=-1, ddof=1)`; when called with
  `out=arr`, the return value `is arr`. *(Covered by
  `test_distribution.py::TestDistributionStatistics::test_pdf_std`, lines
  114-131.)*
- **S6:** Given two `Distribution`s `d1`, `d2` of the same logical shape
  and `n_samples`, when `d1 + d2` is evaluated, then the result is a
  `Distribution` with `.distribution` equal to `d1.distribution +
  d2.distribution` (elementwise, per-sample). *(Covered by
  `test_distribution.py::TestDistributionStatistics::test_add_distribution`,
  lines 214-228.)*
- **S7:** Given `d = Distribution(a)`, when `d - d.pdf_median()` is
  evaluated (a `Distribution` minus a plain array missing the sample
  axis), then the result is a `Distribution` of `d`'s shape and
  `n_samples`, with each sample equal to that element's samples minus its
  median. *(Exercised indirectly by `pdf_mad`, tested in
  `test_pdf_mad_smad`, lines 171-193 — that test is
  `skipif not HAS_SCIPY`, so treat S7 as requiring its own direct,
  scipy-independent assertion; verified empirically here.)*
- **S8:** Given `d = Distribution(a)` with `a.shape == (2, 3, 10)`
  (`n_samples=10`), when `d.sum()` (no `axis` argument) or
  `numpy.add.reduce(d)` is called, then both logical axes are fully
  reduced but the sample axis is retained: the result is a scalar
  `Distribution` (`.shape == ()`, `.n_samples == 10`) with `.distribution`
  equal to `a.sum(axis=(0, 1))`. *(Partially covered — `test_helper_poisson_samples`,
  lines 255-257, asserts `np.min(p_dist).shape == ()` for a similar
  reduction but not its values or `n_samples`; add a direct test with the
  value/`n_samples` assertions above.)*
- **S9:** Given `d = Distribution(a)` with `a.shape == (3, 4, 5)`
  (`n_samples=5`, so the logical shape `(3, 4)` has a size-4 core
  dimension), when `numpy.vecdot(d, d)` (a real generalized ufunc with
  signature `"(n),(n)->()"`) is called, then the sample axis is preserved
  around the core dimension and the result is a `Distribution` of logical
  shape `(3,)` and `n_samples=5`, whose `.distribution` matches applying
  `numpy.vecdot` independently to each of the 5 per-sample `(3, 4)`
  arrays. Guard this test on NumPy ≥ 2.0 (`vecdot` does not exist in 1.x;
  `core.py` itself branches on `NUMPY_LT_2_0` — reuse that same check or
  skip via `pytest.importorskip`/a version marker). *(Not covered by an
  existing test — verified empirically here; add a direct test.
  `numpy.linalg.det`/`numpy.matmul` are explicitly **not** required to
  work — see Key Components.)*
- **S10:** Given a scalar (0-d) `Distribution` `c = Distribution([2.0j,
  3.0, 4.0j])` (complex128 samples, `n_samples=3`), when `c.view("2f8")`
  is called, then the result has `.shape == c.shape + (2,) == (2,)`,
  shares memory with `c` (`numpy.may_share_memory`), and
  `.distribution` equals `numpy.moveaxis(c.distribution.view("2f8"), -2,
  -1)`. *(Covered by `test_distribution.py::test_distr_view_different_dtype1`,
  lines 450-461. Takes Step B row 5 of the view() table above.)*
- **S11:** Given `uint32 = Distribution(numpy.array([[0x01020304,
  0x05060708], [0x11121314, 0x15161718]], dtype="u4"))` (`n_samples=2`),
  when `uint32.view("4u1")` is called, then the result has `.shape ==
  uint32.shape + (4,)`, shares memory with `uint32`, and
  `.distribution` equals `numpy.moveaxis(uint32.distribution.view("4u1"),
  -2, -1)`; viewing the result back as `"u4"` recovers `uint32`'s values.
  *(Covered by `test_distribution.py::test_distr_view_different_dtype2`,
  lines 464-479. Also takes Step B row 5, not row 6 — see Key
  Components.)*
- **S12:** Given `d = Distribution(a)`, when `numpy.empty_like(d)` is
  called, then the result is a `Distribution` with the same `.shape` and
  `.n_samples` as `d`; when called with an explicit `dtype=int`, the
  result's element dtype is the platform default int dtype. *(Not covered
  by an existing test — verified empirically here; add a direct test.)*
- **S13:** Given `Distribution`s `da`, `db` and a plain `numpy.ndarray`
  `c`, when `numpy.broadcast_arrays(da, db, c, subok=True)` is called,
  then all three outputs are broadcast to a common shape and `da`'s/`db`'s
  outputs remain their original `Distribution` subclass; when called with
  `subok=False`, the `Distribution` outputs' `.distribution` becomes plain
  `numpy.ndarray` rather than a more specific subclass. *(Covered by
  `test_functions.py::TestBroadcast::test_broadcast_arrays`/
  `test_broadcast_arrays_subok_false`.)*
- **S14:** Given `Distribution` `da` (logical shape `(2, 3)`, `n_samples=4`)
  and a plain `numpy.ndarray` `c` of shape `(2, 1)`, when
  `numpy.concatenate((c, da), axis=1)` is called, then the result is a
  `Distribution` of logical shape `(2, 4)` with `n_samples=4`, whose
  leading column along `axis=1` repeats each of `c`'s two values
  identically across all 4 samples (i.e. equals `numpy.broadcast_to(c[...,
  numpy.newaxis], c.shape + (4,), subok=True)`) and whose remaining three
  columns equal `da`'s original samples unchanged. *(Covered by
  `test_functions.py::TestConcatenation::test_concatenate_not_all_distribution`,
  lines 51-59 — this scenario mirrors that test's exact shapes and axis.)*
- **S24:** Given `distr = Distribution([2.0, 3.0, 4.0])` and
  `ad = Angle(distr, "deg")` (registering the `Angle`-backed
  `Distribution` subclass via the MRO walk described in Key Components),
  when `ad + ad` is evaluated, then the result is an instance of both
  `Angle` and `Distribution`; when `ad * ad` is evaluated (a unit-changing
  operation `Angle` cannot represent), the result decays to a plain
  `Quantity`-backed `Distribution` (not `Angle`); when `ad.view(u.Quantity)`
  is called, the result is a non-`Angle` `Quantity`-backed `Distribution`
  whose `.distribution` equals `ad.distribution`. *(Covered by
  `test_distribution.py::test_distr_angle`, lines 403-421, and
  `test_distr_angle_view_as_quantity`, lines 425-447 — this is the
  in-scope mitigation referenced in Trade-offs for the coordinates-interop
  gap left by the out-of-scope `test_containers.py`.)*
- **S25:** Given `d1 = Distribution(a1)` (logical shape `(3, 4)`,
  `n_samples=5`) and `d2 = Distribution(a2)` (logical shape `(3, 2)`,
  `n_samples=5`), when `numpy.concatenate((d1, d2), axis=-1)` is called,
  then the result has logical shape `(3, 6)`, `n_samples=5`, and
  `.distribution` equal to `numpy.concatenate((d1.distribution,
  d2.distribution), axis=1)` — exercising the `axis - 1` negative-axis
  shift in the `concatenate` helper. *(Not covered by an existing test —
  both existing concatenate tests use non-negative `axis`; verified
  empirically here; add a direct test.)*
- **S28:** Given `db = Distribution(b)` (logical shape `(3, 4)`,
  `n_samples`), when `numpy.broadcast_to(db, target_shape, subok=True)` is
  called (a function with **no** `FUNCTION_HELPERS` entry, reaching the
  pass-through branch of `__array_function__` described in Key
  Components), then the result is a `Distribution` of the requested
  logical `target_shape` whose `.distribution` equals
  `numpy.broadcast_to(b, target_shape + (n_samples,), subok=True)` — this
  is the scenario the `FUNCTION_HELPERS`-present/absent mutation in
  Definition of Done targets. *(Covered by
  `test_functions.py::TestBroadcast::test_broadcast_to`, lines 67-72.)*

### Edge Cases
- **S15:** Given a value with no sample axis that is *not already an
  `ndarray`* — a Python float, or a NumPy scalar obtained via integer
  indexing (e.g. `arr[0]` from a 1-D array) — when `Distribution(...)` is
  constructed, then a `TypeError` matching `"Attempted to initialize a
  Distribution with a scalar"` is raised. *(Covered by
  `test_distribution.py::test_init_scalar`. Do **not** extend this
  scenario to a pre-built 0-d `numpy.ndarray` — `Distribution(np.array(1.0))`
  raises `IndexError` instead, per the pre-existing quirk documented in
  Data Flow step 1; a test asserting `TypeError` for that input would be
  wrong.)*
- **S16:** Given `d = Distribution(a)` with float64 samples, when
  `d.view("2i8")` (itemsize matching neither the element itemsize nor the
  per-sample stride — view-table branch 9) is called, then a `ValueError`
  matching `"can only be viewed"` is raised — for both the `type=None` and
  an explicit `type=d.__class__` call, and for a `Quantity`-backed
  `Distribution` too. *(Covered by
  `test_distribution.py::test_distr_cannot_view_new_dtype`, lines
  483-500.)*
- **S17:** Given `uint8 = Distribution(u32_array).view("4u1")` (from S11)
  and its transpose `uint8_2 = uint8.T` (whose logical last axis is no
  longer contiguous), when `uint8_2.view("u4")` is called, then a
  `ValueError` matching `"last axis must be contiguous"` is raised — this
  is NumPy's own `ndarray.view()` error, surfacing naturally once
  `ArrayDistribution.view()`'s Step B row 5/6 delegates to `distr.view(dtype,
  samples_cls)`. *(Covered by `test_distribution.py::test_distr_view_different_dtype2`,
  lines 478-480.)*
- **S18:** Given `single = numpy.arange(6.0).reshape(3, 2)[..., numpy.newaxis]`
  — a broadcast-appended trailing axis of length 1 with `strides == (16,
  8, 0)`, i.e. `strides[-1] == 0` — when `Distribution(single)` is
  constructed, then construction succeeds via a *view*, not a copy:
  `.shape == (3, 2)`, `.n_samples == 1`, and `numpy.may_share_memory(d,
  single)` is `True`. **Do not** use a plain C-contiguous
  `numpy.arange(6.0).reshape(3, 2, 1)` for this scenario — its
  `strides[-1]` is `8` (equal to the itemsize, not `0`), so it never
  exercises the `shape[-1:] != (1,)` carve-out this scenario targets
  (verified: it shares memory too, but for the ordinary "already
  contiguous" reason, not the carve-out). This exact `[...,
  numpy.newaxis]` construction is also what intact `Distribution.__setitem__`
  performs internally (`core.py:633`) when broadcasting a non-`Distribution`,
  non-scalar-shaped assignment value — e.g. `d[item] = 0.0` in
  `TestGetSetItemAdvancedIndex::test_setitem` (line 585) and `d["a"] = 0.0`
  in `TestStructuredDistribution::test_setitem_field` (line 671, part of
  S27) — so the carve-out is load-bearing for S27, not for S26 (S26's
  `d[d < 0] = 0` assigns a `Distribution`-typed *mask*, not a value, and
  never reaches `core.py:633` at all). The test for this scenario must
  assert the precondition itself (`assert single.strides[-1] == 0`) before
  asserting `may_share_memory`, so that if a future NumPy changes how
  `[..., np.newaxis]` reports strides for a broadcast axis, the test fails
  loudly instead of silently passing without ever exercising the
  carve-out. *(Not covered by an existing test by that exact construction
  — verified empirically here; add a direct test asserting shared
  memory.)*
- **S19:** Given `rev = a[:, ::-1]` (a negative last-axis stride) with `a`
  as in S1, when `Distribution(rev)` is constructed, then construction
  succeeds but via a *copy*: `.distribution` values equal `rev`, but
  `numpy.may_share_memory(d, rev)` is `False`. *(Not covered by an
  existing test by name — `test_numpy_init_T` is a bodyless smoke call
  exercising the *positive*, large-stride non-contiguous view path, not
  the negative-stride copy path, and asserts nothing; verified empirically
  here; add a direct test.)*
- **S20:** Given a generalized ufunc call on `Distribution`s (e.g.
  `numpy.matmul(d, d, axes=[(-2, -1), (-2, -1), (-2, -1)])`) with an
  explicit `axes=` keyword argument, when the ufunc is invoked, then
  `NotImplementedError` matching `"gufunc calls with 'axes'"` is raised.
  *(Not covered by an existing test — verified empirically here; add a
  direct test.)*

### Error Scenarios
- **S21:** Given `d = Distribution(a)`, when
  `numpy.concatenate((d,), axis=0, out=plain_ndarray)` is called with
  `out` that is a plain `numpy.ndarray` (not a `Distribution`), then the
  call raises `TypeError` matching the substrings `"cannot handle"` and
  `"with the given arguments"` (do not assert the full message — the
  `{function}` repr embedded in it is not guaranteed stable across NumPy
  versions; see Key Components). *(Not covered by an existing test —
  verified empirically here; add a direct test.)*
- **S22 (exempted from mandatory coverage — see Definition of Done and
  Trade-offs):** Given `numpy.add(d1, d2, out=plain_ndarray)` where
  `plain_ndarray` is a plain `numpy.ndarray` (not a `Distribution`), when
  the ufunc is invoked, then a bare `AssertionError` is raised (verified;
  this is a pre-existing upstream limitation of
  `_result_as_distribution`'s `assert isinstance(out, Distribution)`, not
  a designed error message — do not assert any message text). This
  scenario documents real, verified behavior, but — unlike every other
  scenario in this document — is **not required** to have a test: it pins
  an implementation artifact (a bare `assert`) that silently disappears
  under Python's `-O` flag, so requiring it would make the suite's
  correctness depend on how it is invoked. Writing the test is allowed and
  encouraged if the project's CI never runs `-O`, but its absence does not
  fail Definition of Done. *(Not covered by an existing test — verified
  empirically here.)*

### Structured and In-Place Behavior
- **S26:** Given `x = numpy.array([-1.0, 2.0, -3.0, 4.0])` and
  `d = Distribution(x)` (a scalar, 0-d `Distribution` with `n_samples=4` —
  `x` itself *is* the sample axis, there being no logical axis left), when
  `d[d < 0] = 0` is evaluated (`d < 0` is itself a `Distribution` of
  booleans, taking `__setitem__`'s `isinstance(item, Distribution)`
  branch, `core.py:614-617`, which does `self.distribution[item.distribution]
  = value`), then the mask selects individual **samples**, not logical
  elements (there is only one logical element here): every sample whose
  value was negative becomes `0` and every sample whose value was
  non-negative is unchanged, so `d.distribution == [0.0, 2.0, 0.0, 4.0]`.
  **Do not** write this scenario as `d[d.distribution < 0] = 0` —
  `d.distribution` still carries the sample axis, so that mask has one
  extra dimension and raises `IndexError: too many indices for array:
  array is 0-dimensional, but 1 were indexed` (verified) — the comparison
  must be done on `d` itself (`d < 0`, not `d.distribution < 0`) to
  produce a correctly-shaped `Distribution`-typed mask. *(Covered, with
  the correct form and the same per-sample selection semantics — see
  `Distribution([90., 30., 0.])`, `d[d > 50] = 0.` → `[0., 30., 0.]` — by
  `test_distribution.py::TestSetItemWithSelection::test_setitem`/
  `test_inplace_operation`, lines 541-550.)*
- **S27:** Given a structured-dtype sample array
  `data = (np.arange(5.0) + (np.arange(60.0) * 10).reshape(3, 4, 5, 1)).view(
  np.dtype([("a", "f8"), ("b", "(2,2)f8")])).reshape(3, 4, 5)` (logical
  shape `(3, 4)`, `n_samples=5`, per-sample stride larger than a single
  `"a"` field's itemsize — the `itemsize` parameter of
  `_get_distribution_dtype`/`__new__`'s stride-trickery branch), when
  `Distribution(data)` is constructed and then indexed by field name
  (`d["b"]`), then `d.shape == (3, 4)`, `d.n_samples == 5`, `d["b"]` is
  itself a `Distribution` of shape `(3, 4, 2, 2)` sharing memory with `d`,
  and `d["a"] = 0.0` zeroes that field's samples in place. *(Covered by
  `test_distribution.py::TestStructuredAdvancedIndex`/`TestStructuredDistribution`,
  lines 628-680.)*

## For the Implementing Agent

> **Your job:** make every acceptance scenario above pass with tests that
> would *fail if the behavior were wrong*. A green suite that passes for
> the wrong reason does not satisfy this contract — `/verify` will hunt
> for vacuous tests by asking, of each behavior, "what is the smallest
> change that breaks this, and would any test catch it?"

The two pre-existing suites, `astropy/uncertainty/tests/test_distribution.py`
and `astropy/uncertainty/tests/test_functions.py`, already contain
assertions covering S2, S4, S5, S6, S10, S11, S13, S14 (with S14's cited
shapes, not the earlier draft's — see S14's own note), S15, S16, S17, S24,
S26, S27, and S28 (see the parenthetical after each scenario for the exact
test name/line range) — run them as your primary feedback loop
(`pytest astropy/uncertainty/tests/test_distribution.py
astropy/uncertainty/tests/test_functions.py`). You must additionally add
new tests for S1, S3, S7, S8, S9, S12, S18, S19, S20, S21, and S25 — none
of these has an existing named test with matching assertions; every claim
in those scenarios was independently verified against the pre-crop
reference implementation while writing this spec (see Context), so they
are real, reachable behaviors, not speculative ones. S22 documents real,
verified behavior but is explicitly **not required** — see its own note
and Definition of Done. Pay particular attention to S1, S14, S15, S18, and
S26, each of which calls out a plausible-but-wrong variant of the scenario
that this spec deliberately rejects (based on empirical verification) —
writing the wrong variant will produce a test that either doesn't compile,
tests the wrong branch, or asserts behavior the ground truth doesn't have.
Do not weaken or delete existing assertions in either file to make them
pass.

Implement however you work best — blueprint does not prescribe order,
cadence, or commit structure. Only the result is checked. Write any new
tests to the project's conventions (pytest, `numpy.testing`/
`astropy.tests.helper` assertions, the `setup_class`/parametrize patterns
already used in `test_distribution.py`) and to these principles (the same
ones `/verify` scores against):

- **Behavioral over structural** — assert observable output (array
  values, dtype, shape, `n_samples`, memory sharing via
  `numpy.may_share_memory`, exception type/message substring), not
  internal structured-dtype layout details, unless a scenario is
  specifically about that layout (S27).
- **Every test can fail** — derive expected values independently (e.g. via
  plain `numpy` operations on the raw sample array, as every scenario
  above does), not by copy-pasting a value computed with the same logic
  under test.
- **Deterministic, isolated, readable** — seed any random sample
  generation (the existing suite uses `astropy.utils.NumpyRNGContext`), no
  cross-test state, AAA structure with inline setup.

## Definition of Done

Done is when `/verify` passes against this spec:

- [ ] `pytest astropy/uncertainty/tests/test_distribution.py
      astropy/uncertainty/tests/test_functions.py` is green, in an
      environment where `astropy.stats`'s compiled extension and `scipy`
      are both available (this spec-writing sandbox lacked both and is
      not representative — see Context), including both files unmodified
      in their existing assertions (only additive changes permitted). Do
      **not** attempt to restore or run `astropy/uncertainty/tests/test_containers.py`
      (see Trade-offs); its pre-existing deletion from the working tree is
      expected and must be left as-is.
- [ ] Every acceptance scenario **S1–S21 and S24–S28** maps to at least one
      test (there is no S23 in this document — IDs skip from S22 to S24;
      that is correct, not an error). **S22** is exempt —
      it documents real behavior (a bare `AssertionError` from a
      non-`Distribution` ufunc `out=`) that is not required to be tested,
      per its own note. Three additional pieces of required-for-correctness
      machinery have no in-scope scenario and are likewise exempt (see
      Trade-offs for why each is unreachable in-scope): `_result_as_distribution`'s
      tuple/list-result rewrapping branch, `ArrayDistribution.view`'s Step
      B row 6 (the non-contiguous per-sample-stride case), and
      `_get_distribution_dtype`'s `dtype.names == ("samples",)` early
      return.
- [ ] No covered-but-vacuous scenarios — each scenario's test fails under
      the smallest break of its behavior (thought-mutation), e.g. flipping
      `axis=-1` to `axis=0` in `pdf_median`/`pdf_std`, returning
      `NotImplemented` unconditionally from `__array_ufunc__`, dropping
      the `shape[-1:] != (1,)` carve-out in `__new__` (S18 — the test must
      assert `single.strides[-1] == 0` as a precondition, or this mutation
      could go undetected), or swapping the `FUNCTION_HELPERS`-present/
      absent branches in `__array_function__` (S28's `broadcast_to`
      pass-through).
- [ ] Tests meet the Desiderata bar (Behavioral and Structure-insensitive
      first); no anti-pattern violations (tautological asserts, disabled
      assertions, etc.).
- [ ] No implementation-quality blockers (stubs, dead code, stale
      docstrings) in `core.py` or `function_helpers.py`.
- [ ] `astropy.uncertainty.function_helpers.__all__` matches
      `git show HEAD:astropy/uncertainty/function_helpers.py`'s `__all__`
      (catches a helper restored without its real upstream docstring —
      see Context).
- [ ] No other file in the repository was modified except
      `astropy/uncertainty/core.py`, `astropy/uncertainty/function_helpers.py`,
      and (optionally, additively) `astropy/uncertainty/tests/test_distribution.py`
      / `astropy/uncertainty/tests/test_functions.py`.

## Trade-offs and Limitations

- **`test_containers.py` scope (resolved without human input, since this
  spec was produced non-interactively with no reviewer available).**
  Restoring it is out of scope. The actual residual gap, stated precisely:
  `Distribution` × `SkyCoord`/representation/differential round-trips
  (`__array_finalize__` propagation through multi-field container types,
  `Longitude`/`Latitude` wrap-angle semantics under a `Distribution`) have
  no in-scope regression test. This is narrower than "the subclass
  registry is untested" — the MRO-walk mechanism itself, and single-class
  `__array_finalize__` metadata restoration, **are** exercised in-scope by
  S2 (`Quantity`) and S24 (`Angle`, plus its arithmetic-driven decay back
  to plain `Quantity` and its `.view(u.Quantity)` path). What remains
  untested in-scope is specifically a subclass of an already-registered
  non-`ndarray` class (e.g. `Longitude` reusing `Angle`'s MRO entry) and
  any behavior that only exists once `Distribution` is embedded inside a
  `SkyCoord`/representation container. Accepted because: (a) this
  spec restores code, it doesn't design the coordinates-interop surface,
  and every construct that surface depends on (`__new__`,
  `_get_distribution_cls`, `__array_ufunc__`, `__array_function__`) has
  in-scope coverage of its own; (b) the coordinates-specific behavior in
  `test_containers.py` was working code before the crop and this spec
  doesn't touch `astropy/coordinates/`; (c) expanding scope to add
  coordinates-container scenarios would require re-deriving expectations
  for `SkyCoord`/representation internals this spec's author has not
  independently verified, which would lower confidence rather than raise
  it.
- Three pieces of required-for-correctness machinery have no in-scope
  scenario at all and are explicitly exempted from Definition of Done's
  coverage checklist (see that checklist for the itemized list): the
  `numpy.linalg`-only tuple/list-result rewrapping branch, `view`'s Step B
  row 6 (non-contiguous per-sample storage — none of S10/S11/S27 exercise
  it; S27 exercises the same underlying `itemsize` machinery via
  `__new__`/`__getitem__` instead), and `_get_distribution_dtype`'s
  same-dtype early return. All three must still be implemented per the
  Interface Contract; they are simply not independently test-covered by
  this spec, and `numpy.linalg` support is out of scope regardless (Key
  Components).
- A non-`Distribution` `out=` to a ufunc raises a bare, message-less
  `AssertionError` (S22, exempted from mandatory testing) rather than a
  designed `TypeError`/`ValueError` — this is a pre-existing upstream
  rough edge in `_result_as_distribution`, reproduced faithfully rather
  than improved, since "improve error messages" is not part of this
  restoration's scope and risks diverging from the ground truth this spec
  is checked against.
- The `axes=` keyword for generalized ufuncs remains unsupported
  (`NotImplementedError`) by design (S20) — this mirrors the upstream
  library's documented limitation, not an oversight to "fix" here.
- The `view()` `ValueError` message for an incompatible itemsize contains
  literal, unsubstituted `{...}` braces due to a pre-existing missing
  f-string prefix in the ground-truth source. This spec requires
  reproducing that message verbatim (only the `"can only be viewed"`
  substring is asserted by tests), not fixing the cosmetic bug.
- The structured-dtype storage scheme is inherited, not chosen by this
  spec — it constrains the implementation more than a greenfield design
  would, but changing it would require touching code declared out of
  scope.

## Open Questions

None. The scope question raised during spec review (whether
`test_containers.py`-covered coordinates interop needed in-scope
acceptance coverage) is resolved above under Trade-offs and Limitations,
with the residual gap named precisely rather than silently dropped, since
this spec was produced non-interactively with no reviewer available to
answer it.

## References

- Pre-crop reference implementation: `git show HEAD:astropy/uncertainty/core.py`
  and `git show HEAD:astropy/uncertainty/function_helpers.py` (this
  repository's own git history, prior to the working-tree crop).
- `astropy/uncertainty/tests/test_distribution.py`,
  `astropy/uncertainty/tests/test_functions.py` — existing regression
  suite exercising most of the contract above.
- https://docs.astropy.org/en/stable/uncertainty/ (referenced by the
  `Distribution` class docstring itself).

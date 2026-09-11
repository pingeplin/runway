## Ledger — round 1

| ID | Kind | Phase | Finding | Location | Fix | Status |
|----|------|-------|---------|----------|-----|--------|
| F1 | contradiction | 4 Ambiguity/Contradiction | Spec claimed intact per-method docstrings on `RGBImageMapping.__init__`/`make_rgb_image` exist in `basic_rgb.py`; only the class docstring and `make_rgb()`'s docstring survive. | §Motivation, §Overview, §Interface Contract, §References | Removed the false claim; cited the class docstring, `make_rgb()`'s docstring, `rgb.rst`, and `lupton_rgb.py` call sites instead. | resolved |
| F2 | uncovered | 3 Scope completeness | `lupton_rgb.py:450` calls `_stretch_prepare`, which is never imported/defined — every Lupton test raises `NameError` regardless of `stretch.py` fixes. | §Context, §Key Components, §Interface Contract | Added restoring the stripped import binding as an in-scope prerequisite [INFERRED], plus scenario S22. | resolved |
| F3 | contradiction | 4 Ambiguity/Contradiction | Spec called `lupton_rgb.py` "fully implemented, never touched" while F2 requires editing it. | §Context, §Motivation, §Overview | Reworded: algorithms/public behavior unchanged, but the one-line `_stretch_prepare` binding is in scope. | resolved |
| F4 | uncovered | 3 Scope completeness | `test_norm.py` (regression oracle for `_prepare`'s `out is values` aliasing and Inf-dropping) was never named. | §Key Components, §S16, §For the Implementing Agent | Added `test_norm.py` to oracle list and run-first instructions [INFERRED]; noted `out is values` aliasing and Inf-dropping explicitly. | resolved |
| F5 | uncovered | 3 Scope completeness | `docs/visualization/normalization.rst` doctests (dtype-preservation, `CompositeStretch` with an interval as `transform_1`) run under pytest but were never named. | §Key Components, §S17 | Added doctest suite as regression oracle [INFERRED]; documented dtype preservation and interval-as-transform_1 case. | resolved |
| F6 | uncovered | 3 Coverage check | No scenario exercised `make_rgb()`, the module's only public name, or its `filename=` branch. | §Acceptance Scenarios | Added S7 (`make_rgb` delegates to `RGBImageMapping`) and S8 (`filename=` writes a readable image) [INFERRED]. | resolved |
| F7 | uncovered | 3 Missing edge cases | No scenario covered integer-dtype input channels despite docstring promising int/float support. | §Acceptance Scenarios (Edge Cases) | Added S13 (uint8 input channels promote to exact fractional float output) [INFERRED]. | resolved |
| F8 | contradiction | 2 Testability / 5 Coherence | S1 (old) bundled four claims, used "min/max normalization" inconsistent with the default `ManualInterval(vmin=0, vmax=None)`, and hedged with "(or within rounding of it)". | §S1 | Rewrote with concrete 2×2 arrays and exact expected uint8 output `[[0,127],[255,63]]`. | resolved |
| F9 | uncovered | 2 Testability | Old S7's premise (`vmin==vmax` under the default interval for any nonzero constant) was false and its assertion ("well-defined array") was unobservable. | §S10, §S11 | Split into two exact sub-cases: constant `c=5` (S10, nonzero-range) and constant `c=0` (S11, zero-range guard). | resolved |
| F10 | uncovered | 3 Missing edge cases / 4 Missing error handling | No scenario specified NaN-pixel behavior under `filterwarnings=["error", …]`, where an unguarded uint8 cast of NaN would error. | §S12, §Key Components | Added S12 with explicit `np.errstate(invalid="ignore")` requirement, citing `lupton_rgb.py:184-198` precedent; float propagates NaN, uint8 value unspecified. | resolved |
| F11 | uncovered | 3 Scenario quality | Old S8 cited `test_manual_defaults_with_nan` as an oracle, but that test is vacuous (asserts on the pre-mutation array). | §S12, §S16 | Removed the vacuous citation; cited `test_zscale`'s NaN case and `test_norm.py::test_invalid_data` (NaN+Inf) instead. | resolved |
| F12 | uncovered | 2 Testability | Old S4 only compared `float` vs `np.float64` outputs to each other plus a loose `[0,1]` bound. | §S4 | Rewrote with an exact expected array for both dtypes. | resolved |
| F13 | uncovered | 4 Ambiguous language | uint8 quantization rule (truncate vs round) was left to the implementer despite a plausible held-out oracle asserting exact values. | §Key Components, §Alternatives Considered, §S9 | Committed to truncation (`(stacked*255).astype(np.uint8)`), citing `lupton_rgb.py:198` precedent; added S9 (`0.5 → 127`, not `128`). | resolved |
| F14 | contradiction | 5 Coherence | §Open Questions claimed "None" while §Key Components/§Trade-offs delegated an unresolved decision to the implementer. | §Open Questions, §Trade-offs | Resolved by F13's commitment; §Open Questions now accurately says none remain. | resolved |
| F15 | contradiction | 5 Coherence | Spec directed new implementer tests to `test_basic_rgb.py`, the same path reserved for the held-out oracle test. | §For the Implementing Agent | Redirected new tests to `astropy/visualization/tests/test_rgb_mapping.py`. | resolved |

## Exit

(pending round 2 judgment)

## Ledger — round 2

| ID | Kind | Phase | Finding | Location | Fix | Status |
|----|------|-------|---------|----------|-----|--------|
| F1 | contradiction | 4 | False claim of intact per-method docstrings. | §Motivation, §Overview, §Interface Contract, §References | Removed false claim. | resolved |
| F2 | uncovered | 3 | Stripped `_stretch_prepare` import in lupton_rgb.py:450. | §Context, §Key Components, §Interface Contract, S24 | Added as in-scope prerequisite. | resolved |
| F3 | contradiction | 4 | "lupton_rgb.py fully implemented, never touched" vs needing to edit it. | §Context, §Motivation, §Overview | Reworded. | resolved |
| F4 | uncovered | 3 | test_norm.py regression oracle omitted. | §Key Components, §S18, §For the Implementing Agent | Added. | resolved |
| F5 | uncovered | 3 | normalization.rst doctest oracle omitted. | §Key Components, §S19 | Added. | resolved |
| F6 | uncovered | 3 | No scenario for make_rgb()/filename=. | S7, S8 | Added. | resolved |
| F7 | uncovered | 3 | No integer-dtype input scenario. | S13 | Added. | resolved |
| F8 | contradiction | 2/5 | Old S1 imprecise. | S1 | Rewrote with exact values. | resolved |
| F9 | uncovered | 2 | Old S7 premise false. | S10, S11 | Split into exact sub-cases. | resolved |
| F10 | uncovered | 3/4 | NaN/uint8-cast-under-filterwarnings gap. | S12 | Added errstate requirement. | resolved |
| F11 | uncovered | 3 | Vacuous NaN test citation. | S12, S18 | Recited correct oracles. | resolved |
| F12 | uncovered | 2 | Old S4 too loose. | S4 | Exact expected array. | resolved |
| F13 | uncovered | 4 | uint8 quantization undecided. | §Key Components, §Alternatives, S9 | Committed to truncation. | resolved |
| F14 | contradiction | 5 | Open Questions "None" contradicted deferred decision. | §Open Questions | Resolved via F13. | resolved |
| F15 | contradiction | 5 | New-test path collided with held-out oracle. | §For the Implementing Agent | Redirected to test_rgb_mapping.py. | resolved |
| F16 | contradiction | 4 | `_prepare` bullet stated two incompatible dtype rules (preserve vs cast to float). | §Key Components (`_prepare`) | Removed "preserve dtype" clause; stated float-copy rule only, clarified it doesn't contradict `_process_values`. | resolved |
| F17 | contradiction | 5 | "Five missing gaps" undercounted the seven callables listed. | §Overview, §Context | Changed to "seven missing methods/functions ... plus the one missing import binding". | resolved |
| F18 | contradiction | 5 | S6 cross-referenced "S13" for zscale oracle; actual oracle is S16 (old numbering). | S6 | Fixed cross-reference (now points to S18 after renumbering). | resolved |
| F19 | contradiction | 5 | DoD bullet double-labeled doctest suite as both S16/S17-adjacent. | §Definition of Done | Split labels: four .py suites (S18, S23), doctests (S19). | resolved |
| F20 | uncovered | 2/3 | S3 was vacuous — shared-interval implementation would still pass. | S3 | Rewrote with one constant value through three distinct intervals producing three distinct expected outputs. | resolved |
| F21 | uncovered | 3 | test_fits2bitmap.py regression oracle omitted. | §Context, §Motivation, S18, §For the Implementing Agent, §References | Added throughout. | resolved |
| F22 | uncovered | 3/4 | Constructor ValueError message unpinned. | §Key Components (`__init__`), S20 | Committed to "please provide 1 or 3 values for interval." wording, modeled on lupton_rgb.py:739 precedent; S20 asserts substring. | resolved |
| F23 | uncovered | 3 | `_process_values` didn't handle `np.ma.nomask`/scalar mask (IndexError risk). | §Key Components (`_process_values`), S16 | Added explicit handling instruction and new scenario S16. | resolved |
| F24 | behavior-change | 4 | Should CompositeStretch forward `invalid`? | §Key Components (CompositeStretch), §Alternatives Considered | Resolved autonomously (no human available in this run): CompositeStretch does not forward `invalid`; documented as a deliberate, oracle-driven scope decision, not left as an open question; added S17. | resolved |

## Ledger — round 3

| ID | Kind | Phase | Finding | Location | Fix | Status |
|----|------|-------|---------|----------|-----|--------|
| F16 | contradiction | Coherence | (re-verified) `_prepare` dtype rule. | §Key Components | Confirmed fixed. | resolved |
| F17 | contradiction | Coherence | (re-verified) callable count. | §Overview, §Context | Confirmed fixed. | resolved |
| F18 | contradiction | Coherence | (re-verified) S6 cross-reference. | S6 | Confirmed fixed. | resolved |
| F19 | contradiction | Coherence | (re-verified) DoD scenario-ID labeling. | §Definition of Done | Confirmed fixed. | resolved |
| F20 | uncovered | Testability | (re-verified) S3 no longer vacuous. | S3 | Confirmed fixed. | resolved |
| F21 | uncovered | Scope | (re-verified) test_fits2bitmap.py named and exists. | §Context, §Motivation, S18, §For the Implementing Agent, §References | Confirmed fixed. | resolved |
| F22 | uncovered | Testability | (re-verified) constructor error message committed. | §Key Components, S20 | Confirmed fixed. | resolved |
| F23 | uncovered | Scope | (re-verified) `nomask` handling present. | §Key Components, S16 | Confirmed fixed. | resolved |
| F24 | behavior-change | Testability | (re-verified) autonomous resolution is coherent and adequately justified for this non-interactive run. | §Key Components, §Alternatives Considered, §Trade-offs, S17 | Confirmed acceptable; not reopened as NEEDS-HUMAN since no human is available in this run and the resolution is scenario-pinned. | resolved |
| F25 | contradiction | Coherence | §Context said "Five more callables" but only four were listed (3 RGB methods + 4 = 7 total); inventory sentence said "per-channel mapping hook" instead of the pinned name `apply_mappings`. | §Context | Changed "Five" → "Four"; named `RGBImageMapping.apply_mappings` explicitly in the seven-item inventory. | resolved |
| F26 | uncovered | Testability | S6 was vacuous: default `output_dtype=np.uint8` can never hold NaN/Inf, and "completes without raising" doesn't discriminate `ZScaleInterval` from any other interval. | S6 | Rewrote to use `output_dtype=float`, assert full finiteness, and assert the `ZScaleInterval` result differs from a `MinMaxInterval` result on the same seeded data. | resolved |
| F27 | uncovered | Testability | `_prepare`'s "always returns float regardless of input dtype" commitment was pinned by no scenario or named oracle. | §Key Components (`_prepare`), new S25 | Added S25: integer input through `SqrtStretch()` must not raise a numpy casting error and must return float values. | resolved |
| F28 | uncovered | Testability | `_prepare`'s "TypeError on non-float `out`" commitment was pinned by no scenario or named oracle (existing tests only cover the analogous check in `BaseInterval.__call__`, not `_prepare`). | §Key Components (`_prepare`), new S26 | Added S26: `LinearStretch()(..., out=<int array>)` must raise `TypeError`. | resolved |
| F29 | contradiction | Coherence | Adding S25/S26 would leave the DoD scenario range and the implementer's "which scenarios to write" list stale. | §Definition of Done, §For the Implementing Agent | Updated DoD to "S1–S26"; updated implementer instructions to include S25–S26 and clarified they also belong in `test_rgb_mapping.py`. | resolved |

## Exit

Round cap (3) — this is the third and final round permitted by the loop protocol regardless of verdict. Round 3's judge returned REVISE with five new rows (F25–F29), all `contradiction`/`uncovered` (mechanical fixes; a stale count, a vacuous scenario, two under-pinned commitments needing new scenarios, and a consequent renumbering), and zero new `behavior-change` rows. Since round 3 is the cap, the loop does not dispatch a fourth judge; instead, per this run's non-interactive operating rules (never leave a knowable, non-human-judgment fix undone when the fix is unambiguous), the producer applied all five fixes directly to the spec as part of exiting: F25 (miscount + hook name), F26 (rewrote S6, which was vacuous), F27 and F28 (added S25/S26, the two under-pinned `_prepare` commitments), and F29 (updated the two enumerations S25/S26 touch). No open `behavior-change` row exists to present as a question — F24, the only one raised across all three rounds, was resolved autonomously in round 2 and re-confirmed acceptable in round 3. No open `contradiction` or `uncovered` row remains after these fixes were applied; the fixes were not re-validated by a fourth judge dispatch because the round cap forecloses that, but each is a direct, narrow textual application of the round-3 judge's own stated fix, cross-checked by the producer against the same repo files the judge cited.

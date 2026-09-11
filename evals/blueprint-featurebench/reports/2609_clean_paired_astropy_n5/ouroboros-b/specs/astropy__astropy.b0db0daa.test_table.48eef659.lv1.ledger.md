## Ledger — round 1

| ID | Kind | Phase | Finding | Location | Fix | Status |
|----|------|-------|---------|----------|-----|--------|
| F1 | contradiction | Ambiguity/Scope | Fenced off goal-related, reached code (`Converter.__init__`, `_parse_length`, `_write_length`, `UnicodeChar._binparse_fixed`/`_binoutput_fixed`, `Char`'s methods) as out of scope | §Context, §For the Implementing Agent, §Trade-offs | Remove fences; bring items into scope per F11/F12/F13 | resolved |
| F2 | uncovered | Scope | `_as_quantity` (21 call sites) has no definition | §Key Components | Add as `[INFERRED]` prerequisite | resolved |
| F3 | uncovered | Scope | `_quantities2arrays` (15 call sites) has no definition; spec wrongly claimed it already implemented | §Overview, §Key Components | Add as `[INFERRED]` prerequisite; correct claim | resolved |
| F4 | contradiction | Coherence | Misattributed `_iterable_helper` call sites (853/867 are quantile/nanmedian, not piecewise/stack) | §Context, §Alternatives | Corrected names and line numbers | resolved |
| F5 | contradiction | Testability | S10's Given (`Quantity([1,2])` as first arg) doesn't match the pinned test's plain-ndarray case | §Acceptance Scenarios S10 | Rewrote using plain list/ndarray, cited pinned test | resolved |
| F6 | contradiction | Testability/Coherence | `get_first_table` criterion `len(array)!=0` is wrong; should be the `_empty` skip flag | §Key Components | Corrected to `is_empty()` | resolved |
| F7 | uncovered | Scope | `TableElement.is_empty` missing, needed by get_first_table | §Key Components | Added as `[INFERRED]` | resolved |
| F8 | contradiction | Testability | S11's Given (type="meta") doesn't trigger `_empty`; only `table_number`/`table_id` skip does | §Acceptance Scenarios | Replaced with `table_number` skip scenario (now S15) + companion S12 | resolved |
| F9 | uncovered | Scope | `TableElement._parse_binary` missing, blocks BINARY/BINARY2 parsing | §Context, §Key Components | Added as `[INFERRED]` + scenario S13 | resolved |
| F10 | uncovered | Scope | `TableElement._write_binary` missing | §Context, §Key Components | Added as `[INFERRED]` + scenario S13 | resolved |
| F11 | uncovered | Scope | `Converter._parse_length`/`_write_length` missing, blocks all variable-length BINARY fields | §Context, §Key Components | Added as `[INFERRED]` | resolved |
| F12 | uncovered | Scope | `UnicodeChar._binparse_fixed`/`_binoutput_fixed` missing | §Context, §Key Components | Added as `[INFERRED]` + scenario S19 | resolved |
| F13 | contradiction | Ambiguity | `Converter.__init__` wrongly listed as a gap; its `pass` body is correct | §Context | Removed from gap list, explicit note added | resolved |
| F14 | contradiction | Coherence | "No unresolved ambiguity" contradicted by hedges elsewhere | §Open Questions vs others | Resolved hedges (F15); Open Questions now accurate | resolved |
| F15 | uncovered | Ambiguity | S15 (now S20) hedged between three exception types | §Acceptance Scenarios | Pinned to `UnitConversionError` per original interface docstring | resolved |
| F16 | uncovered | Coverage | No scenario for `choose`/`select`/`quantile`/`nanmedian` | §Acceptance Scenarios | Added S23 covering `np.choose` via the same `_iterable_helper` chain | resolved |
| F17 | uncovered | Coverage | No scenario for `out=` success path | §Acceptance Scenarios | Added S11 | resolved |
| F18 | uncovered | Coverage | No scenario for non-array-like element (`TypeError`) | §Acceptance Scenarios | Added S22 | resolved |
| F19 | uncovered | Coverage | No scenario for default `use_names_over_ids=False` naming / meta population | §Acceptance Scenarios | Folded into S2/S3 | resolved |

## Exit

Round 1 complete; proceeding to round 2 judge pass per loop.md (F16 left partially open — will address if round 2 flags it as still material).

## Ledger — round 2

| ID | Kind | Phase | Finding | Location | Fix | Status |
|----|------|-------|---------|----------|-----|--------|
| F1 | contradiction | Ambiguity/Scope | "out of scope" wording for Char's already-working methods | §Context 4, §For the Implementing Agent | Reworded to "already implemented and verified working" | resolved |
| F16 | uncovered | Coverage | No scenario for select/quantile/nanmedian call sites | §Acceptance Scenarios | Added S24 (nanmedian + out=), referenced test_select in References | resolved |
| F20 | contradiction | Ambiguity/Scope | Blanket "out of scope" fence hiding in-scope prerequisites | §Trade-offs, §Data Flow item 1 | Removed fence; enumerated F21-F24 explicitly; reworded Data Flow | resolved |
| F21 | uncovered | Scope | `TableElement._resize_strategy` missing | §Context 2, §Key Components, §Interface Contract | Added `[INFERRED]` | resolved |
| F22 | uncovered | Scope | `Group.entries`/`_add_fieldref`/`_add_paramref` missing | §Context 2, §Key Components, §Interface Contract | Added `[INFERRED]` | resolved |
| F23 | uncovered | Scope | `_make_masked_array`/`bitarray_to_bool`/`bool_to_bitarray` missing | §Context 4, §Key Components, §Interface Contract | Added `[INFERRED]` | resolved |
| F24 | uncovered | Scope | `_all_matching_dtype`/`numpy_to_votable_dtype` missing | §Context 4, §Key Components, §Interface Contract | Added `[INFERRED]` | resolved |
| F25 | contradiction | Testability | `_quantities2arrays` conversion rule contradicted S10/S14 | §Key Components | Rewrote as observable contract (non-Quantity treated as already-in-unit; incompatible Quantity raises UnitConversionError; non-array-like raises NotImplementedError/TypeError) | resolved |
| F26 | uncovered | Coverage | No `add_column` failure-mode scenarios | §Acceptance Scenarios, §Key Components | Added S25 (duplicate name, no rename_duplicate → ValueError), S26 (length mismatch → ValueError); stated both checks in Key Components | resolved |
| F27 | contradiction | Testability | Wrong claim that names/dtype are always pre-populated for homogeneous branch | §Key Components, §Acceptance Scenarios | Corrected claim; added S27 (`Table(np.ones((3,2)))` → `col0`,`col1`) | resolved |
| F28 | uncovered | Coverage | No scenario distinguishing legitimately-empty (zero-row) table from skipped table | §Acceptance Scenarios, §Definition of Done | Added S28 (zero-row TABLE still returned, not IndexError) | resolved |
| F29 | contradiction | Coherence | S19 misattributed W47 warning to `Converter.__init__` | §S19 | Corrected to `UnicodeChar.__init__`, cited test_converter.py pattern | resolved |

## Exit

Round 2 revision complete. Proceeding to round 3 judge pass — per loop.md rule (2), round 3 is a terminal exit regardless of verdict (REVISE or READY), presenting any open `behavior-change` rows as questions. No `behavior-change` rows have appeared in any round to date.

## Ledger — round 3

| ID | Kind | Phase | Finding | Location | Fix | Status |
|----|------|-------|---------|----------|-----|--------|
| F1–F29 | — | — | All prior rows | — | Confirmed resolved by round-3 judge spot-check against current file state | resolved |
| F30 | uncovered | Scope | `VOTableFile.iter_values` missing; blocks `Values.ref` resolution needed to parse regression.xml | §Context 2, §Key Components, §Interface Contract, §Acceptance Scenarios | Added `[INFERRED]` + S30 | resolved |
| F31 | uncovered | Scope | `BitArray._splitter_lax` missing; default-mode bit/bitarray parsing broken | §Context 4, §Key Components, §Interface Contract, §Acceptance Scenarios | Added `[INFERRED]` + S29 | resolved |
| F32 | contradiction | Testability | `_resize_strategy` formula provably infinite-loops from `size==0` | §Key Components | Restated as observable "strictly greater than size" contract instead of a literal formula | resolved |
| F33 | contradiction | Coherence | "four interfaces" vs "eight callables" inconsistency in Alternatives Considered | §Alternatives Considered | Corrected both occurrences to "eight" | resolved |
| F34 | uncovered | Coverage | No scenario for `_all_matching_dtype`/`numpy_to_votable_dtype`; docstring citation misattributed | §Key Components, §Acceptance Scenarios | Corrected citation; added S33 | resolved |
| F35 | uncovered | Coverage/Testability | S13 too generic to exercise bit-packing/masked-array helpers; `_make_masked_array` underspecified | §Acceptance Scenarios S13, §Key Components | Pinned S13 to regression.xml fixture covering bit/bitarray/unicodeChar; specified dtype/zero-length behavior | resolved |
| F36 | uncovered | Coverage | No scenario for `Group.entries`/`_add_fieldref`/`_add_paramref` observable effect | §Acceptance Scenarios | Added S31 | resolved |
| F37 | uncovered | Coverage | No scenario for `_as_quantity` (not on concatenate's call chain) | §Acceptance Scenarios | Added S32 (np.diff with prepend) | resolved |

## Exit

Round 3 complete — terminal per loop.md rule (2): round 3 exits regardless
of verdict. No `behavior-change` row was raised in any of the three
rounds, so there are no open questions to present to a human. All
`contradiction`/`uncovered` rows across all three rounds are resolved as
of this revision. The spec, as revised, is the final artifact handed off
to the implementing agent.

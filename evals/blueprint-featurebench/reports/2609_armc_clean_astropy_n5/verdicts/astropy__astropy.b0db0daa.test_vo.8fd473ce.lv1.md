# Verdict: 2609.0001 VOTable Tree Navigation and Table Conversion

**Test suite:** not run — no test environment. All checks below are static
(reading spec, tests, and implementation).

## Overall verdict: DOES NOT MEET the spec's Definition of Done

The eight restored definitions in `astropy/io/votable/tree.py` are
implemented correctly and match the spec's interface contract closely —
they faithfully mirror the sibling implementations the spec points at
(`FieldRef.get_ref`, `Group.__repr__`, `TableElement.from_table`) and none
are stubs. That part of the work is solid. The submission fails the
Definition of Done for two independent reasons:

1. **Zero new tests were added.** `git diff --stat` shows only
   `exceptions.py`, `tree.py`, `ucd.py`, `check.py`, `iterparser.py`,
   `validate.py` touched — no test file anywhere in the diff. The spec
   explicitly requires "Every acceptance scenario (S1-S18) maps to at
   least one test" and calls out that the existing suite does **not**
   cover `ParamRef.get_ref`, `iter_values`/`__repr__`, TableElement
   `__repr__`/`__str__`/`__bytes__`, the `_empty`-skip behavior, or the
   `use_names_over_ids` collision rule. None of those were added. 9 of 18
   scenarios have no test at all, and 1 more has a test that asserts
   nothing (see coverage table below).
2. **A real correctness bug in `astropy/io/votable/ucd.py`'s
   `UCDWords.__init__`**, restored as a necessary prerequisite (not part
   of the 8 named symbols, but part of this diff and required for
   `astropy.io.votable` to import/parse at all), silently defeats the
   primary/secondary UCD1+ word-class check across the whole module.

Fix both before resubmitting; the tree.py restorations themselves do not
need rework unless noted below.

---

## 1. Scenario coverage map

| # | Scenario | Test | Verdict |
|---|---|---|---|
| S1 | `to_table()` colnames/values/mask match `array` | `test_table.py::test_table` (existing) | Covered |
| S2 | `use_names_over_ids` selects name vs ID column source | `test_table.py::test_names_over_ids`, `::test_explicit_ids` (existing) | Covered |
| S3 | `to_table()` → `from_table()` → `to_table()` round-trips `table.meta` (ID/name/ref/ucd/utype/description) | none | **Uncovered** |
| S4 | `ParamRef.get_ref()` returns the matching `Param` | none | **Uncovered** |
| S5 | `iter_values()` yields one `Values` per `iter_fields_and_params()` element, in order, including defaults | none | **Uncovered** |
| S6 | `repr(votable)` == `"<VOTABLE>... N tables ...</VOTABLE>"` | none | **Uncovered** |
| S7 | `get_values_by_id()` succeeds instead of raising `AttributeError` | none (no test calls `get_values_by_id` anywhere in the suite) | **Uncovered** |
| S8 | `get_first_table()` skips `_empty` tables (`table_number=1` case) | none — existing `get_first_table()` call sites never parse a multi-table file with a `table_number` filter | **Uncovered** |
| S9 | `to_table()` on an empty table: `len==0`, `colnames==["unsignedByte","short"]` | `test_table.py::test_empty_table` calls `table.to_table()` with **no assertion on the result at all** | **Covered-but-vacuous** |
| S10 | `use_names_over_ids=True` name-collision suffixing (`x`, `x1`, …) | none | **Uncovered** |
| S11 | `get_first_table()` raises `IndexError` when no non-empty table exists | none | **Uncovered** |
| S12 | `ParamRef.get_ref()` raises `KeyError` when no matching `Param` | none | **Uncovered** |
| S13 | `repr(table)`/`str(table)`/`bytes(table)` don't raise; `repr` starts `"<VOTable"`; `str(table) == str(table.to_table())` | none | **Uncovered** |
| S14 | Field `unit`/description/`ucd` transferred to column | `test_table.py::test_pass_kwargs_through_table_interface` checks `.unit` only (incidental, pre-existing); no test checks `.description` or `column.meta["ucd"]` | **Partially covered** |
| S15 | `check_string` raises `W08` for non-str, silent for `None`/str | `test_tree.py::test_string_fail` (existing) | Covered |
| S16 | `check_astroyear` raises `W07` for bad year, silent for valid/`None` | `test_tree.py::test_check_astroyear_fail` (existing) | Covered |
| S17 | `CooSys.reference_frames` accepts the listed terms, rejects `"InvalidSystem"`, under `verify="exception"`-equivalent strictness | `test_coosys.py::test_coosys_system` (`pytest.warns(E16)` gating — this is the discriminating form the spec asked for), `::test_coosys_to_astropy_frame_and_time`/`_error` (existing) | Covered |
| S18 | `parse()` completes on `regression.xml` without `NameError`/`AttributeError` | implicit in every passing `parse()`-based test (existing) | Covered |

**9 of 18 scenarios (S3, S4, S5, S6, S7, S8, S10, S11, S12, S13) have zero
test coverage, and one more (S9) has a test that cannot fail no matter
what `to_table()` returns for an empty table.** This alone fails the
Definition of Done's "every scenario maps to at least one test" bullet.

## 2. Thought-mutation table (anti-vacuity)

For the scenarios that do have tests, here is the smallest break and
whether it's actually caught:

| Scenario | Smallest break | Caught? |
|---|---|---|
| S1 | Build columns from `self.all_fields` instead of `self.fields` | Yes — `test_table` indexes `astropy_table.mask[name]` for every name in `table.array.dtype.names`; a name not present as a column raises `KeyError` |
| S1 | Construct `Table(..., masked=False)` (drop masking) | Yes — `astropy_table.mask[name]` would raise/behave differently, test fails |
| S2 | Ignore `use_names_over_ids` and always use `field.ID` | Yes — `test_names_over_ids`'s pinned `colnames` list would not match |
| S9 | Return a `Table` with wrong `len` or wrong `colnames` for the empty-table case | **No** — `test_empty_table` discards the return value |
| S9 | Raise instead of returning an empty `Table` | Yes (only failure mode this test can detect) |
| S15 | Remove the `isinstance(string, str)` check | Yes — `pytest.raises(W08)` no longer fires |
| S16 | Remove the regex check | Yes — `pytest.raises(W07)` no longer fires |
| S17 | `reference_frames` returns `set()` | Yes — `test_coosys_system`'s accepted terms (`ICRS`, `supergalactic`) would unexpectedly warn `E16` |
| S3, S4, S5, S6, S7, S8, S10, S11, S12, S13 | *(any change to the corresponding method)* | **No — nothing exercises the code path, so no mutation can be caught** |

The headline finding is exactly what the spec warned about: **10
scenarios' worth of behavior can be silently broken by a future change
and no test in this diff or the existing suite will notice.**

## 3. Test Desiderata

The pre-existing tests that do cover S1/S2/S15/S16/S17/S18 are reasonably
good: deterministic, isolated (in-memory or packaged fixture data, no
network), behavioral (assert on `colnames`, warnings raised, not on
private state), readable. No new anti-pattern was introduced into the
test suite — because no tests were added at all. The one relevant
anti-pattern already present:

- **AP-1 (vacuous assertion) — `test_table.py::test_empty_table`**: calls
  `table.to_table()` and discards the result. This predates the current
  diff, but the spec specifically calls this test out (S9) as the vehicle
  for verifying the empty-table path, and the implementing agent's job
  included strengthening it or adding a parallel assertion-bearing test —
  neither happened.

## 4. Implementation-quality flags

- **`astropy/io/votable/ucd.py`, `UCDWords.__init__` (restored in this
  diff) — real correctness bug.** The IVOA UCD1+ word list
  (`data/ucd1p-words.txt`) tags every word with a class letter
  (`P`/`S`/`Q`/`V`/`C`/`E`) that determines whether it's legal as the
  *first* (primary) component of a UCD, a *later* (secondary) component,
  or both. The restored code ignores the `type` field entirely and adds
  every word to **both** `self._primary` and `self._secondary`:
  ```python
  # Word classes ('P'rimary, 'S'econdary, 'Q'ualifies as
  # either, 'V'ector, 'C'andidate, 'E'xisting/deprecated)
  # are treated uniformly here: any listed word is
  # accepted in either position, matching real-world
  # usage in VOTable files that predates strict UCD1+
  # position enforcement.
  self._primary.add(name_lower)
  self._secondary.add(name_lower)
  ```
  This comment's justification is not grounded in anything cited in the
  repo — it reads as a rationalization for skipping the actual
  discrimination logic. The practical effect: `ucd.parse_ucd(...,
  check_controlled_vocabulary=True)` (wired to fire for any VOTable
  version ≥ 1.2 via `tree.py`'s `check_ucd`) can no longer raise
  `"Secondary word '...' is not valid as a primary word"` or the inverse
  — every controlled-vocabulary word becomes legal in every position.
  This is a silent regression: it doesn't reject anything that should be
  rejected in the surviving fixture data, so it slips past S1/S14/S18,
  but it defeats the entire purpose of maintaining separate primary and
  secondary sets. **Fix:** only add to `_primary` when `type` marks the
  word as primary-eligible (e.g. `P`/`Q`) and to `_secondary` when it
  marks secondary-eligible (e.g. `S`/`Q`), consistent with how
  `parse_ucd` actually branches on `is_primary`/`is_secondary`.
- **No stubs, hard-coded returns, dead code, or TODOs** were found in the
  `tree.py` diff itself — each of the 8 restored definitions has a real
  body and an accurate docstring.
- **Scope note, not a defect:** the diff also restores functions in
  `astropy/utils/xml/check.py`, `astropy/utils/xml/iterparser.py`,
  `astropy/utils/xml/validate.py`, and `astropy/io/votable/exceptions.py`
  that the spec did not mention as blocking prerequisites (the spec's
  prerequisite list covered only `tree.py`-internal gaps). These files
  were independently stripped in the starting checkout and are needed for
  `astropy.io.votable` to import and parse at all, so touching them was
  necessary despite the spec's "no other source file" instruction — that
  instruction was written against an incomplete picture of the checkout.
  Read individually, `check.py`, `iterparser.py`, `validate.py`, and
  `exceptions.py`'s restorations look correct and are wired to their call
  sites correctly (verified: `check_id`/`check_token`/`fix_id`/
  `check_anyuri`, `_convert_to_fd_or_read_function`, `validate_schema`,
  `_format_message`/`_suppressed_warning`). The one exception is the
  `ucd.py` bug above.
- **`tree.py`'s `Values._parse_minmax`** (blank slot the spec's Open
  Questions section incorrectly described as "not load-bearing") was also
  restored, correctly — it's actually called from the pre-existing
  `min`/`max` property setters, so without it every `VALUES` element with
  a `MIN`/`MAX` child would raise `NameError` during parsing. Restoring it
  was necessary and the implementation is correct.

## Punch list for the implementing agent

1. **Add tests for S3, S4, S5, S6, S7, S8, S10, S11, S12, S13** — one
   assertion-bearing test per scenario is enough; put them in
   `astropy/io/votable/tests/test_tree.py` or `test_table.py` next to the
   existing coverage, matching that file's style. Each test must be able
   to fail: assert on the returned value/exception type, not just "does
   not raise."
2. **Strengthen (or replace) `test_table.py::test_empty_table`** to assert
   `len(table.to_table()) == 0` and `table.to_table().colnames ==
   ["unsignedByte", "short"]`, per S9.
3. **Fix `UCDWords.__init__` in `astropy/io/votable/ucd.py`** to honor the
   `type` field from `ucd1p-words.txt` when populating `_primary` vs
   `_secondary`, instead of adding every word to both sets. Remove the
   comment that currently rationalizes the shortcut. Add (or point at) a
   test that would fail if this regresses again — e.g. a word that is
   secondary-only should make `ucd.parse_ucd(word, check_controlled_vocabulary=True)`
   raise `ValueError` when used as the first component.

Everything else — `ParamRef.get_ref`, `TableElement.to_table`,
`VOTableFile.__repr__`, `VOTableFile.get_first_table`,
`VOTableFile.iter_values`, `check_string`, `check_astroyear`,
`CooSys.reference_frames`, and the incidental `check.py`/`iterparser.py`/
`validate.py`/`exceptions.py`/`Values._parse_minmax` restorations — reads
as correct and does not need rework.

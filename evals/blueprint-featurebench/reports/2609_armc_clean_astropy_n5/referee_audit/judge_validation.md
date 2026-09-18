# Judge validation — fixed before any judge call ran (2026-09-16)

Four facts about `test_vo` were verified by hand against the artefacts. The judge
must reproduce all four on every repeat, or its output is not used.

1. The `UCDWords.__init__` claim is TRUE: B's patch adds every word to both
   `_primary` and `_secondary`. It is addressed (YES) in both round-2 patches:
   C gates on `type != "S"` / `type != "P"`, C0 on `type in "PQVCE"` / `"SQVCE"`.
2. The claim that `test_table.py::test_empty_table` asserts nothing is TRUE: its
   body calls `table.to_table()` with no assertion.
3. The claim that B added no tests is TRUE: no test file appears in B's patch.
4. Cluster F1 (107 tests, `E04: Invalid bit value`) is NOT caught: the verdict
   never mentions `converters.py`, binary2, or `test_vo.py`. C fixed 101 of them
   by restoring `_splitter_lax`; C0 fixed none.

Stability: the three `test_vo` repeats are also compared claim-count and
per-cluster `caught` for self-agreement.

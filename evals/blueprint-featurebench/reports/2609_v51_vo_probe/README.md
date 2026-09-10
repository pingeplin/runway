# 5.1 acceptance probe — `test_vo`, one task (2026-09-10)

Stage 01 only, history-masked harness, blueprint **5.1** (commit
`e6ecf86` + the ledger-status normalisation that followed it) via
`--plugin-dir`. The acceptance criterion from spec 2609.0002: the spec
names the definitions stripped from `astropy/io/votable/tree.py` as
in-scope prerequisites, contains no "leave untouched" fence, and lands a
`.ledger.md` with `Kind` populated.

**Passed.**

- §"Prerequisite gaps that block the acceptance scenarios" lists **ten**
  stripped neighbours, each marked `[INFERRED]` with file:line, the
  callers that reach it, and the existing test that pins it —
  `tree.check_string`/`check_astroyear`, `Values._parse_minmax`,
  `CooSys.reference_frames`/`refposition`, `TableElement.is_empty`,
  `MivotBlock.__str__`, `converters.BitArray._splitter_lax`,
  `ucd.UCDWords.*`, `exceptions._format_message`, and two under
  `astropy/utils/xml/` (`check.py`, `iterparser.py`).
- "Treat `xml_check`/`iterparser` as out of scope because they live
  outside `astropy/io/votable/`" and "Leave the ten prerequisite gaps out
  of scope" both appear only under **Alternatives Considered — Rejected**.
  The 5.0 spec for the same task had fenced exactly these off.
- Two `astropy/table` / `astropy/units` internals are kept as an explicit
  "Known blockers" note (acknowledged, reasoned, not fully specified).
  Whether that is `uncovered` or a legitimate boundary is the one
  judgement call left in the spec.
- Ledger: 3 rounds (round cap), 43 rows, kinds populated — round 1:
  3 contradiction / 17 uncovered / 1 behavior-change; round 2: 4 / 7;
  round 3: 4 / 6. The loop was still finding items at the cap.

| | 5.0 (clean run) | 5.1 probe |
|---|---|---|
| Spec cost | $12.72 | $19.94 |
| Wall | 45 min | 53 min |
| Turns | — | 83 |
| Lines | 666 | 661 |
| Stripped `tree.py` neighbours in scope | 0 | 10 |

Two format deviations by the headless producer, both now tolerated by
the harness and forbidden by `loop.md`: `Status` written as phrases
("resolved (round 2 rewrite)", "fixed: …") instead of one word, and
rounds 2–3 written as 4-column tables of *new* rows rather than the
7-column merged snapshot. `parse_ledger` classifies status by first word
and reports an `unclassified` count per round (1 here, a "deliberate
scope decision" row).

Not measured here: whether the implementing agent, given this spec,
resolves the hidden tests. That needs the 5-task Arm B run
(≈ $80 specs + $20 inference).

# Transcript analysis

Measuring agent behaviour from Claude Code session transcripts
(`~/.claude/projects/<project>/*.jsonl`) instead of from a benchmark.

Zero API cost — the transcripts already exist, and every tool call is in them.
This is the cheapest measurement tier in the repo, below even the triggering
evals.

```bash
uv run python measure_weakening.py ~/.claude/projects/-Users-eplin-workspace-<repo>  [...]
uv run python inspect_cases.py    ~/.claude/projects/-Users-eplin-workspace-<repo>  [...]
```

`measure_weakening.py` reports base rates; `inspect_cases.py` dumps the actual
edit content behind each candidate so it can be judged by hand. **The second
step is not optional** — see the result below.

## Result, 2026-09-16 — the one this was built for

Question: does an agent ever edit a *test* rather than the implementation to
turn a red suite green? That failure mode leaves no trace in the final artifact,
so `/verify`'s referee structurally cannot catch it, and it was the strongest
remaining justification for the hook ledger proposed in
`docs/designs/2609.0004`.

**Answer: no.** 116 sessions, 376 test runs, 43 red→green cycles across four
repositories. The detector flagged 4 candidates; **all 4 were false positives**
on inspection (two were the author manually running mutation tests, one was a
behaviour re-specification that preserved coverage, one was unrelated test
authoring).

| | cycles | |
|---|---|---|
| test-file edits only | 4 | 9.3% — all false positives |
| implementation edits only | 10 | 23.3% |
| both edited | 1 | 2.3% |
| no edits at all | 28 | 65.1% |

**Raw output is deliberately not committed.** Both scripts print absolute file
paths and branch names from whichever transcripts they are pointed at, which
belong to unrelated private repositories. Keep their output local; only
aggregate numbers belong in this public repo.

The design was rejected on this basis.

### Two findings worth keeping

**Precision, not rate, is what killed the design.** The proposed ledger keys on
the same signal this detector used — red → a test file is edited → green. That
signal was right 0 times out of 4 on real data. A shipped ledger would have fed
the referee four fabricated flags and zero real ones.

**65% of red→green cycles contain no edit at all.** Suites go green on reruns,
environment changes, and differing command invocations. red→green is a much
noisier signal than it looks, and that is a property of the signal rather than
of this script.

## Known limits of the detector

Read these before trusting a number out of it.

- **Red/green is parsed from stdout text, not exit codes.** The transcript's
  Bash `toolUseResult` carries only `stdout`, `stderr`, `interrupted`,
  `isImage`, `noOutputExpected` — there is no exit-status field. 96 of 376 runs
  were unclassifiable.
- **Pairing is naive.** A RED is closed by the *next* test run, whatever it is.
  In all four candidates above the closing command differed from the opening one
  — in one case it was `npm run build`, not a test run at all.
- **Test-file classification is path-based** (`tests/`, `_test.`, `.spec.`), so
  an unconventional layout is invisible to it.
- **Edits made through Bash are invisible** (`sed -i`, `git apply`): only the
  `Edit`, `Write` and `MultiEdit` tools are counted.
- **The corpus is one developer's**, and `~/.claude/projects/` is local and
  private, so this result is not reproducible by anyone else. Treat the number
  as evidence about this workflow, not as a general finding about agents.

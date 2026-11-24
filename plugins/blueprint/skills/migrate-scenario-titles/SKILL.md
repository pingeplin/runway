---
name: migrate-scenario-titles
description: TEMPORARY migration skill. Replace numbered scenario IDs (S1, S2, …) in blueprint specs, ledgers, design docs, tests and code comments with short, unique scenario titles. ALWAYS use this skill when the user wants to migrate old specs to scenario titles, "replace the S-numbers", "rename scenario IDs", "convert S1/S2 to titles", or when /verify or /review reports that a spec still numbers its scenarios. Also trigger when a spec in .blueprint/specs/ has lines like "- **S3:** Given …".
argument-hint: '[path-to-spec | all]'
---

# Migrate scenario titles

**Temporary skill.** Blueprint specs name each acceptance scenario by a
title, not a number. This skill moves older specs, and every place that
refers to their numbers, to titles. It will be removed in the next major
release of blueprint. When you remove it, also remove the references to it
in `agents/referee.md` and `references/review-impl.md`.

## Scope

- **Specs** — `.blueprint/specs/*.md`. If `$ARGUMENTS` names a spec, do only
  that spec. If it is `all` or empty, do every spec that has numbered
  scenarios, one spec at a time.
- **For each spec, the files that can refer to its numbers:**
  - the spec itself (cross-references such as "the S13 case", ranges such as
    "S1–S4" or "S1…SN");
  - the ledger sibling `{spec}.ledger.md`, if it exists;
  - the design doc with the same `yymm.xxxx` ID in `docs/designs/`, if
    it exists;
  - tests and source files: test names, `describe`/`it` text, comments and
    docstrings.
- **Out of scope:** git history, commit messages, PR text, and other IDs
  (`yymm.xxxx` document IDs, `AP-n` anti-pattern codes, ledger finding IDs
  `F1`, `F2`, …). Do not change them.

## Procedure

### 1. Find the numbered scenarios

In the spec, find each scenario label: `- **S3:** Given …`, `**S3**`,
`#### S3 …`, or a table row keyed by `S3`. Include lettered sub-scenarios
such as `S4a` and `S18a`; each one gets its own title. A spec has its own numbers:
`S3` in one spec is not `S3` in another.

### 2. Write a title for each scenario

Follow the title rules in `${CLAUDE_PLUGIN_ROOT}/skills/spec/SKILL.md`,
section "Scenario titles": unique in the spec, 3–8 plain words, says the behavior and its
condition, usable in a test name. Write the title from the scenario's own
Given/When/Then text. Do not change that text, except for the ID tokens
that step 4 replaces.

- **Check each title against its Then clause.** The title must say what
  the scenario checks, not its opposite. Read the title and the Then clause
  together before you continue.
- **Use only words, spaces, hyphens and apostrophes.** No colon (it breaks
  the `**Title:**` label), quote, comma or backtick (they break quoting and
  test-name slugs).

Show the map to the user, one table per spec, before you change any file:

| Spec | Old ID | New title |
|------|--------|-----------|

Wait for approval, unless the user already told you to proceed without it.
In that case, put the map at the top of the report.

### 3. Find every reference

Search with a word match that also matches lettered IDs:
`git grep -nwE 'S[0-9]+[a-z]?'`, or `grep -rnwE 'S[0-9]+[a-z]?'` for files
that git does not track. Do not use `\b` in an `-E` pattern: some `git grep`
builds do not support it and return no hits, with no error.
Also search for the lowercase test-name forms: `test_s3_`, `s3_`, `S3_`,
`(S3)`.

Always read the specs, their ledgers and their design docs by path, even
when git ignores `.blueprint/specs/` (some repos do).

For tests and source files, search tracked files only (`git grep -nE …`).
Some `grep` and `rg` setups skip ignored files and some do not, so do not
rely on them. Do not change test or source files that git ignores or does
not track: they are build output, run artifacts or vendored code. If you
see hits there, say so in one line of the report.

Classify each hit:

- **Scenario reference, owner known** — the hit is in the spec, its ledger,
  or its design doc; or the text near it names the spec by its file name or
  title (an ID such as `2609.0002` alone is not enough, because generated or
  copied specs can reuse it); or the file is a test or source file that
  only this spec's implementation touches. Replace it.
- **Not a scenario** — for example AWS `S3`, a size class, a CSS or
  hardware name, a hex value, a variable name (`S14=(…)`), or fixture data
  inside a test (a mock spec or mock ledger that a test reads), or a string
  literal in test code that matches such fixture data. Leave it: changing
  it can change what the test checks.
- **Ambiguous** — you cannot tell which spec it belongs to, or if it is a
  scenario at all. **Do not guess.** Leave it and list it in the report.

### 4. Replace

| Form | Before | After |
|------|--------|-------|
| Scenario label | `- **S3:** Given …` | `- **Expired coupon is rejected:** Given …` |
| Reference in prose | "the S3 case" | "the \"Expired coupon is rejected\" case" |
| List or range | "S1–S3", "S5, S6" | the quoted titles, or a sentence that names the group ("the three happy-path scenarios") |
| Partition | "S1–S11 are X; S12, S13 are Y" | "the scenarios other than the ones below are X; \"A\" and \"B\" are Y" |
| Count over all scenarios | "S1…SN", or a range that covers every scenario | "every acceptance scenario" |
| ID with a gloss | "S5 (referee byte-identical)" | "\"Referee file is byte-identical\"" — drop the gloss when the title says the same |
| Possessive | "S32's ceilings" | "the ceilings of \"Prompt files stay within size ceilings\"" |
| Reference inside another scenario's text | "see S6" | "see \"Referee treats input as unknown\"" — change only the ID token |
| Ledger cell | `S12 "all three kinds" has no assertion` | `"all three kinds" in "Harness counts the ledger" has no assertion` — keep the finding's own words |
| Test text, comment, docstring | `# covers S3` | `# covers "Expired coupon is rejected"` |
| Test function name | `test_s3_expired` | `test_expired_coupon_is_rejected` |

Rename a test function only if no other file contains its name (check with
`git grep -nw`), because test selectors in CI or scripts can use it. Any
mention counts, also one in a comment. If another file contains the name,
change only the comment or docstring and list the name in the report.

### 5. Check

Do all of these before you report:

- In each migrated spec, every scenario has a title, and no two titles are
  the same.
- The search from step 3 finds no scenario reference that you classified as
  "owner known", except the test names that step 4 kept because another file
  contains them.
- The spec's Given/When/Then text is unchanged: compare `git diff` and
  confirm that only labels and references changed.
- If you changed a test file, run the test suite. It must pass with the same
  number of tests as before. If the repo has no test suite, say so in the
  report and check instead that no other file uses a name you changed.

### 6. Report

- The title map for each spec.
- The files you changed.
- Ambiguous hits you left, with `file:line` and the reason.
- Test functions you did not rename, with the file that uses the name.
- The test-suite result, if you changed a test file.

## Principles

- One spec at a time. Its numbers mean nothing outside it.
- Change names, not behavior. The scenario text, the test logic and the code
  stay the same.
- When you are not sure, leave the hit and report it.
- Output guideline: keep the titles, the report and your replies 80% of the
  way to ASD-STE100 (Simplified Technical English).

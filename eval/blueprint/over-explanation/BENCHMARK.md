# BLUEPRINT-BENCH v1 — frozen contract

Single source of truth for the C/U/O benchmark built on the issue-#10 harness. Every threshold here is a number, pre-registered in `preregistration/manifest.*.json` and covered by `PreRegistration.content_hash()`. Implementers build against this file; deviations require a manifest version bump (hash change is the audit trail).

## 0. Frame

| Term | Definition |
|---|---|
| cell | `(arm, brief, seed)`; dir `results/<brief>/<arm>/seed-<seed>/` (C), `impl/<brief>/<arm>/seed-<seed>/` (U/O) |
| unit of analysis | **brief**. Seeds collapse via `stats.average_to_brief({seed: v})` before any test |
| delta | `Δ_b = v(treat, b) − v(A0, b)`. One sign convention: **negative = win** for cost metrics; quality metrics are negated on entry |
| inference | on deltas only: `paired_wilcoxon` + `bootstrap_ci(seed=0)` + `leave_one_brief_out.sign_stable` + `holm_correction` over the win-family `{C1, U1}`; guardrail p-family `{C3, U2, U3, O1, O3}` Holm'd separately |
| C scope | 8 arms × 9 briefs × 2 seeds = **144** cells |
| U/O scope | `u_arms = {A0, A1, A2_placebo, A3_fair, A3b_dumb}` × 6 buildable briefs × 2 seeds = **60** implementer cells. `A3b_dumb` is in `u_arms` **only** to supply U1f's length-strip leg; it authorizes no ship clause |
| buildable | `{b01, b02, b03, b05, b06, b08}` (n=6). `buildable ∩ large_realistic = {b02}` (n=1) |
| N ceiling | N=9/K=2 ⇒ verdict ceiling `promising_scale_to_n18`; U/O stratum n=1 ⇒ **structurally `UNDERPOWERED`** at demo scale (top-level `strata_certifiable:false`) |
| sandbox test cmd | `["<sys.executable>", "-m", "pytest", "-q", "-p", "no:cacheprovider"]` — frozen. `uv run` is for *harness* invocation only; the `run_mutations` tempdir copy has no `pyproject.toml` and `uv run` would fail there |
| token index | `TOKENS = re.compile(r"\S+")`. Whitespace tokens. `code_tok` is a **unitless index**, never called a model token count |
| interface pin | `run_oracle` imports `brief.module` and calls `brief.entrypoint`. The implementer prompt therefore **must** carry those two names, or every arm scores `correctness = 0.0` and O1's gate voids the whole run. They are injected by fixed template substitution (§3 `run-implementer.sh`), identical across arms. **This is not brief leakage**: the harness reads `brief.json`, the implementer never does, and `leak_hits` stays 0 |

Fail-closed chain, stated once: a missing/garbled cell yields `status="missing"` → **excluded and counted**, never imputed and never zero → raises `incomplete_fraction` → `> 0.10` in any arm ⇒ `scorable:false`, exit 4. Without this, an arm that crashes half its U cells scores as the cheapest arm.

---

## 1. Dimension tables

### C — Conciseness (input task: `scripts/run-arm.sh <ARM> <BRIEF_DIR> <SEED>` → design doc + spec; all 9 briefs)

| id | metric formula | mechanical source (file → field) | pass threshold |
|---|---|---|---|
| **C0** generate isolation | `leak_hits` = same §1-U0 word-boundary patterns, over **all** `tool_use` blocks of every generate-cell transcript. `count_leaks` records **every distinct matched fragment per tool_use** (never only the first match), so the ONE stage exemption — bare `brief.md`/`brief.json` fragments are the cell's own staged input (the generate agent must read the brief) and are dropped — is **order-independent**: a single command touching both `brief.md` and `corpus/<b>/oracle.py` yields separate hits for `brief.md`, `corpus` and `oracle.py`, the exemption drops only the `brief.*` fragments, and a tool_use is exempt **only when NO non-exempt fragment matched it**. Summed across the arm's C cells into `GateValues.c0_leak_hits: int \| None` — `None` when **any** generate cell records `leak_scanned:false` | `run-arm.sh` post-hoc scan (`deadend.count_leaks`, `bench.leak_patterns`) → `cell.json.{leak_scanned, leak_hits, leak_hit_details}` + `cell.json.workspace_outside_repo` (§3 `run-arm.sh`); an unscanned cell records `leak_scanned:false` — no signal, never a pass — and `run-arm.sh` **exits non-zero** for it; the packer maps any unscanned generate cell to `c0_leak_hits: null` | `leak_hits == 0` on 100% of generate cells — **GATE** (`C0_generate_isolation`, §2 row 6); `c0_leak_hits = None` **FAILS** the gate (no signal is never a pass). The U0 analogue for the C stage: a spec author that greps `corpus/` has read the oracle. Enforcement is a **post-hoc transcript scan**, not a filesystem restriction — cwd-outside-repo only removes relative-path reach; the scan is what catches absolute-path touches |
| **C1** restatement Δ *(primary, #10)* | `r = 1 − distinct/total_mentions` (`restatement.restatement_rate`); `Δ_b = r_treat − r_A0` | `results/results.json:records[].propositions` (≥2 extractor families) | Holm-adj `p < 0.05` **and** `bootstrap_ci.high < 0` **and** `mean Δ ≤ −max(c1_gate_floor, 2.0 × noise_floor_C)` (absolute floor `c1_gate_floor = 0.025`, same convention as `T_C`/`T_U` — a zero/degenerate noise floor never makes any negative delta a free win) **and** `leave_one_brief_out.sign_stable == True` **and** sign holds on the `large_realistic` subset (n=3). `noise_floor_C`/`noise_floor_U` themselves are domain-checked at score load: `≤ 0` or non-finite (the `estimate_noise_floor` empty-input value — no baseline replicate data existed) is a LOAD ERROR, never free significance |
| **C2** MUST retention | `substance.proposition_recall(substance_alignment).dropped_must` | `records[].substance_alignment` (source = A0 set) | `len(dropped_must) == 0` — **GATE** |
| **C3** coverage non-inferiority | `proposition_recall(...).recall`; `tost(A0, arm, margin=0.05, min_power=0.8)` | same | `non_inferior == True` (**GATE** `C3_coverage_noninferiority`, §2 row 6 — measured content loss never ships) **and** `certifiable == True` (§2 row 8 — underpowered never reads as safe). Both flags are **RECOMPUTED by the scorer** from the transported per-family raw TOST numerics (`tost["C3"]`: `estimate`/`ci90`/`p_value`/`achieved_power`/`margin`): `non_inferior` iff the 90% CI lies strictly inside `±tost_margins["C3"]`, `certifiable` iff `achieved_power ≥ min_power` — packed booleans are at most cross-checks (mismatch = load error), and a packed `margin` contradicting `bench.tost_margins` is a load error |
| **C4** purity (extraneous share) | `purity = |links_for(relation != DROPPED)| / target.distinct` on `align(source=doc, target=gold)`; repetition-invariant | `records[].purity_alignment` + `corpus/<b>/gold_propositions.json` | **REPORTED ONLY, DEFERRED in v1**: no decoy battery covers reverse alignment, and it needs a third per-cell alignment (`+2 × 144 = 288` extractor calls) for a metric that gates nothing. Ship the code, enable behind `--with-purity` |
| **C5** length STOP | `stats.length_falsification_stop(ΔC1, Δword_count, Δ(A3b−A0), noise_floor=noise_floor_C)` | `records[].word_count` | `stop == False` — **STOP**, evaluated before any C number is read |
| **C6** dilution STOP | `stats.partial_out_length(ΔC1, Δdistinct_count, noise_floor=noise_floor_C).survives` | `records[].propositions` → `distinct` | `survives == True` — **STOP**. Closes "pad with novel non-repeating claims": +1 distinct single-mention prop moves `(d5,m10)=0.500 → (d6,m11)=0.455` with zero redundancy removed |
| **C7** merge fidelity | `merge_fidelity(merge_alignment).ok` | `records[].merge_alignment` (fail-closed: absent ⇒ skipped, never a pass) | `ok == True` on every non-skipped cell — **GATE**; `merge_skipped_fraction ≤ 0.30` else `scorable:false` |
| **C8** grammaticality | `DefaultGrammaticalityChecker.check(split_sentences(text))`; `frag_rate = len(fragments)/len(verdicts)` | `records[].sentences` | `frag_rate ≤ frag_rate_cap` (**calibrated**: `max(frag_rate over all A0+A0_prime cells) + 0.02`, floor 0.05) **and** `tost(A0, arm, margin=0.02, min_power=0.8)` with its two flags **RECOMPUTED SPLIT, exactly like C3**, from the raw `tost["C8"]` numerics: `non_inferior` (§2 row 6 **GATE** leg) and `certifiable` (§2 row 8) — a C8 **power gap routes to row 8 `UNDERPOWERED`, never to a row-6 `DO_NOT_SHIP`** (the old conflated caller boolean collapsed both legs into the gate). `split_sentences` splits on newlines, so markdown headings are fragments in A0 too; an absolute `== 0` gate would void the baseline |
| **C9** A3b control | `A3b_dumb` must **fail** C8 | same | `a3b_fails_grammaticality == True` else DO_NOT_SHIP (existing `decide` branch 2) |
| **C-cov** | `Δword_count`, `Δdistinct` | `records[]` | logged covariates, never targets |

`noise_floor_C = estimate_noise_floor(same_arm_seed_spread, placebo_deltas)` from A0/A0_prime, computed once, written to `results.json:noise_floor`.

### U — Usefulness (input task: `scripts/run-implementer.sh` — FIXED pinned implementer, prompt = captured spec text only; 6 buildable briefs)

| id | metric formula | mechanical source | pass threshold |
|---|---|---|---|
| **U0** isolation | `prompt_sha == sha256(render(PREAMBLE_TEMPLATE, module, entrypoint) + "\n\n" + spec_text)` — normalization FROZEN so a verifier can re-derive the hash: `spec_text` is the spec file's UTF-8 text with **all trailing newlines stripped** (POSIX `$(cat …)` command-substitution semantics), the joiner is exactly one `"\n\n"`, and the digest is over the exact UTF-8 bytes of that string with **no newline appended** (`printf '%s'` piping); `spec_sha` by contrast hashes the **raw file bytes** untouched — **and** `preamble_template_sha` matches the manifest (the template, not the rendering, is what must be arm-identical); workspace created **outside the repo tree**; `leak_hits` = count of **(tool_use, distinct matched fragment)** pairs where the serialized input (or any string leaf) matches /\bcorpus\b\|\bbrief\.(md\|json)\b\|\bgold_propositions\.json\b\|\bcases(_holdout)?\.json\b\|\boracle\.py\b\|\bmutations\.json\b/ over **all** tools (Read/Grep/Glob/Bash/WebFetch) — word-boundary, **not** path-anchored, so `ls corpus` and `grep -r expected corpus/` hit; every distinct fragment counts (strictly more sensitive than one-hit-per-tool_use; the gate is `== 0` either way) | `impl-cell.json.prompt_sha`, `impl-cell.json.workspace`, `transcript.jsonl` tool_use blocks | `prompt_sha` matches **and** `leak_hits == 0` on 100% of U cells — **GATE**. Reachability, not listing: cwd outside the repo is what makes O1/O2 mean anything |
| **U1** spend | `spend = output_tokens + code_tok(spec)`; metric `ln(spend)`; `Δ_b = ln s_treat − ln s_A0` | `transcript.jsonl` final `{"type":"result"}` → `usage.output_tokens`; `code_tok` = `deadend.code_token_count`: `TOKENS` count over **whole-document detected code lines** (fenced bodies ∪ 4-space/tab-indented lines ∪ per-line Python classifier — same detector as L1, so unfenced code cannot dodge cost conservation) of `artifacts/**/*spec*.md`. **`input_tokens` excluded** — it is spec length, i.e. the forbidden length proxy | `Δ ≤ −T_U`, `T_U = max(0.1054, 2 × noise_floor_U)` (`0.1054 = |ln 0.9|`, a 10% saving) **and** Holm-adj `p < 0.05`. **Pre-STOP**: `2 × noise_floor_U > 0.1054` ⇒ STOP `"target below detectable floor"`, fires before any U number is read. The win legs are **recomputed by the scorer** from packed `U1Stats` (`u1_failures`, §2 row 10) — never accepted as a caller boolean |
| **U1f** U falsification | `partial_out_length(ΔU1, Δ ln(spec_words), noise_floor=noise_floor_U)` + `length_falsification_stop(..., length_strip_deltas=Δ(A3b−A0))` | spec word count | `survives_partialling == True` **and** `length_strip_reproduces == False` — **STOP** |
| **U2** turns | `num_turns`; `tost(A0, arm, margin=1.0, min_power=0.8)` | result event → `num_turns` (authoritative; never sum assistant lines) | `non_inferior` (**GATE** `U2_turns_noninferiority`, §2 row 6; recomputed from `tost["U2"]`) `and certifiable` (§2 row 8, recomputed) |
| **U3** dead ends | `de = reverted_edits + failed_test_cycles`; `tost(margin=1.0)` | `deadend.py` over paired `tool_use`/`tool_result` | `non_inferior` (**GATE** `U3_deadend_noninferiority`, §2 row 6; recomputed from `tost["U3"]`) `and certifiable` (§2 row 8, recomputed) **and** per-cell `de ≤ 6` — **GATE** on the cap |
| **U4** completion | `result.subtype == "success"` | result event | 100% of U cells — **GATE**. No result event ⇒ `status="missing"` ⇒ excluded+counted (never zeros) |
| **U5** clarifying questions | `q = |{tool_use where name == "AskUserQuestion"}|` | `transcript.jsonl` | `q == 0` — **GATE**. Trailing-`?` count in the final assistant text is a **reported** diagnostic only |
| **U6** cost | `total_cost_usd` | result event | **budget layer only**, never scored (pricing/cache dependent) |

### O — Outcome (input task: implementer's final workspace vs frozen corpus assets; 6 buildable briefs)

| id | metric formula | mechanical source | pass threshold |
|---|---|---|---|
| **O1** correctness | `run_oracle(impl_dir, brief.module, brief.entrypoint, load_oracle_cases(b)).correctness` | `corpus/<b>/cases.json` (frozen, identical every arm) | `mean correctness ≥ 0.90` **and** `tost(A0, arm, margin=0.05).non_inferior` **and** cell-level regression gate `correctness_treat ≥ correctness_A0` for every `(b, seed)` — **GATE**. Per-case regression is **reported only** (recoverable from the documented `"<label>: <error>"` prefix in `OracleResult.errors`, but parsing error strings is not gate-grade) |
| **O2** holdout overfit | `overfit = correctness(cases.json) − correctness(cases_holdout.json)` | `corpus/<b>/cases_holdout.json` (blind-authored, arg literals disjoint from `brief.md` tokens, never in any prompt) | `overfit ≤ 0.10` — **GATE**, fail-closed exactly like O3: an aggregate `overfit` of `None` with `o2_skipped_fraction` **at or under** the 0.30 cap **FAILS** the gate (dropping one's own holdouts is a controllable act); only an over-cap accounted skip omits the gate and routes to §2 row 9 (`UNDERPOWERED`). File absent ⇒ cell **skipped, no signal, never a pass**; > 30% of buildable briefs lacking holdout ⇒ dimension O `UNDERPOWERED` |
| **O3** mutation kill | **smoke first**: run the frozen `test_cmd` against the *unmutated* merged reference dir (`corpus/<b>/oracle.py` + arm's `tests/`, assembled by the CLI per §3); exit != 0 ⇒ cell yields **no O3 signal** (a non-importing suite errors on every mutant and would otherwise score kill_rate 1.0). Then `run_mutations(impl_dir=reference+arm tests, test_cmd, mutations)`; `kill_rate = killed/(killed+survived)` | `corpus/<b>/mutations.json` (**NEW**, blind-authored, 8/brief, 48 total) + arm `workspace/tests/` | `kill_rate ≥ 0.75` **and** `tost(A0, arm, margin=0.10).non_inferior` (recomputed from the raw `tost["O3"]` numerics, enforced inside the `O3_mutation_kill` gate) **and** `len(invalid) == 0` (frozen reference ⇒ find-count is 1 by construction, so the denominator is arm-independent) |
| **O4** workaround lint | AST count (never `exec`) of: `@pytest.mark.skip|skipif|xfail`; bare `assert True`; `try/…/except: pass`; any `Return(Constant)` whose value `==` a `cases.json` `expected`; `NotImplementedError`; `TODO`/`FIXME` in a non-test impl file | implementer workspace `**/*.py` + `cases.json` | `workarounds == 0` — **GATE** |
| **O5** bloat | `ln(sloc(impl) / sloc(corpus/<b>/oracle.py))`, logical lines (comments/blanks stripped) | implementer workspace vs frozen reference | reported + scored; soft cap `ln 3 = 1.0986`; **no gate** |

### L — Leakage control (spec-embeds-implementation; lives in `deadend.py`)

| id | metric formula | source | pass threshold |
|---|---|---|---|
| **L1** code fraction | `code_frac = code_tok(detected code lines) / TOKENS(spec)` — **whole-document** detection (`deadend.spec_code_lines`): fenced bodies ∪ 4-space/tab-indented lines ∪ per-line Python classifier, the last two evaluated on the raw line **and** on its **dressing-stripped** form (`_dedress`: leading `>`/`-`/`*`/`+`/`|`/`1.` markers removed iteratively, indentation preserved, trailing table `|` dropped); fence parsing tolerant of dangling and parity-desynced fences (a stray bare ``` never pushes code "outside"). Detected lines are returned RAW — a dressing may add tokens, never subtract them. Every classifier pattern is `^`-anchored, so before `_dedress` a verbatim oracle pasted as a blockquote, a bullet list or a markdown table detected **0 of 12** lines: L1=L2=L3=0.0 and `code_tok`=0, which also bypassed U1's cost conservation | `artifacts/**/*spec*.md` | `≤ leak_code_frac_cap` = **calibrated** `max(over A0+A0_prime cells) + 0.05`, floor **0.15** |
| **L2** spec↔reference | **REFERENCE-denominated presence**: matched 5-grams / `|grams(oracle.py)|`, i.e. *how much of the reference is in the spec*, as `max` of three channels — `reference → spec_code` (`deadend.spec_code_source`: detected lines in raw **and** dressing-stripped form), `reference → the raw spec token stream` (a dressing-agnostic backstop), and the LEGACY spec-denominated `spec_code → reference` (kept only for partial-paste sensitivity: three lines lifted from a 100-line oracle read 1.0 spec-denominated and 0.03 reference-denominated). Every channel is itself the **max of raw and identifier-skeleton token channels** (non-keyword identifiers → placeholder, so renaming/re-expression cannot zero the signal). The reference side is **docstring-stripped** (`ast`, never `exec`) first — in the skeleton channel a docstring's prose words collapse to one placeholder and would match ordinary honest spec prose (measured **0.092** across the honest-fixture × corpus-oracle sweep, **0.000** stripped). The denominator swap is the point: spec-denominated only, L2 is author-controlled — 10 ordinary indented JSON examples appended to a spec that still carries the verbatim oracle walk it from **0.758 to 0.245**, under the cap, with nothing removed | spec + `corpus/<b>/oracle.py` | `≤ leak_reference_cap` = calibrated `max(honest) + 0.05`, floor **0.25** |
| **L3** impl↔spec | `ngram_containment(impl_source, spec_code, n=5)`, same whole-document `spec_code` (`deadend.spec_code_source`, both dressings) and same two-channel containment as L2. `impl_source` is the **non-test** `*.py` surface of the workspace — the same surface O5 sizes. Test files are excluded because L3's denominator is the impl: a padded generated suite dropped a verbatim transcription from **1.0 to 0.038** with the implementation still a copy. The arm's tests are scored by O3 mutation kill, never by containment | implementer workspace (non-test `*.py`) + spec | `≤ leak_copy_cap` = calibrated `max(honest) + 0.05`, floor **0.30** |
| **L4** executed control | assemble the executable candidate with `deadend.spec_python_source` over the SAME whole-document detection L1–L3 measure (fenced ∪ indented ∪ classifier lines, raw ∪ dressing-stripped): three cascade levels, each tried only when the one above fails to parse (`ast.parse`, never `exec`) and each trying raw lines before their dressing-stripped form — (1) the whole detected set common-dedented, (2) each maximal detected line-run, (3) each blank-line-separated group inside a run (runs break only on non-blank prose, so a payload example one BLANK LINE above the paste is part of the same run and level 3 is what keeps L4 alive there) — write it to `<tempdir>/<brief.module>.py` → `run_oracle(...)` → `spec_only_correctness`. Two dead ends closed: fenced-only extraction (one working implementation embedded as 4-space-INDENTED markdown executed nothing while sliding under the L1–L3 caps) and all-or-nothing assembly (one ordinary indented non-Python example — a transport sample, a payload listing — made the candidate a syntax error, reported as *no signal*, so the working implementation beside it was never executed, whether separated by prose or by a single blank line) | spec + `cases.json` | `< 0.5`. `≥ 0.5` ⇒ the spec *is* the implementation. If the assembled source does not import, emit **no L4 signal** (`null`, flagged) — a non-import must never read as clean; L1–L3 carry the gate. In the score transport `l4_spec_only_correctness` is **REQUIRED-nullable**: explicit `null` = no signal (emitted + flagged), an ABSENT key = load error (matching `c0_leak_hits`) — deleting the key must never drop the gate with no schema trace. The "flagged" half is `score.json`'s `arms.<ARM>.l4_no_signal: bool` (§2 exact keys): a null value emits no `L4_spec_only_correctness` GateCheck (L1–L3 carry the gate, so this never blocks on its own) but `l4_no_signal` is ALWAYS rendered, so the null leaves a greppable trace for the `human_read_required` gate instead of vanishing with no schema footprint |
| — | any of L1–L4 fails ⇒ **that arm's U and O subscores void to 0.0** (arm-local, not run-wide); on the **treatment** arm the run is additionally blocked at §2 precedence #7 (`DO_NOT_SHIP`, exit 1) — a detected leak never ships | | |

Calibration protocol (all four caps + `frag_rate_cap`): compute over **every A0 and A0_prime cell**, take `max(honest) + ε`, write into the manifest, re-hash, and freeze **before any treated arm is generated**. Floors above apply if the calibrated value is lower. **The L caps require recalibration on A0/A0_prime under the whole-document detector** — the detector counts strictly more code (indented/classifier lines, skeleton-channel containment) than the fence-only one the floors were first drafted against, **and L4's executed control now runs over that same whole-document surface** (an honest A0 spec whose prose lines trip the per-line classifier will typically assemble to a non-importing source — no signal, flagged — but the calibration pass must confirm no honest cell crosses `spec_only_correctness ≥ 0.5`); the floor NUMBERS are unchanged pending that recalibration. **L2's denominator swap does not move the honest floor**: reference-denominated presence asks how much of the frozen oracle appears in the spec, and an honest spec contains none of it — the honest-fixture × corpus-oracle sweep measures **0.000 on all three channels** (0.092 on the raw-stream channel *before* docstring-stripping the reference, which is why that strip is mandatory). Padding can only lower the legacy channel, which enters the `max`, so dilution cannot lower L2 as a whole; the calibration pass still runs all three channels over A0/A0_prime.

---

## 2. `score.json` schema, composite, gates

### Precedence (first match wins; extends `decision.decide`, never overrides it)

| # | condition | outcome | exit |
|---|---|---|---|
| 0 | manifest hash mismatch or `validate()` non-empty | `scorable:false`, `reason:"manifest_invalid"` | 4 |
| 1 | `instrument.instrument_trust_gate(...).trusted == False` | `DO_NOT_SHIP`, **no per-arm numbers emitted** | 1 |
| 2 | benchmark-trust gate fails (§5 G-BT) | `scorable:false`, `reason:"benchmark_blind"` | 4 |
| 3 | `a3b_fails_grammaticality == False` | `DO_NOT_SHIP` (positive control dead) | 1 |
| 4 | any STOP fired (C5, C6, U1 pre-STOP, U1f) | `DO_NOT_SHIP` | 1 |
| 5 | `incomplete_fraction > 0.10` \| `merge_skipped_fraction > 0.30` \| budget exhausted | `scorable:false` | 4 |
| 6 | any hard GATE fails (C0, C2, C3-NI, C7, C8, U0, U2-NI, U3-cap, U3-NI, U4, U5, O1, O2, O3, O4) | `DO_NOT_SHIP` | 1 |
| 7 | any leakage gate (L1–L4) fails on the **treatment** arm (`leakage_voided`) | `DO_NOT_SHIP` — the arm's U/O subscores are voided to 0.0 *and* the run is blocked; a detected leak never ships | 1 |
| 8 | any required TOST not certifiable — **recomputed** as `achieved_power < min_power` from the packed raw `tost` numerics (an absent family already failed its row-6 gate) | `UNDERPOWERED` — *"underpowered to certify safety — do not ship"* | 1 |
| 9 | any dimension's required stratum `n < 3` | that dimension forced `UNDERPOWERED` + verdict ceiling | 1 |
| 10 | any §1 win-family sub-threshold fails — **C1**: Holm-adj `p < 0.05`, `ci.high < 0`, `mean Δ ≤ −c1_gate_noise_multiple × noise_floor_C`, `sign_stable`, `large_realistic` sign; **U1**: Holm-adj `p < 0.05`, `mean Δ ≤ −T_U` — **recomputed by the scorer from the raw packed statistics** (`c1_failures`/`u1_failures`), never accepted as a caller boolean | `DO_NOT_SHIP` | 1 |
| 11 | treatment `composite < composite_pass` (70) | `DO_NOT_SHIP` — composite ≥ pass is **necessary**, never sufficient | 1 |
| 12 | `a4_captures_effect` | `SHIP_EVALUATOR_ONLY` | 0 |
| 13 | `not beats_a3_fair.beats` | `SHIP_ONELINER` | 0 |
| 14 | `not beats_a2_placebo.beats` | `DO_NOT_SHIP` | 1 |
| 15 | else | `SHIP_TREATMENT`, capped to `promising_scale_to_n18` when N<18 | 0 |

Exit codes: `0` scored & passing · `1` scored & blocked/STOP/no-ship · `2` usage · `3` load error · `4` **not scorable** (never scored). A partial composite is never emitted.

### Composite

```
clip(x) = min(1, max(0, x))
T_C   = max(0.05, c_scale_noise_multiple × noise_floor_C)   # c_scale_noise_multiple = 4.0
T_U   = max(0.1054, 2.0 × noise_floor_U)
den_C = max(T_C − noise_floor_C, 0.02)      # knife-edge floor
den_U = max(T_U − noise_floor_U, 0.05)      # knife-edge floor
S_C = 100 × clip((−mean_ΔC1 − noise_floor_C) / den_C)          # 0 at the noise floor
S_U = 100 × clip((−mean_ΔU1 − noise_floor_U) / den_U)          # 0 if leakage gate failed
S_O = 100 × (0.50 × mean_correctness_holdout        # HOLDOUT only — never substituted with visible-case O1
           + 0.30 × mean_kill_rate
           + 0.20 × clip(1 − max(0, O5) / 1.0986))
composite = 0.30×S_C + 0.30×S_U + 0.40×S_O
meets = composite ≥ 70                               # enforced at precedence row 11
```

**The two C noise multiples are distinct fields on purpose.** `c1_gate_noise_multiple = 2.0` is the §1-C1 *gate* (`mean Δ ≤ −2.0 × noise_floor_C`, precedence #10); `c_scale_noise_multiple = 4.0` is the composite *scale* (`T_C` above). Wiring one name into both would halve `T_C` and inflate `S_C` by up to 15 points — the manifest (§4) and `ScoreThresholds` carry both names separately.

**Missing-signal rule for `S_O` (no measurement may silently become a number, and dropping a term may never RAISE the score).** A brief contributes an O2 or O3 term only if that term has signal (holdout present / smoke green + `mutations.json` present). For each of the two terms: `skipped_fraction > 0.30` over buildable briefs ⇒ dimension **O forced `UNDERPOWERED`** (precedence #9). Aggregate rules, **UNIFORM**, monotone and fail-closed:

* correctness and kill both missing ⇒ `S_O = 0.0` outright — the bloat term alone must never carry the dimension (all-signal-missing ⇒ 0.0 a fortiori);
* **every** missing term scores **0 within its ORIGINAL weight** — the surviving weights are **never** renormalized upward, so `S_O` with a term missing can never exceed `S_O` with that term measured at any value. There is no renormalization exception (the old one let a dropped kill term outscore a measured one). Accounted skips change **routing only**: with `o2_/o3_skipped_fraction` at or under the 0.30 cap an aggregate value must exist, so `overfit = None` **FAILS the O2 hard gate** and `kill_rate = None` **FAILS the O3 hard gate** (precedence #6) — breaking one's own holdouts or smoke is a controllable act; over the cap the gate is omitted (skipped, never a pass) and row 9 forces O `UNDERPOWERED`. The `o2_/o3_skipped_fraction` values themselves are **derived by the scorer** from the packed cell counts (`holdout_skipped`/`mutations_skipped` over the manifest panel's expected implement cells) — a packed fraction is at most a cross-check (3-decimal mismatch = load error), never the source, so an understated fraction can never route a skip-heavy arm past the gate or past row 9. `dimensions.O.renormalized` remains in the schema as a **purely descriptive** flag with exactly one meaning: an accounted **OVER-cap** O3 skip dropped the kill term (the only state where a missing kill rate is not itself an O3 gate failure). It changes no arithmetic and is computed independently of leakage voiding — never `True` on an under-cap gate-failing run, never `False` merely because the arm was voided;
* the correctness term is the **holdout mean only**: `correctness_holdout = None` scores 0 in its original 0.50 weight and emits `dimensions.O.correctness_holdout_missing: true` — it is **never silently substituted** with visible-case O1 (that would hand O2's weight to the very cases O2 exists to distrust);
* a dropped term is never imputed as 0.0-measured and never as 1.0; `o2_skipped_fraction` / `o3_skipped_fraction` are always emitted (3-decimal rounded).

`composite ≥ 70` is **necessary, never sufficient** — enforced at precedence #11 (`composite < composite_pass` ⇒ `DO_NOT_SHIP`, exit 1). `authorizes_ship` is always `false`; a ship verdict comes from the precedence table alone.

### Exact keys

```json
{
  "schema": "blueprint-bench/1",
  "manifest_content_hash": "sha256:…",
  "generated_at": "2026-08-13T00:00:00Z",
  "scorable": true,
  "reason": null,
  "instrument_trusted": true,
  "benchmark_trusted": true,
  "human_read_required": true,
  "n_briefs": 9,
  "n_buildable": 6,
  "k_seeds": 2,
  "extractor_families": ["anthropic-claude", "openai-gpt"],
  "noise_floor": {"C": 0.031, "U": 0.084},
  "strata_certifiable": false,
  "strata_coverage": {
    "C": {"elicit_prone": 3, "large_realistic": 3, "neutral": 3},
    "U": {"elicit_prone": 2, "large_realistic": 1, "neutral": 3},
    "O": {"elicit_prone": 2, "large_realistic": 1, "neutral": 3}
  },
  "stops": {
    "c_length_falsification": false,
    "c_distinct_dilution": false,
    "u_below_detectable_floor": false,
    "u_length_falsification": false
  },
  "arms_compared": {"baseline": "A0", "treatment": "A1"},
  "arms": {
    "A1": {
      "cells": {
        "generate": {"expected": 18, "complete": 18, "missing": 0, "timeout": 0, "error": 0,
                     "retried": 0, "incomplete_fraction": 0.0,
                     "merge_skipped": 2, "merge_skipped_fraction": 0.111,
                     "mutations_skipped": 0, "holdout_skipped": 0},
        "implement": {"expected": 12, "complete": 12, "missing": 0, "timeout": 0, "error": 0,
                      "retried": 1, "incomplete_fraction": 0.0,
                      "merge_skipped": 0, "merge_skipped_fraction": 0.0,
                      "mutations_skipped": 1, "holdout_skipped": 0}
      },
      "gates": [
        {"id": "C2_must_retention", "value": 0, "threshold": 0, "passed": true},
        {"id": "L3_impl_spec_copy", "value": 0.11, "threshold": 0.30, "passed": true}
      ],
      "gates_blocked": false,
      "gates_failed": [],
      "l4_no_signal": false,
      "leakage_voided": false,
      "dimensions": {
        "C": {"metrics": {"C1": {"mean_delta": -0.11, "ci": [-0.18, -0.04], "p": 0.008,
                                 "p_holm": 0.024, "sign_stable": true, "n": 9,
                                 "large_realistic_delta": -0.10},
                          "C3": {"tost": {"non_inferior": true, "power": 0.86, "certifiable": true}},
                          "C4": {"delta_purity": -0.004, "reported_only": true},
                          "C8": {"frag_rate": 0.03, "cap": 0.05,
                                 "tost": {"non_inferior": true, "power": 0.83, "certifiable": true}}},
              "covariates": {"word_count_delta": -210.0, "distinct_delta": -1.2},
              "subscore": 84.95, "verdict": "promising"},
        "U": {"metrics": {"U1": {"mean_delta": -0.23, "p_holm": 0.02, "spend_index": 4821.0},
                          "U2": {"tost": {"non_inferior": true, "power": 0.86, "certifiable": true}},
                          "U3": {"mean": 1.5, "max_cell": 4,
                                 "tost": {"non_inferior": true, "power": 0.81, "certifiable": true}},
                          "U5": {"clarifying_questions": 0, "trailing_question_marks": 2}},
              "subscore": 100.0, "verdict": "underpowered"},
        "O": {"metrics": {"O1": {"correctness": 0.94, "regressed_cells": []},
                          "O2": {"overfit": 0.04, "skipped_briefs": []},
                          "O3": {"kill_rate": 0.78, "invalid": 0, "smoke_failed_cells": 1},
                          "O4": {"workarounds": 0},
                          "O5": {"bloat_ln": 0.11}},
              "renormalized": false, "o2_skipped_fraction": 0.0, "o3_skipped_fraction": 0.083,
              "correctness_holdout_missing": false,
              "subscore": 86.4, "verdict": "underpowered"}
      },
      "composite": {"weights": {"C": 0.30, "U": 0.30, "O": 0.40},
                    "value": 90.04, "pass_threshold": 70, "meets": true,
                    "authorizes_ship": false}
    }
  },
  "budget": {"spent_usd": 41.2, "projected_usd": 68.9, "max_usd": 120.0, "exhausted": false},
  "verdict": "underpowered_no_ship",
  "verdict_reasons": ["U/O stratum large_realistic n=1 < 3 — structurally uncertifiable at demo scale"],
  "ceiling": "promising_scale_to_n18"
}
```

Serialization is canonical: `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` — byte-stable, asserted against a golden fixture.

---

## 3. Module contracts

Style, mandatory: `from __future__ import annotations`; frozen dataclasses; pure functions over already-parsed dicts; rich module docstring stating the assumption each formula makes; **no new Protocols** (the implementer is a data producer, not a non-deterministic seam the harness calls).

### `src/eval_overexplanation/usage.py`

```python
@dataclass(frozen=True)
class UsageReport:
    status: str            # "ok" | "missing" | "timeout" | "error"
    subtype: str | None    # result.subtype; None when status != "ok"
    num_turns: int | None
    output_tokens: int | None
    input_tokens: int | None            # recorded, NEVER scored (length proxy)
    cache_read_input_tokens: int | None  # diagnostic only
    total_cost_usd: float | None
    duration_ms: int | None
    detail: str = ""

def parse_usage(lines: Iterable[str], *, return_code: int = 0) -> UsageReport
def spend_index(report: UsageReport, code_tokens: int) -> float   # ln(output_tokens + code_tokens)
```

**FAIL-CLOSED contract, non-negotiable:** a transcript with no `{"type":"result"}` event yields `UsageReport(status="missing", ...)` with **every numeric field `None`** — never `0`. Zeros would make a crashed cell read as the cheapest cell and hand the arm a fraudulent U win. `rc == 124` ⇒ `status="timeout"`; `subtype == "error_during_execution"` or `"error_max_turns"` ⇒ `status="error"`. Malformed JSON lines are skipped, not fatal; the **last** result event wins. Missing/timeout/error cells are excluded from every U/O statistic **and counted** into `incomplete_fraction`; `> 0.10` ⇒ `scorable:false` exit 4.

### `src/eval_overexplanation/deadend.py`

```python
@dataclass(frozen=True)
class DeadEndReport:
    reverted_edits: int
    failed_test_cycles: int
    clarifying_questions: int
    trailing_question_marks: int     # reported diagnostic, never a gate
    leak_hits: tuple[str, ...]       # matched tool_use input fragments
    @property
    def dead_ends(self) -> int: ...  # reverted_edits + failed_test_cycles

@dataclass(frozen=True)
class WorkaroundReport:
    skips: int; assert_true: int; swallowed_except: int
    hardcoded_expectations: int; not_implemented: int; todos: int
    hits: tuple[str, ...]            # "<file>:<lineno>: <kind>"
    @property
    def total(self) -> int: ...

@dataclass(frozen=True)
class LeakageReport:
    code_frac: float; reference_containment: float; copy_containment: float
    spec_only_correctness: float; blocked: bool; reasons: tuple[str, ...]

def iter_tool_uses(lines: Iterable[str]) -> tuple[ToolUse, ...]   # lifted from analysis/assemble.py:_iter_tool_uses
def count_reverted_edits(tool_uses) -> int
def count_failed_test_cycles(tool_uses, tool_results) -> int
def count_clarifying_questions(tool_uses) -> int
def count_leaks(tool_uses, patterns: Sequence[str]) -> tuple[str, ...]
def deadend_report(lines, *, leak_patterns) -> DeadEndReport
def workaround_lint(src_dir: Path, cases: Sequence[OracleCase]) -> WorkaroundReport
def ngram_containment(a: str, b: str, *, n: int = 5) -> float
def spec_code_blocks(markdown: str) -> tuple[str, ...]   # fenced bodies only — retained fence-parsing utility (NOT a leakage surface)
def spec_code_lines(markdown: str) -> tuple[str, ...]    # whole-document detection, RAW lines — L1's numerator + code_tok
def spec_code_source(markdown: str) -> str               # the same lines in BOTH dressings — L2/L3's containment surface
def spec_python_source(markdown: str) -> str             # L4's executable candidate: the detected code that actually parses
def code_token_count(markdown: str) -> int               # code_tok(spec) for U1 + L1, same detector
def leakage_report(spec_md, reference_py, impl_src, spec_only_correctness, caps) -> LeakageReport
```

Definitions, frozen: **revert** = an `Edit` whose `new_string` equals an earlier `Edit.old_string` for the same `file_path`, **or** a `Write` whose `content` drops at least one pending earlier `Edit.new_string` for the same `file_path` (a clobber — the common abandonment path; one count per clobbering Write, pending edits superseded either way). **failed test cycle** = a `Bash` `tool_use` whose `input.command` matches the widened test-runner regex (`pytest` as a command word incl. path-prefixed, `python -m pytest|unittest`, `make test|check`, `tox`, `npm|yarn|pnpm test`, `cargo|go test`, `run[_-]tests` wrapper scripts, `*test(s).sh`) and whose paired `tool_result` (by `tool_use_id`) has `is_error == true`. Only top-level events (`parent_tool_use_id is null`) count. `workaround_lint` uses `ast` only — **never `exec`/`import`** on untrusted source. `ngram_containment` normalizes to lowercase `TOKENS`, strips Python comments, and returns the **max over two channels** — raw tokens and identifier-skeleton tokens (non-keyword identifiers → placeholder) — of `|shared 5-grams| / |a's 5-grams|` (0.0 when `a` has fewer than 5 tokens). **Spec code detection** for L1-L3 and `code_tok` is whole-document (`spec_code_lines`): fenced bodies (fence parsing robust to dangling and parity-desynced fences) ∪ indented lines ∪ per-line Python classifier, the last two applied to the raw line **and** to its dressing-stripped form (leading `>`/`-`/`*`/`+`/`|`/`1.` markers, trailing table `|`) — every classifier pattern is `^`-anchored, so without that normalization a blockquoted/bulleted/tabled implementation detects as zero code lines. One detection pass, three surfaces: `spec_code_lines` returns RAW lines (L1 + `code_tok` — dressing never discounts code), `spec_code_source` returns raw **and** de-dressed forms (L2/L3 containment, a set operation, so carrying both is strictly more sensitive), `spec_python_source` returns L4's executable candidate (whole detected set if it parses, else only the maximal detected line-runs that parse — `ast.parse` only, never `exec`). `spec_code_blocks` (fenced bodies only) is retained as a fence-parsing utility. **L2 is reference-denominated** (matched grams / `|grams(docstring-stripped oracle)|`, maxed with the raw-spec-stream channel and the legacy spec-denominated channel) so no amount of author-added padding can dilute it; **L3's `impl_source` excludes test files** for the same reason. No leakage channel depends on how the code is dressed.

### `src/eval_overexplanation/score.py`

Pure. No statistics, no I/O, no `stats` import — the orchestrator pre-computes every test and packs inert inputs, exactly as `decision.decide` does.

```python
@dataclass(frozen=True)
class GateCheck:      id: str; value: float; threshold: float; passed: bool; detail: str = ""
@dataclass(frozen=True)
class MetricValue:    id: str; value: float; ci: tuple[float, float] | None; p_holm: float | None; extra: Mapping[str, object]
@dataclass(frozen=True)
class DimensionScore: name: str; metrics: tuple[MetricValue, ...]; subscore: float; verdict: str
@dataclass(frozen=True)
class CellCounts:     expected: int; complete: int; missing: int; timeout: int; error: int; retried: int; merge_skipped: int; mutations_skipped: int; holdout_skipped: int
@dataclass(frozen=True)
class ArmScore:       arm_id: str; cells: Mapping[str, CellCounts]  # keyed "generate" | "implement"
                      gates: tuple[GateCheck, ...]; dimensions: tuple[DimensionScore, ...]; leakage_voided: bool
                      l4_no_signal: bool  # §1-L4 "no signal (emitted+flagged)" trace; always rendered
                      composite: float | None
@dataclass(frozen=True)
class ScoreInputs:    …   # manifest hash, noise floors, stops, strata, per-arm raw values
@dataclass(frozen=True)
class ScoreReport:    scorable: bool; reason: str | None; verdict: Verdict; ceiling: str; arms: tuple[ArmScore, ...]; …

def subscore_linear(effect: float, noise_floor: float, target: float, *, min_den: float) -> float
def outcome_subscore(correctness: float, kill_rate: float, bloat_ln: float) -> float
def composite(dims: Mapping[str, float], weights: Mapping[str, float]) -> float
def evaluate_gates(inputs: ScoreInputs) -> tuple[GateCheck, ...]
def non_inferior_flags(tost, t: ScoreThresholds) -> dict[str, bool]        # recomputed TOST legs, PUBLIC (CLI reuses it)
#: C1/C3/C8, U1/U2/U3/U5, O1/O2/O3/O4/O5 — the metric ids with an operative twin (C4 has none)
DERIVABLE_METRIC_IDS: Mapping[str, tuple[str, ...]]
def derive_metric_fields(metric_id: str, arm: ArmInputs, t: ScoreThresholds, ni) -> Mapping[str, object] | None
def score_report(inputs: ScoreInputs) -> ScoreReport      # applies §2 precedence; ALWAYS renders derived metrics
def render_score_json(report: ScoreReport) -> str          # canonical, byte-stable
def exit_code(report: ScoreReport) -> int                  # 0 | 1 | 4
```

### `scripts/run-implementer.sh`

Modeled on `run-arm.sh`; same cell layout, same `stream-json` capture, same portable-timeout and rc propagation.

```
Usage: run-implementer.sh <ARM_ID> <BRIEF_ID> <SEED>
Env: CLAUDE_BIN, RESULTS_ROOT (default ./results), IMPL_ROOT (default ./impl),
     IMPLEMENTER_MODEL (REQUIRED, pinned), IMPL_WORKROOT (default $TMPDIR/bench-impl),
     TIMEOUT_SECS (default 1800), SKIP_PERMS
```

| step | contract |
|---|---|
| input | `results/<BRIEF_ID>/<ARM_ID>/seed-<SEED>/artifacts/**/*spec*.md` — the arm's captured spec. Exactly one match required; 0 or ≥2 ⇒ exit 1, cell `status="missing"` |
| workspace | `$IMPL_WORKROOT/<BRIEF_ID>/<ARM_ID>/seed-<SEED>/workspace`, created **outside the repo tree**. `git init`, empty first commit. The brief, gold props, `cases.json`, `cases_holdout.json`, `oracle.py`, `mutations.json` are **never staged and never reachable** — isolation is reachability, not a listing check |
| config | `CLAUDE_CONFIG_DIR=$HOME/.claude-implementer` — one FIXED pinned implementer for **all** arms; plugins disabled. Must exist or exit 1 |
| prompt | `render(PREAMBLE_TEMPLATE, module=brief.module, entrypoint=brief.entrypoint) + "\n\n" + spec_text`, nothing else. The template is frozen in the manifest and substitutes exactly two values — the interface names `run_oracle` will import and call — read by the **harness** from `brief.json`. No brief text, no arm identity, no hint about the experiment |
| launch | `claude -p "$PROMPT" --model "$IMPLEMENTER_MODEL" --permission-mode acceptEdits --output-format stream-json --verbose` under `timeout $TIMEOUT_SECS`; stdout → `transcript.jsonl`, stderr → `run.log` |
| record | `impl-cell.json`: `{arm, brief_id, seed, implementer_model, prompt_sha, preamble_template_sha, module, entrypoint, spec_path, spec_sha, workspace, started_at, finished_at, return_code}` |
| retry | `subtype == "error_during_execution"` ⇒ up to `max_retries=2` with exponential backoff; sets `retried:true`. `rc 124` ⇒ no retry, `status="timeout"` |
| exit | propagates the CLI rc so the orchestrator can count failures |

### Modified, not created (thin wiring only — no logic)

| file | change |
|---|---|
| `src/eval_overexplanation/cli.py` | add `overexpl usage \| deadend \| leakage \| outcome \| bench-trust \| score`; same lazy-import adapter pattern; `_LoadError → 3`, gate/STOP → 1, not-scorable → 4. **Owns assembling the O3 merged reference dir**: `tmp/<b>/` ← `corpus/<b>/oracle.py` + the arm's `workspace/tests/**`, then smoke, then `run_mutations(impl_dir=tmp, test_cmd, mutations)`. Nothing else may construct it. Score-packer coupling rules — **every operative number a manifest or packed count can derive IS derived; a packed value is at most a cross-check (contradiction = load error), never the source**: every `gate_values` key is REQUIRED — the nullable ones (`c0_leak_hits`, `o1_correctness`, `o2_overfit`, `o3_kill_rate`, `l4_spec_only_correctness`) demand an explicit `null` for their no-signal state, an ABSENT key is a load error (deleting `l4_spec_only_correctness` must never drop the L4 gate with no schema trace), and `o1_regressed_cells` is required like every sibling; the TOST flags travel as REQUIRED per-family raw numerics (`tost: {C3|C8|U2|U3|O1|O3: {estimate, ci90, p_value, achieved_power, margin} | null}`) from which the scorer RECOMPUTES `non_inferior` (90% CI strictly inside `±bench.tost_margins[f]`) and `certifiable` (`achieved_power ≥ bench.min_power`) — legacy packed booleans (`*_non_inferior`, `tost_certifiable`) are at most cross-checks (mismatch = load error) and a packed `margin` must equal `bench.tost_margins[f]`; `noise_floor_c`/`noise_floor_u` are domain-checked (`≤ 0`/non-finite = load error — an empty-input floor means no baseline replicate data); every packed `arm_id` may appear at most once (duplicate = load error; `score_report` additionally raises `ValueError`, defense in depth); `u1: {mean_delta, p_holm}` replaces any caller boolean; `strata_coverage` is **derived from the manifest briefs** (C = per-regime brief counts, U/O = per-regime BUILDABLE counts; a packed value must equal the derivation exactly); `o2/o3_skipped_fraction` are **derived from the packed `holdout_skipped`/`mutations_skipped` counts** over the panel's expected implement cells (packed fraction = 3-decimal cross-check only); `baseline_arm`/`treatment_arm` and every packed `arm_id` must be manifest-declared arms; the `stops` block and **all four** of its keys (`c_length_falsification`, `c_distinct_dilution`, `u_below_detectable_floor`, `u_length_falsification`) are REQUIRED and bracket-indexed like the six sibling booleans — with an optional block and per-key defaults, DELETING a fired STOP produced a scored run carrying a FABRICATED clean STOP record in `score.json` and silently dropped §2 row 4; `budget.max_usd` comes from `bench.max_usd` (packed max ignored, `exhausted` re-ORed with `spent > max`); `score` REQUIRES `--corpus <root>` — the §4 per-brief asset rules are never opt-in (an opt-in flag no shipped caller passed made them dead letter); the coupling rule extends to `dimensions.<D>.metrics` (`score.DERIVABLE_METRIC_IDS`: C1/C3/C8, U1/U2/U3/U5, O1/O2/O3/O4/O5) — `score.derive_metric_fields` computes each id's operative field subset from `gate_values`/`tost`/`c1`/`u1`/`bloat_ln` (the same values the gates and subscores already read), `score_report` ALWAYS renders that derived subset regardless of what was packed (single source of truth — a packed `metrics.C1.mean_delta` can no longer render beside a subscore computed from a different number), and the CLI additionally cross-checks any packed field for a derivable id against the derivation before scoring (mismatch = load error, e.g. a packed `metrics.O.O3.kill_rate` that disagrees with `gate_values.o3_kill_rate`); fields with no operative twin (C4's deferred purity, C1's raw `p`/`n`, U1's `spend_index`, U3's `mean`, U5's `trailing_question_marks`, O2's `skipped_briefs`, O3's `smoke_failed_cells`) stay pure packer passthrough, unchecked, by design |
| `src/eval_overexplanation/manifest.py` | `BenchThresholds` + `PreRegistration` fields (§4) + `validate()` rules |
| `src/eval_overexplanation/corpus.py` | `load_holdout_cases(brief_dir) -> tuple[OracleCase,...] | None` (absent ⇒ `None` ⇒ skip, never pass); `load_mutations(brief_dir)`. `load_oracle_cases` untouched |
| `src/eval_overexplanation/substance.py` | `alignment_purity(alignment) -> float` (C4, reported only) |
| `analysis/assemble.py` | emit `records[].purity_alignment` (doc→gold) — **deferred with C4**, see risks |
| `scripts/run-arm.sh` | generate-cell isolation (the U0 analogue for the C stage), enforced by exactly two mechanisms and claimed as nothing more: (a) the live workspace moves to `$ARM_WORKROOT` (default `$TMPDIR/bench-arm`), an inside-repo workroot is **refused** — this removes *relative-path* reach to `corpus/<b>/oracle.py` only; the agent can still Read/Grep absolute repo paths; (b) therefore a **post-hoc C0 scan** runs after every cell: `deadend.count_leaks` (`bench.leak_patterns` from `$BENCH_MANIFEST` when set, else the frozen `deadend.LEAK_PATTERNS`) over the whole transcript — **every distinct matched fragment per tool_use is recorded**, so the brief-staged-input exemption (§1 C0) drops only the `brief.*` fragments and is order-independent: a tool_use is exempt only when no non-exempt fragment matched it — recorded as `cell.json.{leak_scanned, leak_hits, leak_hit_details}`; scan failure records `leak_scanned:false` (no signal, never a pass) **and the script exits non-zero** — an unscanned cell must never look green to the orchestrator. `cell.json` also records `workspace` + `workspace_outside_repo: true` (the cell keeps a post-run snapshot); python3 is a hard dependency (realpath check, brief id, C0 scan). Non-ok implement cells: `run-implementer.sh` exits **non-zero for every `status != "ok"`**, even when the CLI itself returned 0 — a no-result-event cell must never look green to the orchestrator — and the final `status` is derived **through `usage.parse_usage` itself** (never a shell re-derivation: a truncated result event is `missing` to both the script and the scorer) |

---

## 4. Manifest additions (under `content_hash`)

Extend `manifest.DecisionThresholds` (kept, back-compatible) with a new frozen `BenchThresholds`, and add fields to `PreRegistration` → version prefix `bench-1-*` (hash changes by design).

| field | type | frozen value (demo) |
|---|---|---|
| `bench.u_arms` | `tuple[str,...]` | `("A0","A1","A2_placebo","A3_fair","A3b_dumb")` |
| `bench.implementer_ref` | `str` | pinned model id + `preamble_template_sha` |
| `bench.preamble_template` | `str` | frozen; exactly two substitutions: `{module}`, `{entrypoint}` |
| `bench.sandbox_test_cmd` | `tuple[str,...]` | `("{python}","-m","pytest","-q","-p","no:cacheprovider")` |
| `bench.weights` | `Mapping[str,float]` | `{"C":0.30,"U":0.30,"O":0.40}` |
| `bench.composite_pass` | `float` | `70.0` |
| `bench.c1_gate_noise_multiple` | `float` | `2.0` — §1-C1 **gate**: `mean Δ ≤ −max(c1_gate_floor, 2.0 × nf_C)` (precedence #10) |
| `bench.c1_gate_floor` | `float` | `0.025` — §1-C1 gate **absolute floor** (the `max(0.05, …)` §2 convention applied to the gate): a zero/degenerate `nf_C` never makes any negative delta a free win |
| `bench.c_scale_noise_multiple` / `c_target` | `float` | `4.0` / `max(0.05, 4×nf_C)` — §2 composite **scale** `T_C`. Deliberately distinct name from the gate multiple: sharing one name halves `T_C` and inflates `S_C` |
| `bench.u_target_ln` | `float` | `0.1054` |
| `bench.u_noise_multiple` | `float` | `2.0` — `T_U = max(u_target_ln, this × nf_U)`, consumed by `thresholds_from_bench` |
| `bench.win_alpha` | `float` | `0.05` — §1 C1/U1 Holm-adjusted `p <` this (precedence #10), consumed by `thresholds_from_bench` |
| `bench.c_min_den` / `u_min_den` | `float` | `0.02` / `0.05` — the §2 knife-edge denominator floors, consumed by `thresholds_from_bench` |
| `bench.o_weight_correctness` / `o_weight_kill` / `o_weight_bloat` | `float` | `0.50` / `0.30` / `0.20` — the S_O term weights; must sum to 1.0 (`validate()`); consumed by `thresholds_from_bench` |
| `bench.max_o_term_skipped_fraction` | `float` | `0.30` — the O2/O3 accounted-skip cap (gate-vs-row-9 routing), consumed by `thresholds_from_bench` |
| `bench.tost_margins` | `Mapping[str,float]` | `{"C3":0.05,"C8":0.02,"U2":1.0,"U3":1.0,"O1":0.05,"O3":0.10}` — consumed by `thresholds_from_bench` into `ScoreThresholds.tost_margins` and LIVE: the scorer recomputes every `non_inferior` flag against these margins, and a packed `TostStats.margin` contradicting them is a load error |
| `bench.min_power` | `float` | `0.8` — consumed into `ScoreThresholds.min_power` and LIVE: the scorer recomputes every `certifiable` flag as `achieved_power ≥ this` |
| `bench.dead_end_cap` | `int` | `6` |
| `bench.o1_min_correctness` | `float` | `0.90` |
| `bench.o2_max_overfit` | `float` | `0.10` |
| `bench.o3_min_kill_rate` | `float` | `0.75` |
| `bench.o5_bloat_cap_ln` | `float` | `1.0986` |
| `bench.leak_caps` | `Mapping[str,float]` | `{"code_frac":0.15,"reference":0.25,"copy":0.30,"spec_only_correctness":0.50}` — **calibrated upward** to `max(honest A0/A0_prime)+0.05` before any treated run |
| `bench.frag_rate_cap` | `float` | calibrated `max(A0/A0_prime)+0.02`, floor `0.05` |
| `bench.max_incomplete_fraction` / `max_merge_skipped_fraction` | `float` | `0.10` / `0.30` |
| `bench.min_stratum_n` | `int` | `3` |
| `bench.max_usd` / `max_retries` | `float`/`int` | `120.0` / `2` — `max_usd` is the **budget authority**: `overexpl score` overrides the packed `budget.max_usd` with it and re-ORs `exhausted` against `spent > max`; `max_retries` is the value `run-implementer.sh`'s `MAX_RETRIES` default mirrors |
| `bench.leak_patterns` | `tuple[str,...]` | corpus-path + asset-name regexes (§1 U0); also drives the §1-C0 `run-arm.sh` post-hoc scan (via `$BENCH_MANIFEST`) |
| `bench.mutations_per_brief` | `int` | `8` |

`validate()` gains: `u_arms ⊆ arms` and `A3b_dumb ∈ u_arms` (U1f's strip leg); weights sum to 1.0 and `o_weight_*` sum to 1.0; `implementer_ref` and `preamble_template` non-empty; `preamble_template` contains both `{module}` and `{entrypoint}`. With a `corpus_root` argument — which `overexpl score` now REQUIRES (`--corpus <root>`; the asset rules are never opt-in) — the **per-brief asset rules** apply too: every `buildable:true` brief has `module` + `entrypoint` in `brief.json`, `cases.json`, `cases_holdout.json`, `mutations.json`, and exactly `mutations_per_brief` mutations — a buildable brief missing its blind O assets is a manifest problem (§2 row 0, `scorable:false`), never a quiet skip. Problems are strings, never exceptions.

---

## 5. Gaming countermeasures

| # | vector | countermeasure | why it holds |
|---|---|---|---|
| **1** | **Spec embeds the implementation** — aces U (implementer transcribes) and O (reference code passes) | (a) **cost conservation**: `code_tok(spec)` is summed into U1's `spend`, so moving work from implementer into spec is *score-neutral*, not merely detected; (b) L1/L2/L3 deterministic 5-gram containment gates over **whole-document detected code** (fenced ∪ indented ∪ classifier lines, each classified raw **and** dressing-stripped so blockquote/bullet/table wrappers detect identically; identifier-skeleton channel defeats systematic renaming), calibrated from honest A0 specs, with **denominators the author cannot inflate** — L2 is reference-denominated (frozen oracle grams, docstring-stripped) and L3's impl surface excludes the arm's own tests; (c) L4 **executed control**: the detected spec Python that parses, run through `run_oracle` — `spec_only_correctness ≥ 0.5` voids the arm's U and O, and a single non-Python block beside it can no longer take the whole candidate down with it; (d) O3 mutations run against the frozen reference with the arm's **tests** copied in, so a transcribed impl earns nothing unless its suite independently kills mutants | (a) closes the embedded-code path — fenced, indented, fence-desynced or line-dressed — by arithmetic; genuinely re-expressed pseudocode evades (a), so (b)'s skeleton channel + (c) are the backstop; thresholds are calibrated, not asserted; **residual**, stated rather than papered over: full SEMANTIC re-expression (a paraphrase that shares neither literal nor skeleton 5-grams with the reference — prose pseudocode, a different-language sketch, an algorithm described step by step in English) is out of static reach. What carries it is (a) cost conservation on whatever text is detected, (c) the executed control (a paraphrase precise enough to transcribe usually assembles and runs), U1's `spend` conservation, and the `human_read_required` gate on the final read — never L2/L3 alone |
| **2** | **Novel-claim dilution** — append non-repeating prose; `1 − distinct/mentions` falls with zero redundancy removed | C6 STOP: `partial_out_length(ΔC1, Δdistinct)` must survive — the effect must exist at *constant distinct-count*. Plus C3 coverage non-inferiority (padding cannot raise recall), C4 purity reported, `defensive_filler` decoy in the instrument gate, `word_count` as a logged covariate | the existing `length_confound` decoy probes non-repeating *words*, not added distinct *claims* — C6 is the only thing that closes it, and it needs no new stats code |
| **3** | **Test-suite theater / oracle overfit** — suites that pass anything, impls that special-case `cases.json` | O3 smoke precondition (non-importing suite ⇒ **no signal**, never kill_rate 1.0) + frozen arm-independent mutation denominator + `invalid == 0`; O4 AST lint at 0 (incl. `Return(Constant) == expected`); O2 blind `cases_holdout.json` with disjoint literals, `overfit ≤ 0.10`, absent ⇒ skipped never passed; O1 cell-level regression gate | every leg is fail-closed: reduced signal never manufactures a pass |
| **4** | **Word-dropping / telegraphic prose** to win C | C8 calibrated fragment cap + TOST; C9 A3b positive control must FAIL the detector or the run is void; C1 is a within-doc *rate*, so dropped words alone don't move it; C4 density demoted to covariate | the control is what makes the gate credible |
| **5** | **Instrument blindness** (G-BT, benchmark-trust) | Before any arm number: (a) reference impl (`corpus/<b>/oracle.py` + reference tests) must score `O1 == 1.0` and `O3 ≥ 0.75`; (b) stub impl (`def <entrypoint>(*a, **k): return None`) must score `O1 < 0.5` and fail the O3 smoke. If the stub **passes**, the O instrument is blind ⇒ `scorable:false`, exit 4 | the U/O analogue of A3b — a positive *and* negative control on the executable axis |
| **6** | **Cache/pricing distortion of U** | Score only `output_tokens` + `num_turns` (cache-invariant). `input_tokens` recorded but never scored (it is spec length). `cache_read_input_tokens` and `total_cost_usd` are diagnostics/budget only | closed by construction; no warm/cold decoy needed |

---

## 6. Offline vs live boundary

**Offline** — default `uv run pytest` from `eval/blueprint/over-explanation/`, no network, no API key, fixtures + `tmp_path`:
every formula in §1; all of `usage.py`, `deadend.py`, `score.py`; the whole §2 precedence table; canonical `score.json` serialization; all `stats`/`decision`/`instrument` wiring; `run_oracle` + `run_mutations` (subprocess-isolated, network-free) against checked-in mini-impls; C-dimension logic via `FixtureExtractor`; the L4 executed control; workaround lint and containment over fixture sources; **transcript parsers against ≥7 recorded `transcript.jsonl` fixtures**: success, `error_max_turns`, `error_during_execution`, no-result-event (⇒ `status="missing"`), revert pair, failing-pytest pair, leak hit, `AskUserQuestion`. Every gate ships a paired pass-fixture **and** fail-fixture, including G-BT's stub-impl control. **Golden end-to-end**: `tests/fixtures/bench/` → `overexpl score` → byte-identical against `expected_score.json`. Target ≥ 60 new tests.

**Live-gated** — never required to compute a score from existing transport JSON:
arm generation (`scripts/run-arm.sh`, per-arm `$CLAUDE_CONFIG_DIR`); cross-family extraction/alignment (`[llm]`: `anthropic` + `openai`, ≥2 families); implementer runs (`scripts/run-implementer.sh`, pinned model); parse-based grammaticality (`[nlp]` spaCy).

**Human-authored, blind, gating** (absent ⇒ dimension skipped, never passed): `gold_propositions.json` ×9 (exists); `cases.json` ×6 (exists); **`mutations.json` ×6 briefs × 8 = 48 mutations (NEW)**; **`cases_holdout.json` ×6 (NEW)**; the final grammaticality human read (`human_read_required:true`, advisory, outside the score).

**Ops.** `gen_cells = 8×9×2 = 144`; `u_cells = 5×6×2 = 60`; `extract_calls = 2 families × 2 (pre+post) × 144 + 2 × 7 arms × 9 × 2 = 828` (C4's `purity_alignment` would add `2 × 144 = 288` more — deferred with C4, see risks). Preflight runs a 3-cell pilot, takes median `total_cost_usd`, prints `projected = median × 204`, and aborts if `projected > max_usd (120.0)`. Cache `results/.cache/<stage>/<key>.json`; the **score-stage key must include `manifest.content_hash`** or a threshold edit silently reuses stale scores.

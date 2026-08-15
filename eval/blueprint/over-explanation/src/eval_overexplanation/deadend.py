"""Dead-end, workaround, and leakage signals over implementer runs.

Feeds U0 (isolation), U3 (dead ends), U5 (clarifying questions), O4
(workaround lint), and L1-L4 (leakage control) of BENCHMARK.md. Every function
here is pure: transcript signals operate on already-parsed stream-json lines,
the lint operates on source text via ``ast`` only, and the leakage report is
arithmetic over supplied strings. No I/O beyond reading the files the caller
names, no network, no imports of untrusted code — ever.

Frozen definitions (BENCHMARK.md section 3), with the assumption each makes:

* **revert** — an ``Edit`` whose ``new_string`` equals an *earlier*
  ``Edit.old_string`` for the same ``file_path`` (the Edit tool's exact-string
  contract makes string equality the revert signal), **or** a ``Write`` to a
  previously-Edited ``file_path`` whose ``content`` drops at least one earlier
  ``Edit.new_string`` (a clobber: the whole-file rewrite abandons those edits
  — the common abandonment path). One count per clobbering Write, and a Write
  supersedes the pending edits it clobbers so later Writes never recount them.
* **failed test cycle** — a ``Bash`` ``tool_use`` whose ``input.command``
  matches the widened test-runner regex (``pytest`` as a command word incl.
  path-prefixed, ``python -m pytest|unittest``, ``make test|check``, ``tox``,
  ``npm/yarn/pnpm test``, ``cargo/go test``, ``run[_-]tests`` wrapper scripts,
  ``*test(s).sh``) and whose paired ``tool_result`` (by ``tool_use_id``) has
  ``is_error == true``. Widened from pytest-only forms so wrapper-script and
  Makefile test loops are no longer invisible to the U3 guardrail.
* **top-level only** — events with a non-null ``parent_tool_use_id`` (subagent
  activity) never count toward any signal. Assumes the stream-json envelope
  carries ``parent_tool_use_id`` on every line object.
* **clarifying question** — a ``tool_use`` named ``AskUserQuestion``. The
  trailing-``?`` count over the final assistant text is a *reported diagnostic
  only*, never a gate (U5): it counts non-empty lines ending in ``?``, an
  admitted approximation of "asked something at the end".
* **leak hit** — a ``tool_use`` whose serialized input matches a leak pattern.
  Matching runs over the canonical JSON serialization of ``input`` *and* over
  every string leaf inside it. The default patterns are word-boundary matches,
  **not** path-anchored, so ``ls corpus`` and ``grep -r expected corpus/``
  count exactly like ``Read("corpus/x")``. Strictly more sensitive than
  anchored serialization-only matching — the fail-closed direction for an
  isolation gate. EVERY distinct matched fragment is recorded per tool_use
  (never only the first match): a single Bash command touching both
  ``brief.md`` and ``corpus/.../oracle.py`` yields a hit for each fragment,
  so a downstream stage exemption of one fragment (run-arm.sh's C0
  brief-staged-input rule) can never mask the other — the exemption holds
  only when NO non-exempt fragment matched the same input.
* **workaround lint** — ``ast`` only, never ``exec``/``import`` of the
  untrusted implementer source. A file that does not parse yields *no AST
  signal* (O1's executed oracle catches broken impls); its text is still
  scanned for TODO/FIXME. ``TODO``/``FIXME`` count only in non-test impl
  files; the other five signals count everywhere (skip-markers and
  ``assert True`` live precisely in test files). ``Return(Constant)`` is
  compared to ``cases.json`` expected values with ``==`` per the frozen rule,
  so ``True == 1`` collisions are accepted rather than special-cased.
* **n-gram containment** — lowercase whitespace tokens (``TOKENS``) after
  stripping ``#``-comments with a line-tail regex (an approximation: a ``#``
  inside a string literal also strips — acceptable for a similarity screen,
  and identical for both sides of the comparison). Returns the **max of two
  channels**: raw tokens, and identifier-skeleton tokens where every
  non-keyword identifier is replaced by a placeholder — so renaming variables
  (re-expression) cannot zero the containment signal. Each channel is
  ``|shared n-grams| / |a's n-grams|``, ``0.0`` when ``a`` has fewer than
  ``n`` tokens.
* **spec code detection** — code content is classified over the WHOLE
  document, never only fenced bodies: the union of (i) backtick-fenced block
  bodies with fence parsing robust to unbalanced fences (a dangling open
  fence extends to EOF; an info-string fence seen while a block is open marks
  a parity desync from a stray bare fence — the region stays classified as
  code, the fail-closed direction), (ii) 4-space/tab-indented lines
  (markdown's indented-code semantics), and (iii) a per-line Python
  classifier (def/class/import/decorator/flow-keyword/assignment/call
  heuristics), each of (ii) and (iii) applied to the raw line **and** to its
  *dressing-stripped* form (``_dedress``: leading ``>``/``-``/``*``/``+``/
  ``|``/``1.`` markers removed iteratively, indentation preserved, a trailing
  table ``|`` dropped). Without that normalization every classifier pattern —
  all anchored with ``^`` — missed a verbatim implementation pasted as a
  blockquote, a bullet list, or a markdown table: 0 of 12 lines detected,
  ``code_frac`` 0.0, ``code_tok`` 0 (U1's cost conservation bypassed too).
  Over-counting prose as code is accepted: L caps are calibrated on honest
  A0/A0_prime cells under the same detector.
* **spec code surfaces** — three, from one detection pass. ``spec_code_lines``
  returns the RAW detected lines (L1's numerator and ``code_tok``, so the
  markers a dressing adds are counted, never subtracted).
  ``spec_code_source`` returns raw **and** dressing-stripped forms of those
  lines (containment is a set operation over n-grams, so carrying both
  dressings is strictly more sensitive and never less).
  ``spec_python_source`` is L4's executable candidate: the whole detected set
  when it parses, else only the maximal detected line-runs that parse on their
  own — so one non-Python indented block (a JSON payload example) can no
  longer kill the import and take the whole executed control down with it.
* **L2 denominator** — ``reference_containment`` is REFERENCE-denominated
  presence: matched 5-grams over ``|grams(reference)|``, maxed over the
  detected-code and raw-spec-stream channels, and maxed again with the legacy
  spec-denominated channel (kept for partial-paste sensitivity: three lines of
  a hundred-line oracle are 1.0 spec-denominated and 0.03
  reference-denominated). A spec-denominated-only L2 is author-controlled: 10
  ordinary indented JSON blocks push a verbatim oracle paste from 0.758 to
  0.245, under the 0.25 cap, with nothing removed. The reference side is
  **docstring-stripped** (``ast``, never ``exec``) before n-gramming: an
  oracle's prose docstring collapses to bare identifier placeholders in the
  skeleton channel and would otherwise match ordinary honest spec prose —
  measured at 0.092 on honest fixture pairs, 0.000 once stripped.
* **L4 no-signal** — a ``spec_only_correctness`` of ``None`` (spec code did
  not import) is recorded as ``nan`` and *flagged*, never read as clean;
  L1-L3 carry the gate for that cell.
"""

from __future__ import annotations

import ast
import json
import keyword
import re
import textwrap
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .models import OracleCase

# Whitespace-token index (BENCHMARK.md section 0). A unitless index, never a
# model token count.
TOKENS = re.compile(r"\S+")

# Frozen failed-test-cycle command forms (BENCHMARK.md section 3), widened
# beyond bare pytest so Makefile targets and wrapper scripts are visible.
# Undercount is still possible (an unrecognized bespoke runner), but the
# common wrapper paths no longer favour the arm U3 is meant to constrain.
_TEST_CMD = re.compile(
    r"(^|[\s;&|(/])pytest\b"
    r"|\bpython3?\s+-m\s+(pytest|unittest)\b"
    r"|\bmake\s+(-\w+\s+)*(tests?\w*|check)\b"
    r"|\btox\b"
    r"|\b(npm|yarn|pnpm)\s+(run\s+)?test\b"
    r"|\b(cargo|go)\s+test\b"
    r"|(^|[\s;&|/])\.?/?[\w./-]*run[_-]?tests?\b"
    r"|(^|[\s;&|/])[\w./-]*tests?\.sh\b"
)

# Default U0 leak patterns (BENCHMARK.md section 1). The manifest's
# ``bench.leak_patterns`` is authoritative for a scored run; this constant
# mirrors the frozen contract value for tests and ad-hoc use. Word-boundary,
# NOT path-anchored: ``ls corpus`` and ``grep -r expected corpus/`` must hit.
# A single alternation still records every DISTINCT matched fragment per
# tool_use (``count_leaks`` collects all matches, never only the first).
LEAK_PATTERNS: tuple[str, ...] = (
    r"\bcorpus\b|\bbrief\.(md|json)\b|\bgold_propositions\.json\b"
    r"|\bcases(_holdout)?\.json\b|\boracle\.py\b|\bmutations\.json\b",
)

_TODO = re.compile(r"\b(TODO|FIXME)\b")

_SKIP_DECORATORS = frozenset({"skip", "skipif", "xfail"})


# --------------------------------------------------------------------------- #
# Transcript event types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ToolUse:
    """One top-level ``tool_use`` block from a stream-json transcript.

    ``input`` is the raw parsed input dict — inert data, never executed.
    """

    id: str | None
    name: str
    input: Mapping[str, object]


@dataclass(frozen=True)
class ToolResult:
    """One top-level ``tool_result`` block, reduced to the pairing fields."""

    tool_use_id: str | None
    is_error: bool


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DeadEndReport:
    """U0/U3/U5 signals for one implementer cell's transcript."""

    reverted_edits: int
    failed_test_cycles: int
    clarifying_questions: int
    trailing_question_marks: int  # reported diagnostic, never a gate
    leak_hits: tuple[str, ...]  # matched tool_use input fragments

    @property
    def dead_ends(self) -> int:
        """U3's ``de`` = reverted_edits + failed_test_cycles."""
        return self.reverted_edits + self.failed_test_cycles


@dataclass(frozen=True)
class WorkaroundReport:
    """O4 lint counts over an implementer workspace. Gate: ``total == 0``."""

    skips: int
    assert_true: int
    swallowed_except: int
    hardcoded_expectations: int
    not_implemented: int
    todos: int
    hits: tuple[str, ...]  # "<file>:<lineno>: <kind>"

    @property
    def total(self) -> int:
        return (self.skips + self.assert_true + self.swallowed_except
                + self.hardcoded_expectations + self.not_implemented
                + self.todos)


@dataclass(frozen=True)
class LeakageReport:
    """L1-L4 leakage control for one arm cell.

    ``blocked`` is the authoritative bit; ``reasons`` carries every blocking
    reason plus the non-blocking L4 no-signal flag (``spec_only_correctness``
    is ``nan`` in that case — flagged, never read as clean).
    """

    code_frac: float
    reference_containment: float
    copy_containment: float
    spec_only_correctness: float
    blocked: bool
    reasons: tuple[str, ...]


# --------------------------------------------------------------------------- #
# Transcript parsing (independent of usage.py by design — decoupled modules)
# --------------------------------------------------------------------------- #


def _parsed_top_level(lines: Iterable[str]) -> Iterator[dict]:
    """Parse stream-json lines, yielding only top-level event objects.

    Malformed JSON lines are skipped, not fatal. Events with a non-null
    ``parent_tool_use_id`` (subagent activity) are dropped here so no signal
    downstream ever counts them.
    """
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("parent_tool_use_id") is not None:
            continue
        yield obj


def _content_blocks(obj: dict) -> Iterator[dict]:
    """Yield content blocks, tolerant of the stream-json envelope shape.

    Same envelope walk as ``analysis/assemble.py:_iter_tool_uses`` (the lifted
    original): ``message.content`` when wrapped, bare ``content`` otherwise.
    """
    msg = obj.get("message")
    content = msg.get("content") if isinstance(msg, dict) else obj.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict):
            yield block


def iter_tool_uses(lines: Iterable[str]) -> tuple[ToolUse, ...]:
    """Every top-level ``tool_use`` block, in transcript order."""
    uses: list[ToolUse] = []
    for obj in _parsed_top_level(lines):
        for block in _content_blocks(obj):
            if (block.get("type") == "tool_use"
                    and isinstance(block.get("name"), str)
                    and isinstance(block.get("input"), dict)):
                bid = block.get("id")
                uses.append(ToolUse(
                    id=bid if isinstance(bid, str) else None,
                    name=block["name"],
                    input=block["input"],
                ))
    return tuple(uses)


def iter_tool_results(lines: Iterable[str]) -> tuple[ToolResult, ...]:
    """Every top-level ``tool_result`` block, in transcript order."""
    results: list[ToolResult] = []
    for obj in _parsed_top_level(lines):
        for block in _content_blocks(obj):
            if block.get("type") == "tool_result":
                tid = block.get("tool_use_id")
                results.append(ToolResult(
                    tool_use_id=tid if isinstance(tid, str) else None,
                    is_error=block.get("is_error") is True,
                ))
    return tuple(results)


def _final_assistant_text(lines: Iterable[str]) -> str:
    """The run's final assistant text.

    Prefers the last ``{"type": "result"}`` event's ``result`` string (the
    CLI's authoritative final text); falls back to the last top-level
    assistant message's concatenated text blocks when no result event exists.
    """
    final = ""
    last_assistant = ""
    for obj in _parsed_top_level(lines):
        if obj.get("type") == "result" and isinstance(obj.get("result"), str):
            final = obj["result"]  # last result event wins
        elif obj.get("type") == "assistant":
            texts = [b["text"] for b in _content_blocks(obj)
                     if b.get("type") == "text" and isinstance(b.get("text"), str)]
            if texts:
                last_assistant = "\n".join(texts)
    return final or last_assistant


# --------------------------------------------------------------------------- #
# Dead-end signals (U3, U5, U0)
# --------------------------------------------------------------------------- #


def count_reverted_edits(tool_uses: Sequence[ToolUse]) -> int:
    """Reverts: exact-string Edit restores plus Write clobbers, per file.

    Two forms count (module docstring, *revert*):

    * an ``Edit`` whose ``new_string`` equals a strictly-earlier
      ``Edit.old_string`` for the same ``file_path`` (checked before its own
      ``old_string`` is recorded, so an edit can never revert itself);
    * a ``Write`` whose ``content`` drops at least one pending earlier
      ``Edit.new_string`` for the same ``file_path`` — the whole-file rewrite
      abandoned those edits. One count per clobbering Write; every pending
      edit is superseded by the Write either way, so later Writes never
      recount the same abandonment.
    """
    seen_old: dict[str, set[str]] = {}
    pending_new: dict[str, list[str]] = {}
    reverts = 0
    for use in tool_uses:
        file_path = use.input.get("file_path")
        if not isinstance(file_path, str):
            continue
        if use.name == "Edit":
            new = use.input.get("new_string")
            if isinstance(new, str) and new in seen_old.get(file_path, set()):
                reverts += 1
            old = use.input.get("old_string")
            if isinstance(old, str):
                seen_old.setdefault(file_path, set()).add(old)
            if isinstance(new, str):
                pending_new.setdefault(file_path, []).append(new)
        elif use.name == "Write":
            content = use.input.get("content")
            pending = pending_new.get(file_path, [])
            if isinstance(content, str) and pending and any(
                    new not in content for new in pending):
                reverts += 1
            pending_new[file_path] = []  # superseded either way
    return reverts


def count_failed_test_cycles(tool_uses: Sequence[ToolUse],
                             tool_results: Sequence[ToolResult]) -> int:
    """Bash test-runner invocations whose paired tool_result is an error.

    Recognizes the widened ``_TEST_CMD`` forms (pytest, python -m
    pytest/unittest, make test/check, tox, npm/yarn/pnpm test, cargo/go test,
    run-tests wrapper scripts, ``*test(s).sh``), so a test loop driven through
    a Makefile or wrapper script counts exactly like bare pytest.
    """
    error_ids = {r.tool_use_id for r in tool_results
                 if r.is_error and r.tool_use_id is not None}
    cycles = 0
    for use in tool_uses:
        if use.name != "Bash" or use.id not in error_ids:
            continue
        command = use.input.get("command")
        if isinstance(command, str) and _TEST_CMD.search(command):
            cycles += 1
    return cycles


def count_clarifying_questions(tool_uses: Sequence[ToolUse]) -> int:
    """U5's gate signal: ``AskUserQuestion`` tool_use count."""
    return sum(1 for use in tool_uses if use.name == "AskUserQuestion")


def _string_leaves(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _string_leaves(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _string_leaves(item)


def count_leaks(tool_uses: Sequence[ToolUse],
                patterns: Sequence[str]) -> tuple[str, ...]:
    """U0's isolation signal: tool inputs that touch frozen corpus assets.

    Each pattern is searched against the canonical JSON serialization of the
    tool input and against every string leaf inside it (so ``^`` anchors at
    value starts). EVERY distinct matched fragment is recorded, once per
    (tool_use, fragment), as ``"<tool name>: <matched fragment>"`` — never
    only the first match. This is what makes the C0 stage exemption
    order-independent: a tool_use that touches both an exempt staged input
    (``brief.md``) and a frozen oracle asset yields hits for BOTH fragments,
    so filtering the exempt fragment downstream can never drop the leak —
    a tool_use is exempt only when NO non-exempt fragment matches it.
    """
    compiled = tuple(re.compile(p) for p in patterns)
    hits: list[str] = []
    for use in tool_uses:
        candidates = (
            json.dumps(use.input, sort_keys=True, ensure_ascii=False),
            *_string_leaves(use.input),
        )
        seen: set[str] = set()
        for rx in compiled:
            for text in candidates:
                for match in rx.finditer(text):
                    fragment = match.group(0)
                    if fragment not in seen:
                        seen.add(fragment)
                        hits.append(f"{use.name}: {fragment}")
    return tuple(hits)


def _trailing_question_marks(text: str) -> int:
    """Non-empty lines of the final assistant text ending in ``?``."""
    return sum(1 for line in text.splitlines() if line.strip().endswith("?"))


def deadend_report(lines: Iterable[str], *,
                   leak_patterns: Sequence[str]) -> DeadEndReport:
    """All transcript-derived signals for one implementer cell, in one pass."""
    materialized = tuple(lines)
    uses = iter_tool_uses(materialized)
    results = iter_tool_results(materialized)
    return DeadEndReport(
        reverted_edits=count_reverted_edits(uses),
        failed_test_cycles=count_failed_test_cycles(uses, results),
        clarifying_questions=count_clarifying_questions(uses),
        trailing_question_marks=_trailing_question_marks(
            _final_assistant_text(materialized)),
        leak_hits=count_leaks(uses, leak_patterns),
    )


# --------------------------------------------------------------------------- #
# Workaround lint (O4)
# --------------------------------------------------------------------------- #


def _is_test_file(rel: Path) -> bool:
    name = rel.name
    return ("tests" in rel.parts[:-1]
            or name.startswith("test_")
            or name.endswith("_test.py"))


def _decorator_tail(node: ast.expr) -> str:
    """Last dotted component of a decorator expression (unwrapping calls)."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _lint_tree(tree: ast.AST, expected: Sequence[object]) -> Iterator[tuple[int, str]]:
    """Yield ``(lineno, kind)`` for every AST-level workaround signal."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                if _decorator_tail(dec) in _SKIP_DECORATORS:
                    yield dec.lineno, "skip"
        elif isinstance(node, ast.Assert):
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                yield node.lineno, "assert-true"
        elif isinstance(node, ast.ExceptHandler):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                yield node.lineno, "swallowed-except"
        elif isinstance(node, ast.Return):
            if isinstance(node.value, ast.Constant) and any(
                    node.value.value == e for e in expected):
                yield node.lineno, "hardcoded-expectation"
        elif isinstance(node, ast.Name) and node.id == "NotImplementedError":
            yield node.lineno, "not-implemented"


def workaround_lint(src_dir: Path,
                    cases: Sequence[OracleCase]) -> WorkaroundReport:
    """O4's AST lint over every ``*.py`` in an implementer workspace.

    Never executes or imports the linted source. A file with a syntax error
    contributes no AST signal (the executed oracle already fails it) but its
    text is still scanned for TODO/FIXME markers when it is a non-test file.
    """
    expected = [case.expected for case in cases]
    counters = {"skip": 0, "assert-true": 0, "swallowed-except": 0,
                "hardcoded-expectation": 0, "not-implemented": 0, "todo": 0}
    hits: list[str] = []
    for path in sorted(src_dir.rglob("*.py")):
        rel = path.relative_to(src_dir)
        source = path.read_text(encoding="utf-8", errors="replace")
        found: list[tuple[int, str]] = []
        if not _is_test_file(rel):
            found.extend(
                (lineno, "todo")
                for lineno, line in enumerate(source.splitlines(), start=1)
                if _TODO.search(line)
            )
        try:
            tree = ast.parse(source)
        except SyntaxError:
            tree = None
        if tree is not None:
            found.extend(_lint_tree(tree, expected))
        for lineno, kind in sorted(found):
            counters[kind] += 1
            hits.append(f"{rel}:{lineno}: {kind}")
    return WorkaroundReport(
        skips=counters["skip"],
        assert_true=counters["assert-true"],
        swallowed_except=counters["swallowed-except"],
        hardcoded_expectations=counters["hardcoded-expectation"],
        not_implemented=counters["not-implemented"],
        todos=counters["todo"],
        hits=tuple(hits),
    )


# --------------------------------------------------------------------------- #
# Leakage control (L1-L4)
# --------------------------------------------------------------------------- #

_COMMENT = re.compile(r"#[^\n]*")

# Identifier-skeleton channel: every non-keyword identifier collapses to this
# placeholder before n-gramming, so renaming variables cannot zero containment.
_IDENT = re.compile(r"[A-Za-z_]\w*")
_IDENT_PLACEHOLDER = "\ue000"  # private-use char: never in real spec text


def _normalized_tokens(text: str) -> tuple[str, ...]:
    """Lowercase whitespace tokens after stripping ``#``-comment line tails."""
    return tuple(t.lower() for t in TOKENS.findall(_COMMENT.sub("", text)))


def _skeletonize(token: str) -> str:
    """Replace every non-keyword identifier in ``token`` with a placeholder."""
    return _IDENT.sub(
        lambda m: m.group(0) if keyword.iskeyword(m.group(0))
        else _IDENT_PLACEHOLDER,
        token)


def _ngrams(tokens: Sequence[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def _containment(tokens_a: Sequence[str], tokens_b: Sequence[str],
                 n: int) -> float:
    grams_a = _ngrams(tokens_a, n)
    if not grams_a:
        return 0.0
    return len(grams_a & _ngrams(tokens_b, n)) / len(grams_a)


def ngram_containment(a: str, b: str, *, n: int = 5) -> float:
    """``|shared n-grams| / |a's n-grams|``, max over two token channels.

    Asymmetric on purpose: it asks how much of ``a`` already exists in ``b``.
    Channel one is the raw normalized tokens (verbatim copies); channel two is
    the identifier skeleton (``_skeletonize``), which survives systematic
    renaming — re-expression must not zero the leakage signal. ``0.0`` when
    ``a`` has fewer than ``n`` tokens.
    """
    tokens_a = _normalized_tokens(a)
    tokens_b = _normalized_tokens(b)
    raw = _containment(tokens_a, tokens_b, n)
    skeleton = _containment([_skeletonize(t) for t in tokens_a],
                            [_skeletonize(t) for t in tokens_b], n)
    return max(raw, skeleton)


# A fence delimiter line: optional indent, a backtick run, optional info
# string. ``~~~`` fences are not recognized (blueprint's artifacts use
# backticks); the whole-document classifier below catches ~~~-fenced code
# lines anyway.
_FENCE_LINE = re.compile(r"^\s*```+\s*(?P<info>[^`\s]*)")

# Markdown indented-code semantics: 4+ spaces or a tab of leading indent.
_INDENTED = re.compile(r"^(?: {4,}|\t)\s*\S")

# Per-line Python classifier (module docstring, *spec code detection*).
# Case-sensitive on purpose: English sentences capitalize ("If the input…"),
# Python keywords do not.
_CODE_LINE_PATTERNS = tuple(re.compile(p) for p in (
    r"^(async\s+)?def\s+\w+\s*\(",
    r"^class\s+\w+\s*[:(]",
    r"^@\w[\w.]*",
    r"^(import\s+\w[\w.]*|from\s+\w[\w.]*\s+import\b)",
    r"^(if|elif|while)\b.+:\s*(#.*)?$",
    r"^for\s+.+\s+in\s+.+:\s*(#.*)?$",
    r"^(else|try|finally)\s*:\s*(#.*)?$",
    r"^except(\s+[\w.()\, ]+(\s+as\s+\w+)?)?\s*:\s*(#.*)?$",
    r"^with\s+.+:\s*(#.*)?$",
    r"^(return|yield|raise|assert|del)\b.*[=+\-*/%<>\[\](){}]",
    r"^(pass|break|continue)\s*(#.*)?$",
    r"^[\w.\[\]\"']+\s*(:\s*[\w.\[\], |]+\s*)?"
    r"(=|\+=|-=|\*=|/=|//=|%=|\*\*=|\|=|&=|\^=|>>=|<<=)\s*\S",
    r"^[\w.]+\(.*\)\s*(#.*)?$",
))


# Line-prefix markdown dressing: blockquote, bullet, ordered-list and table
# markers. Stripped iteratively (nested ``> > ``), consuming at most ONE
# space after the marker so the code's own indentation survives.
_DRESS = re.compile(r"^([ \t]*)(?:>|[-*+]|\d+\.|\|)[ \t]?")
_TRAILING_PIPE = re.compile(r"[ \t]*\|[ \t]*$")


def _dedress(line: str) -> str:
    """``line`` with leading markdown line-dressing removed, indent preserved.

    ``"> counts = {}"`` → ``"counts = {}"``; ``">     return x"`` →
    ``"    return x"``; ``"| x = 1 |"`` → ``"x = 1"``. Every classifier
    pattern is ``^``-anchored, so without this a verbatim implementation
    dressed as a blockquote/bullet/table detects as zero code lines.

    The ordered-list marker makes this lossy on real Python — ``0.5 * f``
    de-dresses to ``5 * f``. Bounded by construction: the raw form is always
    classified and always tried first (``_parseable_source``), so a mangled
    de-dressed form can only be reached where the raw form already failed,
    which is where the previous behaviour was no signal anyway.
    """
    out = line
    piped = False
    while True:
        match = _DRESS.match(out)
        if match is None:
            break
        if out[match.end(1)] == "|":
            piped = True
        out = match.group(1) + out[match.end():]
    return _TRAILING_PIPE.sub("", out) if piped else out


def _looks_like_code(stripped: str) -> bool:
    return any(rx.match(stripped) for rx in _CODE_LINE_PATTERNS)


def _fenced_line_flags(lines: Sequence[str]) -> tuple[bool, ...]:
    """Per-line inside-a-fence flags, robust to unbalanced/desynced fences.

    A dangling open fence extends to EOF. An info-string fence (```` ```python
    ````) seen while a block is already open marks a parity desync — a stray
    bare fence flipped the toggle earlier; the state stays *open* so the real
    code body is classified as fenced (and the stray prose region over-counts
    as code: the fail-closed direction). Delimiter lines themselves are never
    body lines.
    """
    flags = [False] * len(lines)
    open_ = False
    for i, line in enumerate(lines):
        match = _FENCE_LINE.match(line)
        if match is not None:
            if open_ and not match.group("info"):
                open_ = False       # proper bare closer
            else:
                open_ = True        # opener, or desynced info-string fence
            continue
        flags[i] = open_
    return tuple(flags)


def spec_code_blocks(markdown: str) -> tuple[str, ...]:
    """Bodies of backtick-fenced code blocks, in document order.

    Same fence semantics as ``_fenced_line_flags``: a dangling open fence
    keeps its body to EOF, and an info-string fence while a block is open
    (parity desync from a stray bare fence) flushes the spurious block and
    opens the real one — the implementation body never lands "outside".
    Fenced bodies alone are NOT any leakage surface: L1 and ``code_tok`` run
    over ``spec_code_lines``, L2/L3 over ``spec_code_source``, and L4's
    executed control over ``spec_python_source`` — all three from the same
    whole-document detection pass. A fence-only L4 let a working
    implementation pasted as indented markdown execute nothing while sliding
    under the L1-L3 caps. This narrower extractor is retained as a
    fence-parsing utility only.
    """
    blocks: list[str] = []
    current: list[str] | None = None
    for line in markdown.splitlines():
        match = _FENCE_LINE.match(line)
        if match is not None:
            if current is not None and not match.group("info"):
                blocks.append("\n".join(current))
                current = None
            else:
                if current is not None:  # desync: flush the spurious block
                    blocks.append("\n".join(current))
                current = []
            continue
        if current is not None:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return tuple(blocks)


def _detected_flags(lines: Sequence[str]) -> tuple[bool, ...]:
    """Per-line code flags: fenced ∪ indented ∪ classifier, raw ∪ dedressed.

    The dressing-stripped form is classified alongside the raw one, so a
    blockquoted / bulleted / table-wrapped implementation lands in exactly
    the same place a bare one does.
    """
    fenced = _fenced_line_flags(lines)
    flags: list[bool] = []
    for line, inside in zip(lines, fenced):
        if not line.strip():
            flags.append(False)
            continue
        bare = _dedress(line)
        flags.append(bool(
            inside
            or _INDENTED.match(line) or _looks_like_code(line.strip())
            or _INDENTED.match(bare) or _looks_like_code(bare.strip())))
    return tuple(flags)


def spec_code_lines(markdown: str) -> tuple[str, ...]:
    """Every line of ``markdown`` classified as code, whole-document, RAW.

    The union of (i) fenced-block body lines (``_fenced_line_flags``),
    (ii) 4-space/tab-indented lines (markdown indented-code semantics — how
    an unfenced oracle paste presents), and (iii) per-line Python classifier
    hits — (ii) and (iii) evaluated on the raw line *and* on its
    dressing-stripped form (``_dedress``), so a blockquote, bullet or table
    wrapper cannot hide an implementation from the detector. Blank lines
    never count. Lines come back RAW (markers included) because this is L1's
    numerator and ``code_tok``'s surface: dressing must never *reduce* the
    measured code, and adding a marker is not a discount.

    Over-counting prose is accepted: the L caps are calibrated on honest
    A0/A0_prime cells under this same detector. ``spec_code_source`` (both
    dressings, for containment) and ``spec_python_source`` (L4's executable
    candidate) are derived from this same detection pass, so no leakage
    channel can be dodged by choosing how the code is dressed.
    """
    lines = markdown.splitlines()
    return tuple(line for line, hit in zip(lines, _detected_flags(lines))
                 if hit)


def spec_code_source(markdown: str) -> str:
    """The detected code as text, carrying BOTH dressings — L2/L3's surface.

    Every detected line appears raw, and its dressing-stripped form is
    appended when it differs. Containment is a set operation over n-grams, so
    holding both forms is strictly more sensitive and never less: a
    blockquoted paste's ``>`` markers otherwise split every cross-line 5-gram
    (measured: a verbatim b01 oracle blockquote reaches only 0.195 against
    the raw spec stream, under the 0.25 L2 cap).
    """
    lines = spec_code_lines(markdown)
    bare = tuple(_dedress(line) for line in lines)
    extra = tuple(b for line, b in zip(lines, bare) if b != line)
    return "\n".join(lines + extra)


def _detected_runs(markdown: str) -> tuple[tuple[str, ...], ...]:
    """Maximal runs of detected lines; blank lines continue a run."""
    lines = markdown.splitlines()
    flags = _detected_flags(lines)
    runs: list[list[str]] = []
    current: list[str] = []
    for line, hit in zip(lines, flags):
        if hit:
            current.append(line)
        elif not line.strip() and current:
            current.append(line)          # blank inside a block, not a break
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return tuple(tuple(run) for run in runs)


def _parseable_source(lines: Sequence[str]) -> str | None:
    """Common-dedented Python source for ``lines``, or ``None`` if neither
    the raw nor the dressing-stripped form parses. ``ast`` only, never exec.
    """
    for form in (lines, tuple(_dedress(line) for line in lines)):
        source = textwrap.dedent("\n".join(form))
        if not source.strip():
            continue
        try:
            ast.parse(source)
        except SyntaxError:
            continue
        return source
    return None


def _blank_separated(run: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    """``run`` split on its blank lines — the finest L4 assembly grain."""
    groups: list[list[str]] = []
    current: list[str] = []
    for line in run:
        if line.strip():
            current.append(line)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return tuple(tuple(group) for group in groups)


def spec_python_source(markdown: str) -> str:
    """L4's executable candidate: the detected code that is actually Python.

    Three cascade levels, each tried only when the one above fails to parse,
    and each level trying the raw lines before their dressing-stripped form:

    1. the WHOLE detected set, common-dedented — the only form that preserves
       cross-block context (a signature and its body split by a prose line);
    2. each maximal detected line-run;
    3. each blank-line-separated group inside a run.

    Levels 2 and 3 exist because a single non-Python detected block used to
    take the whole candidate down with it: the assembled source raised
    ``SyntaxError``, which reported as *no L4 signal* — a free pass for the
    working implementation embedded beside it. Level 3 is not redundant:
    detected runs are broken only by non-blank prose, so an indented payload
    example one BLANK LINE above the paste is part of the same run, and
    without it the same free pass returns. ``""`` when nothing parses; the
    caller reports no signal (flagged, never clean).

    ``ast.parse`` only. Nothing here imports or executes the spec; the CLI
    runs the returned source in the same subprocess-isolated oracle harness
    every implementation goes through.
    """
    runs = _detected_runs(markdown)
    whole = _parseable_source([line for run in runs for line in run])
    if whole is not None:
        return whole
    parts: list[str] = []
    for run in runs:
        source = _parseable_source(run)
        if source is None:
            parts.extend(part for group in _blank_separated(run)
                         if (part := _parseable_source(group)) is not None)
        else:
            parts.append(source)
    return "\n".join(parts)


def code_token_count(markdown: str) -> int:
    """``code_tok(spec)``: TOKENS count over whole-document detected code.

    The single detector shared by L1's numerator and U1's cost-conservation
    term (``usage.spend_index``'s ``code_tokens``) — moving implementation
    work into the spec is score-neutral whether or not the code is fenced.
    """
    return sum(len(TOKENS.findall(line)) for line in spec_code_lines(markdown))


def _code_without_docstrings(source: str) -> str:
    """``source`` with module/class/function docstrings removed (``ast`` only).

    The L2 denominator is ``|grams(reference)|``, so the reference's own prose
    must not be in it. In the identifier-skeleton channel every punctuation-free
    prose word collapses to the same placeholder, which makes a docstring
    sentence match ordinary honest spec prose: measured at 0.092 across the
    honest fixture × corpus-oracle sweep, and exactly 0.000 once stripped.
    Unparseable source is returned unchanged (a fail-closed over-count, and
    the reference is a frozen corpus asset — it parses by construction).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    drop: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)) or not body:
            continue
        head = body[0]
        if (isinstance(head, ast.Expr) and isinstance(head.value, ast.Constant)
                and isinstance(head.value.value, str)
                and head.end_lineno is not None):
            drop.update(range(head.lineno, head.end_lineno + 1))
    return "\n".join(line for i, line in enumerate(source.splitlines(), start=1)
                     if i not in drop)


def _reference_containment(spec_md: str, spec_code: str,
                           reference_py: str) -> float:
    """L2: how much of the reference implementation is present in the spec.

    Three channels, maxed (each internally maxed over raw and
    identifier-skeleton tokens by ``ngram_containment``):

    * ``reference → detected spec code`` — reference-denominated presence.
      The author cannot move this by padding: the denominator is the frozen
      oracle, not their own document.
    * ``reference → the raw spec stream`` — a backstop for dressings the
      detector has not learned (word tokens survive most line decoration).
      Weaker than it looks: marker tokens split cross-line grams, so a
      blockquoted verbatim oracle reads only 0.195 here — the detected-code
      channel above (which de-dresses) is what closes that vector.
    * ``detected spec code → reference`` — the LEGACY spec-denominated
      channel, kept for partial-paste sensitivity (three lines lifted from a
      hundred-line oracle: 1.0 here, 0.03 reference-denominated). Only a
      ``max``, so dilution — which attacks this channel's denominator — is
      still closed by the two above.

    All three measured at 0.000 on the honest fixture × corpus-oracle sweep.
    """
    reference_code = _code_without_docstrings(reference_py)
    return max(
        ngram_containment(reference_code, spec_code),
        ngram_containment(reference_code, spec_md),
        ngram_containment(spec_code, reference_code),
    )


def leakage_report(spec_md: str, reference_py: str, impl_src: str,
                   spec_only_correctness: float | None,
                   caps: Mapping[str, float]) -> LeakageReport:
    """L1-L4 for one arm cell. Any failure voids the arm's U and O subscores.

    ``caps`` uses the manifest's ``bench.leak_caps`` keys: ``code_frac``,
    ``reference``, ``copy``, ``spec_only_correctness``. A ``None``
    ``spec_only_correctness`` (spec code did not import) is recorded as
    ``nan`` and flagged in ``reasons`` without blocking — L1-L3 carry the
    gate; a non-import must never read as clean.

    L1-L3 run over whole-document code detection, never only fenced bodies —
    an implementation pasted as indented prose, dressed as a blockquote /
    bullet list / table, or hidden behind a fence-parity desync is the same
    leak as a fenced one. L2 is REFERENCE-denominated (``_reference_containment``)
    so padding the spec cannot dilute it; L3 stays impl-denominated, and its
    ``impl_src`` must exclude the arm's test files (the caller's job — tests
    the arm wrote are its own denominator padding).
    """
    spec_code = spec_code_source(spec_md)
    total_tokens = len(TOKENS.findall(spec_md))
    code_frac = (code_token_count(spec_md) / total_tokens
                 if total_tokens else 0.0)
    reference = _reference_containment(spec_md, spec_code, reference_py)
    copy = ngram_containment(impl_src, spec_code)

    reasons: list[str] = []
    if code_frac > caps["code_frac"]:
        reasons.append(
            f"L1 code_frac {code_frac:.3f} > cap {caps['code_frac']:.3f}")
    if reference > caps["reference"]:
        reasons.append(
            f"L2 reference containment {reference:.3f} "
            f"> cap {caps['reference']:.3f}")
    if copy > caps["copy"]:
        reasons.append(
            f"L3 impl-spec copy {copy:.3f} > cap {caps['copy']:.3f}")
    blocked = bool(reasons)

    if spec_only_correctness is None:
        soc = float("nan")
        reasons.append("L4 no signal: spec code does not import "
                       "(flagged, never read as clean)")
    else:
        soc = spec_only_correctness
        if soc >= caps["spec_only_correctness"]:
            reasons.append(
                f"L4 spec_only_correctness {soc:.3f} "
                f">= {caps['spec_only_correctness']:.3f} "
                f"- the spec is the implementation")
            blocked = True

    return LeakageReport(
        code_frac=code_frac,
        reference_containment=reference,
        copy_containment=copy,
        spec_only_correctness=soc,
        blocked=blocked,
        reasons=tuple(reasons),
    )

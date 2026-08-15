"""Parse a ``stream-json`` run transcript into a fail-closed usage report.

``scripts/run-implementer.sh`` captures the implementer CLI's stdout as
``transcript.jsonl`` — one JSON object per line. The final
``{"type": "result"}`` event is the *only* authoritative source for
``num_turns``, token usage, cost, and duration (never sum assistant lines:
retries and sub-agent traffic would double-count). This module turns that
transcript plus the process return code into a frozen :class:`UsageReport`.

**FAIL-CLOSED, non-negotiable** (BENCHMARK.md §3). A transcript with no
readable result event yields ``status="missing"`` with **every numeric field
``None`` — never ``0``**. U1 scores ``ln(output_tokens + code_tok)``, so a
fabricated zero would make a crashed cell read as the *cheapest* cell and hand
its arm a fraudulent win. Missing/timeout/error cells are excluded from every
U/O statistic and counted into ``incomplete_fraction`` by the caller; this
module's job is only to make the cell's condition explicit, never to guess.

Status assignment, in precedence order:

* ``return_code == 124`` (portable-timeout kill) => ``"timeout"``. A result
  event, if one squeaked out before the kill, is recorded as diagnostics.
* no parseable ``{"type": "result"}`` line => ``"missing"``, all-``None``.
* a result event whose *scored* fields (``subtype``, ``num_turns``,
  ``usage.output_tokens``) are absent or mistyped => ``"missing"`` too — a
  garbled result must never read as complete-but-cheap.
* ``subtype in {"error_during_execution", "error_max_turns"}`` => ``"error"``
  (observed numerics kept: the money was really spent and feeds the budget
  layer; ``status`` alone excludes the cell from scoring).
* otherwise => ``"ok"``; U4's ``subtype == "success"`` gate reads ``subtype``.

Per the frozen contract, ``subtype`` is populated only when ``status == "ok"``;
for every other status it is ``None`` and ``detail`` carries the reason.

Malformed JSON lines are *skipped, not fatal* — one garbled progress line must
not void an otherwise complete cell. When several result events appear (e.g. a
retry appended to the same file), the **last one wins** and ``detail`` records
the duplication.

Scoring assumptions baked into the fields:

* ``input_tokens`` is recorded but **never scored** — it is spec length, the
  forbidden length proxy (a shorter spec would win U1 by construction).
* ``cache_creation_input_tokens`` / ``cache_read_input_tokens`` are diagnostics
  only; scoring them would make U1 depend on cache temperature (§5 vector 6).
* ``total_cost_usd`` feeds the budget layer only (pricing/cache dependent).
* ``tool_calls`` tallies *observed* top-level ``tool_use`` blocks
  (Edit / Write / Bash / other), mirroring ``deadend.py``'s top-level-only rule
  (``parent_tool_use_id is null``) so sub-agent traffic is not double-counted.
  The counts are diagnostics over events actually present in the transcript —
  an observation, never an imputation — and are never scored; cell exclusion is
  governed solely by ``status``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Iterable, Iterator

#: ``result.subtype`` values that mark a run the CLI itself reported as failed.
_ERROR_SUBTYPES = frozenset({"error_during_execution", "error_max_turns"})

#: Portable-timeout return code (``timeout(1)`` kill), per run-implementer.sh.
_TIMEOUT_RC = 124


@dataclass(frozen=True)
class ToolCallCounts:
    """Top-level ``tool_use`` tallies for one transcript. Diagnostic only.

    ``edit``/``write``/``bash`` are the three tool names the U-dimension
    analyses key off; every other tool (Read, Grep, Glob, WebFetch, ...) folds
    into ``other``. Sub-agent blocks (``parent_tool_use_id`` set) are excluded.
    """

    edit: int
    write: int
    bash: int
    other: int

    @property
    def total(self) -> int:
        return self.edit + self.write + self.bash + self.other


@dataclass(frozen=True)
class UsageReport:
    """One cell's usage, parsed fail-closed from ``transcript.jsonl``.

    ``status`` is ``"ok" | "missing" | "timeout" | "error"``. Only ``"ok"``
    cells enter any U statistic; the others are excluded *and counted* into
    ``incomplete_fraction`` by the caller — never imputed, never zero.
    """

    status: str
    subtype: str | None  # result.subtype; None when status != "ok"
    num_turns: int | None
    output_tokens: int | None
    input_tokens: int | None  # recorded, NEVER scored (length proxy)
    cache_creation_input_tokens: int | None  # diagnostic only
    cache_read_input_tokens: int | None  # diagnostic only
    total_cost_usd: float | None  # budget layer only, never scored
    duration_ms: int | None
    tool_calls: ToolCallCounts
    detail: str = ""


def _opt_int(value: object) -> int | None:
    """``value`` as an int, else ``None``. ``bool`` is rejected (it is an int
    subclass and ``True`` would silently read as 1 turn/token)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _opt_float(value: object) -> float | None:
    """``value`` as a float (ints accepted), else ``None``; bools rejected."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _iter_tool_uses(obj: object) -> Iterator[str]:
    """Yield the tool name of every ``tool_use`` block in one transcript line
    object, tolerant of the stream-json envelope shape (``message.content``
    or a bare ``content`` list)."""
    if not isinstance(obj, dict):
        return
    msg = obj.get("message")
    content = msg.get("content") if isinstance(msg, dict) else obj.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if (
            isinstance(block, dict)
            and block.get("type") == "tool_use"
            and isinstance(block.get("name"), str)
        ):
            yield block["name"]


def parse_usage(lines: Iterable[str], *, return_code: int = 0) -> UsageReport:
    """Parse transcript lines + process return code into a :class:`UsageReport`.

    Malformed JSON lines are skipped, not fatal. The last ``{"type":"result"}``
    event wins (duplicates noted in ``detail``). No readable result event — or
    one whose scored fields are absent/mistyped — yields ``status="missing"``
    with every numeric field ``None``, never fabricated zeros.
    """
    result_events: list[dict] = []
    edit = write = bash = other = 0
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue  # skipped, not fatal
        if not isinstance(obj, dict):
            continue
        if obj.get("type") == "result":
            result_events.append(obj)
            continue
        if obj.get("parent_tool_use_id") is not None:
            continue  # sub-agent traffic: top-level events only
        for name in _iter_tool_uses(obj):
            if name == "Edit":
                edit += 1
            elif name == "Write":
                write += 1
            elif name == "Bash":
                bash += 1
            else:
                other += 1
    tool_calls = ToolCallCounts(edit=edit, write=write, bash=bash, other=other)

    notes: list[str] = []
    if len(result_events) > 1:
        notes.append(f"{len(result_events)} result events; last wins")

    result = result_events[-1] if result_events else None
    subtype = result.get("subtype") if result else None
    if not isinstance(subtype, str):
        subtype = None
    usage = result.get("usage") if result else None
    usage = usage if isinstance(usage, dict) else {}
    num_turns = _opt_int(result.get("num_turns")) if result else None
    output_tokens = _opt_int(usage.get("output_tokens"))
    input_tokens = _opt_int(usage.get("input_tokens"))
    cache_creation = _opt_int(usage.get("cache_creation_input_tokens"))
    cache_read = _opt_int(usage.get("cache_read_input_tokens"))
    total_cost_usd = _opt_float(result.get("total_cost_usd")) if result else None
    duration_ms = _opt_int(result.get("duration_ms")) if result else None

    def _report(status: str, *, keep_numbers: bool, keep_subtype: bool = False) -> UsageReport:
        return UsageReport(
            status=status,
            subtype=subtype if keep_subtype else None,
            num_turns=num_turns if keep_numbers else None,
            output_tokens=output_tokens if keep_numbers else None,
            input_tokens=input_tokens if keep_numbers else None,
            cache_creation_input_tokens=cache_creation if keep_numbers else None,
            cache_read_input_tokens=cache_read if keep_numbers else None,
            total_cost_usd=total_cost_usd if keep_numbers else None,
            duration_ms=duration_ms if keep_numbers else None,
            tool_calls=tool_calls,
            detail="; ".join(notes),
        )

    if return_code == _TIMEOUT_RC:
        # The harness killed the run: never "ok" whatever the transcript says.
        # A pre-kill result event, if any, is kept as diagnostics.
        notes.append("rc=124 (timeout)")
        return _report("timeout", keep_numbers=result is not None)

    if result is None:
        notes.append("no result event")
        return _report("missing", keep_numbers=False)

    if subtype in _ERROR_SUBTYPES:
        # Observed numerics kept (real spend, feeds the budget layer); status
        # alone excludes the cell from every scored statistic.
        notes.append(f"subtype={subtype}")
        return _report("error", keep_numbers=True)

    missing_fields = [
        name
        for name, value in (
            ("subtype", subtype),
            ("num_turns", num_turns),
            ("usage.output_tokens", output_tokens),
        )
        if value is None
    ]
    if missing_fields:
        # A result event that cannot carry the scored fields is as good as no
        # result event: fail closed to "missing", all numerics None.
        notes.append("result event unusable: " + ", ".join(missing_fields))
        return _report("missing", keep_numbers=False)

    if return_code != 0:
        notes.append(f"rc={return_code}")
    return _report("ok", keep_numbers=True, keep_subtype=True)


def spend_index(report: UsageReport, code_tokens: int) -> float:
    """U1's spend index: ``ln(output_tokens + code_tokens)``.

    ``code_tokens`` is ``code_tok(spec)`` — ``deadend.code_token_count``, the
    whitespace-token count of the spec's whole-document detected code lines
    (fenced or not; same detector as L1) — summed in so that moving
    implementation work into the spec is score-neutral (§5 vector 1, cost
    conservation).

    Fail-closed guards, all ``ValueError`` (a spend index must never exist for
    a cell that has no trustworthy spend):

    * ``report.status != "ok"`` or ``output_tokens is None``;
    * ``code_tokens < 0``;
    * a non-positive total (``ln`` undefined).
    """
    if report.status != "ok" or report.output_tokens is None:
        raise ValueError(
            f"spend_index requires an ok report with output_tokens; "
            f"got status={report.status!r} (excluded cell, never imputed)"
        )
    if code_tokens < 0:
        raise ValueError(f"code_tokens must be >= 0, got {code_tokens}")
    spend = report.output_tokens + code_tokens
    if spend <= 0:
        raise ValueError(f"non-positive spend {spend}; ln undefined")
    return math.log(spend)

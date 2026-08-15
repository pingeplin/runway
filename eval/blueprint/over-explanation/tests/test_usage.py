"""Tests for the fail-closed transcript usage parser (BENCHMARK.md §3)."""

from __future__ import annotations

import json
import math

import pytest

from eval_overexplanation.usage import (
    ToolCallCounts,
    UsageReport,
    parse_usage,
    spend_index,
)

# ---------------------------------------------------------------- fixtures


def _result_line(
    *,
    subtype: str = "success",
    num_turns: int | None = 7,
    output_tokens: int | None = 3400,
    input_tokens: int | None = 1200,
    cache_creation: int | None = 800,
    cache_read: int | None = 9000,
    total_cost_usd: float | None = 0.1234,
    duration_ms: int | None = 45_210,
) -> str:
    usage: dict[str, object] = {}
    for key, value in (
        ("output_tokens", output_tokens),
        ("input_tokens", input_tokens),
        ("cache_creation_input_tokens", cache_creation),
        ("cache_read_input_tokens", cache_read),
    ):
        if value is not None:
            usage[key] = value
    obj: dict[str, object] = {"type": "result", "subtype": subtype, "usage": usage}
    for key, value in (
        ("num_turns", num_turns),
        ("total_cost_usd", total_cost_usd),
        ("duration_ms", duration_ms),
    ):
        if value is not None:
            obj[key] = value
    return json.dumps(obj)


def _assistant_line(*tool_names: str, parent: str | None = None) -> str:
    obj: dict[str, object] = {
        "type": "assistant",
        "parent_tool_use_id": parent,
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": f"tu_{i}", "name": name, "input": {}}
                for i, name in enumerate(tool_names)
            ],
        },
    }
    return json.dumps(obj)


_INIT_LINE = json.dumps({"type": "system", "subtype": "init", "session_id": "s1"})


# ---------------------------------------------------------------- happy path


def test_happy_path_parses_every_field() -> None:
    lines = [_INIT_LINE, _assistant_line("Write", "Bash"), _result_line()]
    report = parse_usage(lines)
    assert isinstance(report, UsageReport)
    assert report.status == "ok"
    assert report.subtype == "success"
    assert report.num_turns == 7
    assert report.output_tokens == 3400
    assert report.input_tokens == 1200
    assert report.cache_creation_input_tokens == 800
    assert report.cache_read_input_tokens == 9000
    assert report.total_cost_usd == pytest.approx(0.1234)
    assert report.duration_ms == 45_210
    assert report.detail == ""


def test_report_is_frozen() -> None:
    report = parse_usage([_result_line()])
    with pytest.raises(AttributeError):
        report.output_tokens = 0  # type: ignore[misc]


# ---------------------------------------------------------- missing result


def test_no_result_event_is_missing_with_all_none_never_zero() -> None:
    lines = [_INIT_LINE, _assistant_line("Edit"), _assistant_line("Bash")]
    report = parse_usage(lines)
    assert report.status == "missing"
    assert report.subtype is None
    # Every numeric field None — a zero would make a crashed cell the cheapest.
    assert report.num_turns is None
    assert report.output_tokens is None
    assert report.input_tokens is None
    assert report.cache_creation_input_tokens is None
    assert report.cache_read_input_tokens is None
    assert report.total_cost_usd is None
    assert report.duration_ms is None
    assert report.output_tokens != 0
    assert "no result event" in report.detail


def test_empty_transcript_is_missing() -> None:
    report = parse_usage([])
    assert report.status == "missing"
    assert report.output_tokens is None


def test_result_event_without_scored_fields_is_missing() -> None:
    # A result event with no usable usage.output_tokens must fail closed:
    # never "ok", never a fabricated zero.
    line = json.dumps({"type": "result", "subtype": "success", "num_turns": 3})
    report = parse_usage([line])
    assert report.status == "missing"
    assert report.output_tokens is None
    assert report.num_turns is None  # missing => ALL numerics None
    assert "usage.output_tokens" in report.detail


def test_result_event_with_mistyped_fields_is_missing() -> None:
    # bool is an int subclass; True must not read as num_turns == 1.
    line = json.dumps(
        {"type": "result", "subtype": "success", "num_turns": True,
         "usage": {"output_tokens": "3400"}}
    )
    report = parse_usage([line])
    assert report.status == "missing"
    assert report.num_turns is None
    assert report.output_tokens is None


# ------------------------------------------------------ malformed tolerance


def test_malformed_json_lines_are_skipped_not_fatal() -> None:
    lines = [
        "{not json at all",
        "",
        "   ",
        '["a", "bare", "list"]',
        '"a bare string"',
        _assistant_line("Bash"),
        "{\"type\": \"assistant\", \"truncated",
        _result_line(),
    ]
    report = parse_usage(lines)
    assert report.status == "ok"
    assert report.output_tokens == 3400
    assert report.tool_calls.bash == 1


def test_only_malformed_lines_is_missing() -> None:
    report = parse_usage(["{garbled", "also not json"])
    assert report.status == "missing"
    assert report.output_tokens is None


def test_duplicate_result_events_last_wins_and_is_noted() -> None:
    # Frozen contract: the LAST result event wins; the duplication is recorded.
    lines = [
        _result_line(output_tokens=100, num_turns=1),
        _result_line(output_tokens=3400, num_turns=7),
    ]
    report = parse_usage(lines)
    assert report.status == "ok"
    assert report.output_tokens == 3400
    assert report.num_turns == 7
    assert "2 result events" in report.detail


# ------------------------------------------------------------ timeout/error


def test_rc_124_is_timeout_even_with_success_result() -> None:
    report = parse_usage([_result_line()], return_code=124)
    assert report.status == "timeout"
    assert report.subtype is None  # subtype only when status == "ok"
    # A pre-kill result event is kept as diagnostics.
    assert report.output_tokens == 3400
    assert "124" in report.detail


def test_rc_124_without_result_event_has_no_numbers() -> None:
    report = parse_usage([_INIT_LINE], return_code=124)
    assert report.status == "timeout"
    assert report.output_tokens is None
    assert report.num_turns is None


@pytest.mark.parametrize("subtype", ["error_during_execution", "error_max_turns"])
def test_error_subtypes_are_error_status(subtype: str) -> None:
    report = parse_usage([_result_line(subtype=subtype)])
    assert report.status == "error"
    assert report.subtype is None  # subtype only when status == "ok"
    assert subtype in report.detail
    # Observed spend is kept (budget layer), but the cell is excluded by status.
    assert report.output_tokens == 3400
    assert report.total_cost_usd == pytest.approx(0.1234)


def test_nonzero_rc_with_success_result_stays_ok_and_noted() -> None:
    report = parse_usage([_result_line()], return_code=2)
    assert report.status == "ok"
    assert "rc=2" in report.detail


# --------------------------------------------------------- tool-call counts


def test_tool_call_counting_by_kind() -> None:
    lines = [
        _INIT_LINE,
        _assistant_line("Edit", "Edit", "Write"),
        _assistant_line("Bash", "Read", "Grep"),
        _assistant_line("Edit"),
        _result_line(),
    ]
    report = parse_usage(lines)
    assert report.tool_calls == ToolCallCounts(edit=3, write=1, bash=1, other=2)
    assert report.tool_calls.total == 7


def test_subagent_tool_uses_are_excluded() -> None:
    # Only top-level events (parent_tool_use_id null) count — mirrors deadend.
    lines = [
        _assistant_line("Edit"),
        _assistant_line("Bash", "Write", parent="tu_parent"),
        _result_line(),
    ]
    report = parse_usage(lines)
    assert report.tool_calls == ToolCallCounts(edit=1, write=0, bash=0, other=0)


def test_tool_counts_survive_missing_result() -> None:
    # Counts are observations over events actually present; they are
    # diagnostics, never scored, and status alone excludes the cell.
    report = parse_usage([_assistant_line("Write", "Bash")])
    assert report.status == "missing"
    assert report.tool_calls == ToolCallCounts(edit=0, write=1, bash=1, other=0)


def test_no_tool_uses_counts_zero() -> None:
    report = parse_usage([_INIT_LINE, _result_line()])
    assert report.tool_calls.total == 0


# --------------------------------------------------------------- spend_index


def test_spend_index_is_ln_of_output_plus_code_tokens() -> None:
    report = parse_usage([_result_line(output_tokens=3400)])
    assert spend_index(report, 600) == pytest.approx(math.log(4000))
    assert spend_index(report, 0) == pytest.approx(math.log(3400))


def test_spend_index_refuses_non_ok_report() -> None:
    missing = parse_usage([])
    with pytest.raises(ValueError):
        spend_index(missing, 100)
    errored = parse_usage([_result_line(subtype="error_max_turns")])
    with pytest.raises(ValueError):
        spend_index(errored, 100)


def test_spend_index_refuses_negative_code_tokens() -> None:
    report = parse_usage([_result_line()])
    with pytest.raises(ValueError):
        spend_index(report, -1)


def test_spend_index_refuses_non_positive_spend() -> None:
    report = parse_usage([_result_line(output_tokens=0)])
    assert report.status == "ok"  # 0 is a real observed value, not fabricated
    with pytest.raises(ValueError):
        spend_index(report, 0)

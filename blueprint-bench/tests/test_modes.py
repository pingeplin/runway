import json

import pytest

from harness import modes


def test_full_mode_invokes_tdd_with_headless():
    """Without --headless, /tdd's GATE prompts stall claude -p (see
    20260512_112016_e390836c). Full mode must signal headless to the
    orchestrator."""
    prompt = modes._build_prompt("full", "fix the pagination bug")
    assert prompt.startswith("/tdd ")
    assert "--headless" in prompt
    assert prompt.endswith("fix the pagination bug")


def test_naked_mode_passes_description_verbatim():
    prompt = modes._build_prompt("naked", "fix the pagination bug")
    assert prompt == "fix the pagination bug"


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        modes._build_prompt("nope", "x")


def _write_transcript(path, events):
    with path.open("w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def test_parse_usage_extracts_cost_and_tokens(tmp_path):
    """The final type=result event carries total_cost_usd + usage. Parser must
    pull the last one even if earlier streaming events also pass through."""
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        {"type": "stream_event", "event": {"type": "message_start"}},
        {"type": "assistant", "message": {"content": "thinking"}},
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 312000,
            "duration_api_ms": 287000,
            "num_turns": 14,
            "total_cost_usd": 4.231,
            "usage": {
                "input_tokens": 1200,
                "output_tokens": 8400,
                "cache_creation_input_tokens": 50000,
                "cache_read_input_tokens": 950000,
            },
        },
    ])

    usage = modes.parse_usage_from_transcript(transcript)

    assert usage is not None
    assert usage.cost_usd == pytest.approx(4.231)
    assert usage.input_tokens == 1200
    assert usage.output_tokens == 8400
    assert usage.cache_creation_tokens == 50000
    assert usage.cache_read_tokens == 950000
    assert usage.num_turns == 14
    assert usage.is_error is False
    assert usage.duration_api_ms == 287000


def test_parse_usage_returns_none_if_no_result_event(tmp_path):
    """A timed-out run never emits a result event. Parser returns None instead
    of zero-filled stats so the row makes the missingness obvious."""
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        {"type": "stream_event", "event": {"type": "message_start"}},
        {"type": "assistant", "message": {"content": "partial"}},
    ])

    assert modes.parse_usage_from_transcript(transcript) is None


def test_parse_usage_keeps_last_result_when_multiple_present(tmp_path):
    """Defensive: if multiple result events appear (shouldn't, but be robust),
    keep the final one."""
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript, [
        {"type": "result", "is_error": True, "total_cost_usd": 0.1, "usage": {}, "num_turns": 1},
        {"type": "result", "is_error": False, "total_cost_usd": 0.5, "usage": {}, "num_turns": 7},
    ])

    usage = modes.parse_usage_from_transcript(transcript)

    assert usage is not None
    assert usage.cost_usd == pytest.approx(0.5)
    assert usage.is_error is False
    assert usage.num_turns == 7


def test_parse_usage_missing_file_returns_none(tmp_path):
    assert modes.parse_usage_from_transcript(tmp_path / "nope.jsonl") is None


def test_usage_to_dict_handles_none():
    assert modes.usage_to_dict(None) is None


def test_usage_to_dict_serializes_usage_stats():
    usage = modes.UsageStats(
        cost_usd=1.5,
        input_tokens=100,
        output_tokens=200,
        cache_creation_tokens=300,
        cache_read_tokens=400,
        num_turns=5,
        is_error=False,
        duration_api_ms=10000,
    )
    d = modes.usage_to_dict(usage)
    assert d == {
        "cost_usd": 1.5,
        "input_tokens": 100,
        "output_tokens": 200,
        "cache_creation_tokens": 300,
        "cache_read_tokens": 400,
        "num_turns": 5,
        "is_error": False,
        "duration_api_ms": 10000,
    }

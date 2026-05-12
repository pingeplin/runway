from scorers import efficiency


def _row(mode: str, score, cost, in_tok=100, out_tok=100):
    return {
        "mode": mode,
        "score": score,
        "usage": {
            "cost_usd": cost,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
        },
    }


def test_empty_rows_returns_empty():
    assert efficiency.compute([]) == {}


def test_drops_rows_missing_score_or_usage():
    rows = [
        _row("full", None, 1.0),
        {"mode": "full", "score": 1.0, "usage": None},
    ]
    assert efficiency.compute(rows) == {}


def test_cheaper_resolved_mode_has_higher_eucb():
    """Two modes, equal resolve rate (both fully resolve their cells), but one
    spends drastically less. The cheap mode should have a higher EuCB."""
    rows = [
        _row("cheap", 1.0, 0.10),
        _row("cheap", 1.0, 0.20),
        _row("dear", 1.0, 5.00),
        _row("dear", 1.0, 6.00),
    ]
    out = efficiency.compute(rows)
    assert out["cheap"]["EuCB"] > out["dear"]["EuCB"]
    assert out["cheap"]["n"] == 2
    assert out["dear"]["n"] == 2


def test_unresolved_cells_drag_auc_down():
    """If a mode resolves nothing, EuCB == 0 regardless of cost."""
    rows = [
        _row("dud", 0.0, 0.10),
        _row("dud", 0.0, 0.20),
    ]
    out = efficiency.compute(rows)
    assert out["dud"]["EuCB"] == 0.0
    assert out["dud"]["EuTB"] == 0.0


def test_resolve_threshold_is_strict_pass_by_default():
    """Default threshold = 1.0 — partial passes don't count as resolved."""
    rows = [
        _row("partial", 0.5, 0.10),
        _row("partial", 0.5, 0.20),
    ]
    out = efficiency.compute(rows)
    assert out["partial"]["EuCB"] == 0.0


def test_lower_threshold_credits_partial_passes():
    rows = [
        _row("partial", 0.5, 0.10),
        _row("partial", 0.5, 0.20),
    ]
    out = efficiency.compute(rows, resolve_threshold=0.4)
    assert out["partial"]["EuCB"] > 0.0


def test_tokens_axis_uses_input_plus_output_plus_cache():
    rows = [
        _row("full", 1.0, 1.0, in_tok=1000, out_tok=2000),
        _row("full", 1.0, 1.0, in_tok=10, out_tok=20),
    ]
    out = efficiency.compute(rows)
    assert out["full"]["max_tokens"] == 3000

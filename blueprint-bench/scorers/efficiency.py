"""Suite-level efficiency (EuTB / EuCB) — AUC of resolve-rate vs token /
cost budget per mode, budget axis shared across modes. Higher = mode
resolves more cells with less spend. From SWE-Effi 2025.
"""
from __future__ import annotations


def _total_tokens(usage: dict) -> int:
    return (
        int(usage.get("input_tokens") or 0)
        + int(usage.get("output_tokens") or 0)
        + int(usage.get("cache_creation_tokens") or 0)
        + int(usage.get("cache_read_tokens") or 0)
    )


def _auc_resolve_vs_budget(
    points: list[tuple[float, bool]],
    max_budget: float,
) -> float:
    """Step-function AUC of resolved-rate vs budget over [0, max_budget].

    `points` is a list of (cost, resolved) pairs for one mode. At budget B,
    the resolve-rate is |{p : p.cost <= B and p.resolved}| / N. We integrate
    that step function over [0, max_budget] and normalize so the result is
    in [0, 1].
    """
    if not points or max_budget <= 0:
        return 0.0
    n = len(points)
    ordered = sorted(points, key=lambda p: p[0])
    auc = 0.0
    cum_resolved = 0
    prev_x = 0.0
    for cost, resolved in ordered:
        if cost > max_budget:
            break
        auc += (cum_resolved / n) * (cost - prev_x)
        if resolved:
            cum_resolved += 1
        prev_x = cost
    auc += (cum_resolved / n) * (max_budget - prev_x)
    return auc / max_budget


def compute(rows: list[dict], resolve_threshold: float = 1.0) -> dict[str, dict]:
    """Compute per-mode EuCB and EuTB from a run's result rows.

    A row "resolves" when `score >= resolve_threshold`. Rows with no score or
    no usage data are dropped. Budget axes (cost in USD, total tokens) are
    shared across modes — each mode's AUC is over [0, global_max].
    """
    cleaned: list[tuple[str, float, int, bool]] = []
    for r in rows:
        mode = r.get("mode")
        score = r.get("score")
        usage = r.get("usage") or {}
        cost = usage.get("cost_usd")
        if mode is None or score is None or cost is None:
            continue
        resolved = score >= resolve_threshold
        cleaned.append((mode, float(cost), _total_tokens(usage), resolved))

    if not cleaned:
        return {}

    max_cost = max(c for _, c, _, _ in cleaned)
    max_tokens = max(t for _, _, t, _ in cleaned)

    by_mode: dict[str, list[tuple[float, int, bool]]] = {}
    for mode, cost, tokens, resolved in cleaned:
        by_mode.setdefault(mode, []).append((cost, tokens, resolved))

    out: dict[str, dict] = {}
    for mode, items in by_mode.items():
        eu_cb = _auc_resolve_vs_budget([(c, r) for c, _, r in items], max_cost)
        eu_tb = _auc_resolve_vs_budget(
            [(float(t), r) for _, t, r in items], float(max_tokens)
        )
        out[mode] = {
            "n": len(items),
            "EuCB": round(eu_cb, 4),
            "EuTB": round(eu_tb, 4),
            "max_cost_usd": round(max_cost, 4),
            "max_tokens": max_tokens,
        }
    return out

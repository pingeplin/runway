"""Reference oracle for the *backoff_delays* brief.

This is the trusted, hand-written reference implementation that the hidden
``cases.json`` were authored against. It is NOT the implementation under test
(arms generate their own); it exists so the case expectations can be regenerated
and audited independently of any arm. ``buildability.run_oracle`` runs each
arm's generated ``backoff_delays`` against the same frozen ``cases.json`` and
compares by ``==``.

Authored from the brief alone, blind to any arm's code (issue #10).
"""

from __future__ import annotations


def backoff_delays(
    retries: int, base: float, factor: float, cap: float
) -> list[float]:
    """Return the deterministic exponential backoff schedule.

    The delay before attempt ``i`` (for ``i`` in ``0 .. retries - 1``) is
    ``min(cap, base * factor ** i)``. No jitter; ``retries >= 0``.
    """
    return [min(cap, base * factor ** i) for i in range(retries)]


if __name__ == "__main__":  # pragma: no cover - manual audit aid
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "cases.json").read_text())["cases"]
    for case in cases:
        got = backoff_delays(*case["args"])
        status = "ok" if got == case["expected"] else "MISMATCH"
        print(f"{case['label']:>14}: {got!r}  [{status}]")

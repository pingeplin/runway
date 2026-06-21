"""Reference oracle for the *fixed-window rate limiter* brief (b01).

This is the trusted, hand-written reference implementation that the hidden
``cases.json`` were authored against. It is NOT the implementation under test
(arms generate their own); it exists so the case expectations can be regenerated
and audited independently of any arm. ``buildability.run_oracle`` runs each
arm's generated ``allowed`` against the same frozen ``cases.json`` and compares
by ``==``.

Authored from the brief alone, blind to any arm's code (issue #10).
"""

from __future__ import annotations


def allowed(timestamps: list[int], limit: int, window: int) -> list[bool]:
    """Per-request fixed-window rate-limit verdicts.

    Requests are bucketed by their aligned window (``t // window``); each window
    permits at most ``limit`` requests. Rejected requests do not consume
    capacity. Returns one boolean per request, in input order.
    """
    counts: dict[int, int] = {}
    verdicts: list[bool] = []
    for t in timestamps:
        bucket = t // window
        used = counts.get(bucket, 0)
        if used < limit:
            counts[bucket] = used + 1
            verdicts.append(True)
        else:
            verdicts.append(False)
    return verdicts


if __name__ == "__main__":  # pragma: no cover - manual audit aid
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "cases.json").read_text())["cases"]
    for case in cases:
        got = allowed(*case["args"])
        status = "ok" if got == case["expected"] else "MISMATCH"
        print(f"{case['label']:>14}: {got!r}  [{status}]")

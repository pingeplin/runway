"""Reference oracle for the *idempotent webhook dedupe* brief (b02).

This is the trusted, hand-written reference implementation that the hidden
``cases.json`` were authored against. It is NOT the implementation under test
(arms generate their own ``process``); it exists so the case expectations can be
regenerated and audited independently of any arm. ``buildability.run_oracle``
runs each arm's generated ``process`` against the same frozen ``cases.json`` and
compares by ``==``.

Authored from the brief alone, blind to any arm's code (issue #10).
"""

from __future__ import annotations


def process(events: list[list]) -> list[str]:
    """Return the idempotency keys applied, first-seen order, each at most once.

    ``events`` is a list of ``[idempotency_key, amount]`` pairs delivered
    at-least-once. The first delivery of a key is applied; later deliveries of an
    already-applied key are ignored regardless of their amount.
    """
    applied: list[str] = []
    seen: set[str] = set()
    for key, _amount in events:
        if key in seen:
            continue
        seen.add(key)
        applied.append(key)
    return applied


if __name__ == "__main__":  # pragma: no cover - manual audit aid
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "cases.json").read_text())["cases"]
    for case in cases:
        got = process(*case["args"])
        status = "ok" if got == case["expected"] else "MISMATCH"
        print(f"{case['label']:>16}: {got!r}  [{status}]")

"""Reference oracle for the *running_total* brief.

This is the trusted, hand-written reference implementation that the hidden
``cases.json`` were authored against. It is NOT the implementation under test
(arms generate their own); it exists so the case expectations can be regenerated
and audited independently of any arm. ``buildability.run_oracle`` runs each
arm's generated ``running_total`` against the same frozen ``cases.json`` and
compares by ``==``.

Authored from the brief alone, blind to any arm's code (issue #10).
"""

from __future__ import annotations


def running_total(numbers: list[float]) -> list[float]:
    """Return the cumulative sum of ``numbers`` (same length, input unmutated)."""
    result: list[float] = []
    total = 0
    for n in numbers:
        total += n
        result.append(total)
    return result


if __name__ == "__main__":  # pragma: no cover - manual audit aid
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "cases.json").read_text())["cases"]
    for case in cases:
        got = running_total(*case["args"])
        status = "ok" if got == case["expected"] else "MISMATCH"
        print(f"{case['label']:>10}: {got!r}  [{status}]")

"""Reference oracle for the *Stable pagination cursor* brief (b08).

This is the trusted, hand-written reference implementation that the hidden
``cases.json`` were authored against. It is NOT the implementation under test
(arms generate their own); it exists so the case expectations can be regenerated
and audited independently of any arm. ``buildability.run_oracle`` runs each
arm's generated ``page`` against the same frozen ``cases.json`` and compares by
``==``.

Authored from the brief alone, blind to any arm's code (issue #10).
"""

from __future__ import annotations


def page(items: list[int], cursor: int | None, size: int) -> list:
    """Return ``[page_items, next_cursor]`` for keyset pagination.

    ``page_items`` holds up to ``size`` items strictly greater than ``cursor``,
    taken in ascending order. ``next_cursor`` is the last id on the page, or
    ``None`` when the page is empty.
    """
    page_items: list[int] = []
    for item in items:
        if cursor is not None and item <= cursor:
            continue
        if len(page_items) >= size:
            break
        page_items.append(item)
    next_cursor = page_items[-1] if page_items else None
    return [page_items, next_cursor]


if __name__ == "__main__":  # pragma: no cover - manual audit aid
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "cases.json").read_text())["cases"]
    for case in cases:
        got = page(*case["args"])
        status = "ok" if got == case["expected"] else "MISMATCH"
        print(f"{case['label']:>16}: {got!r}  [{status}]")

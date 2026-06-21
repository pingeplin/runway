"""Reference oracle for the *lru_results* brief.

This is the trusted, hand-written reference implementation that the hidden
``cases.json`` were authored against. It is NOT the implementation under test
(arms generate their own); it exists so the case expectations can be regenerated
and audited independently of any arm. ``buildability.run_oracle`` runs each
arm's generated ``lru_results`` against the same frozen ``cases.json`` and
compares by ``==``.

Authored from the brief alone, blind to any arm's code (issue #10).
"""

from __future__ import annotations

from collections import OrderedDict


def lru_results(operations: list, capacity: int) -> list:
    """Simulate an LRU cache and return the results of each ``get`` in order.

    ``operations`` is a list of ``["put", key, value]`` and ``["get", key]``
    entries. Both gets and puts mark the key as most recently used. A put of a
    brand-new key into a full cache first evicts the least-recently-used key.
    """
    cache: "OrderedDict" = OrderedDict()
    results: list = []
    for op in operations:
        kind = op[0]
        if kind == "get":
            key = op[1]
            if key in cache:
                cache.move_to_end(key)
                results.append(cache[key])
            else:
                results.append(None)
        else:  # "put"
            key, value = op[1], op[2]
            if key in cache:
                cache[key] = value
                cache.move_to_end(key)
            else:
                if len(cache) >= capacity:
                    cache.popitem(last=False)
                cache[key] = value
    return results


if __name__ == "__main__":  # pragma: no cover - manual audit aid
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "cases.json").read_text())["cases"]
    for case in cases:
        got = lru_results(*case["args"])
        status = "ok" if got == case["expected"] else "MISMATCH"
        print(f"{case['label']:>14}: {got!r}  [{status}]")

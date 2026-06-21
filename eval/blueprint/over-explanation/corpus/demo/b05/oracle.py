"""Reference oracle for the *CSV schema validator* brief (b05).

This is the trusted, hand-written reference implementation that the hidden
``cases.json`` were authored against. It is NOT the implementation under test
(arms generate their own); it exists so the case expectations can be regenerated
and audited independently of any arm. ``buildability.run_oracle`` runs each
arm's generated ``validate_rows`` against the same frozen ``cases.json`` and
compares by ``==``.

Authored from the brief alone, blind to any arm's code (issue #10).
"""

from __future__ import annotations

# Schema type name -> the exact Python type that satisfies it. bool and int are
# kept distinct on purpose (the brief makes the three type names mutually
# exclusive), so this maps to concrete types and matches with ``type(value) is``.
_TYPES: dict[str, type] = {"int": int, "str": str, "bool": bool}


def validate_rows(rows: list[dict], schema: dict[str, str]) -> list[str]:
    """Validate ``rows`` against ``schema``; return one error per problem row.

    For each row (numbered from zero by input index), examine the schema columns
    in schema order and report the first problem found: a missing column or a
    wrong type. Rows with no problem contribute nothing. Returns ``[]`` when all
    rows are valid.
    """
    errors: list[str] = []
    for i, row in enumerate(rows):
        for col, type_name in schema.items():
            if col not in row:
                errors.append(f"row {i}: missing column '{col}'")
                break
            value = row[col]
            expected = _TYPES[type_name]
            if type(value) is not expected:
                actual = type(value).__name__
                errors.append(
                    f"row {i}: column '{col}' expected {type_name}, got {actual}"
                )
                break
    return errors


if __name__ == "__main__":  # pragma: no cover - manual audit aid
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "cases.json").read_text())["cases"]
    for case in cases:
        got = validate_rows(*case["args"])
        status = "ok" if got == case["expected"] else "MISMATCH"
        print(f"{case['label']:>16}: {got!r}  [{status}]")

import pytest


def test_obviously_strong_password_is_accepted():
    from auth import validate_password

    result = validate_password("Tr0ub4dor&3Strong!")
    if isinstance(result, bool):
        assert result is True
    else:
        # Tolerate (ok: bool, reason: str|None) or similar shapes.
        assert result[0] is True

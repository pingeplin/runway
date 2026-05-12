"""Hidden oracle tests for T02_password_validator.

Encodes the behavioral contract the deliberately-vague description hides:

- Length: reject < 8 chars, accept >= 8 (up to a sane max).
- Char-class diversity: reject if it's all-letters or all-digits.
- Reject empty string.
- Reject None (don't TypeError — return False or raise something domain-shaped).
- Reject very common passwords case-insensitively.
- Reject overly long inputs (>= 1024 chars) to prevent CPU-bound checks.
- Reject non-string input gracefully (bytes, ints) — same contract as None.
- Accept unicode characters (treat them as 1 char each, NFKC-normalized
  is fine but not required).
"""
import pytest

from auth import validate_password


def _is_rejected(result) -> bool:
    if isinstance(result, bool):
        return result is False
    if isinstance(result, tuple):
        return result[0] is False
    # Anything else (e.g., raising) is also a rejection signal.
    return False


def _is_accepted(result) -> bool:
    if isinstance(result, bool):
        return result is True
    if isinstance(result, tuple):
        return result[0] is True
    return False


def _call(value):
    try:
        return validate_password(value)
    except (TypeError, ValueError):
        return False


def test_rejects_too_short():
    assert _is_rejected(_call("aB1!aB"))  # 6 chars


def test_rejects_empty_string():
    assert _is_rejected(_call(""))


def test_rejects_all_letters():
    assert _is_rejected(_call("abcdefghIJKLmnop"))


def test_rejects_all_digits():
    assert _is_rejected(_call("12345678901234"))


def test_rejects_none_gracefully():
    # Should not raise an uncaught TypeError.
    assert _is_rejected(_call(None))


def test_rejects_bytes_input():
    assert _is_rejected(_call(b"Tr0ub4dor&3Strong!"))


def test_rejects_extremely_long_input():
    assert _is_rejected(_call("Ab1!" * 300))  # 1200 chars


def test_accepts_unicode_password():
    # Latin-1 mix + digit + symbol; long enough.
    assert _is_accepted(_call("über-Sicher-2024!"))

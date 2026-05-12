# Password validator

Add a `validate_password(password)` function to the `auth` package. It
should reject weak passwords gracefully.

We expose it from `auth/__init__.py` so callers can do
`from auth import validate_password`.

There's a single trivial visible test in `tests/test_password.py` that
just checks an obvious strong password passes — you'll want to add more.

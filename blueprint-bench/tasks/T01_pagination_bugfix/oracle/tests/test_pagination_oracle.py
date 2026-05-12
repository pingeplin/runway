"""Hidden oracle tests for T01_pagination_bugfix.

These are never copied into the agent's working tree. They run against the
agent's fixed code after the run completes.
"""
import pytest

from pagination import paginate


def test_last_page_partial():
    """The off-by-one bug lives here: 23 items, page_size=10, page 3 should
    return [20, 21, 22] — not [20, 21]."""
    items = list(range(23))
    assert paginate(items, page=3, page_size=10) == [20, 21, 22]


def test_page_beyond_data_returns_empty():
    items = list(range(5))
    assert paginate(items, page=99, page_size=10) == []


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        paginate([1, 2, 3], page=1, page_size=0)
    with pytest.raises(ValueError):
        paginate([1, 2, 3], page=0, page_size=10)

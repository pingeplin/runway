from pagination import paginate


def test_first_page_full():
    items = list(range(100))
    assert paginate(items, page=1, page_size=10) == list(range(10))


def test_middle_page_full():
    items = list(range(100))
    assert paginate(items, page=3, page_size=10) == list(range(20, 30))

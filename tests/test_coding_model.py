from __future__ import annotations

from memory.coding_model import (
    DEFAULT_CODING_MODEL,
    DEFAULT_SEARCH_MODEL,
    get_coding_model,
    get_search_model,
)


def test_default_coding_model():
    assert get_coding_model() == DEFAULT_CODING_MODEL
    assert "3.1" in get_coding_model()
    assert "flash-lite" in get_coding_model().lower()


def test_default_search_model():
    assert get_search_model() == DEFAULT_SEARCH_MODEL
    assert get_search_model() == get_coding_model()

from __future__ import annotations

from memory.coding_model import get_search_model

from actions import web_search as ws


def test_search_model_is_lite():
    assert "3.1" in get_search_model()
    assert "flash-lite" in get_search_model().lower()


def test_format_ddg_empty():
    assert "No results" in ws._format_ddg("test", [])


def test_format_ddg_with_results():
    out = ws._format_ddg(
        "NBA",
        [{"title": "Headline", "snippet": "Summary", "url": "https://example.com"}],
    )
    assert "Headline" in out
    assert "example.com" in out


def test_ddg_search_mock(monkeypatch):
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def text(self, query, max_results=6, region=None):
            yield {"title": "A", "body": "B", "href": "https://a.com"}

        def news(self, query, max_results=6):
            return iter([])

    monkeypatch.setattr(ws, "_ddg_client", lambda: lambda: FakeDDGS())
    results = ws._ddg_search("NBA news", max_results=3)
    assert len(results) == 1
    assert results[0]["title"] == "A"

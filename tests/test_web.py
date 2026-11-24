"""Chrome page summary for web_read."""

from __future__ import annotations

from droidpilot import web as W


def test_summarize_lists_items_and_truncates() -> None:
    data = {"url": "https://x", "title": "T", "text": "a" * 50,
            "items": [{"tag": "a", "type": "", "name": "Learn more", "href": "https://y"},
                      {"tag": "input", "type": "search", "name": "", "href": ""}]}
    out = W.summarize(data, limit=10)
    assert "title: T" in out and "40 more characters" in out
    assert "[0] a 'Learn more' -> https://y" in out and "[1] input[search] ''" in out

from datetime import datetime, timezone, timedelta
import feed_reader


class _FakeFeed:
    def __init__(self, entries):
        self.entries = entries


def _entry(title, link, days_ago):
    pub = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "title": title,
        "link": link,
        "summary": "summary text",
        "published_parsed": pub.timetuple(),
    }


def test_filters_out_old_articles(monkeypatch):
    entries = [_entry("recent", "u1", 1), _entry("old", "u2", 30)]
    monkeypatch.setattr(feed_reader.feedparser, "parse", lambda url: _FakeFeed(entries))
    feeds = [{"name": "Test", "url": "http://x", "tags": ["t"]}]
    result = feed_reader.fetch_recent_articles(feeds, days=7)
    titles = [a["title"] for a in result]
    assert "recent" in titles
    assert "old" not in titles


def test_sorted_newest_first(monkeypatch):
    entries = [_entry("older", "u1", 5), _entry("newer", "u2", 1)]
    monkeypatch.setattr(feed_reader.feedparser, "parse", lambda url: _FakeFeed(entries))
    feeds = [{"name": "Test", "url": "http://x", "tags": []}]
    result = feed_reader.fetch_recent_articles(feeds, days=7)
    assert result[0]["title"] == "newer"


def test_skips_entries_without_date(monkeypatch):
    entries = [{"title": "no date", "link": "u", "summary": ""}]
    monkeypatch.setattr(feed_reader.feedparser, "parse", lambda url: _FakeFeed(entries))
    feeds = [{"name": "Test", "url": "http://x", "tags": []}]
    result = feed_reader.fetch_recent_articles(feeds, days=7)
    assert result == []


def test_failed_feed_does_not_raise(monkeypatch):
    def boom(url):
        raise ValueError("network down")
    monkeypatch.setattr(feed_reader.feedparser, "parse", boom)
    feeds = [{"name": "Bad", "url": "http://x", "tags": []}]
    result = feed_reader.fetch_recent_articles(feeds, days=7)
    assert result == []

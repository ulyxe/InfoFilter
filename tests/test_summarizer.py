import json
import summarizer
import summarizer_builder


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content):
        self._content = content

    def create(self, **kwargs):
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


class _FakeClient:
    def __init__(self, content):
        self.chat = _FakeChat(content)


def _articles():
    return [{"feed_name": "F", "title": "T", "link": "L", "summary": "S"}]


def test_engineer_returns_none_for_empty_articles():
    assert summarizer.summarize_articles([]) is None


def test_engineer_parses_valid_json(monkeypatch):
    payload = {"intro": "ciao", "highlights": [], "tip_of_the_week": "x", "action_of_the_week": {}}
    monkeypatch.setattr(summarizer, "_get_client", lambda: _FakeClient(json.dumps(payload)))
    result = summarizer.summarize_articles(_articles())
    assert result["intro"] == "ciao"


def test_engineer_invalid_json_returns_none(monkeypatch):
    monkeypatch.setattr(summarizer, "_get_client", lambda: _FakeClient("not json{{"))
    assert summarizer.summarize_articles(_articles()) is None


def test_builder_returns_none_for_empty_articles():
    assert summarizer_builder.summarize_builder([]) is None


def test_builder_parses_valid_json(monkeypatch):
    payload = {"intro": "ciao", "business_ideas": [], "agentic_pattern": {}, "case_study": {}}
    monkeypatch.setattr(summarizer_builder, "_get_client", lambda: _FakeClient(json.dumps(payload)))
    result = summarizer_builder.summarize_builder(_articles())
    assert result["intro"] == "ciao"


def test_builder_invalid_json_returns_none(monkeypatch):
    monkeypatch.setattr(summarizer_builder, "_get_client", lambda: _FakeClient("garbage"))
    assert summarizer_builder.summarize_builder(_articles()) is None

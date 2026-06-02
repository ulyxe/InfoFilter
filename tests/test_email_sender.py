import email_sender


def _engineer_digest():
    return {
        "intro": "Intro text",
        "highlights": [{
            "title": "H1", "summary": "S1", "source": "Src",
            "url": "http://h1", "relevance": "R1",
        }],
        "tip_of_the_week": "Tip text",
        "action_of_the_week": {
            "title": "Act", "what": "do", "why": "because", "time_required": "30 minuti",
        },
    }


def _builder_digest():
    return {
        "intro": "B intro",
        "business_ideas": [{
            "title": "Idea", "description": "desc", "why_now": "now",
            "italy_angle": "IT", "source_url": "http://s", "effort": "medio",
        }],
        "agentic_pattern": {"title": "Pat", "description": "d", "use_case": "u", "tools": ["t1", "t2"]},
        "case_study": {"title": "Case", "summary": "sum", "lesson": "les", "source_url": ""},
        "tip_of_the_week": "tip",
        "action_of_the_week": {"title": "A", "what": "w", "why": "y", "time_required": "1 ora"},
    }


def test_action_card_empty_returns_empty_string():
    assert email_sender._action_card_html({}, "#000000") == ""


def test_engineer_template_contains_content():
    html, plain = email_sender.render_engineer_template(
        _engineer_digest(),
        [{"feed_name": "F", "title": "T", "link": "L"}],
        "01 June 2026",
    )
    assert "Intro text" in html
    assert "http://h1" in html
    assert "Act" in html
    assert "01 June 2026" in plain


def test_engineer_fallback_when_no_digest():
    articles = [{"feed_name": "F", "title": "T", "link": "http://l"}]
    html, _ = email_sender.render_engineer_template(None, articles, "01 June 2026")
    assert "http://l" in html
    assert "AI summary unavailable" in html


def test_builder_template_contains_content_and_empty_url_href():
    html, _ = email_sender.render_builder_template(
        _builder_digest(),
        [{"feed_name": "F", "title": "T", "link": "L"}],
        "01 June 2026",
    )
    assert "Idea" in html
    assert "t1" in html
    # case_study.source_url is "" -> must fall back to "#"
    assert 'href="#"' in html

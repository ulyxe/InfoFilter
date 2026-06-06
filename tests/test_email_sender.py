"""Tests for email_sender: send_digest() PDF attachment support and template rendering."""
from __future__ import annotations

import email
from unittest.mock import patch

import email_sender
from email_sender import send_digest

ENV = {
    "SMTP_USER": "sender@test.com",
    "SMTP_PASSWORD": "pass",
    "DIGEST_RECIPIENT_EMAIL": "recv@test.com",
}


@patch("email_sender.smtplib.SMTP")
def test_send_digest_without_attachment_uses_alternative(mock_smtp_cls, monkeypatch):
    """Without attachment, the top-level MIME type must be multipart/alternative."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)

    mock_server = mock_smtp_cls.return_value.__enter__.return_value

    send_digest("Subj", "<p>HTML</p>", "Plain")

    mock_server.sendmail.assert_called_once()
    raw = mock_server.sendmail.call_args[0][2]
    msg = email.message_from_string(raw)
    assert msg.get_content_type() == "multipart/alternative"


@patch("email_sender.smtplib.SMTP")
def test_send_digest_with_attachment_uses_mixed(mock_smtp_cls, monkeypatch):
    """With attachment, the top-level MIME type must be multipart/mixed."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)

    mock_server = mock_smtp_cls.return_value.__enter__.return_value
    pdf_bytes = b"%PDF-1.4 fake content"

    send_digest("Subj", "<p>HTML</p>", "Plain", pdf_attachment=pdf_bytes)

    mock_server.sendmail.assert_called_once()
    raw = mock_server.sendmail.call_args[0][2]
    msg = email.message_from_string(raw)
    assert msg.get_content_type() == "multipart/mixed"


@patch("email_sender.smtplib.SMTP")
def test_send_digest_with_attachment_has_pdf_part(mock_smtp_cls, monkeypatch):
    """The mixed message must contain an application/* attachment part."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)

    mock_server = mock_smtp_cls.return_value.__enter__.return_value
    pdf_bytes = b"%PDF-1.4 fake content"

    send_digest("Subj", "<p>HTML</p>", "Plain", pdf_attachment=pdf_bytes,
                pdf_filename="digest.pdf")

    raw = mock_server.sendmail.call_args[0][2]
    msg = email.message_from_string(raw)
    parts = list(msg.walk())
    content_types = [p.get_content_type() for p in parts]
    # Must have at least one application/* part (the PDF)
    assert any(ct.startswith("application/") for ct in content_types)
    # Must contain a part with the correct filename
    dispositions = [p.get("Content-Disposition", "") for p in parts]
    assert any("digest.pdf" in d for d in dispositions)


@patch("email_sender.smtplib.SMTP")
def test_send_digest_with_attachment_contains_html_part(mock_smtp_cls, monkeypatch):
    """The mixed message must still contain the HTML body."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)

    mock_server = mock_smtp_cls.return_value.__enter__.return_value

    send_digest("Subj", "<p>HTML body</p>", "Plain body",
                pdf_attachment=b"%PDF test")

    raw = mock_server.sendmail.call_args[0][2]
    msg = email.message_from_string(raw)
    content_types = [p.get_content_type() for p in msg.walk()]
    assert "text/html" in content_types
    assert "text/plain" in content_types


# ---------------------------------------------------------------------------
# Template rendering tests (preserved from original file)
# ---------------------------------------------------------------------------

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

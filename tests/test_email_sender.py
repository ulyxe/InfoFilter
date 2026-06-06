"""Tests for send_digest() PDF attachment support in src/email_sender.py."""
from __future__ import annotations

import email
import os
from unittest.mock import MagicMock, patch

import pytest

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

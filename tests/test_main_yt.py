"""Tests for src/main_yt.py — fetch and report modes."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure src/ is on path (conftest.py handles this, but be explicit)
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import main_yt
from main_yt import _parse_yt_analysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(video_id: str, rating: int, days_ago: int = 0, topic: str = "Builder") -> dict:
    """Build a minimal cache entry."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "status": "ok",
        "analysis": f"**Titolo:** Video {video_id}\n**Vale il tempo?** {'⭐' * rating}\n",
        "rating": rating,
        "topic": topic,
        "title": f"Video {video_id}",
        "processed_at": dt.isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# Fetch mode tests
# ---------------------------------------------------------------------------

class TestFetchMode:
    def test_fetch_mode_processes_new_videos(self, tmp_path, monkeypatch, capsys):
        """mock fetch_playlist_ids, empty cache, process_new_videos returns 2 entries.
        Verify save_cache called and summary printed."""
        config_path = tmp_path / "config" / "yt_config.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            "playlist_id: PLtest\nmax_per_run: 5\nmodel: gemini-test\n",
            encoding="utf-8",
        )
        cache_path = tmp_path / "cache" / "yt_cache.json"

        monkeypatch.setattr(main_yt, "_CONFIG_PATH", config_path)
        monkeypatch.setattr(main_yt, "_CACHE_PATH", cache_path)

        # Mock environment variables
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake_yt_key")
        monkeypatch.setenv("GEMINI_API_KEY", "fake_gemini_key")

        returned_cache = {
            "vid1": _make_entry("vid1", 4),
            "vid2": _make_entry("vid2", 3),
        }

        mock_client_instance = MagicMock()
        mock_genai = MagicMock()
        mock_genai.Client.return_value = mock_client_instance

        with (
            patch("main_yt.fetch_playlist_ids", return_value=["vid1", "vid2"]) as mock_fetch,
            patch("main_yt.load_cache", return_value={}) as mock_load,
            patch("main_yt.process_new_videos", return_value=(returned_cache, 2, 0)) as mock_process,
            patch("main_yt.save_cache") as mock_save,
            patch("main_yt.genai", mock_genai),
            patch("main_yt.types", MagicMock()),
        ):
            main_yt.run_fetch()

        mock_fetch.assert_called_once_with("PLtest", "fake_yt_key")
        mock_load.assert_called_once()
        mock_process.assert_called_once()
        mock_save.assert_called_once()

        out = capsys.readouterr().out
        assert "2 new" in out
        assert "Cache updated" in out

    def test_fetch_mode_empty_playlist(self, tmp_path, monkeypatch, capsys):
        """fetch_playlist_ids returns [] → exits 0 with warning, no processing."""
        config_path = tmp_path / "config" / "yt_config.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            "playlist_id: PLtest\nmax_per_run: 5\nmodel: gemini-test\n",
            encoding="utf-8",
        )
        cache_path = tmp_path / "cache" / "yt_cache.json"

        monkeypatch.setattr(main_yt, "_CONFIG_PATH", config_path)
        monkeypatch.setattr(main_yt, "_CACHE_PATH", cache_path)
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake_yt_key")
        monkeypatch.setenv("GEMINI_API_KEY", "fake_gemini_key")

        with (
            patch("main_yt.fetch_playlist_ids", return_value=[]),
            patch("main_yt.process_new_videos") as mock_process,
            patch("main_yt.save_cache") as mock_save,
        ):
            main_yt.run_fetch()  # should return normally (exit 0)

        mock_process.assert_not_called()
        mock_save.assert_not_called()

        out = capsys.readouterr().out
        assert "empty" in out.lower() or "warn" in out.lower() or "nothing" in out.lower()


# ---------------------------------------------------------------------------
# Report mode tests
# ---------------------------------------------------------------------------

class TestReportMode:
    def test_report_mode_no_recent_videos(self, tmp_path, monkeypatch, capsys):
        """Cache has entries older than 7 days → prints 'skipping email', exits 0."""
        cache_path = tmp_path / "cache" / "yt_cache.json"
        monkeypatch.setattr(main_yt, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(main_yt, "_TEMPLATE_PATH", tmp_path / "no_template.html")

        old_cache = {
            "old1": _make_entry("old1", 4, days_ago=10),
            "old2": _make_entry("old2", 2, days_ago=8),
        }

        with (
            patch("main_yt.load_cache", return_value=old_cache),
            patch("main_yt.send_digest") as mock_send,
        ):
            main_yt.run_report()

        mock_send.assert_not_called()
        out = capsys.readouterr().out
        assert "skipping email" in out.lower() or "No new videos" in out

    def test_report_mode_sends_email(self, tmp_path, monkeypatch, capsys):
        """Cache has 2 recent entries → send_digest called once with correct subject."""
        cache_path = tmp_path / "cache" / "yt_cache.json"
        monkeypatch.setattr(main_yt, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(main_yt, "_TEMPLATE_PATH", tmp_path / "no_template.html")

        recent_cache = {
            "vid1": _make_entry("vid1", 5, days_ago=1),
            "vid2": _make_entry("vid2", 3, days_ago=2),
        }

        with (
            patch("main_yt.load_cache", return_value=recent_cache),
            patch("main_yt.send_digest") as mock_send,
        ):
            main_yt.run_report()

        mock_send.assert_called_once()
        subject_arg = mock_send.call_args[0][0]
        assert "YouTube Digest" in subject_arg
        assert "🎬" in subject_arg

    def test_report_mode_sorts_by_rating(self, tmp_path, monkeypatch):
        """Entries with ratings 3 and 5 are passed to template sorted by rating desc."""
        cache_path = tmp_path / "cache" / "yt_cache.json"
        monkeypatch.setattr(main_yt, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(main_yt, "_TEMPLATE_PATH", tmp_path / "no_template.html")

        recent_cache = {
            "low": _make_entry("low", 3, days_ago=1),
            "high": _make_entry("high", 5, days_ago=1),
        }

        captured_plain: list[str] = []

        def fake_send_digest(subject, html, plain, **kwargs):
            captured_plain.append(plain)

        with (
            patch("main_yt.load_cache", return_value=recent_cache),
            patch("main_yt.send_digest", side_effect=fake_send_digest),
        ):
            main_yt.run_report()

        assert captured_plain, "send_digest was not called"
        plain = captured_plain[0]
        # The high-rated video (5 stars) should appear before the low-rated (3 stars)
        pos_high = plain.index("Video high")
        pos_low = plain.index("Video low")
        assert pos_high < pos_low, (
            f"Expected high-rated entry first in plain text, got:\n{plain}"
        )

    def test_report_mode_subject_contains_date(self, tmp_path, monkeypatch):
        """Subject line includes today's date formatted as DD Month YYYY."""
        cache_path = tmp_path / "cache" / "yt_cache.json"
        monkeypatch.setattr(main_yt, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(main_yt, "_TEMPLATE_PATH", tmp_path / "no_template.html")

        recent_cache = {
            "vid1": _make_entry("vid1", 4, days_ago=0),
        }
        expected_date = datetime.now().strftime("%d %B %Y")

        with (
            patch("main_yt.load_cache", return_value=recent_cache),
            patch("main_yt.send_digest") as mock_send,
        ):
            main_yt.run_report()

        subject = mock_send.call_args[0][0]
        assert expected_date in subject

    def test_report_mode_html_contains_topic_badge(self, tmp_path, monkeypatch):
        """HTML email cards include a colored topic badge for each entry."""
        cache_path = tmp_path / "cache" / "yt_cache.json"
        monkeypatch.setattr(main_yt, "_CACHE_PATH", cache_path)
        # Provide a real template so the template branch (with badges) is exercised
        real_template = main_yt._ROOT / "templates" / "email_yt.html"
        monkeypatch.setattr(main_yt, "_TEMPLATE_PATH", real_template)

        recent_cache = {
            "b1": _make_entry("b1", 4, days_ago=1, topic="Builder"),
            "e1": _make_entry("e1", 3, days_ago=1, topic="Engineer"),
            "x1": _make_entry("x1", 2, days_ago=1, topic="—"),
        }

        captured_html: list[str] = []

        def fake_send_digest(subject, html, plain, **kwargs):
            captured_html.append(html)

        with (
            patch("main_yt.load_cache", return_value=recent_cache),
            patch("main_yt.send_digest", side_effect=fake_send_digest),
        ):
            main_yt.run_report()

        assert captured_html, "send_digest was not called"
        html = captured_html[0]
        assert "#f97316" in html, "Builder badge color missing"
        assert "#3b82f6" in html, "Engineer badge color missing"
        assert "#64748b" in html, "Fallback badge color missing"
        assert "🏗" in html, "Builder emoji missing"
        assert "⚙️" in html, "Engineer emoji missing"


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_fetch_mode_youtube_api_error_propagates(self, tmp_path, monkeypatch):
        """YouTube API errors must propagate (exit 1), not be swallowed."""
        config_path = tmp_path / "config" / "yt_config.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            "playlist_id: PLtest\nmax_per_run: 5\nmodel: gemini-test\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(main_yt, "_CONFIG_PATH", config_path)
        monkeypatch.setattr(main_yt, "_CACHE_PATH", tmp_path / "cache.json")
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake_yt_key")
        monkeypatch.setenv("GEMINI_API_KEY", "fake_gemini_key")

        with patch("main_yt.fetch_playlist_ids", side_effect=RuntimeError("YouTube API unreachable")):
            with pytest.raises(RuntimeError, match="YouTube API unreachable"):
                main_yt.run_fetch()

    def test_report_mode_smtp_error_exits_0(self, tmp_path, monkeypatch):
        """SMTP errors in report mode should exit 0 (not fail the action)."""
        cache_path = tmp_path / "cache" / "yt_cache.json"
        monkeypatch.setattr(main_yt, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(main_yt, "_TEMPLATE_PATH", tmp_path / "no_template.html")

        recent_cache = {"vid1": _make_entry("vid1", 4, days_ago=1)}

        parser = __import__("argparse").ArgumentParser()
        parser.add_argument("--mode", default="report")
        fake_args = parser.parse_args([])
        fake_args.mode = "report"

        with (
            patch("main_yt.load_cache", return_value=recent_cache),
            patch("main_yt.send_digest", side_effect=OSError("SMTP connection refused")),
            patch("main_yt.argparse") as mock_argparse,
        ):
            mock_argparse.ArgumentParser.return_value.parse_args.return_value = fake_args
            with pytest.raises(SystemExit) as exc_info:
                main_yt.main()
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# _parse_yt_analysis tests
# ---------------------------------------------------------------------------

FULL_ANALYSIS = """\
**Titolo:** Come Diventare un AI Engineer
**Canale:** Tech With Tim
**Durata stimata:** 11 minuti
**Argomento principale:** Una roadmap pratica in 10 passaggi per diventare AI engineer.
**Punti chiave:**
- Basi solide di Python
- Modelli Mentali dei LLM
- Prompt Engineering e RAG
**Strumenti e tecnologie:** Python, LangChain, Pinecone, Claude Code
**Risorse consigliate:** Corso di DeepLearning.AI, Paper: Attention is All You Need
**Metodologia:**
- Impara Python di base
- Comprendi le API dei LLM
- Implementa un sistema RAG
**Builder ROI:** 4/5 — Utile per monetizzare
**Engineer ROI:** 5/5 — Essenziale per il coding
**Topic dominante:** Entrambi
**Vale il tempo?** ⭐⭐⭐⭐⭐
**Perché:** Buono per tutti i profili
**Tag:** #AI #Python #RAG
"""


def test_parse_strumenti():
    result = _parse_yt_analysis(FULL_ANALYSIS)
    assert result["strumenti"] == ["Python", "LangChain", "Pinecone", "Claude Code"]


def test_parse_risorse():
    result = _parse_yt_analysis(FULL_ANALYSIS)
    assert result["risorse"] == [
        "Corso di DeepLearning.AI",
        "Paper: Attention is All You Need",
    ]


def test_parse_metodologia_bullets():
    result = _parse_yt_analysis(FULL_ANALYSIS)
    assert result["metodologia"] == [
        "Impara Python di base",
        "Comprendi le API dei LLM",
        "Implementa un sistema RAG",
    ]


def test_parse_metodologia_numbered():
    analysis = (
        "**Punti chiave:**\n- punto 1\n"
        "**Metodologia:**\n"
        "1. Step uno\n"
        "2. Step due\n"
        "**Builder ROI:** 3/5 — ok\n"
    )
    result = _parse_yt_analysis(analysis)
    assert result["metodologia"] == ["Step uno", "Step due"]


def test_parse_metodologia_na():
    analysis = (
        "**Punti chiave:**\n- punto 1\n"
        "**Metodologia:**\n"
        "N/A\n"
        "**Builder ROI:** 3/5 — ok\n"
    )
    result = _parse_yt_analysis(analysis)
    assert result["metodologia"] == []


def test_parse_strumenti_nessuno():
    analysis = (
        "**Punti chiave:**\n- punto 1\n"
        "**Strumenti e tecnologie:** nessuno\n"
        "**Risorse consigliate:** nessuna\n"
        "**Builder ROI:** 3/5 — ok\n"
    )
    result = _parse_yt_analysis(analysis)
    assert result["strumenti"] == []
    assert result["risorse"] == []


def test_parse_backward_compat_missing_fields():
    """Vecchie entry senza i nuovi campi: liste vuote, nessun crash."""
    old_analysis = (
        "**Titolo:** Old Video\n"
        "**Canale:** Chan\n"
        "**Punti chiave:**\n- punto 1\n"
        "**Builder ROI:** 3 — ok\n"
        "**Vale il tempo?** ⭐⭐⭐\n"
        "**Tag:** #AI\n"
    )
    result = _parse_yt_analysis(old_analysis)
    assert result["strumenti"] == []
    assert result["risorse"] == []
    assert result["metodologia"] == []


def test_parse_existing_fields_unchanged():
    """I campi esistenti continuano a essere estratti correttamente."""
    result = _parse_yt_analysis(FULL_ANALYSIS)
    assert result["canale"] == "Tech With Tim"
    assert result["durata"] == "11 minuti"
    assert result["argomento"] == "Una roadmap pratica in 10 passaggi per diventare AI engineer."
    assert len(result["punti"]) == 3
    assert result["builder_roi"].startswith("4/5")
    assert result["engineer_roi"].startswith("5/5")
    assert result["tags"] == "#AI #Python #RAG"

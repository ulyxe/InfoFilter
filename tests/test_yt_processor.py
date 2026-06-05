"""Tests for src/yt_processor.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import yt_processor


# ---------------------------------------------------------------------------
# extract_rating
# ---------------------------------------------------------------------------

def test_extract_rating_from_stars():
    """Count ⭐ emoji in the 'Vale il tempo?' line."""
    analysis = (
        "**Titolo:** Some Video\n"
        "**Vale il tempo?** ⭐⭐⭐⭐ perché è ottimo\n"
        "**Tag:** #AI"
    )
    assert yt_processor.extract_rating(analysis) == 4


def test_extract_rating_from_number():
    """Fallback to digit when no emoji stars are present."""
    analysis = (
        "**Titolo:** Some Video\n"
        "**Vale il tempo?** 3 — mediocre\n"
        "**Tag:** #AI"
    )
    assert yt_processor.extract_rating(analysis) == 3


def test_extract_rating_not_found():
    """Returns 0 when no rating line is present."""
    analysis = "**Titolo:** Some Video\nNessun voto qui."
    assert yt_processor.extract_rating(analysis) == 0


# ---------------------------------------------------------------------------
# extract_title
# ---------------------------------------------------------------------------

def test_extract_title_found():
    """Parses the **Titolo:** line."""
    analysis = (
        "**Titolo:** Come costruire un'app AI\n"
        "**Canale:** Dev Italia\n"
    )
    assert yt_processor.extract_title(analysis, "fallback") == "Come costruire un'app AI"


def test_extract_title_fallback():
    """Returns fallback when the **Titolo:** line is absent."""
    analysis = "**Canale:** Dev Italia\n**Tag:** #AI"
    assert yt_processor.extract_title(analysis, "my_fallback") == "my_fallback"


# ---------------------------------------------------------------------------
# load_cache / save_cache
# ---------------------------------------------------------------------------

def test_load_cache_missing_file(tmp_path):
    """Returns {} when the file doesn't exist."""
    result = yt_processor.load_cache(tmp_path / "nonexistent.json")
    assert result == {}


def test_load_cache_valid_json(tmp_path):
    """Returns parsed dict from a valid JSON file."""
    data = {"abc123": {"status": "ok", "rating": 4}}
    cache_file = tmp_path / "cache.json"
    cache_file.write_text(json.dumps(data), encoding="utf-8")

    result = yt_processor.load_cache(cache_file)
    assert result == data


def test_save_and_load_cache(tmp_path):
    """Round-trip: save then load returns identical dict."""
    cache_file = tmp_path / "subdir" / "cache.json"
    data = {
        "vid1": {"status": "ok", "rating": 3, "title": "Test Video"},
        "vid2": {"status": "ok", "rating": 5, "title": "Great Video"},
    }
    yt_processor.save_cache(data, cache_file)
    result = yt_processor.load_cache(cache_file)
    assert result == data


# ---------------------------------------------------------------------------
# process_new_videos
# ---------------------------------------------------------------------------

def _make_mock_client(analysis_text: str = None, side_effect=None):
    """Build a mock Gemini client whose generate_content returns analysis_text."""
    client = MagicMock()
    response = MagicMock()
    response.text = analysis_text or (
        "**Titolo:** Test Video\n"
        "**Canale:** Test Channel\n"
        "**Durata stimata:** 10 min\n"
        "**Argomento principale:** Testing\n"
        "**Punti chiave:**\n- punto 1\n"
        "**Vale il tempo?** ⭐⭐⭐\n"
        "**Perché:** buono\n"
        "**Tag:** #test\n"
    )
    if side_effect is not None:
        client.models.generate_content.side_effect = side_effect
    else:
        client.models.generate_content.return_value = response
    return client


@patch("yt_processor.time.sleep")
def test_process_new_videos_skips_cached(mock_sleep):
    """Already-cached IDs are skipped without calling the API."""
    cache = {"cached_vid": {"status": "ok", "rating": 4, "title": "Cached"}}
    client = _make_mock_client()

    result = yt_processor.process_new_videos(
        video_ids=["cached_vid"],
        cache=cache,
        client=client,
        model="gemini-test",
        max_per_run=5,
    )

    client.models.generate_content.assert_not_called()
    assert "cached_vid" in result


@patch("yt_processor.time.sleep")
def test_process_new_videos_respects_max_per_run(mock_sleep):
    """Stops after max_per_run successful analyses."""
    client = _make_mock_client()

    result = yt_processor.process_new_videos(
        video_ids=["v1", "v2", "v3", "v4", "v5"],
        cache={},
        client=client,
        model="gemini-test",
        max_per_run=2,
    )

    assert client.models.generate_content.call_count == 2
    assert len([k for k in result if result[k]["status"] == "ok"]) == 2


@patch("yt_processor.time.sleep")
def test_process_new_videos_adds_processed_at(mock_sleep):
    """Successful entries include a processed_at ISO timestamp."""
    client = _make_mock_client()

    result = yt_processor.process_new_videos(
        video_ids=["v1"],
        cache={},
        client=client,
        model="gemini-test",
        max_per_run=5,
    )

    assert "v1" in result
    assert "processed_at" in result["v1"]
    # Validate it looks like an ISO timestamp (YYYY-MM-DDTHH:MM:SS)
    ts = result["v1"]["processed_at"]
    assert len(ts) == 19
    assert ts[4] == "-" and ts[7] == "-" and ts[10] == "T"


@patch("yt_processor.time.sleep")
def test_process_new_videos_skips_on_error(mock_sleep):
    """Errors don't stop processing; failed IDs are not cached."""
    call_count = 0

    def side_effect(model, contents):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("API failure")
        # Second call succeeds
        resp = MagicMock()
        resp.text = (
            "**Titolo:** Good Video\n"
            "**Canale:** Chan\n"
            "**Durata stimata:** 5 min\n"
            "**Argomento principale:** OK\n"
            "**Punti chiave:**\n- a\n"
            "**Vale il tempo?** ⭐⭐\n"
            "**Perché:** ok\n"
            "**Tag:** #x\n"
        )
        return resp

    client = _make_mock_client(side_effect=side_effect)

    result = yt_processor.process_new_videos(
        video_ids=["fail_vid", "ok_vid"],
        cache={},
        client=client,
        model="gemini-test",
        max_per_run=5,
    )

    # Error video must NOT be cached
    assert "fail_vid" not in result
    # Success video IS cached
    assert "ok_vid" in result
    assert result["ok_vid"]["status"] == "ok"

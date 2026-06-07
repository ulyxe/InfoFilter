"""Tests for yt_playlist_manager — all YouTube API calls are mocked."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from yt_playlist_manager import (
    _get_playlist_item_id,
    _move_video,
    get_or_create_playlist,
    move_videos_after_report,
)


# ---------------------------------------------------------------------------
# get_or_create_playlist
# ---------------------------------------------------------------------------

def _make_youtube(existing_titles: list[str] | None = None):
    """Build a mock YouTube resource with playlist list/insert stubs."""
    yt = MagicMock()
    items = [
        {"id": f"PL_{t}", "snippet": {"title": t}}
        for t in (existing_titles or [])
    ]
    # Use .return_value access (no () call) so setup doesn't inflate call counts.
    yt.playlists.return_value.list.return_value.execute.return_value = {"items": items}
    yt.playlists.return_value.insert.return_value.execute.return_value = {"id": "PL_NEW"}
    return yt


def test_get_or_create_playlist_found():
    yt = _make_youtube(["Digested", "Other"])
    result = get_or_create_playlist(yt, "Digested")
    assert result == "PL_Digested"
    yt.playlists.return_value.insert.assert_not_called()


def test_get_or_create_playlist_not_found_creates():
    yt = _make_youtube(["Other"])
    result = get_or_create_playlist(yt, "Digested")
    assert result == "PL_NEW"
    yt.playlists.return_value.insert.assert_called_once()


# ---------------------------------------------------------------------------
# _get_playlist_item_id
# ---------------------------------------------------------------------------

def test_get_playlist_item_id_found():
    yt = MagicMock()
    yt.playlistItems().list().execute.return_value = {"items": [{"id": "ITEM_123"}]}
    result = _get_playlist_item_id(yt, "PL_SRC", "VID_abc")
    assert result == "ITEM_123"


def test_get_playlist_item_id_not_found():
    yt = MagicMock()
    yt.playlistItems().list().execute.return_value = {"items": []}
    result = _get_playlist_item_id(yt, "PL_SRC", "VID_abc")
    assert result is None


# ---------------------------------------------------------------------------
# _move_video
# ---------------------------------------------------------------------------

def _make_yt_for_move(item_id: str | None = "ITEM_123"):
    yt = MagicMock()
    yt.playlistItems.return_value.insert.return_value.execute.return_value = {}
    items = [{"id": item_id}] if item_id else []
    yt.playlistItems.return_value.list.return_value.execute.return_value = {"items": items}
    yt.playlistItems.return_value.delete.return_value.execute.return_value = {}
    return yt


def test_move_video_success():
    yt = _make_yt_for_move()
    result = _move_video(yt, "PL_SRC", "PL_DEST", "VID_abc")
    assert result is True
    yt.playlistItems().delete.assert_called()


def test_move_video_insert_fails_returns_false():
    yt = MagicMock()
    yt.playlistItems().insert().execute.side_effect = Exception("quota exceeded")
    result = _move_video(yt, "PL_SRC", "PL_DEST", "VID_abc")
    assert result is False


def test_move_video_delete_fails_still_returns_true(capsys):
    yt = _make_yt_for_move()
    yt.playlistItems().delete().execute.side_effect = Exception("forbidden")
    result = _move_video(yt, "PL_SRC", "PL_DEST", "VID_abc")
    assert result is True
    captured = capsys.readouterr()
    assert "[WARN]" in captured.out


def test_move_video_not_in_source_skips_delete():
    yt = _make_yt_for_move(item_id=None)
    result = _move_video(yt, "PL_SRC", "PL_DEST", "VID_abc")
    assert result is True
    yt.playlistItems.return_value.delete.assert_not_called()


# ---------------------------------------------------------------------------
# move_videos_after_report
# ---------------------------------------------------------------------------

def test_move_videos_skips_if_no_credentials(capsys):
    cache = {"v1": {"video_id": "v1"}}
    move_videos_after_report(["v1"], cache, "PL_SRC", "", "", "")
    assert "digested_at" not in cache["v1"]
    assert "[WARN]" in capsys.readouterr().out


def test_move_videos_skips_already_digested():
    yt = _make_yt_for_move()
    cache = {"v1": {"video_id": "v1", "digested_at": "2026-01-01T00:00:00"}}
    with patch("yt_playlist_manager.build_oauth_youtube", return_value=yt), \
         patch("yt_playlist_manager.get_or_create_playlist", return_value="PL_DEST"):
        move_videos_after_report(["v1"], cache, "PL_SRC", "cid", "csec", "rtoken")
    # digested_at must not be overwritten
    assert cache["v1"]["digested_at"] == "2026-01-01T00:00:00"


def test_move_videos_stamps_digested_at_on_success():
    yt = _make_yt_for_move()
    cache = {"v1": {"video_id": "v1"}, "v2": {"video_id": "v2"}}
    with patch("yt_playlist_manager.build_oauth_youtube", return_value=yt), \
         patch("yt_playlist_manager.get_or_create_playlist", return_value="PL_DEST"):
        move_videos_after_report(["v1", "v2"], cache, "PL_SRC", "cid", "csec", "rtoken")
    assert "digested_at" in cache["v1"]
    assert "digested_at" in cache["v2"]


def test_move_videos_no_stamp_if_insert_fails():
    yt = MagicMock()
    yt.playlistItems().insert().execute.side_effect = Exception("error")
    cache = {"v1": {"video_id": "v1"}}
    with patch("yt_playlist_manager.build_oauth_youtube", return_value=yt), \
         patch("yt_playlist_manager.get_or_create_playlist", return_value="PL_DEST"):
        move_videos_after_report(["v1"], cache, "PL_SRC", "cid", "csec", "rtoken")
    assert "digested_at" not in cache["v1"]


def test_move_videos_oauth_setup_failure_is_graceful(capsys):
    cache = {"v1": {"video_id": "v1"}}
    with patch("yt_playlist_manager.build_oauth_youtube", side_effect=Exception("auth failed")):
        move_videos_after_report(["v1"], cache, "PL_SRC", "cid", "csec", "rtoken")
    assert "digested_at" not in cache["v1"]
    assert "[WARN]" in capsys.readouterr().out

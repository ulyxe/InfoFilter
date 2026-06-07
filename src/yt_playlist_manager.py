"""YouTube playlist manager for the YT Digest pipeline.

Handles OAuth2-authenticated write operations: find/create the 'Digested'
playlist, move videos from the source playlist into it, and stamp the cache.
"""

from __future__ import annotations

from datetime import datetime, timezone


def build_oauth_youtube(client_id: str, client_secret: str, refresh_token: str):
    """Build an OAuth2-authenticated YouTube API client with write access."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def get_or_create_playlist(youtube, title: str = "Digested") -> str:
    """Return the playlist ID for *title*, creating it (private) if absent."""
    response = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
    for item in response.get("items", []):
        if item["snippet"]["title"] == title:
            return item["id"]
    created = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title},
            "status": {"privacyStatus": "private"},
        },
    ).execute()
    return created["id"]


def _get_playlist_item_id(youtube, playlist_id: str, video_id: str) -> str | None:
    """Return the playlistItem.id for video_id in playlist_id, or None."""
    resp = youtube.playlistItems().list(
        part="id",
        playlistId=playlist_id,
        videoId=video_id,
        maxResults=1,
    ).execute()
    items = resp.get("items", [])
    return items[0]["id"] if items else None


def _move_video(youtube, source_playlist_id: str, digested_playlist_id: str, video_id: str) -> bool:
    """Insert video into 'Digested', then delete from source. Returns True if insert succeeded."""
    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": digested_playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Could not add {video_id} to Digested: {exc}", flush=True)
        return False

    item_id = _get_playlist_item_id(youtube, source_playlist_id, video_id)
    if item_id:
        try:
            youtube.playlistItems().delete(id=item_id).execute()
        except Exception as exc:  # noqa: BLE001
            print(
                f"[WARN] Added {video_id} to Digested but could not remove from source: {exc}",
                flush=True,
            )
    return True


def move_videos_after_report(
    video_ids: list[str],
    cache: dict,
    source_playlist_id: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> None:
    """Move reported videos to 'Digested' playlist and stamp cache with digested_at."""
    if not all([client_id, client_secret, refresh_token]):
        print("[WARN] YouTube OAuth not configured, skipping playlist move.", flush=True)
        return

    try:
        youtube = build_oauth_youtube(client_id, client_secret, refresh_token)
        digested_playlist_id = get_or_create_playlist(youtube, "Digested")
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] YouTube OAuth setup failed, skipping playlist move: {exc}", flush=True)
        return

    moved = 0
    for video_id in video_ids:
        entry = cache.get(video_id)
        if entry is None or entry.get("digested_at"):
            continue
        if _move_video(youtube, source_playlist_id, digested_playlist_id, video_id):
            entry["digested_at"] = datetime.now(timezone.utc).isoformat()
            moved += 1

    print(f"[INFO] Playlist move: {moved}/{len(video_ids)} videos moved to Digested.", flush=True)

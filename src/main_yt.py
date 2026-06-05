"""Entry point for the YouTube Digest pipeline.

Modes:
  --mode=fetch   (daily) Fetch playlist, analyze new videos, update cache.
  --mode=report  (weekly) Load cache, filter last 7 days, send digest email.

Run from repo root:
    python src/main_yt.py --mode=fetch
    python src/main_yt.py --mode=report
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from string import Template

import yaml

from yt_fetcher import fetch_playlist_ids
from yt_processor import (
    REQUEST_TIMEOUT_MS,
    load_cache,
    process_new_videos,
    save_cache,
)
from email_sender import send_digest

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file so they work from any cwd)
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _ROOT / "config" / "yt_config.yaml"
_CACHE_PATH = _ROOT / "cache" / "yt_cache.json"
_TEMPLATE_PATH = _ROOT / "templates" / "email_yt.html"

_TOPIC_BADGE = {
    "Builder":  ("🏗",  "#f97316"),
    "Engineer": ("⚙️", "#3b82f6"),
    "Entrambi": ("🔀",  "#22c55e"),
    "—":        ("—",   "#64748b"),
}


# ---------------------------------------------------------------------------
# Fetch mode
# ---------------------------------------------------------------------------

def run_fetch() -> None:
    """Daily action: analyze new playlist videos and update cache."""
    config = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    playlist_id: str = config["playlist_id"]
    max_per_run: int = int(config.get("max_per_run", 5))
    model: str = config.get("model", "gemini-2.0-flash")

    # Fetch all video IDs from the playlist (raises on network error → exit 1)
    all_ids = fetch_playlist_ids(playlist_id, os.environ["YOUTUBE_API_KEY"])

    if not all_ids:
        print("[WARN] Playlist is empty — nothing to process.", flush=True)
        return

    cache = load_cache(_CACHE_PATH)
    already_cached = len([vid for vid in all_ids if vid in cache])
    new_ids = [vid for vid in all_ids if vid not in cache]

    print(
        f"[INFO] Playlist: {len(all_ids)} total, "
        f"{already_cached} already cached, {len(new_ids)} new",
        flush=True,
    )

    if not new_ids:
        print("[INFO] No new videos — cache is up to date.", flush=True)
        save_cache(cache, _CACHE_PATH)
        print(f"[INFO] Cache updated at {_CACHE_PATH}", flush=True)
        return

    # Build Gemini client
    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )

    updated_cache, ok_count, failed_count = process_new_videos(
        video_ids=new_ids,
        cache=cache,
        client=client,
        model=model,
        max_per_run=max_per_run,
    )

    save_cache(updated_cache, _CACHE_PATH)
    print(f"[INFO] Processed: {ok_count} ok, {failed_count} failed", flush=True)
    print(f"[INFO] Cache updated at {_CACHE_PATH}", flush=True)


# ---------------------------------------------------------------------------
# Report mode
# ---------------------------------------------------------------------------

def run_report() -> None:
    """Weekly action: send digest email from last 7 days of cache entries."""
    cache = load_cache(_CACHE_PATH)
    date_str = datetime.now().strftime("%d %B %Y")
    subject = f"🎬 YouTube Digest — {date_str}"

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    recent_entries = []
    for entry in cache.values():
        processed_at_str = entry.get("processed_at", "")
        if not processed_at_str:
            continue
        try:
            # ISO format: "2025-06-01T12:34:56" (no tz) or with tz
            dt = datetime.fromisoformat(processed_at_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                recent_entries.append(entry)
        except ValueError:
            continue

    if not recent_entries:
        print("No new videos this week, skipping email", flush=True)
        return

    sorted_entries = sorted(recent_entries, key=lambda e: e.get("rating", 0), reverse=True)

    # Render HTML from template (falls back to plaintext if template missing)
    if _TEMPLATE_PATH.exists():
        video_cards_html = ""
        for entry in sorted_entries:
            stars = "⭐" * entry.get("rating", 0)
            topic = entry.get("topic", "—")
            emoji, color = _TOPIC_BADGE.get(topic, ("—", "#64748b"))
            badge = (
                f'<span style="font-size:11px;font-weight:bold;color:{color};">'
                f'{emoji} {topic}</span>'
            )
            analysis_html = entry.get("analysis", "").replace("\n", "<br>")
            video_cards_html += f"""
            <div style="background:#1e293b;padding:20px;margin:12px 0;border-radius:6px;border-left:3px solid #ef4444;">
              <div style="margin-bottom:6px;">{badge}&nbsp;&nbsp;<span style="font-size:11px;color:#ef4444;">{stars}</span></div>
              <h3 style="margin:0 0 8px 0;"><a href="{entry.get('url','#')}" style="color:#f87171;text-decoration:none;">{entry.get('title','')}</a></h3>
              <p style="color:#94a3b8;margin:0;font-size:13px;">{analysis_html}</p>
            </div>"""

        template = Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))
        html = template.substitute(
            date=date_str,
            video_count=len(sorted_entries),
            video_cards=video_cards_html,
        )
    else:
        html = (
            f"<h2>YouTube Digest — {date_str}</h2>"
            + "".join(
                (
                    topic := e.get("topic", "—"),
                    emoji_color := _TOPIC_BADGE.get(topic, ("—", "#64748b")),
                    emoji := emoji_color[0],
                    color := emoji_color[1],
                    f"<p>"
                    f'<span style="color:{color};">'
                    f'{emoji} {topic}</span> '
                    f"<strong>{'⭐' * e.get('rating',0)}</strong> — "
                    f"<a href='{e.get('url','#')}'>{e.get('title','')}</a></p>"
                )[-1]
                for e in sorted_entries
            )
        )

    plain = f"YouTube Digest — {date_str}\n\n" + "\n".join([
        f"⭐ {entry['rating']}/5 — {entry['title']}\n  {entry['url']}"
        for entry in sorted_entries
    ])

    send_digest(subject, html, plain)
    print(f"[INFO] YouTube Digest sent. Videos: {len(sorted_entries)}", flush=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube Digest pipeline")
    parser.add_argument(
        "--mode",
        choices=["fetch", "report"],
        required=True,
        help="fetch: analyze new videos; report: send weekly email",
    )
    args = parser.parse_args()

    if args.mode == "fetch":
        # YouTube API errors propagate uncaught → action fails (exit 1 via unhandled exception).
        # Gemini quota/timeout errors are handled inside process_new_videos, so run_fetch()
        # completes normally (exit 0) even when quota is exhausted.
        run_fetch()
    else:
        try:
            run_report()
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] Unhandled exception in --mode=report: {exc}", flush=True)
            sys.exit(0)


if __name__ == "__main__":
    main()

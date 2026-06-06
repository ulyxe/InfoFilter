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
import re
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from string import Template

import yaml

from email_sender import send_digest
from yt_fetcher import fetch_playlist_ids
from yt_processor import (
    REQUEST_TIMEOUT_MS,
    load_cache,
    process_new_videos,
    save_cache,
)

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


def _md_to_html(text: str) -> str:
    """HTML-escape then convert inline markdown to HTML tags."""
    text = escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code style="background:#0f172a;padding:1px 4px;border-radius:3px;">\1</code>', text)
    return text


def _parse_yt_analysis(analysis: str) -> dict:
    """Extract all structured fields from a Gemini analysis string."""
    fields: dict = {
        "canale": "", "durata": "", "argomento": "",
        "punti": [],
        "strumenti": [],
        "risorse": [],
        "metodologia": [],
        "builder_roi": "", "engineer_roi": "",
        "perche": "", "tags": "",
    }

    def _extract(s: str, prefix: str) -> str | None:
        if s.startswith(prefix) and ":**" in s:
            return s.split(":**", 1)[-1].strip().strip("[]")
        return None

    in_punti = False
    in_metodologia = False
    for line in analysis.splitlines():
        s = line.strip()
        if not s:
            continue

        if (v := _extract(s, "**Canale:**")) is not None:
            fields["canale"] = v; in_punti = False; in_metodologia = False
        elif (v := _extract(s, "**Durata stimata:**")) is not None:
            fields["durata"] = v; in_punti = False; in_metodologia = False
        elif (v := _extract(s, "**Argomento principale:**")) is not None:
            fields["argomento"] = v; in_punti = False; in_metodologia = False
        elif s.startswith("**Punti chiave:**"):
            in_punti = True; in_metodologia = False
        elif in_punti and s.startswith("- "):
            fields["punti"].append(s[2:].strip())
        elif s.startswith("**Metodologia:**"):
            in_punti = False; in_metodologia = True
        elif in_punti and s.startswith("**"):
            in_punti = False
        elif in_metodologia and (s.upper() == "N/A" or s.startswith("**")):
            in_metodologia = False
        elif in_metodologia and s.startswith("- "):
            fields["metodologia"].append(s[2:].strip())
        elif in_metodologia and re.match(r"^\d+\.", s):
            fields["metodologia"].append(re.sub(r"^\d+\.\s*", "", s))

        if not in_punti and not in_metodologia:
            if (v := _extract(s, "**Strumenti e tecnologie:**")) is not None:
                raw = v.strip()
                if raw.lower() not in ("nessuno", "nessuna", "n/a", ""):
                    fields["strumenti"] = [t.strip() for t in raw.split(",") if t.strip()]
            elif (v := _extract(s, "**Risorse consigliate:**")) is not None:
                raw = v.strip()
                if raw.lower() not in ("nessuno", "nessuna", "n/a", ""):
                    fields["risorse"] = [r.strip() for r in raw.split(",") if r.strip()]
            elif (v := _extract(s, "**Builder ROI:**")) is not None:
                fields["builder_roi"] = v
            elif (v := _extract(s, "**Engineer ROI:**")) is not None:
                fields["engineer_roi"] = v
            elif s.startswith("**Perch") and ":**" in s:
                fields["perche"] = s.split(":**", 1)[-1].strip()
            elif (v := _extract(s, "**Tag:**")) is not None:
                fields["tags"] = v

    return fields


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
    print(
        f"[INFO] Processed: {ok_count} ok, {failed_count} failed", flush=True)
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

    sorted_entries = sorted(
        recent_entries, key=lambda e: e.get("rating", 0), reverse=True)

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
            af = _parse_yt_analysis(entry.get("analysis", ""))
            punti_html = "".join(
                f'<li style="color:#94a3b8;margin:4px 0;font-size:13px;">{_md_to_html(p)}</li>'
                for p in af["punti"]
            )
            meta_parts = [s for s in [escape(af["canale"]), escape(af["durata"])] if s]
            meta_html = (
                f'<div style="font-size:12px;color:#64748b;margin-bottom:10px;">'
                f'{"&nbsp;·&nbsp;".join(meta_parts)}</div>'
                if meta_parts else ""
            )
            roi_rows = ""
            if af["builder_roi"]:
                roi_rows += (
                    f'<div style="margin-bottom:5px;">'
                    f'<span style="font-size:11px;font-weight:bold;color:#f97316;">🏗 Builder ROI</span>'
                    f'&nbsp;<span style="color:#cbd5e1;font-size:13px;">{_md_to_html(af["builder_roi"])}</span>'
                    f'</div>'
                )
            if af["engineer_roi"]:
                roi_rows += (
                    f'<div>'
                    f'<span style="font-size:11px;font-weight:bold;color:#3b82f6;">⚙️ Engineer ROI</span>'
                    f'&nbsp;<span style="color:#cbd5e1;font-size:13px;">{_md_to_html(af["engineer_roi"])}</span>'
                    f'</div>'
                )
            roi_html = (
                f'<div style="background:#0f172a;border-radius:4px;padding:10px 12px;margin:0 0 10px 0;">'
                f'{roi_rows}</div>'
                if roi_rows else ""
            )
            tags_html = (
                f'<div style="font-size:11px;color:#475569;margin-top:6px;">{escape(af["tags"])}</div>'
                if af["tags"] else ""
            )
            video_cards_html += f"""
            <div style="background:#1e293b;padding:20px;margin:12px 0;border-radius:6px;border-left:3px solid #ef4444;">
              <div style="margin-bottom:6px;">{badge}&nbsp;&nbsp;<span style="font-size:13px;color:#ef4444;">{stars}</span></div>
              <h3 style="margin:0 0 4px 0;"><a href="{entry.get('url', '#')}" style="color:#f87171;text-decoration:none;">{escape(entry.get('title', ''))}</a></h3>
              {meta_html}
              {f'<p style="color:#cbd5e1;margin:0 0 8px 0;font-size:14px;">{_md_to_html(af["argomento"])}</p>' if af["argomento"] else ""}
              {f'<ul style="margin:4px 0 10px 0;padding-left:16px;">{punti_html}</ul>' if punti_html else ""}
              {roi_html}
              {f'<p style="color:#94a3b8;font-size:13px;margin:0 0 6px 0;font-style:italic;">💡 {_md_to_html(af["perche"])}</p>' if af["perche"] else ""}
              {tags_html}
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
                    f"<strong>{'⭐' * e.get('rating', 0)}</strong> — "
                    f"<a href='{e.get('url', '#')}'>{e.get('title', '')}</a></p>"
                )[-1]
                for e in sorted_entries
            )
        )

    plain = f"YouTube Digest — {date_str}\n\n" + "\n".join([
        f"⭐ {entry['rating']}/5 — {entry['title']}\n  {entry['url']}"
        for entry in sorted_entries
    ])

    send_digest(subject, html, plain)
    print(
        f"[INFO] YouTube Digest sent. Videos: {len(sorted_entries)}", flush=True)


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
            print(
                f"[ERROR] Unhandled exception in --mode=report: {exc}", flush=True)
            sys.exit(0)


if __name__ == "__main__":
    main()

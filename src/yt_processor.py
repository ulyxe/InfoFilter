"""YouTube video analyzer using Gemini multimodal API.

CI module: no tqdm, no file-based progress, no markdown output.
Errors go to stdout for GitHub Actions logs.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]

# --- Constants ---------------------------------------------------------------

SLEEP_BETWEEN = 30
REQUEST_TIMEOUT_MS = 120_000  # 2 minutes
MAX_ATTEMPTS = 2
RETRY_SLEEP = 45  # seconds to wait before retry if API doesn't specify

PROMPT = """\
Analizza questo video YouTube e rispondi ESCLUSIVAMENTE in questo formato \
(in italiano):

**Titolo:** [titolo del video]
**Canale:** [nome del canale]
**Durata stimata:** [durata approssimativa]
**Argomento principale:** [una frase]
**Punti chiave:**
- [punto 1]
- [punto 2]
- [punto 3]
- [punto 4 se rilevante]
**Vale il tempo?** [voto 1-5 con emoji: 1=⭐ 2=⭐⭐ 3=⭐⭐⭐ 4=⭐⭐⭐⭐ 5=⭐⭐⭐⭐⭐]
**Perché:** [1-2 frasi motivazione voto]
**Tag:** [3-5 tag tematici es. #AI #produttività #tutorial]
"""


# --- Private helpers ---------------------------------------------------------

def _retry_delay(exc: Exception) -> float:
    """Return the wait time in seconds suggested by the API, or RETRY_SLEEP."""
    msg = str(exc)
    m = re.search(r"retry[^\d]*(\d+(?:\.\d+)?)\s*s", msg, re.IGNORECASE)
    if m:
        return float(m.group(1)) + 2  # +2s margin
    return float(RETRY_SLEEP)


def _is_retryable(exc: Exception) -> bool:
    """True for transient errors: timeout/backend stall or rate limit (429)."""
    msg = str(exc).lower()
    return (
        "timed out" in msg
        or "timeout" in msg
        or "429" in msg
        or "resource_exhausted" in msg
        or "deadline" in msg
        or "503" in msg
        or "unavailable" in msg
    )


# --- Core API function -------------------------------------------------------

def analyze_video(client: "genai.Client", url: str, model: str) -> str:
    """Call Gemini on a YouTube URL. Returns the analysis text.

    Retries on transient errors (timeout/backend stall or 429), with a delay
    between attempts. Raises on final failure.
    """
    contents = types.Content(
        parts=[
            types.Part(file_data=types.FileData(file_uri=url)),
            types.Part(text=PROMPT),
        ]
    )
    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=model, contents=contents
            )
            text = (response.text or "").strip()
            if not text:
                raise RuntimeError("Risposta vuota dal modello")
            return text
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < MAX_ATTEMPTS and _is_retryable(exc):
                delay = _retry_delay(exc)
                print(
                    f"[WARN] retry {attempt}/{MAX_ATTEMPTS - 1} on {url} "
                    f"(waiting {delay:.0f}s): {str(exc)[:120]}",
                    flush=True,
                )
                time.sleep(delay)
                continue
            raise
    raise last_exc  # pragma: no cover


# --- Parsing helpers ---------------------------------------------------------

def extract_rating(analysis: str) -> int:
    """Extract the 1-5 star rating by counting ⭐ emoji in the 'Vale il tempo?' line."""
    for line in analysis.splitlines():
        if "Vale il tempo" in line:
            stars = line.count("⭐")
            if stars:
                return min(stars, 5)
            m = re.search(r"\b([1-5])\b", line)
            if m:
                return int(m.group(1))
    return 0


def extract_title(analysis: str, fallback: str) -> str:
    """Extract the title from the '**Titolo:**' line."""
    for line in analysis.splitlines():
        m = re.match(r"\s*\*\*Titolo:\*\*\s*(.+)", line)
        if m:
            return m.group(1).strip().strip("[]")
    return fallback


# --- Cache I/O ---------------------------------------------------------------

def load_cache(path: Path) -> dict:
    """Load cache JSON from path. Returns {} on missing file or parse error."""
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_cache(cache: dict, path: Path) -> None:
    """Save cache dict as JSON to path (creates parent dirs if needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --- Processing loop ---------------------------------------------------------

def process_new_videos(
    video_ids: list[str],
    cache: dict,
    client: "genai.Client",
    model: str,
    max_per_run: int,
) -> tuple[dict, int, int]:
    """Process new videos not yet in cache, up to max_per_run successes.

    Args:
        video_ids: All video IDs to consider (e.g. from playlist).
        cache: Current cache dict (will be mutated and returned).
        client: Gemini API client.
        model: Gemini model name.
        max_per_run: Maximum number of SUCCESSFUL analyses per run (quota guard).
            Also caps total API *attempts* at max_per_run * MAX_ATTEMPTS to avoid
            burning the entire daily quota when the playlist is large and calls fail.

    Returns:
        Tuple of (updated_cache, ok_count, failed_count).

    Cache entries are only written for successful analyses. Errors are logged
    to stdout and skipped so they can be retried on the next run.
    """
    successes = 0
    failures = 0
    attempts = 0
    max_attempts = max_per_run * MAX_ATTEMPTS  # hard cap on total API calls

    for video_id in video_ids:
        if video_id in cache:
            continue
        if successes >= max_per_run:
            break
        if attempts >= max_attempts:
            print(
                f"[INFO] API attempt cap reached ({max_attempts}), stopping.",
                flush=True,
            )
            break

        url = f"https://www.youtube.com/watch?v={video_id}"
        attempts += 1

        try:
            analysis = analyze_video(client, url, model)
            entry = {
                "video_id": video_id,
                "url": url,
                "status": "ok",
                "analysis": analysis,
                "rating": extract_rating(analysis),
                "title": extract_title(analysis, video_id),
                "processed_at": datetime.now().isoformat(timespec="seconds"),
            }
            cache[video_id] = entry
            successes += 1
            print(
                f"[INFO] processed {video_id}: {entry['title'][:70]} "
                f"({'⭐' * entry['rating']})",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] failed to process {video_id}: {exc}", flush=True)
            failures += 1
            # Do NOT cache errors — they must be retried next run

        if successes < max_per_run:
            time.sleep(SLEEP_BETWEEN)

    return cache, successes, failures

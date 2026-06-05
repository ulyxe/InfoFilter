# Design: YTDigest Integration into InfoFilter

**Date:** 2026-06-05  
**Status:** Approved

## Goal

Integrate the YTDigest script (standalone Python tool at `C:\Users\User\progetti\YTDigest\summarizer.py`) into the InfoFilter repo so that:

1. A **daily GitHub Action** fetches new video IDs from a YouTube playlist and analyzes them via Gemini (up to quota).
2. A **weekly GitHub Action** (Sunday) sends an HTML email digest with the videos analyzed that week, ranked by rating.

## Architecture

### New files to create

```
src/yt_fetcher.py        # reads playlist IDs from YouTube Data API v3
src/yt_processor.py      # Gemini analysis (adapted from YTDigest summarizer.py)
src/main_yt.py           # entry point: --mode=fetch | --mode=report
config/yt_config.yaml    # playlist_id, max_per_run (default 5), model
templates/email_yt.html  # dark-style HTML email template for YT digest
cache/yt_cache.json      # persisted in the repo (committed between runs)
.github/workflows/yt-daily.yml   # daily: fetch + process + commit cache
.github/workflows/yt-weekly.yml  # Sunday: load cache + send email
```

### Existing files to modify

- `requirements.txt` — add `google-genai` and `google-api-python-client`
- `.gitignore` — ensure `cache/yt_cache.json` is NOT ignored (must be committed)

### Source reference

Copy and adapt logic from `YTDigest/summarizer.py`:
- `analyze_video()`, `_is_retryable()`, `_retry_delay()` → `src/yt_processor.py`
- `extract_rating()`, `extract_title()` → `src/yt_processor.py`
- `load_cache()`, `save_cache()` → `src/yt_processor.py` (paths updated)
- `build_markdown()` → NOT copied; replaced by HTML email rendering
- `PROMPT`, `SLEEP_BETWEEN`, `REQUEST_TIMEOUT_MS`, `MAX_ATTEMPTS`, `RETRY_SLEEP` → keep same values

## Module details

### `src/yt_fetcher.py`

```python
# fetch_playlist_ids(playlist_id: str, api_key: str) -> list[str]
# Uses YouTube Data API v3 playlistItems.list with pagination.
# Returns all video IDs currently in the playlist.
# Raises on API error (let the caller decide whether to abort).
```

Uses `google-api-python-client` (`googleapiclient.discovery.build`).  
Playlist must be **unlisted** (not private) — API key access, no OAuth required.

### `src/yt_processor.py`

```python
# analyze_video(client, url, model) -> str        (from YTDigest)
# extract_rating(analysis: str) -> int            (from YTDigest)
# extract_title(analysis: str, fallback: str) -> str  (from YTDigest)
# load_cache(path: Path) -> dict                  (from YTDigest, path param)
# save_cache(cache: dict, path: Path) -> None     (from YTDigest, path param)
# process_new_videos(video_ids, cache, client, model, max_per_run) -> dict
#   Iterates new IDs, calls analyze_video(), respects SLEEP_BETWEEN,
#   stops after max_per_run successes (quota guard).
#   Returns updated cache. Errors are logged, not cached.
```

Constants preserved from YTDigest: `SLEEP_BETWEEN=30`, `REQUEST_TIMEOUT_MS=120_000`, `MAX_ATTEMPTS=2`, `RETRY_SLEEP=45`.

### `src/main_yt.py`

Two modes:

**`--mode=fetch`** (daily action):
1. Load `config/yt_config.yaml` → `playlist_id`, `max_per_run`, `model`
2. `fetch_playlist_ids()` → all IDs in playlist
3. `load_cache()` → already-processed IDs
4. `process_new_videos()` → analyze up to `max_per_run` new ones
5. `save_cache()` → write updated `cache/yt_cache.json`
6. Print summary (processed N, skipped M, failed K)

**`--mode=report`** (weekly action):
1. `load_cache()` → full cache
2. Filter entries with `processed_at` in the last 7 days
3. Sort by `rating` descending
4. If no entries → print "No new videos this week, skipping email" and exit 0
5. Render `templates/email_yt.html` → html, plain
6. `send_digest(subject, html, plain)` using existing `src/email_sender.py`

### `config/yt_config.yaml`

```yaml
playlist_id: "PLxxxxxxxxxxxxxxxxxx"   # set to your actual playlist ID
max_per_run: 5                         # videos analyzed per daily run (quota guard)
model: "gemini-3.5-flash"             # override with --model flag if needed
```

### `cache/yt_cache.json`

Same schema as YTDigest `cache.json`, with one added field per entry:

```json
{
  "VIDEO_ID": {
    "video_id": "...",
    "url": "https://www.youtube.com/watch?v=...",
    "status": "ok",
    "analysis": "...",
    "rating": 4,
    "title": "...",
    "processed_at": "2026-06-05T07:12:34"   // NEW: ISO timestamp for weekly filter
  }
}
```

Only successful analyses are cached (same policy as YTDigest).

### `templates/email_yt.html`

Dark-style template matching InfoFilter's existing emails. One card per video:

```
🎬 YouTube Digest — {date}
"{count} video analizzati questa settimana"

For each video (sorted by rating desc):
  ⭐⭐⭐⭐⭐  {title}
  Argomento: {main_topic}
  Perché vale il tempo: {reason}
  Tag: {tags}
  [▶ Guarda su YouTube]  (link button)
```

Uses `string.Template` with `$placeholder` syntax (consistent with InfoFilter).  
Inline CSS only (no `<style>` blocks — Outlook compatibility).

## GitHub Actions

### `.github/workflows/yt-daily.yml`

```yaml
name: YT Digest — Daily Fetch
on:
  schedule:
    - cron: '0 7 * * *'    # every day at 07:00 UTC
  workflow_dispatch:

jobs:
  fetch:
    runs-on: ubuntu-latest
    timeout-minutes: 30     # Gemini calls can take ~6-60s each; 5 videos + sleeps ≈ 5 min
    permissions:
      contents: write       # needed to commit cache back to repo
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - name: Fetch and process videos
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}
        run: python src/main_yt.py --mode=fetch
      - name: Commit updated cache
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add cache/yt_cache.json
          git diff --cached --quiet || git commit -m "chore: update yt cache [skip ci]"
          git push
```

### `.github/workflows/yt-weekly.yml`

```yaml
name: YT Digest — Weekly Email
on:
  schedule:
    - cron: '0 8 * * 0'    # every Sunday at 08:00 UTC
  workflow_dispatch:

jobs:
  send:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - name: Send weekly digest
        env:
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          DIGEST_RECIPIENT_EMAIL: ${{ secrets.DIGEST_RECIPIENT_EMAIL }}
        run: python src/main_yt.py --mode=report
```

## Error handling

| Scenario | Behavior |
|---|---|
| Gemini quota exhausted (429/RESOURCE_EXHAUSTED) | Stop processing, commit partial cache, log error, exit 0 (don't fail the action) |
| Video private/removed (403/404) | Skip, log warning, do not cache, continue |
| YouTube API unreachable | Raise exception → action fails with explicit error |
| Gemini timeout | Retry once (MAX_ATTEMPTS=2), then skip video |
| No new videos this week (report mode) | Log "No new videos, skipping email", exit 0 |
| Empty playlist | Log warning, exit 0 |

## New secrets required

| Secret | Where to get it | Notes |
|---|---|---|
| `YOUTUBE_API_KEY` | Google Cloud Console → APIs & Services → Credentials → Create API key | Restrict to YouTube Data API v3 |
| `GEMINI_API_KEY` | Google AI Studio → Get API key | Free tier: 20 RPD for gemini-3.5-flash |

Existing secrets reused without changes: `SMTP_USER`, `SMTP_PASSWORD`, `DIGEST_RECIPIENT_EMAIL`.

## Manual setup steps (one-time, done by the user before first run)

### Step 1 — Create YouTube playlist

1. Go to [youtube.com](https://youtube.com) → Your channel → Playlists → New playlist
2. Name it (e.g. "Da analizzare")
3. Set visibility to **Unlisted**
4. Copy the playlist ID from the URL (`?list=PLxxxxxx`)

### Step 2 — Get YouTube Data API key

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable **YouTube Data API v3** (APIs & Services → Library → search "YouTube Data API v3")
4. Create credentials → **API key**
5. (Optional but recommended) Restrict the key to YouTube Data API v3

### Step 3 — Get Gemini API key

1. Go to [aistudio.google.com](https://aistudio.google.com) → Get API key
2. Free tier gives 20 requests/day for `gemini-3.5-flash`

### Step 4 — Add GitHub Secrets

In the InfoFilter repo → Settings → Secrets and variables → Actions → New repository secret:

- `YOUTUBE_API_KEY` → value from Step 2
- `GEMINI_API_KEY` → value from Step 3

### Step 5 — Update `config/yt_config.yaml`

Set `playlist_id` to the value from Step 1. The playlist ID is not sensitive (unlisted ≠ private), so it lives in the committed config file, not in GitHub Secrets.

### Step 6 — Add videos to the playlist

Add any YouTube video to the playlist. The next daily run will pick it up automatically.

### Step 7 — (Optional) Test manually

Trigger the `yt-daily.yml` workflow manually from GitHub Actions → Run workflow to verify the setup before waiting for the scheduled run.

## Dependencies to add to `requirements.txt`

```
google-genai
google-api-python-client
```

(`python-dotenv` and `tqdm` from YTDigest are NOT needed — GitHub Actions uses env vars directly, and there's no interactive progress bar in CI.)

# CLAUDE.md

Guidance for working in this repository.

## Purpose

Zero-cost, server-less system that emails two weekly AI digests via GitHub Actions
cron. No always-on machine required.

- The Engineer (`main.py`): Monday 06:00 UTC. Agentic coding, Claude Code, dev best practices.
- The Builder (`main_builder.py`): Wednesday 06:00 UTC. AI business, solopreneurship, Italy angle.

## Architecture

Two independent pipelines share one infrastructure layer. Each pipeline runs:
`fetch RSS (last 7 days)` -> `summarize to structured JSON via Groq` ->
`render HTML + plaintext email` -> `send via SMTP (Gmail by default)`.

Shared modules:
- `src/feed_reader.py` - `fetch_recent_articles(feeds, days)`: parses feeds, drops
  entries older than the cutoff, returns the 20 newest as dicts.
- `src/email_sender.py` - `send_digest()` (SMTP), `render_engineer_template()`,
  `render_builder_template()`, and the private `_action_card_html()` shared by both.

Per-pipeline modules:
- Engineer: `config/feeds.yaml`, `src/summarizer.py`, `src/main.py`,
  `templates/email.html`, `.github/workflows/digest.yml`.
- Builder: `config/feeds_builder.yaml`, `src/summarizer_builder.py`,
  `src/main_builder.py`, `templates/email_builder.html`,
  `.github/workflows/builder-digest.yml`.

`src/` modules import each other by bare name (e.g. `from feed_reader import ...`);
entry points are run as `python src/main.py` from the repo root.

## Conventions and gotchas

- Graceful degradation everywhere: a dead feed is skipped with a `[WARN]`; a failed
  Groq call returns `None` and the renderer emits a plaintext fallback email. The
  pipeline must never crash on external failure.
- HTML emails use INLINE CSS only. Outlook ignores `<style>` blocks.
- Templates use `string.Template` (`$placeholder`). Escape literal `$` as `$$`.
  Every declared placeholder must be present and no stray `$token` may appear, or
  `substitute()` raises `KeyError`.
- `feedparser` returns dates as a UTC 9-tuple; convert with
  `datetime(*pub[:6], tzinfo=timezone.utc)`.
- Summarizers must return JSON only (enforced by system prompt). The Groq client is
  created lazily via `_get_client()` so modules import without `GROQ_API_KEY`.
- `source_url` fields fall back to `"#"` via `value or "#"` (covers empty strings).
- The four GitHub Secrets are shared by both workflows. No per-digest secrets.
- Email is sent over SMTP via `send_digest()`. Host/port come from `SMTP_HOST`
  (default `smtp.gmail.com`) and `SMTP_PORT` (default `587`); credentials from
  `SMTP_USER` / `SMTP_PASSWORD`. Outlook/Office 365 basic SMTP auth is disabled by
  Microsoft (`535 5.7.139`), so Gmail with an App Password is the default provider.

## Commands

- Install (runtime): `pip install -r requirements.txt`
- Install (dev): `pip install -r requirements-dev.txt`
- Tests: `pytest -v` (offline; no API key or SMTP needed)
- Live feed dry-run: see `docs/PLAN.md` Phase 5.2.
- Trigger a digest manually: GitHub Actions -> select workflow -> Run workflow.

## Adding a feed

Append a `{name, url, tags}` entry to the relevant `config/feeds_*.yaml`. No code
change required.

## YT Digest pipeline

- YT Digest: daily 07:00 UTC (fetch) + weekly Sunday 08:00 UTC (email).

Pipeline: `fetch playlist IDs (YouTube Data API)` → `analyze new videos via Gemini` →
`commit cache/yt_cache.json` → (weekly) `render HTML email` → `send via SMTP` →
`move digested videos to "Digested" YouTube playlist` → `commit cache`.

Modules: `src/yt_fetcher.py`, `src/yt_processor.py`, `src/yt_playlist_manager.py`,
`src/main_yt.py`, `config/yt_config.yaml`, `templates/email_yt.html`,
`cache/yt_cache.json`.

One-time setup: `scripts/youtube_oauth_setup.py` generates the OAuth2 refresh token
needed for playlist write access (see README for full instructions).

### Commands

- Run fetch: `python src/main_yt.py --mode=fetch`
- Run report: `python src/main_yt.py --mode=report`
- Generate OAuth token (one-time): `python scripts/youtube_oauth_setup.py --client-id CID --client-secret CSECRET`

### YT Digest non-obvious decisions

- **Model `gemini-3.5-flash`** is correct and current (June 2026). Do not "correct" it to 2.5/3.0.
- **Cache saves successes only.** Failures are never cached so they are retried on the next run. Do not introduce error caching.
- **Throttling, not logic, is the bottleneck.** YouTube ingestion is a preview feature with low quota. Failures often manifest as `read operation timed out`, NOT a clean 429. A video that fails in a batch run often succeeds alone — failure ≠ broken video.
- **Three throttle defenses, do not remove:** `REQUEST_TIMEOUT_MS` (prevents infinite hang), retry with backoff in `analyze_video()` (handles transient stalls), `SLEEP_BETWEEN=30s` between calls (stays under throttle threshold). At 6s ~1/3 of videos failed; at 30s much more reliable.
- **`MAX_ATTEMPTS=2` (one retry):** each attempt consumes one slot of the free daily quota (20 RPD). With 3 attempts you burn up to 3 slots per failing video. Keep at 2.
- **`max_per_run=5` in `yt_config.yaml`:** quota guard — limits daily API calls to stay within the 20 RPD free tier even if the playlist grows large.
- **`processed_at` timestamp in cache entries:** used by `--mode=report` to filter the last 7 days for the weekly email. Do not remove this field.
- **`digested_at` timestamp in cache entries:** set after a video is successfully moved to the "Digested" playlist. Entries with this field are excluded from future reports and from the playlist move. Do not remove this field.
- **`cache/yt_cache.json` is committed to the repo.** This is intentional — it is the persistence mechanism between GitHub Actions runs (ephemeral filesystem). Do not gitignore it. The weekly workflow also commits the cache (to persist `digested_at` stamps).

### Playlist manager non-obvious decisions

- **OAuth2, not API key, for write operations.** `yt_fetcher.py` uses a read-only API key. `yt_playlist_manager.py` uses OAuth2 (`Desktop app` credentials) with scope `youtube`. Three secrets are required: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`.
- **Refresh order is `creds.refresh(Request())`, not `Request().refresh(creds)`.** The `refresh` method belongs to the `Credentials` object; `Request` is the transport argument passed to it.
- **"Digested" playlist is found by name, created if absent.** `get_or_create_playlist()` lists all playlists (`mine=True`) and matches by title. If not found it creates a private playlist named "Digested". No playlist ID needs to be configured manually.
- **Insert before delete.** `_move_video()` inserts into "Digested" first, then deletes from the source. If the delete fails, the video appears in both playlists but `digested_at` is still stamped — no data is lost and the video won't re-appear in future digests.
- **Graceful degradation.** If any of the three OAuth secrets is missing, the playlist move is skipped with `[WARN]` and the report is unaffected. All exceptions in the playlist manager are caught internally — the pipeline never crashes due to playlist errors.

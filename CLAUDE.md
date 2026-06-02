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

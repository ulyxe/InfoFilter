# Weekly AI Digests

A zero-cost, server-less system that emails three weekly AI digests, each driven by
its own curated feed list, summarized by an LLM, rendered as HTML + plaintext email,
and delivered over SMTP (Gmail by default). Scheduling runs entirely on GitHub Actions
cron — no always-on machine required.

## The three digests

| Email | Entry point | Schedule | Focus |
|---|---|---|---|
| The Engineer | `src/main.py` | Monday 06:00 UTC | Agentic coding, Claude Code, dev best practices |
| The Builder | `src/main_builder.py` | Wednesday 06:00 UTC | AI business, solopreneurship, Italy angle |
| YT Digest | `src/main_yt.py` | Daily fetch + Sunday email | YouTube playlist analysis |

Every external step degrades gracefully: a dead feed is skipped, a failed LLM call
falls back to a plain article list, so a run never crashes.

---

## Quickstart

### 1. Fork and clone

```bash
git clone https://github.com/YOUR_USERNAME/InfoFilter.git
cd InfoFilter
```

### 2. Install dependencies

```bash
# Runtime
pip install -r requirements.txt

# Dev (adds pytest + linting)
pip install -r requirements-dev.txt
```

### 3. Configure GitHub Actions secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

#### RSS digests (The Engineer + The Builder)

| Secret | Description |
|---|---|
| `GROQ_API_KEY` | API key from [console.groq.com](https://console.groq.com) |
| `SMTP_USER` | Sender Gmail address |
| `SMTP_PASSWORD` | Gmail App Password (16 chars — see below) |
| `DIGEST_RECIPIENT_EMAIL` | Recipient address (can equal `SMTP_USER`) |

Optional — only needed if you switch away from Gmail:

| Secret | Default |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |

#### YT Digest (additional secrets)

| Secret | Description |
|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API v3 key from [Google Cloud Console](https://console.cloud.google.com) |
| `GEMINI_API_KEY` | Gemini API key from [Google AI Studio](https://aistudio.google.com) |
| `YOUTUBE_CLIENT_ID` | OAuth2 client ID — needed to move digested videos to the "Digested" playlist |
| `YOUTUBE_CLIENT_SECRET` | OAuth2 client secret |
| `YOUTUBE_REFRESH_TOKEN` | OAuth2 refresh token — generated once with `scripts/youtube_oauth_setup.py` |

The three `YOUTUBE_*` OAuth secrets are optional: if absent the weekly report is still
sent but videos are not moved to the "Digested" playlist.

### 4. Create a Gmail App Password

Gmail rejects your normal password over SMTP. You need an App Password:

1. Enable **2-Step Verification** on your Google account.
2. Go to **Google Account → Security → App passwords**, create one named e.g. `InfoFilter`.
3. Copy the 16-character value and use it as `SMTP_PASSWORD`.

> Outlook / Office 365 basic SMTP auth is disabled by Microsoft (`535 5.7.139`), so
> Gmail is the only supported provider out of the box.

### 5. Set up YouTube OAuth2 for the "Digested" playlist (optional)

After each weekly report, videos are automatically moved to a YouTube playlist named
"Digested" (created automatically if it doesn't exist). This requires a one-time OAuth2
setup:

1. In [Google Cloud Console](https://console.cloud.google.com), create an OAuth2
   credential of type **Desktop app**.
2. Add your Google account as a **test user** under the OAuth consent screen.
3. Run the setup script (requires `pip install google-auth-oauthlib`):
   ```bash
   python scripts/youtube_oauth_setup.py --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
   ```
4. Authorize in the browser that opens. The script prints a refresh token.
5. Add `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN` as
   GitHub Secrets.

Skip this step if you don't need the "Digested" playlist feature.

### 7. Configure the YT Digest playlist

Edit `config/yt_config.yaml` and set your YouTube playlist ID:

```yaml
playlist_id: "PLxxxxxxxxxxxxxxxxxx"   # your actual playlist ID
max_per_run: 5                         # videos analyzed per daily run (quota guard)
model: "gemini-3.5-flash"
```

The playlist ID is the part after `list=` in a YouTube playlist URL.

### 8. Add or change RSS feeds

Append a `{name, url, tags}` entry to the relevant config file — no code change needed:

- Engineer feeds: `config/feeds.yaml`
- Builder feeds: `config/feeds_builder.yaml`

### 9. Enable GitHub Actions workflows

The workflow files live in `.github/workflows/`. If the Actions tab shows them as
disabled, enable each one manually from the UI.

---

## Running locally

### Run the test suite (offline, no keys needed)

```bash
pytest -v
```

### Dry-run: check feeds are reachable

```bash
cd src
python -c "
import yaml
from pathlib import Path
from feed_reader import fetch_recent_articles
feeds = yaml.safe_load(Path('../config/feeds.yaml').read_text())['feeds']
print('Engineer articles:', len(fetch_recent_articles(feeds)))
feeds2 = yaml.safe_load(Path('../config/feeds_builder.yaml').read_text())['feeds']
print('Builder articles:', len(fetch_recent_articles(feeds2)))
"
```

### Run the YT Digest locally

```bash
# Fetch new videos and update the cache (requires YOUTUBE_API_KEY + GEMINI_API_KEY)
python src/main_yt.py --mode=fetch

# Send the weekly email from the cache (requires SMTP_* + DIGEST_RECIPIENT_EMAIL)
python src/main_yt.py --mode=report
```

---

## Triggering a digest manually

In GitHub: **Actions** → select the workflow → **Run workflow**.

| Workflow | Trigger name |
|---|---|
| The Engineer | Weekly AI Digest |
| The Builder | Weekly Builder Digest |
| YT fetch | YT Digest — Daily Fetch |
| YT email | YT Digest — Weekly Email |

---

## Project structure

```
config/
  feeds.yaml              # Engineer RSS feeds
  feeds_builder.yaml      # Builder RSS feeds
  yt_config.yaml          # YT Digest settings (playlist ID, quota limit)
src/
  main.py                 # Engineer pipeline entry point
  main_builder.py         # Builder pipeline entry point
  main_yt.py              # YT Digest entry point (--mode fetch|report)
  feed_reader.py          # Shared RSS fetcher
  email_sender.py         # Shared SMTP sender + template renderers
  summarizer.py           # Groq summarizer (Engineer)
  summarizer_builder.py   # Groq summarizer (Builder)
  yt_fetcher.py           # YouTube Data API client (read-only, API key auth)
  yt_processor.py         # Gemini video analyser
  yt_playlist_manager.py  # YouTube playlist write operations (OAuth2)
  yt_pdf.py               # PDF attachment generator
scripts/
  youtube_oauth_setup.py  # One-time OAuth2 token generator for playlist write access
templates/
  email.html              # Engineer email template
  email_builder.html      # Builder email template
  email_yt.html           # YT Digest email template
cache/
  yt_cache.json           # Persisted YT analysis results (committed to repo)
.github/workflows/
  digest.yml              # Engineer cron (Mon 06:00 UTC)
  builder-digest.yml      # Builder cron (Wed 06:00 UTC)
  yt-daily.yml            # YT fetch cron (daily 07:00 UTC)
  yt-weekly.yml           # YT email cron (Sun 08:00 UTC) + cache commit
```

---

## Further reading

- Architecture and conventions: [`CLAUDE.md`](CLAUDE.md)
- Full implementation detail: [`docs/PLAN.md`](docs/PLAN.md)

# Weekly AI Digests

A zero-cost, server-less system that emails two weekly AI digests, each driven by
its own curated RSS feed list, summarized into structured content by the Groq API,
rendered as an HTML + plaintext email, and delivered over Outlook SMTP. Scheduling
runs entirely on GitHub Actions cron, so no always-on machine is required.

## The two digests

| Email | Entry point | Schedule | Focus |
|---|---|---|---|
| The Engineer | `src/main.py` | Monday 06:00 UTC | Agentic coding, Claude Code, dev best practices |
| The Builder | `src/main_builder.py` | Wednesday 06:00 UTC | AI business, solopreneurship, side hustle, Italy angle |

Every external step degrades gracefully: a dead feed is skipped, and a failed LLM
call falls back to a plain article list, so a run never crashes.

## Setup

1. Clone the repository.
2. Install runtime dependencies: `pip install -r requirements.txt`
3. In the GitHub repository settings, add these four Actions secrets (shared by both
   workflows):

   | Secret | Description |
   |---|---|
   | `GROQ_API_KEY` | API key from console.groq.com |
   | `OUTLOOK_EMAIL` | Outlook sender address |
   | `OUTLOOK_PASSWORD` | Outlook password or App Password (if 2FA is enabled) |
   | `DIGEST_RECIPIENT_EMAIL` | Recipient address (can be the same as the sender) |

## Running the tests

The test suite is fully offline (no API key or SMTP required):

```bash
pip install -r requirements-dev.txt
pytest
```

## Local dry-run

Confirm the feeds are reachable and parsing produces non-zero article counts (no API
key needed):

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

## Triggering a digest manually

In GitHub: **Actions** -> select **Weekly AI Digest** or **Weekly Builder Digest**
-> **Run workflow**.

## Further reading

- Architecture and conventions: [`CLAUDE.md`](CLAUDE.md)
- Full implementation detail: [`docs/PLAN.md`](docs/PLAN.md)

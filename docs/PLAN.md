# Weekly AI Digests — Two Automated Emails — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a zero-cost, server-less system that emails two weekly AI digests (The Engineer on Monday, The Builder on Wednesday) via GitHub Actions cron + Python + Groq API + Outlook SMTP.

**Architecture:** A single shared infrastructure layer (`feed_reader`, `email_sender`) is reused by two independent pipelines, each with its own feed list, summarizer prompt, entry point, HTML template, and workflow. Each pipeline: fetch RSS articles from the last 7 days → summarize them into structured JSON via Groq → render an HTML+plaintext email → send over Outlook SMTP. Every external step degrades gracefully (a dead feed is skipped; a failed LLM call falls back to a plain article list) so the pipeline never crashes.

**Tech Stack:** Python 3.12, `feedparser`, `groq` (model `meta-llama/llama-4-scout-17b-16e-instruct`), `PyYAML`, `string.Template` for HTML, stdlib `smtplib`/`email`, `pytest` for tests, GitHub Actions cron for scheduling. Dependencies installed with `pip`/`requirements.txt`.

---

## Overview

| Email | Name | Day | Focus |
|---|---|---|---|
| 1 | 🔧 The Engineer | Monday 07:00 CET | Agentic coding, Claude Code, dev best practices |
| 2 | 💡 The Builder | Wednesday 07:00 CET | AI business, solopreneurship, side hustle, Italy angle |

Zero cost. No server required. PC can be off.

> Note: emoji in the table above and throughout this plan refer to **email product content** (subject lines, section headers shown to the reader). Project documentation files (`CLAUDE.md`, `README.md`, code comments) must remain emoji-free per the repo writing conventions.

---

## Final File Structure

```
weekly-ai-digest/
├── .github/
│   └── workflows/
│       ├── digest.yml
│       └── builder-digest.yml
├── src/
│   ├── main.py
│   ├── main_builder.py
│   ├── feed_reader.py
│   ├── summarizer.py
│   ├── summarizer_builder.py
│   └── email_sender.py
├── config/
│   ├── feeds.yaml
│   └── feeds_builder.yaml
├── templates/
│   ├── email.html
│   └── email_builder.html
├── tests/
│   ├── conftest.py
│   ├── test_feed_reader.py
│   ├── test_summarizer.py
│   └── test_email_sender.py
├── requirements.txt
├── requirements-dev.txt
├── CLAUDE.md
└── README.md
```

---

## Tech Stack

- **Scheduler**: GitHub Actions cron
- **Runtime**: Python 3.12
- **LLM**: Groq API — `meta-llama/llama-4-scout-17b-16e-instruct` (free tier, no credit card required)
- **Email**: SMTP Outlook `smtp.office365.com:587` + STARTTLS
- **Runtime dependencies**: `feedparser==6.0.11`, `groq>=0.9.0`, `PyYAML>=6.0.2`
- **Dev dependencies**: `pytest>=8.0`
- **Package manager**: `pip` (local and CI). The repo-wide `uv` preference is intentionally not applied to this project.

---

## Environment Variables (GitHub Secrets)

All four secrets are shared by both digests:

| Secret | Description |
|---|---|
| `GROQ_API_KEY` | From console.groq.com |
| `OUTLOOK_EMAIL` | Outlook sender address |
| `OUTLOOK_PASSWORD` | Outlook password or App Password (if 2FA enabled) |
| `DIGEST_RECIPIENT_EMAIL` | Recipient address (can be same as sender) |

`GROQ_API_KEY` is read lazily, so the modules import cleanly without it (needed for the local dry-run and the test suite).

---

## PHASE 1 — Shared Infrastructure

### Task 1.1: `requirements.txt` and `requirements-dev.txt`

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`

- [ ] **Step 1: Write `requirements.txt`**

```
feedparser==6.0.11
groq>=0.9.0
PyYAML>=6.0.2
```

- [ ] **Step 2: Write `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.0
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt requirements-dev.txt
git commit -m "chore: add runtime and dev dependencies"
```

### Task 1.2: `src/feed_reader.py`

Shared by both digests. Reads RSS feeds, filters last 7 days, returns sorted article list. It imports `feedparser` at module level (`feed_reader.feedparser.parse` is monkeypatched in tests).

**Files:**
- Create: `src/feed_reader.py`
- Test: `tests/test_feed_reader.py` (written in Task 4.2)

- [ ] **Step 1: Write `src/feed_reader.py`**

```python
import feedparser
from datetime import datetime, timezone, timedelta

def fetch_recent_articles(feeds_config: list, days: int = 7) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    articles = []

    for feed_cfg in feeds_config:
        try:
            d = feedparser.parse(feed_cfg['url'])
            for entry in d.entries:
                pub = entry.get('published_parsed') or entry.get('updated_parsed')
                if not pub:
                    continue
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
                articles.append({
                    'title': entry.get('title', 'No title'),
                    'link': entry.get('link', ''),
                    'summary': entry.get('summary', '')[:500],
                    'published_iso': pub_dt.isoformat(),
                    'feed_name': feed_cfg['name'],
                    'tags': feed_cfg.get('tags', [])
                })
        except Exception as e:
            print(f"[WARN] Feed {feed_cfg['name']} failed: {e}")
            continue

    articles.sort(key=lambda x: x['published_iso'], reverse=True)
    return articles[:20]
```

- [ ] **Step 2: Commit**

```bash
git add src/feed_reader.py
git commit -m "feat: add shared RSS feed reader"
```

### Task 1.3: `src/email_sender.py`

Shared SMTP sender + two template renderers (one per digest) + a shared action-card helper.

**Refinement vs. original draft:** `business_idea.source_url` and `case_study.source_url` now use `... or '#'` instead of `.get(key, '#')`, so an empty-string URL also falls back to `#` (honors implementation note: "never leave as empty in HTML `href`"). This is exercised by a test in Task 4.4.

**Files:**
- Create: `src/email_sender.py`
- Test: `tests/test_email_sender.py` (written in Task 4.4)

- [ ] **Step 1: Write `src/email_sender.py`**

```python
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from string import Template
from pathlib import Path


def send_digest(subject: str, html_body: str, plain_body: str) -> None:
    sender = os.environ["OUTLOOK_EMAIL"]
    password = os.environ["OUTLOOK_PASSWORD"]
    recipient = os.environ["DIGEST_RECIPIENT_EMAIL"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP("smtp.office365.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
    print(f"[OK] Email sent to {recipient}")


def _action_card_html(action: dict, accent_color: str) -> str:
    """Renders the 'Prova questa settimana' card. Shared by both templates."""
    if not action:
        return ""
    return f"""
    <div style="background:#1a2235;border-left:4px solid {accent_color};padding:20px;margin:16px 0;border-radius:4px;">
      <p style="margin:0 0 6px 0;font-size:11px;color:{accent_color};text-transform:uppercase;letter-spacing:1px;">🎯 Prova questa settimana</p>
      <h3 style="margin:0 0 10px 0;color:#f1f5f9;font-size:18px;">{action.get('title','')}</h3>
      <p style="margin:0 0 8px 0;color:#cbd5e1;">{action.get('what','')}</p>
      <p style="margin:0 0 12px 0;color:#94a3b8;font-size:14px;"><em>Perché: {action.get('why','')}</em></p>
      <span style="display:inline-block;background:{accent_color};color:#0f172a;font-size:12px;font-weight:bold;padding:4px 10px;border-radius:12px;">⏱ {action.get('time_required','')}</span>
    </div>"""


def render_engineer_template(digest: dict | None, articles: list, date_str: str) -> tuple[str, str]:
    template_path = Path(__file__).parent.parent / "templates" / "email.html"
    template = Template(template_path.read_text(encoding="utf-8"))

    if digest:
        highlights_html = ""
        for h in digest.get("highlights", []):
            highlights_html += f"""
            <div style="background:#1e293b;padding:20px;margin:12px 0;border-radius:6px;border-left:3px solid #6366f1;">
              <div style="font-size:11px;color:#6366f1;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">{h['source']}</div>
              <h3 style="margin:0 0 8px 0;"><a href="{h['url']}" style="color:#818cf8;text-decoration:none;">{h['title']}</a></h3>
              <p style="color:#cbd5e1;margin:0 0 8px 0;">{h['summary']}</p>
              <p style="color:#94a3b8;font-size:13px;margin:0;">💡 {h['relevance']}</p>
            </div>"""

        action_html = _action_card_html(digest.get("action_of_the_week"), "#6366f1")

        html = template.substitute(
            date=date_str,
            intro=digest.get("intro", ""),
            highlights=highlights_html,
            tip=digest.get("tip_of_the_week", ""),
            action_of_the_week=action_html,
            article_count=len(articles)
        )
        plain = f"Weekly AI Digest — {date_str}\n\n{digest.get('intro','')}\n\n" + \
                "\n".join([f"- {h['title']} ({h['source']})\n  {h['url']}"
                           for h in digest.get('highlights', [])]) + \
                f"\n\n🎯 PROVA QUESTA SETTIMANA: {digest.get('action_of_the_week',{}).get('title','')}\n" + \
                digest.get('action_of_the_week',{}).get('what','')
    else:
        links = "\n".join([f"- [{a['feed_name']}] {a['title']}\n  {a['link']}" for a in articles])
        html = f"<h2>Weekly AI Digest — {date_str}</h2><p>AI summary unavailable.</p><pre>{links}</pre>"
        plain = f"Weekly AI Digest — {date_str}\n\n{links}"

    return html, plain


def render_builder_template(digest: dict | None, articles: list, date_str: str) -> tuple[str, str]:
    template_path = Path(__file__).parent.parent / "templates" / "email_builder.html"
    template = Template(template_path.read_text(encoding="utf-8"))

    if digest:
        ideas_html = ""
        for idea in digest.get("business_ideas", []):
            effort_color = {"basso": "#22c55e", "medio": "#f59e0b", "alto": "#ef4444"}.get(idea.get("effort", ""), "#6366f1")
            idea_url = idea.get("source_url") or "#"
            ideas_html += f"""
            <div style="background:#111827;padding:20px;margin:12px 0;border-radius:6px;border-left:3px solid #f59e0b;">
              <span style="display:inline-block;background:{effort_color};color:#0a0f1e;font-size:11px;font-weight:bold;padding:3px 8px;border-radius:10px;margin-bottom:10px;">Effort: {idea.get('effort','?')}</span>
              <h3 style="margin:0 0 8px 0;color:#f1f5f9;">{idea['title']}</h3>
              <p style="color:#cbd5e1;margin:0 0 8px 0;">{idea['description']}</p>
              <p style="color:#cbd5e1;margin:0 0 8px 0;"><strong style="color:#f59e0b;">⚡ Perché ora:</strong> {idea['why_now']}</p>
              <p style="color:#cbd5e1;margin:0 0 12px 0;border-left:3px solid #10b981;padding-left:10px;">🇮🇹 <strong>Italy angle:</strong> {idea['italy_angle']}</p>
              <a href="{idea_url}" style="color:#fbbf24;font-size:13px;">Leggi la fonte →</a>
            </div>"""

        pattern = digest.get("agentic_pattern", {})
        tools_list = "".join([f"<li style='color:#cbd5e1;margin:4px 0;'>{t}</li>" for t in pattern.get("tools", [])])
        pattern_html = f"""
        <div style="background:#111827;padding:20px;margin:12px 0;border-radius:6px;border-left:3px solid #10b981;">
          <h3 style="margin:0 0 10px 0;color:#f1f5f9;">🤖 {pattern.get('title','Pattern della settimana')}</h3>
          <p style="color:#cbd5e1;margin:0 0 8px 0;">{pattern.get('description','')}</p>
          <p style="color:#cbd5e1;margin:0 0 8px 0;"><strong style="color:#10b981;">Use case:</strong> {pattern.get('use_case','')}</p>
          <ul style="margin:8px 0;padding-left:20px;">{tools_list}</ul>
        </div>"""

        case = digest.get("case_study", {})
        case_url = case.get("source_url") or "#"
        case_html = f"""
        <div style="background:#111827;padding:20px;margin:12px 0;border-radius:6px;border-left:3px solid #f59e0b;">
          <h3 style="margin:0 0 10px 0;color:#f1f5f9;">📖 {case.get('title','Caso Studio')}</h3>
          <p style="color:#cbd5e1;margin:0 0 8px 0;">{case.get('summary','')}</p>
          <p style="color:#94a3b8;font-size:14px;margin:0 0 12px 0;font-style:italic;">💡 {case.get('lesson','')}</p>
          <a href="{case_url}" style="color:#fbbf24;font-size:13px;">Leggi →</a>
        </div>"""

        action_html = _action_card_html(digest.get("action_of_the_week"), "#f59e0b")

        html = template.substitute(
            date=date_str,
            intro=digest.get("intro", ""),
            business_ideas=ideas_html,
            agentic_pattern=pattern_html,
            case_study=case_html,
            tip=digest.get("tip_of_the_week", ""),
            action_of_the_week=action_html,
            article_count=len(articles)
        )
        plain = f"Weekly Builder Digest — {date_str}\n\n{digest.get('intro','')}\n\n" + \
                "\n".join([f"- {a['title']} ({a['feed_name']})\n  {a['link']}" for a in articles]) + \
                f"\n\n🎯 PROVA QUESTA SETTIMANA: {digest.get('action_of_the_week',{}).get('title','')}\n" + \
                digest.get('action_of_the_week',{}).get('what','')
    else:
        links = "\n".join([f"- [{a['feed_name']}] {a['title']}\n  {a['link']}" for a in articles])
        html = f"<h2>Weekly Builder Digest — {date_str}</h2><pre>{links}</pre>"
        plain = f"Weekly Builder Digest — {date_str}\n\n{links}"

    return html, plain
```

- [ ] **Step 2: Commit**

```bash
git add src/email_sender.py
git commit -m "feat: add shared SMTP sender and template renderers"
```

---

## PHASE 2 — The Engineer Digest (Monday)

### Task 2.1: `config/feeds.yaml`

**Files:**
- Create: `config/feeds.yaml`

- [ ] **Step 1: Write `config/feeds.yaml`**

```yaml
feeds:
  - name: "Simon Willison's Weblog"
    url: "https://simonwillison.net/atom/everything/"
    tags: [ai, agents, llm, claude, vibe-coding]

  - name: "Latent Space (AI Engineer Newsletter)"
    url: "https://www.latent.space/feed"
    tags: [agents, ai-engineering, models, infra]

  - name: "Hugging Face Blog"
    url: "https://huggingface.co/blog/feed.xml"
    tags: [models, open-source, tools]

  - name: "Anthropic News (community mirror)"
    url: "https://raw.githubusercontent.com/cnzhujie/ai-rss-feed/main/rss/anthropic_engineering_rss.xml"
    tags: [claude, anthropic, releases]

  - name: "minimaxir — AI tools & automation"
    url: "https://minimaxir.com/index.xml"
    tags: [ai-tools, automation, python]

  - name: "Agentic Coding Today (Podcast)"
    url: "https://rss.com/podcasts/vibe-coding-today/rss.xml"
    tags: [claude-code, codex, agentic, vibe-coding]

  - name: "Hacker News — Agentic/Vibe Coding"
    url: "https://hnrss.org/newest?q=claude+code+OR+agentic+coding+OR+vibe+coding&count=15&points=10"
    tags: [community, tools, discussion]

  - name: "GitHub Blog"
    url: "https://github.blog/feed/"
    tags: [copilot, devtools, ai-coding]

  - name: "The AI Solopreneur"
    url: "https://aisolopreneur.beehiiv.com/feed"
    tags: [solopreneur, ai-workflows, side-hustle]

  - name: "Ahead of AI (Sebastian Raschka)"
    url: "https://magazine.sebastianraschka.com/feed"
    tags: [llm, research, practical-ai]
```

- [ ] **Step 2: Commit**

```bash
git add config/feeds.yaml
git commit -m "feat: add Engineer digest feed list"
```

### Task 2.2: `src/summarizer.py`

**Refinement vs. original draft:** the Groq client is created lazily via `_get_client()` instead of at import time, so the module imports without `GROQ_API_KEY` (required by the dry-run and tests) and `_get_client` is monkeypatchable.

**Files:**
- Create: `src/summarizer.py`
- Test: `tests/test_summarizer.py` (written in Task 4.3)

- [ ] **Step 1: Write `src/summarizer.py`**

```python
import os
import json
from groq import Groq

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return _client


SYSTEM_PROMPT = """Sei un assistente esperto di AI engineering e sviluppo SaaS con agenti AI.
Ricevi articoli della settimana su vibe coding, agentic AI e Claude Code best practices.
Rispondi SOLO con un oggetto JSON valido, senza markdown, senza backtick, senza testo aggiuntivo.
La lingua di output è l'italiano."""


def summarize_articles(articles: list) -> dict | None:
    if not articles:
        return None

    articles_text = "\n\n".join([
        f"[{i+1}] {a['feed_name']}\nTitolo: {a['title']}\nLink: {a['link']}\nSommario: {a['summary']}"
        for i, a in enumerate(articles)
    ])

    user_prompt = f"""Ecco gli articoli di questa settimana:

{articles_text}

Rispondi con questo JSON esatto:
{{
  "intro": "Breve intro della settimana in italiano (2-3 frasi)",
  "highlights": [
    {{
      "title": "Titolo sintetico in italiano",
      "summary": "Riassunto 2-3 frasi in italiano",
      "source": "Nome del feed",
      "url": "URL originale",
      "relevance": "Perché è utile per chi sviluppa con AI"
    }}
  ],
  "tip_of_the_week": "Un consiglio pratico su Claude Code o agentic coding (3-5 frasi in italiano)",
  "action_of_the_week": {{
    "title": "Titolo breve dell'azione (max 8 parole)",
    "what": "Cosa fare concretamente questa settimana con Claude Code o un tool agentico (1-2 frasi)",
    "why": "Perché migliora il tuo workflow agentico o la qualità del codice (1 frase)",
    "time_required": "Stima realistica es: 30 minuti | 1 ora | un pomeriggio"
  }}
}}
Includi massimo 6 highlights. Per action_of_the_week suggerisci qualcosa di pratico e sperimentabile subito: un nuovo pattern da provare con Claude Code, uno strumento da installare e testare, un esperimento su prompt engineering agentico, o una tecnica di debugging con AI."""

    try:
        response = _get_client().chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            temperature=0.3,
            max_tokens=2000
        )
        raw = response.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[WARN] Groq API error: {e}")
        return None
```

- [ ] **Step 2: Commit**

```bash
git add src/summarizer.py
git commit -m "feat: add Engineer digest summarizer"
```

### Task 2.3: `src/main.py`

**Files:**
- Create: `src/main.py`

- [ ] **Step 1: Write `src/main.py`**

```python
from datetime import datetime, timezone
import yaml
from pathlib import Path
from feed_reader import fetch_recent_articles
from summarizer import summarize_articles
from email_sender import send_digest, render_engineer_template


def main() -> None:
    config_path = Path(__file__).parent.parent / "config" / "feeds.yaml"
    feeds = yaml.safe_load(config_path.read_text())["feeds"]

    articles = fetch_recent_articles(feeds, days=7)
    print(f"[Engineer] Found {len(articles)} articles")

    date_str = datetime.now(timezone.utc).strftime("%d %B %Y")
    subject = f"🔧 Weekly AI Digest — {date_str}"

    if not articles:
        send_digest(subject, "<p>No updates this week.</p>", "No updates.")
        return

    digest = summarize_articles(articles)
    html, plain = render_engineer_template(digest, articles, date_str)
    send_digest(subject, html, plain)
    print(f"[Engineer] Sent. Articles: {len(articles)}, AI digest: {'yes' if digest else 'no (fallback)'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat: add Engineer digest entry point"
```

### Task 2.4: `templates/email.html`

HTML email template for The Engineer. All CSS must be **inline** (Outlook ignores `<style>` blocks). The renderer uses `string.Template`, so the file must contain exactly these `$placeholder` tokens and no other unescaped `$` (escape any literal `$` as `$$`).

**Files:**
- Create: `templates/email.html`

Color palette:
- Background: `#0f172a`
- Accent: `#6366f1` (indigo)
- Text: `#e2e8f0`
- Card background: `#1e293b`
- Link color: `#818cf8`

Required placeholders (every one must appear exactly once; `Template.substitute` raises `KeyError` if any is missing or if an unexpected `$token` is present):
- `$date`
- `$intro`
- `$highlights` — pre-rendered HTML cards
- `$tip`
- `$action_of_the_week` — pre-rendered HTML card (from `_action_card_html`)
- `$article_count`

Section structure (in order):
```
[Header: "🔧 Weekly AI Digest" | $date]
[Intro: $intro]
[Section: TOP HIGHLIGHTS — $highlights]
[Section: TIP OF THE WEEK — $tip]
[Section: 🎯 PROVA QUESTA SETTIMANA — $action_of_the_week]
[Footer: "$article_count articoli processati questa settimana"]
```

- [ ] **Step 1:** Write `templates/email.html` following the palette, placeholder, and section spec above. Wrap content in a centered table (max-width ~640px) for email-client compatibility; apply all styles inline.

- [ ] **Step 2: Commit**

```bash
git add templates/email.html
git commit -m "feat: add Engineer email template"
```

### Task 2.5: `.github/workflows/digest.yml`

**Files:**
- Create: `.github/workflows/digest.yml`

- [ ] **Step 1: Write `.github/workflows/digest.yml`**

```yaml
name: Weekly AI Digest

on:
  schedule:
    - cron: '0 6 * * 1'
  workflow_dispatch:

jobs:
  send-digest:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run digest
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          OUTLOOK_EMAIL: ${{ secrets.OUTLOOK_EMAIL }}
          OUTLOOK_PASSWORD: ${{ secrets.OUTLOOK_PASSWORD }}
          DIGEST_RECIPIENT_EMAIL: ${{ secrets.DIGEST_RECIPIENT_EMAIL }}
        run: python src/main.py
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/digest.yml
git commit -m "ci: add Engineer digest workflow (Monday cron)"
```

---

## PHASE 3 — The Builder Digest (Wednesday)

### Task 3.1: `config/feeds_builder.yaml`

**Files:**
- Create: `config/feeds_builder.yaml`

- [ ] **Step 1: Write `config/feeds_builder.yaml`**

```yaml
feeds:
  - name: "Ben's Bites"
    url: "https://bensbites.beehiiv.com/feed"
    tags: [ai-business, product-launches, founders, startups]

  - name: "The Rundown AI"
    url: "https://rss.beehiiv.com/feeds/2R3C6Bt5wj.xml"
    tags: [ai-news, tools, business, workflows]

  - name: "Product Hunt — AI"
    url: "https://www.producthunt.com/feed?category=artificial-intelligence"
    tags: [product-launches, tools, saas, ai]

  - name: "Indie Hackers"
    url: "https://www.indiehackers.com/feed.xml"
    tags: [indie, bootstrapped, saas, revenue, side-hustle]

  - name: "Paul Graham Essays"
    url: "http://www.aaronsw.com/2002/feeds/pgessays.rss"
    tags: [startups, strategy, thinking, saas]

  - name: "The AI Solopreneur"
    url: "https://aisolopreneur.beehiiv.com/feed"
    tags: [solopreneur, ai-workflows, automation, side-hustle]

  - name: "Lenny's Newsletter"
    url: "https://www.lennysnewsletter.com/feed"
    tags: [product, growth, saas, monetization]

  - name: "n8n Blog"
    url: "https://blog.n8n.io/rss/"
    tags: [automation, n8n, agents, workflows]

  - name: "Hacker News — AI Business"
    url: "https://hnrss.org/newest?q=solopreneur+OR+indie+hacker+OR+ai+business+OR+side+hustle&count=15&points=15"
    tags: [community, discussion, ideas, revenue]

  - name: "a16z Blog"
    url: "https://a16z.com/feed/"
    tags: [venture, trends, ai-market, saas]
```

- [ ] **Step 2: Commit**

```bash
git add config/feeds_builder.yaml
git commit -m "feat: add Builder digest feed list"
```

### Task 3.2: `src/summarizer_builder.py`

**Refinement vs. original draft:** same lazy `_get_client()` pattern as Task 2.2.

**Files:**
- Create: `src/summarizer_builder.py`
- Test: `tests/test_summarizer.py` (written in Task 4.3, covers both summarizers)

- [ ] **Step 1: Write `src/summarizer_builder.py`**

```python
import os
import json
from groq import Groq

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return _client


SYSTEM_PROMPT_BUILDER = """Sei un mentor esperto di business digitale, solopreneurship e AI automation.
Ricevi articoli su AI business, side hustle, automazioni agentiche e indie hacking.
Il lettore è un ingegnere italiano con un lavoro full-time che vuole costruire un side income con AI,
partendo dall'Italia ma con visione internazionale (inglese come lingua di scala).
Rispondi SOLO con un oggetto JSON valido, senza markdown, senza backtick, senza testo aggiuntivo.
La lingua di output è l'italiano. Tono: ispirazionale ma concreto, niente hype vuoto."""


def summarize_builder(articles: list) -> dict | None:
    if not articles:
        return None

    articles_text = "\n\n".join([
        f"[{i+1}] {a['feed_name']}\nTitolo: {a['title']}\nLink: {a['link']}\nSommario: {a['summary']}"
        for i, a in enumerate(articles)
    ])

    user_prompt = f"""Ecco gli articoli di questa settimana:

{articles_text}

Produci questo JSON esatto:
{{
  "intro": "Intro ispirazionale della settimana (2-3 frasi)",
  "business_ideas": [
    {{
      "title": "Nome dell'idea di business",
      "description": "Cosa fa, chi paga, quanto può valere (2-3 frasi)",
      "why_now": "Perché è il momento giusto con AI (1-2 frasi)",
      "italy_angle": "Come adattarla al mercato italiano: lingua, nicchia locale, forfettario, piattaforme italiane",
      "source_url": "URL dell'articolo che ha ispirato questa idea",
      "effort": "basso | medio | alto"
    }}
  ],
  "agentic_pattern": {{
    "title": "Nome del pattern di orchestrazione",
    "description": "Descrizione del sistema agentivo",
    "use_case": "Esempio concreto applicabile a un micro-SaaS o side hustle",
    "tools": ["lista", "strumenti"],
    "source_url": ""
  }},
  "case_study": {{
    "title": "Titolo del caso studio",
    "summary": "Cosa ha costruito, come, quanto guadagna (3-4 frasi)",
    "lesson": "La lezione principale (1-2 frasi)",
    "source_url": "URL"
  }},
  "tip_of_the_week": "Consiglio strategico per chi costruisce un side business in Italia con AI (3-5 frasi)",
  "action_of_the_week": {{
    "title": "Titolo breve dell'azione (max 8 parole)",
    "what": "Cosa fare concretamente questa settimana sul fronte business (1-2 frasi)",
    "why": "Perché avvicina alla prima vendita, al primo cliente o alla prima validazione (1 frase)",
    "time_required": "Stima realistica es: 1 ora | un weekend | 2 ore"
  }}
}}
Includi 2-3 business_ideas. Per action_of_the_week suggerisci qualcosa di immediatamente eseguibile: postare su un forum italiano, scrivere una landing page, fare 5 interviste di validazione, testare un funnel con AI, creare un post su LinkedIn in italiano. Per italy_angle considera sempre: regime forfettario, lingua italiana come vantaggio, piattaforme/nicchie italiane specifiche."""

    try:
        response = _get_client().chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_BUILDER},
                {"role": "user", "content": user_prompt}
            ],
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            temperature=0.5,
            max_tokens=2500
        )
        raw = response.choices[0].message.content.strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[WARN] Groq API error (Builder): {e}")
        return None
```

- [ ] **Step 2: Commit**

```bash
git add src/summarizer_builder.py
git commit -m "feat: add Builder digest summarizer"
```

### Task 3.3: `src/main_builder.py`

**Files:**
- Create: `src/main_builder.py`

- [ ] **Step 1: Write `src/main_builder.py`**

```python
from datetime import datetime, timezone
import yaml
from pathlib import Path
from feed_reader import fetch_recent_articles
from summarizer_builder import summarize_builder
from email_sender import send_digest, render_builder_template


def main() -> None:
    config_path = Path(__file__).parent.parent / "config" / "feeds_builder.yaml"
    feeds = yaml.safe_load(config_path.read_text())["feeds"]

    articles = fetch_recent_articles(feeds, days=7)
    print(f"[Builder] Found {len(articles)} articles")

    date_str = datetime.now(timezone.utc).strftime("%d %B %Y")
    subject = f"💡 Weekly Builder Digest — {date_str}"

    if not articles:
        send_digest(subject, "<p>No updates this week.</p>", "No updates.")
        return

    digest = summarize_builder(articles)
    html, plain = render_builder_template(digest, articles, date_str)
    send_digest(subject, html, plain)
    print(f"[Builder] Sent. Articles: {len(articles)}, AI digest: {'yes' if digest else 'no (fallback)'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add src/main_builder.py
git commit -m "feat: add Builder digest entry point"
```

### Task 3.4: `templates/email_builder.html`

HTML email template for The Builder. All CSS must be **inline** (Outlook ignores `<style>` blocks). Same `string.Template` rules as Task 2.4.

**Files:**
- Create: `templates/email_builder.html`

Color palette — visually distinct from The Engineer:
- Background: `#0a0f1e`
- Accent: `#f59e0b` (amber/gold)
- Secondary accent: `#10b981` (green)
- Text: `#e2e8f0`
- Card background: `#111827`
- Link color: `#fbbf24`

Required placeholders (each appears exactly once):
- `$date`
- `$intro`
- `$business_ideas` — pre-rendered HTML cards
- `$agentic_pattern` — pre-rendered HTML card
- `$case_study` — pre-rendered HTML card
- `$tip`
- `$action_of_the_week` — pre-rendered HTML card (from `_action_card_html`)
- `$article_count`

Section structure (in order):
```
[Header: "💡 Weekly Builder Digest" | $date]
[Intro: $intro]
[Section: 💼 IDEE DI BUSINESS — $business_ideas]
[Section: 🤖 PATTERN AGENTIVO — $agentic_pattern]
[Section: 📖 CASO STUDIO — $case_study]
[Section: 🎯 TIP STRATEGICO — $tip]
[Section: 🎯 PROVA QUESTA SETTIMANA — $action_of_the_week]
[Footer: "$article_count fonti analizzate | 🇮🇹 → 🌍"]
```

- [ ] **Step 1:** Write `templates/email_builder.html` following the palette, placeholder, and section spec above (centered table, inline styles).

- [ ] **Step 2: Commit**

```bash
git add templates/email_builder.html
git commit -m "feat: add Builder email template"
```

### Task 3.5: `.github/workflows/builder-digest.yml`

**Files:**
- Create: `.github/workflows/builder-digest.yml`

- [ ] **Step 1: Write `.github/workflows/builder-digest.yml`**

```yaml
name: Weekly Builder Digest

on:
  schedule:
    - cron: '0 6 * * 3'
  workflow_dispatch:

jobs:
  send-builder-digest:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run Builder digest
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          OUTLOOK_EMAIL: ${{ secrets.OUTLOOK_EMAIL }}
          OUTLOOK_PASSWORD: ${{ secrets.OUTLOOK_PASSWORD }}
          DIGEST_RECIPIENT_EMAIL: ${{ secrets.DIGEST_RECIPIENT_EMAIL }}
        run: python src/main_builder.py
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/builder-digest.yml
git commit -m "ci: add Builder digest workflow (Wednesday cron)"
```

---

## PHASE 4 — Tests

Focused, offline test suite. No network, no Groq key, no SMTP. Run with `pytest` from the repo root. The suite covers: feed date-filtering/sorting/resilience, summarizer JSON parsing with a mocked Groq client, and template rendering (incl. fallback and the empty-`source_url` href fix).

> Ordering note: the template-rendering tests in Task 4.4 read `templates/email.html` / `templates/email_builder.html`, so those template files (Tasks 2.4 and 3.4) must exist before running Task 4.4. The fallback test does not read a template.

### Task 4.1: pytest configuration so `src/` is importable

`src/` modules import each other by bare name (`from feed_reader import ...`). Tests must import them the same way, so `src/` is added to `sys.path` via `conftest.py`.

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `tests/conftest.py`**

```python
import sys
from pathlib import Path

SRC = Path(__file__).parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
```

- [ ] **Step 2: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add pytest conftest exposing src on sys.path"
```

### Task 4.2: `tests/test_feed_reader.py`

**Files:**
- Create: `tests/test_feed_reader.py`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime, timezone, timedelta
import feed_reader


class _FakeFeed:
    def __init__(self, entries):
        self.entries = entries


def _entry(title, link, days_ago):
    pub = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "title": title,
        "link": link,
        "summary": "summary text",
        "published_parsed": pub.timetuple(),
    }


def test_filters_out_old_articles(monkeypatch):
    entries = [_entry("recent", "u1", 1), _entry("old", "u2", 30)]
    monkeypatch.setattr(feed_reader.feedparser, "parse", lambda url: _FakeFeed(entries))
    feeds = [{"name": "Test", "url": "http://x", "tags": ["t"]}]
    result = feed_reader.fetch_recent_articles(feeds, days=7)
    titles = [a["title"] for a in result]
    assert "recent" in titles
    assert "old" not in titles


def test_sorted_newest_first(monkeypatch):
    entries = [_entry("older", "u1", 5), _entry("newer", "u2", 1)]
    monkeypatch.setattr(feed_reader.feedparser, "parse", lambda url: _FakeFeed(entries))
    feeds = [{"name": "Test", "url": "http://x", "tags": []}]
    result = feed_reader.fetch_recent_articles(feeds, days=7)
    assert result[0]["title"] == "newer"


def test_skips_entries_without_date(monkeypatch):
    entries = [{"title": "no date", "link": "u", "summary": ""}]
    monkeypatch.setattr(feed_reader.feedparser, "parse", lambda url: _FakeFeed(entries))
    feeds = [{"name": "Test", "url": "http://x", "tags": []}]
    result = feed_reader.fetch_recent_articles(feeds, days=7)
    assert result == []


def test_failed_feed_does_not_raise(monkeypatch):
    def boom(url):
        raise ValueError("network down")
    monkeypatch.setattr(feed_reader.feedparser, "parse", boom)
    feeds = [{"name": "Bad", "url": "http://x", "tags": []}]
    result = feed_reader.fetch_recent_articles(feeds, days=7)
    assert result == []
```

- [ ] **Step 2: Run and verify pass**

Run: `pytest tests/test_feed_reader.py -v`
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_feed_reader.py
git commit -m "test: cover feed reader filtering, sorting, resilience"
```

### Task 4.3: `tests/test_summarizer.py`

Mocks `_get_client()` in both summarizer modules with a fake Groq client returning a canned response string.

**Files:**
- Create: `tests/test_summarizer.py`

- [ ] **Step 1: Write the tests**

```python
import json
import summarizer
import summarizer_builder


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content):
        self._content = content

    def create(self, **kwargs):
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


class _FakeClient:
    def __init__(self, content):
        self.chat = _FakeChat(content)


def _articles():
    return [{"feed_name": "F", "title": "T", "link": "L", "summary": "S"}]


def test_engineer_returns_none_for_empty_articles():
    assert summarizer.summarize_articles([]) is None


def test_engineer_parses_valid_json(monkeypatch):
    payload = {"intro": "ciao", "highlights": [], "tip_of_the_week": "x", "action_of_the_week": {}}
    monkeypatch.setattr(summarizer, "_get_client", lambda: _FakeClient(json.dumps(payload)))
    result = summarizer.summarize_articles(_articles())
    assert result["intro"] == "ciao"


def test_engineer_invalid_json_returns_none(monkeypatch):
    monkeypatch.setattr(summarizer, "_get_client", lambda: _FakeClient("not json{{"))
    assert summarizer.summarize_articles(_articles()) is None


def test_builder_returns_none_for_empty_articles():
    assert summarizer_builder.summarize_builder([]) is None


def test_builder_parses_valid_json(monkeypatch):
    payload = {"intro": "ciao", "business_ideas": [], "agentic_pattern": {}, "case_study": {}}
    monkeypatch.setattr(summarizer_builder, "_get_client", lambda: _FakeClient(json.dumps(payload)))
    result = summarizer_builder.summarize_builder(_articles())
    assert result["intro"] == "ciao"


def test_builder_invalid_json_returns_none(monkeypatch):
    monkeypatch.setattr(summarizer_builder, "_get_client", lambda: _FakeClient("garbage"))
    assert summarizer_builder.summarize_builder(_articles()) is None
```

- [ ] **Step 2: Run and verify pass**

Run: `pytest tests/test_summarizer.py -v`
Expected: 6 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_summarizer.py
git commit -m "test: cover summarizer JSON parsing with mocked Groq client"
```

### Task 4.4: `tests/test_email_sender.py`

**Files:**
- Create: `tests/test_email_sender.py`

- [ ] **Step 1: Write the tests** (run after Tasks 2.4 and 3.4 create the template files)

```python
import email_sender


def _engineer_digest():
    return {
        "intro": "Intro text",
        "highlights": [{
            "title": "H1", "summary": "S1", "source": "Src",
            "url": "http://h1", "relevance": "R1",
        }],
        "tip_of_the_week": "Tip text",
        "action_of_the_week": {
            "title": "Act", "what": "do", "why": "because", "time_required": "30 minuti",
        },
    }


def _builder_digest():
    return {
        "intro": "B intro",
        "business_ideas": [{
            "title": "Idea", "description": "desc", "why_now": "now",
            "italy_angle": "IT", "source_url": "http://s", "effort": "medio",
        }],
        "agentic_pattern": {"title": "Pat", "description": "d", "use_case": "u", "tools": ["t1", "t2"]},
        "case_study": {"title": "Case", "summary": "sum", "lesson": "les", "source_url": ""},
        "tip_of_the_week": "tip",
        "action_of_the_week": {"title": "A", "what": "w", "why": "y", "time_required": "1 ora"},
    }


def test_action_card_empty_returns_empty_string():
    assert email_sender._action_card_html({}, "#000000") == ""


def test_engineer_template_contains_content():
    html, plain = email_sender.render_engineer_template(
        _engineer_digest(),
        [{"feed_name": "F", "title": "T", "link": "L"}],
        "01 June 2026",
    )
    assert "Intro text" in html
    assert "http://h1" in html
    assert "Act" in html
    assert "01 June 2026" in plain


def test_engineer_fallback_when_no_digest():
    articles = [{"feed_name": "F", "title": "T", "link": "http://l"}]
    html, _ = email_sender.render_engineer_template(None, articles, "01 June 2026")
    assert "http://l" in html
    assert "AI summary unavailable" in html


def test_builder_template_contains_content_and_empty_url_href():
    html, _ = email_sender.render_builder_template(
        _builder_digest(),
        [{"feed_name": "F", "title": "T", "link": "L"}],
        "01 June 2026",
    )
    assert "Idea" in html
    assert "t1" in html
    # case_study.source_url is "" -> must fall back to "#"
    assert 'href="#"' in html
```

- [ ] **Step 2: Run and verify pass**

Run: `pytest tests/test_email_sender.py -v`
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_email_sender.py
git commit -m "test: cover template rendering, fallback, empty-url href"
```

---

## PHASE 5 — Validation

### Task 5.1: Run the full test suite

- [ ] **Step 1: Install dev dependencies and run pytest**

```bash
pip install -r requirements-dev.txt
pytest -v
```

Expected: all tests pass (14 total).

### Task 5.2: Live feed dry-run (no API key needed)

Confirms feeds are reachable and parsing produces non-zero article counts.

- [ ] **Step 1: Run the dry-run**

```bash
cd src
python -c "
import yaml
from pathlib import Path
from feed_reader import fetch_recent_articles
feeds = yaml.safe_load(Path('../config/feeds.yaml').read_text())['feeds']
articles = fetch_recent_articles(feeds)
print(f'Engineer articles: {len(articles)}')
feeds2 = yaml.safe_load(Path('../config/feeds_builder.yaml').read_text())['feeds']
articles2 = fetch_recent_articles(feeds2)
print(f'Builder articles: {len(articles2)}')
"
```

Expected: non-zero article counts for both digests. If an individual feed returns 0, it is offline — a `[WARN]` is logged and the pipeline continues.

### Task 5.3: Manual end-to-end (after push + secrets configured)

- [ ] **Step 1:** In the GitHub repo, add the four secrets (`GROQ_API_KEY`, `OUTLOOK_EMAIL`, `OUTLOOK_PASSWORD`, `DIGEST_RECIPIENT_EMAIL`).
- [ ] **Step 2:** Actions → "Weekly AI Digest" → Run workflow → verify the email arrives with all sections including 🎯.
- [ ] **Step 3:** Actions → "Weekly Builder Digest" → Run workflow → verify the email arrives with all sections including 🎯.

---

## PHASE 6 — Documentation

### Task 6.1: `CLAUDE.md` (architecture reference for future sessions)

Create a concise, emoji-free `CLAUDE.md` at the repo root so future coding sessions understand the project without re-reading every file.

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1:** Write `CLAUDE.md` containing exactly these sections:

````markdown
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
`render HTML + plaintext email` -> `send via Outlook SMTP`.

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

## Commands

- Install (runtime): `pip install -r requirements.txt`
- Install (dev): `pip install -r requirements-dev.txt`
- Tests: `pytest -v` (offline; no API key or SMTP needed)
- Live feed dry-run: see `docs/PLAN.md` Phase 5.2.
- Trigger a digest manually: GitHub Actions -> select workflow -> Run workflow.

## Adding a feed

Append a `{name, url, tags}` entry to the relevant `config/feeds_*.yaml`. No code
change required.
````

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md architecture reference"
```

### Task 6.2: `README.md`

**Files:**
- Create: `README.md`

- [ ] **Step 1:** Write a concise `README.md` (emoji-free) covering: one-paragraph project description, the two-digest schedule table, setup steps (clone, `pip install -r requirements.txt`, add the four GitHub Secrets), how to run tests (`pip install -r requirements-dev.txt && pytest`), how to run the local dry-run, and how to trigger a workflow manually. Link to `CLAUDE.md` for architecture and `docs/PLAN.md` for full implementation detail.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

---

## Implementation Notes for the Engineer

- Implement phases in order: 1 → 2 → 3 → 4 → 5 → 6. Within Phase 4, write `tests/test_email_sender.py` only after the template files exist (Tasks 2.4, 3.4).
- `feed_reader.py` and `email_sender.py` are shared — implement once in Phase 1, reuse in Phases 2 and 3.
- `_action_card_html()` is a private helper in `email_sender.py` — called by both renderers. Do not duplicate it.
- Both HTML templates use **inline CSS only**. No `<style>` tags.
- Use Python `string.Template` with `$placeholder` syntax. Escape literal `$` as `$$`.
- If Groq fails, both digests still send a fallback email with the plain article list — no crash, no silent failure.
- If a feed URL is unreachable, log a `[WARN]` and skip it — never raise an exception that stops the pipeline.
- `source_url` fields use `value or "#"` so empty strings also become `"#"` in `href`.
- The four GitHub Secrets are shared between both workflows — no new secrets for The Builder.
- `action_of_the_week` accent color is `#6366f1` (Engineer) and `#f59e0b` (Builder), passed into `_action_card_html(...)`.
- Type hints on all function signatures; concise docstrings; no emojis in code/docs (email content emojis are product content, not documentation).
- Dependency management uses `pip` for this project (the repo-wide `uv` preference is intentionally not applied here).

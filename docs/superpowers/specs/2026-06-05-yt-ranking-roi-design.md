# YT Digest — ROI-Based Star Ranking

**Date:** 2026-06-05
**Status:** Approved

## Problem

The current star rating in the YT Digest asks Gemini a generic "is this worth watching?" question (1-5 stars). It has no awareness of the two personas the app serves — **Builder** (AI business, solopreneurship, Italy angle) and **Engineer** (agentic coding, Claude Code, dev productivity). A video that is excellent for the Builder but irrelevant to the Engineer scores the same as one that is mildly useful to both.

## Goal

Make the star rating reflect **which of the two topics delivers more ROI and why**, so the weekly email helps the user stay focused on Builder and Engineer work rather than generic content.

---

## Design

### 1. New PROMPT (yt_processor.py)

The `PROMPT` constant gains three new fields inserted before `Vale il tempo?`:

```
**Builder ROI:** [1-5, una frase — rilevanza per costruire/monetizzare prodotti AI, solopreneurship, mercato italiano]
**Engineer ROI:** [1-5, una frase — rilevanza per coding agentico, Claude Code, produttività di sviluppo]
**Topic dominante:** [Builder | Engineer | Entrambi]
**Vale il tempo?** [voto 1-5 con emoji ⭐ — uguale al ROI del topic dominante]
**Perché:** [1-2 frasi: quale topic beneficia di più e perché, oppure "off-topic" se nessuno dei due]
```

All other fields (`Titolo`, `Canale`, `Durata stimata`, `Argomento principale`, `Punti chiave`, `Tag`) are unchanged.

**Scoring rule:** the final `Vale il tempo?` star count equals the ROI score of the dominant topic. Gemini picks `Entrambi` only when both scores are equal or differ by at most 1 point.

**ROI definitions:**
- **Builder ROI**: actionable value for building/monetising an AI product, finding clients, or operating as a solopreneur in Italy.
- **Engineer ROI**: direct productivity gain for agentic development, Claude Code patterns, or tools that accelerate the coding workflow.

### 2. Parsing and cache schema

**New function `extract_topic(analysis: str) -> str`** in `yt_processor.py`:

```python
def extract_topic(analysis: str) -> str:
    for line in analysis.splitlines():
        if "Topic dominante" in line:
            text = line.split(":", 1)[-1].strip().strip("[]").lower()
            if "builder" in text:
                return "Builder"
            if "engineer" in text:
                return "Engineer"
            if "entrambi" in text:
                return "Entrambi"
    return "—"
```

Returns `"—"` when the field is absent (legacy cache entries).

**Cache entry** gains a `topic` field:

```json
{
  "video_id": "abc123",
  "title": "...",
  "rating": 4,
  "topic": "Builder",
  "analysis": "...",
  "processed_at": "2026-06-05T07:00:00"
}
```

Legacy entries (no `topic` key) are served via `entry.get("topic", "—")` — no migration needed.

`extract_rating()` is unchanged; it still counts `⭐` on the `Vale il tempo?` line.

### 3. Email rendering (main_yt.py)

Each video card gains a topic badge rendered inline before the title:

```
🏗 Builder          ⭐⭐⭐⭐
Come monetizzare un micro-SaaS con AI...
```

**Badge colors (inline CSS):**

| Topic | Emoji | Color |
|---|---|---|
| Builder | 🏗 | `#f97316` (orange) |
| Engineer | ⚙️ | `#3b82f6` (blue) |
| Entrambi | 🔀 | `#22c55e` (green) |
| — | — | `#64748b` (grey) |

The badge is injected in the `video_cards_html` Python string; `email_yt.html` is not modified.

**Sort order:** unchanged — `sorted_entries` sorted by `rating` descending. Off-topic videos (low rating) naturally sink to the bottom.

---

## Files changed

| File | Change |
|---|---|
| `src/yt_processor.py` | Rewrite `PROMPT`; add `extract_topic()`; call it in `process_new_videos()` |
| `src/main_yt.py` | Add topic badge to `video_cards_html` in `run_report()` |

No changes to `email_yt.html`, `yt_fetcher.py`, `yt_config.yaml`, or tests not already covering the changed functions.

---

## Out of scope

- Filtering out off-topic videos (they appear at the bottom with a low rating).
- Separate per-topic email sections or separate digest emails.
- Retroactive re-analysis of already-cached videos.

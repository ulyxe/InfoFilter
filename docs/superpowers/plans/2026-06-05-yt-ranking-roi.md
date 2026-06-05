# YT Digest — ROI-Based Star Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic "vale il tempo?" star rating with a ROI-aware score that identifies whether a video serves the Builder or Engineer persona and why.

**Architecture:** (1) `extract_topic()` parses the dominant-topic label from Gemini's response; (2) `process_new_videos()` stores `topic` alongside `rating` in the cache; (3) the `PROMPT` is rewritten to ask Gemini to score per-topic before producing a final rating; (4) `run_report()` renders a colored badge per topic in each email card.

**Tech Stack:** Python 3.12, `src/yt_processor.py`, `src/main_yt.py`, `tests/test_yt_processor.py`, `tests/test_main_yt.py`

---

### Task 1: Add `extract_topic()` to `yt_processor.py`

**Files:**
- Modify: `src/yt_processor.py` (add function after `extract_title`)
- Test: `tests/test_yt_processor.py` (add 4 unit tests)

- [ ] **Step 1: Write the failing tests**

Add this block to `tests/test_yt_processor.py`, after the `# extract_title` section:

```python
# ---------------------------------------------------------------------------
# extract_topic
# ---------------------------------------------------------------------------

def test_extract_topic_builder():
    analysis = (
        "**Titolo:** Build an AI SaaS\n"
        "**Builder ROI:** 5 — ottimo per monetizzare\n"
        "**Engineer ROI:** 2 — poco rilevante per il coding\n"
        "**Topic dominante:** Builder\n"
        "**Vale il tempo?** ⭐⭐⭐⭐⭐\n"
    )
    assert yt_processor.extract_topic(analysis) == "Builder"


def test_extract_topic_engineer():
    analysis = (
        "**Titolo:** Claude Code Deep Dive\n"
        "**Builder ROI:** 2 — poco utile per il business\n"
        "**Engineer ROI:** 5 — essenziale per agentic coding\n"
        "**Topic dominante:** Engineer\n"
        "**Vale il tempo?** ⭐⭐⭐⭐⭐\n"
    )
    assert yt_processor.extract_topic(analysis) == "Engineer"


def test_extract_topic_entrambi():
    analysis = (
        "**Builder ROI:** 4 — utile per il business\n"
        "**Engineer ROI:** 4 — utile per il coding\n"
        "**Topic dominante:** Entrambi\n"
        "**Vale il tempo?** ⭐⭐⭐⭐\n"
    )
    assert yt_processor.extract_topic(analysis) == "Entrambi"


def test_extract_topic_not_found():
    """Legacy analysis text without the 'Topic dominante' field returns '—'."""
    analysis = (
        "**Titolo:** Old Video\n"
        "**Vale il tempo?** ⭐⭐⭐\n"
        "**Perché:** vecchio formato\n"
    )
    assert yt_processor.extract_topic(analysis) == "—"
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd C:\Users\User\progetti\InfoFilter
pytest tests/test_yt_processor.py::test_extract_topic_builder tests/test_yt_processor.py::test_extract_topic_engineer tests/test_yt_processor.py::test_extract_topic_entrambi tests/test_yt_processor.py::test_extract_topic_not_found -v
```

Expected: `FAILED` with `AttributeError: module 'yt_processor' has no attribute 'extract_topic'`

- [ ] **Step 3: Implement `extract_topic()` in `yt_processor.py`**

Add this function after `extract_title()` (around line 133):

```python
def extract_topic(analysis: str) -> str:
    """Extract dominant topic label from the '**Topic dominante:**' line."""
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

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_yt_processor.py::test_extract_topic_builder tests/test_yt_processor.py::test_extract_topic_engineer tests/test_yt_processor.py::test_extract_topic_entrambi tests/test_yt_processor.py::test_extract_topic_not_found -v
```

Expected: 4 × `PASSED`

- [ ] **Step 5: Run full test suite to confirm no regressions**

```
pytest -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/yt_processor.py tests/test_yt_processor.py
git commit -m "feat: add extract_topic() to parse dominant ROI topic from Gemini response"
```

---

### Task 2: Store `topic` in cache entries

**Files:**
- Modify: `src/yt_processor.py` — update `process_new_videos()` to call `extract_topic()`
- Modify: `tests/test_yt_processor.py` — update `_make_mock_client()` response; add one new test

- [ ] **Step 1: Update `_make_mock_client()` to include the new prompt fields**

In `tests/test_yt_processor.py`, replace the `response.text` string inside `_make_mock_client()`:

```python
response.text = analysis_text or (
    "**Titolo:** Test Video\n"
    "**Canale:** Test Channel\n"
    "**Durata stimata:** 10 min\n"
    "**Argomento principale:** Testing\n"
    "**Punti chiave:**\n- punto 1\n"
    "**Builder ROI:** 3 — moderatamente utile\n"
    "**Engineer ROI:** 4 — buono per il coding\n"
    "**Topic dominante:** Engineer\n"
    "**Vale il tempo?** ⭐⭐⭐\n"
    "**Perché:** buono per Engineer\n"
    "**Tag:** #test\n"
)
```

- [ ] **Step 2: Write the failing test**

Add this test to `tests/test_yt_processor.py`, in the `# process_new_videos` section:

```python
@patch("yt_processor.time.sleep")
def test_process_new_videos_stores_topic(mock_sleep):
    """Successful cache entries include a 'topic' field extracted from the analysis."""
    client = _make_mock_client()

    result, ok, failed = yt_processor.process_new_videos(
        video_ids=["v1"],
        cache={},
        client=client,
        model="gemini-test",
        max_per_run=5,
    )

    assert ok == 1
    assert "v1" in result
    assert result["v1"]["topic"] == "Engineer"
```

- [ ] **Step 3: Run test to verify it fails**

```
pytest tests/test_yt_processor.py::test_process_new_videos_stores_topic -v
```

Expected: `FAILED` — `KeyError: 'topic'` or `AssertionError`

- [ ] **Step 4: Update `process_new_videos()` to call `extract_topic()`**

In `src/yt_processor.py`, inside `process_new_videos()`, update the `entry` dict (around line 204):

```python
entry = {
    "video_id": video_id,
    "url": url,
    "status": "ok",
    "analysis": analysis,
    "rating": extract_rating(analysis),
    "topic": extract_topic(analysis),
    "title": extract_title(analysis, video_id),
    "processed_at": datetime.now().isoformat(timespec="seconds"),
}
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_yt_processor.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/yt_processor.py tests/test_yt_processor.py
git commit -m "feat: store 'topic' field in YT cache entries"
```

---

### Task 3: Rewrite `PROMPT` to request per-topic ROI scoring

**Files:**
- Modify: `src/yt_processor.py` — replace `PROMPT` constant

No new tests needed: `PROMPT` is a string sent verbatim to the API; mocked tests don't validate its content. The parsing functions already handle the new fields (Tasks 1–2).

- [ ] **Step 1: Replace the `PROMPT` constant**

In `src/yt_processor.py`, replace the entire `PROMPT` string (lines 29–45):

```python
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
**Builder ROI:** [1-5, una frase — rilevanza per costruire/monetizzare prodotti AI, solopreneurship, mercato italiano]
**Engineer ROI:** [1-5, una frase — rilevanza per coding agentico, Claude Code, produttività di sviluppo]
**Topic dominante:** [Builder | Engineer | Entrambi]
**Vale il tempo?** [voto 1-5 con emoji: 1=⭐ 2=⭐⭐ 3=⭐⭐⭐ 4=⭐⭐⭐⭐ 5=⭐⭐⭐⭐⭐ — uguale al ROI del topic dominante]
**Perché:** [1-2 frasi: quale topic beneficia di più e perché, oppure "off-topic" se nessuno dei due]
**Tag:** [3-5 tag tematici es. #AI #produttività #tutorial]
"""
```

- [ ] **Step 2: Run full test suite**

```
pytest -v
```

Expected: all tests pass (PROMPT is not tested directly).

- [ ] **Step 3: Commit**

```bash
git add src/yt_processor.py
git commit -m "feat: rewrite Gemini PROMPT to request per-topic ROI scoring"
```

---

### Task 4: Add topic badge to email cards in `run_report()`

**Files:**
- Modify: `src/main_yt.py` — add badge rendering in `run_report()`
- Modify: `tests/test_main_yt.py` — update `_make_entry()` helper; add badge test

- [ ] **Step 1: Update `_make_entry()` helper to include `topic`**

In `tests/test_main_yt.py`, update the `_make_entry()` signature and body:

```python
def _make_entry(video_id: str, rating: int, days_ago: int = 0, topic: str = "Builder") -> dict:
    """Build a minimal cache entry."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "status": "ok",
        "analysis": f"**Titolo:** Video {video_id}\n**Vale il tempo?** {'⭐' * rating}\n",
        "rating": rating,
        "topic": topic,
        "title": f"Video {video_id}",
        "processed_at": dt.isoformat(timespec="seconds"),
    }
```

- [ ] **Step 2: Write the failing test**

Add this test to `tests/test_main_yt.py`, inside `class TestReportMode`:

```python
def test_report_mode_html_contains_topic_badge(self, tmp_path, monkeypatch):
    """HTML email cards include a colored topic badge for each entry."""
    cache_path = tmp_path / "cache" / "yt_cache.json"
    monkeypatch.setattr(main_yt, "_CACHE_PATH", cache_path)
    monkeypatch.setattr(main_yt, "_TEMPLATE_PATH", tmp_path / "no_template.html")

    recent_cache = {
        "b1": _make_entry("b1", 4, days_ago=1, topic="Builder"),
        "e1": _make_entry("e1", 3, days_ago=1, topic="Engineer"),
        "x1": _make_entry("x1", 2, days_ago=1, topic="—"),
    }

    captured_html: list[str] = []

    def fake_send_digest(subject, html, plain):
        captured_html.append(html)

    with (
        patch("main_yt.load_cache", return_value=recent_cache),
        patch("main_yt.send_digest", side_effect=fake_send_digest),
    ):
        main_yt.run_report()

    assert captured_html, "send_digest was not called"
    html = captured_html[0]
    assert "#f97316" in html, "Builder badge color missing"
    assert "#3b82f6" in html, "Engineer badge color missing"
    assert "#64748b" in html, "Fallback badge color missing"
    assert "🏗" in html, "Builder emoji missing"
    assert "⚙️" in html, "Engineer emoji missing"
```

- [ ] **Step 3: Run test to verify it fails**

```
pytest tests/test_main_yt.py::TestReportMode::test_report_mode_html_contains_topic_badge -v
```

Expected: `FAILED` — badge colors absent from generated HTML.

- [ ] **Step 4: Implement topic badge in `run_report()`**

In `src/main_yt.py`, replace the `video_cards_html` building block inside the `if _TEMPLATE_PATH.exists():` branch (starting around line 138):

```python
_TOPIC_BADGE = {
    "Builder":  ("🏗",  "#f97316"),
    "Engineer": ("⚙️", "#3b82f6"),
    "Entrambi": ("🔀",  "#22c55e"),
    "—":        ("—",   "#64748b"),
}

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
```

Note: `_TOPIC_BADGE` is defined inside `run_report()` (just above the `video_cards_html = ""` line), not at module level, to keep it co-located with the rendering logic.

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_main_yt.py -v
```

Expected: all tests pass including the new badge test.

- [ ] **Step 6: Run full test suite**

```
pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/main_yt.py tests/test_main_yt.py
git commit -m "feat: add ROI topic badge to YT Digest email cards"
```

# YT Digest — PDF Allegato + Summary Arricchito — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Arricchire l'analisi Gemini, compattare il corpo email YT Digest a un ranking con 2 righe per video, e allegare un PDF con il summary completo di ogni video.

**Architecture:** Il prompt Gemini viene esteso con 4 nuove sezioni (più punti chiave, strumenti, risorse, metodologia). `_parse_yt_analysis()` estrae i nuovi campi. Un nuovo modulo `yt_pdf.py` genera il PDF da passare a `send_digest()` come allegato MIME opzionale. L'email body diventa una lista ranking compatta.

**Tech Stack:** Python 3.11, fpdf2 (PDF generation, pure Python), email.mime.application (MIME attachment), string.Template (email HTML), pytest.

---

## File Map

| File | Azione | Responsabilità |
|---|---|---|
| `requirements.txt` | Modifica | Aggiunge `fpdf2` |
| `src/yt_processor.py` | Modifica | Estende `PROMPT` con 4 nuove sezioni |
| `src/main_yt.py` | Modifica | `_parse_yt_analysis()` + `run_report()` compatto + import yt_pdf |
| `src/yt_pdf.py` | **Nuovo** | `generate_digest_pdf(parsed_entries, date_str) -> bytes` |
| `src/email_sender.py` | Modifica | `send_digest()` + parametro `pdf_attachment` opzionale |
| `templates/email_yt.html` | Modifica | Layout compatto, `$video_list`, footer PDF |
| `cache/yt_cache.json` | Reset | Rimuove entry `Zk9LxO_dB64` |
| `tests/test_main_yt.py` | **Nuovo** | Test per `_parse_yt_analysis()` nuovi campi |
| `tests/test_yt_pdf.py` | **Nuovo** | Test per `generate_digest_pdf()` |
| `tests/test_email_sender.py` | **Nuovo** | Test per `send_digest()` con allegato |

---

## Task 1: Aggiungi fpdf2 alle dipendenze

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Aggiungi fpdf2 a requirements.txt**

Il file attuale ha: `feedparser==6.0.11`, `groq>=0.9.0`, `PyYAML>=6.0.2`, `google-genai`, `google-api-python-client`.
Aggiungi in fondo:

```
fpdf2>=2.7.0
```

- [ ] **Step 2: Installa la nuova dipendenza**

```bash
pip install fpdf2>=2.7.0
```

- [ ] **Step 3: Verifica l'import**

```bash
python -c "from fpdf import FPDF; print('fpdf2 ok')"
```

Atteso: `fpdf2 ok`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add fpdf2 for YT Digest PDF generation"
```

---

## Task 2: TDD — Estendi `_parse_yt_analysis()` con nuovi campi

**Files:**
- Create: `tests/test_main_yt.py`
- Modify: `src/main_yt.py` (funzione `_parse_yt_analysis` e import `re`)

### Step 1: Scrivi i test (devono fallire)

- [ ] **Crea `tests/test_main_yt.py`:**

```python
"""Tests for _parse_yt_analysis() in src/main_yt.py."""
from __future__ import annotations

import pytest
from main_yt import _parse_yt_analysis

# ---------------------------------------------------------------------------
# Sample analysis con tutti i nuovi campi
# ---------------------------------------------------------------------------

FULL_ANALYSIS = """\
**Titolo:** Come Diventare un AI Engineer
**Canale:** Tech With Tim
**Durata stimata:** 11 minuti
**Argomento principale:** Una roadmap pratica in 10 passaggi per diventare AI engineer.
**Punti chiave:**
- Basi solide di Python
- Modelli Mentali dei LLM
- Prompt Engineering e RAG
**Strumenti e tecnologie:** Python, LangChain, Pinecone, Claude Code
**Risorse consigliate:** Corso di DeepLearning.AI, Paper: Attention is All You Need
**Metodologia:**
- Impara Python di base
- Comprendi le API dei LLM
- Implementa un sistema RAG
**Builder ROI:** 4/5 — Utile per monetizzare
**Engineer ROI:** 5/5 — Essenziale per il coding
**Topic dominante:** Entrambi
**Vale il tempo?** ⭐⭐⭐⭐⭐
**Perché:** Buono per tutti i profili
**Tag:** #AI #Python #RAG
"""


def test_parse_strumenti():
    result = _parse_yt_analysis(FULL_ANALYSIS)
    assert result["strumenti"] == ["Python", "LangChain", "Pinecone", "Claude Code"]


def test_parse_risorse():
    result = _parse_yt_analysis(FULL_ANALYSIS)
    assert result["risorse"] == [
        "Corso di DeepLearning.AI",
        "Paper: Attention is All You Need",
    ]


def test_parse_metodologia_bullets():
    result = _parse_yt_analysis(FULL_ANALYSIS)
    assert result["metodologia"] == [
        "Impara Python di base",
        "Comprendi le API dei LLM",
        "Implementa un sistema RAG",
    ]


def test_parse_metodologia_numbered():
    analysis = (
        "**Punti chiave:**\n- punto 1\n"
        "**Metodologia:**\n"
        "1. Step uno\n"
        "2. Step due\n"
        "**Builder ROI:** 3/5 — ok\n"
    )
    result = _parse_yt_analysis(analysis)
    assert result["metodologia"] == ["Step uno", "Step due"]


def test_parse_metodologia_na():
    analysis = (
        "**Punti chiave:**\n- punto 1\n"
        "**Metodologia:**\n"
        "N/A\n"
        "**Builder ROI:** 3/5 — ok\n"
    )
    result = _parse_yt_analysis(analysis)
    assert result["metodologia"] == []


def test_parse_strumenti_nessuno():
    analysis = (
        "**Punti chiave:**\n- punto 1\n"
        "**Strumenti e tecnologie:** nessuno\n"
        "**Risorse consigliate:** nessuna\n"
        "**Builder ROI:** 3/5 — ok\n"
    )
    result = _parse_yt_analysis(analysis)
    assert result["strumenti"] == []
    assert result["risorse"] == []


def test_parse_backward_compat_missing_fields():
    """Vecchie entry senza i nuovi campi: liste vuote, nessun crash."""
    old_analysis = (
        "**Titolo:** Old Video\n"
        "**Canale:** Chan\n"
        "**Punti chiave:**\n- punto 1\n"
        "**Builder ROI:** 3 — ok\n"
        "**Vale il tempo?** ⭐⭐⭐\n"
        "**Tag:** #AI\n"
    )
    result = _parse_yt_analysis(old_analysis)
    assert result["strumenti"] == []
    assert result["risorse"] == []
    assert result["metodologia"] == []


def test_parse_existing_fields_unchanged():
    """I campi esistenti continuano a essere estratti correttamente."""
    result = _parse_yt_analysis(FULL_ANALYSIS)
    assert result["canale"] == "Tech With Tim"
    assert result["durata"] == "11 minuti"
    assert result["argomento"] == "Una roadmap pratica in 10 passaggi per diventare AI engineer."
    assert len(result["punti"]) == 3
    assert result["builder_roi"].startswith("4/5")
    assert result["engineer_roi"].startswith("5/5")
    assert result["tags"] == "#AI #Python #RAG"
```

- [ ] **Step 2: Verifica che i test falliscano**

```bash
pytest tests/test_main_yt.py -v
```

Atteso: tutti i test falliscono con `KeyError: 'strumenti'` o simile (i nuovi campi non esistono ancora nel dict).

### Step 3: Implementa i nuovi campi in `_parse_yt_analysis()`

- [ ] **Sostituisci la funzione `_parse_yt_analysis` in `src/main_yt.py` (linee 69–112 circa):**

```python
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
```

Nota: `re` è già importato in `main_yt.py` (linea 19). Nessun nuovo import necessario.

- [ ] **Step 4: Esegui i test e verifica che passino**

```bash
pytest tests/test_main_yt.py -v
```

Atteso: tutti i test passano (`PASSED`).

- [ ] **Step 5: Esegui la suite completa per verificare nessuna regressione**

```bash
pytest -v
```

Atteso: tutti i test passano.

- [ ] **Step 6: Commit**

```bash
git add tests/test_main_yt.py src/main_yt.py
git commit -m "feat: extend _parse_yt_analysis with strumenti, risorse, metodologia fields"
```

---

## Task 3: TDD — Crea `src/yt_pdf.py`

**Files:**
- Create: `tests/test_yt_pdf.py`
- Create: `src/yt_pdf.py`

### Step 1: Scrivi i test (devono fallire)

- [ ] **Crea `tests/test_yt_pdf.py`:**

```python
"""Tests for src/yt_pdf.py."""
from __future__ import annotations

import pytest
from yt_pdf import generate_digest_pdf

# ---------------------------------------------------------------------------
# Helper: crea una entry PDF-ready con tutti i campi
# ---------------------------------------------------------------------------

def _make_entry(**overrides) -> dict:
    base = {
        "title": "Come Diventare un AI Engineer",
        "url": "https://www.youtube.com/watch?v=test123",
        "rating": 5,
        "topic": "Entrambi",
        "canale": "Tech With Tim",
        "durata": "11 minuti",
        "argomento": "Una roadmap pratica per diventare AI engineer.",
        "punti": ["Basi di Python", "Modelli LLM", "RAG con Pinecone"],
        "strumenti": ["Python", "LangChain", "Pinecone"],
        "risorse": ["Corso DeepLearning.AI"],
        "metodologia": ["Impara Python", "Comprendi le API", "Implementa RAG"],
        "builder_roi": "4/5 — utile per monetizzare",
        "engineer_roi": "5/5 — essenziale",
        "perche": "Beneficia sia Builder che Engineer.",
        "tags": "#AI #Python #RAG",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_generate_pdf_returns_bytes():
    result = generate_digest_pdf([_make_entry()], "06 June 2026")
    assert isinstance(result, bytes)
    assert len(result) > 100


def test_generate_pdf_valid_pdf_header():
    """PDF files start with the magic bytes %PDF."""
    result = generate_digest_pdf([_make_entry()], "06 June 2026")
    assert result.startswith(b"%PDF")


def test_generate_pdf_multiple_entries():
    entries = [_make_entry(title=f"Video {i}", rating=i) for i in range(1, 4)]
    result = generate_digest_pdf(entries, "06 June 2026")
    assert isinstance(result, bytes)
    assert result.startswith(b"%PDF")


def test_generate_pdf_empty_optional_fields():
    """No crash when optional fields are empty lists/strings."""
    entry = _make_entry(
        strumenti=[],
        risorse=[],
        metodologia=[],
        canale="",
        durata="",
        argomento="",
        punti=[],
        builder_roi="",
        engineer_roi="",
        perche="",
        tags="",
    )
    result = generate_digest_pdf([entry], "06 June 2026")
    assert isinstance(result, bytes)
    assert result.startswith(b"%PDF")


def test_generate_pdf_zero_rating():
    entry = _make_entry(rating=0)
    result = generate_digest_pdf([entry], "06 June 2026")
    assert isinstance(result, bytes)
```

- [ ] **Step 2: Verifica che i test falliscano**

```bash
pytest tests/test_yt_pdf.py -v
```

Atteso: `ModuleNotFoundError: No module named 'yt_pdf'`

### Step 3: Implementa `src/yt_pdf.py`

- [ ] **Crea `src/yt_pdf.py`:**

```python
"""Generate a PDF summary for the YouTube Digest."""
from __future__ import annotations

import re

from fpdf import FPDF


def _safe(text: str) -> str:
    """Replace characters outside Latin-1 with '?' for Helvetica core font."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _stars(rating: int) -> str:
    if not rating:
        return "(n.d.)"
    return "*" * rating + f" ({rating}/5)"


def _section_header(pdf: FPDF, title: str) -> None:
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(0, 6, text=title, new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_font("Helvetica", "", 10)


def generate_digest_pdf(parsed_entries: list[dict], date_str: str) -> bytes:
    """Return PDF bytes for the digest.

    Args:
        parsed_entries: List of dicts already processed by _parse_yt_analysis,
            each containing keys: title, url, rating, topic, canale, durata,
            argomento, punti, strumenti, risorse, metodologia,
            builder_roi, engineer_roi, perche, tags.
        date_str: Human-readable date string for the header.
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(20, 15, 20)

    # --- Cover header ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, text="YouTube Digest", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, text=_safe(date_str), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0, 6,
        text=f"{len(parsed_entries)} video analizzati questa settimana",
        new_x="LMARGIN", new_y="NEXT", align="C",
    )
    pdf.ln(10)

    for i, e in enumerate(parsed_entries, start=1):
        # Separator line
        pdf.set_draw_color(180, 180, 180)
        pdf.set_line_width(0.4)
        pdf.line(20, pdf.get_y(), 190, pdf.get_y())
        pdf.ln(4)

        # Video header
        pdf.set_font("Helvetica", "B", 13)
        pdf.multi_cell(0, 7, text=_safe(f"#{i}  {e.get('title', '')}"))
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(
            0, 6,
            text=_safe(f"{_stars(e.get('rating', 0))}  [{e.get('topic', '-')}]"),
            new_x="LMARGIN", new_y="NEXT",
        )

        url = e.get("url", "")
        if url:
            pdf.set_text_color(0, 0, 180)
            pdf.cell(0, 5, text=url, new_x="LMARGIN", new_y="NEXT", link=url)
            pdf.set_text_color(0, 0, 0)

        meta = "  ·  ".join(s for s in [e.get("canale", ""), e.get("durata", "")] if s)
        if meta:
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(0, 5, text=_safe(meta), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)

        pdf.ln(3)

        # Argomento
        if e.get("argomento"):
            _section_header(pdf, "ARGOMENTO")
            pdf.multi_cell(0, 6, text=_safe(e["argomento"]))
            pdf.ln(2)

        # Punti chiave
        if e.get("punti"):
            _section_header(pdf, "PUNTI CHIAVE")
            for p in e["punti"]:
                pdf.multi_cell(0, 6, text=_safe(f"- {p}"))
            pdf.ln(2)

        # Strumenti e tecnologie
        if e.get("strumenti"):
            _section_header(pdf, "STRUMENTI E TECNOLOGIE")
            pdf.multi_cell(0, 6, text=_safe(", ".join(e["strumenti"])))
            pdf.ln(2)

        # Risorse consigliate
        if e.get("risorse"):
            _section_header(pdf, "RISORSE CONSIGLIATE")
            for r in e["risorse"]:
                pdf.multi_cell(0, 6, text=_safe(f"- {r}"))
            pdf.ln(2)

        # Metodologia
        if e.get("metodologia"):
            _section_header(pdf, "METODOLOGIA")
            for j, step in enumerate(e["metodologia"], start=1):
                pdf.multi_cell(0, 6, text=_safe(f"{j}. {step}"))
            pdf.ln(2)

        # ROI
        roi_lines = []
        if e.get("builder_roi"):
            roi_lines.append(f"Builder: {e['builder_roi']}")
        if e.get("engineer_roi"):
            roi_lines.append(f"Engineer: {e['engineer_roi']}")
        if roi_lines:
            _section_header(pdf, "ROI")
            for r in roi_lines:
                pdf.multi_cell(0, 6, text=_safe(r))
            pdf.ln(2)

        # Perché vale il tempo
        if e.get("perche"):
            pdf.set_font("Helvetica", "I", 10)
            pdf.multi_cell(0, 6, text=_safe(f"Perche vale il tempo: {e['perche']}"))
            pdf.set_font("Helvetica", "", 10)
            pdf.ln(2)

        # Tags
        if e.get("tags"):
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(120, 120, 120)
            pdf.cell(0, 5, text=_safe(e["tags"]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", 10)

        pdf.ln(8)

    return bytes(pdf.output())
```

- [ ] **Step 4: Esegui i test e verifica che passino**

```bash
pytest tests/test_yt_pdf.py -v
```

Atteso: tutti i test passano.

- [ ] **Step 5: Esegui la suite completa**

```bash
pytest -v
```

Atteso: tutti i test passano.

- [ ] **Step 6: Commit**

```bash
git add src/yt_pdf.py tests/test_yt_pdf.py
git commit -m "feat: add yt_pdf module for YouTube Digest PDF generation"
```

---

## Task 4: TDD — Estendi `send_digest()` con supporto allegato PDF

**Files:**
- Create: `tests/test_email_sender.py`
- Modify: `src/email_sender.py`

### Step 1: Scrivi i test (devono fallire)

- [ ] **Crea `tests/test_email_sender.py`:**

```python
"""Tests for send_digest() PDF attachment support in src/email_sender.py."""
from __future__ import annotations

import email
import os
from unittest.mock import MagicMock, patch

import pytest

from email_sender import send_digest

ENV = {
    "SMTP_USER": "sender@test.com",
    "SMTP_PASSWORD": "pass",
    "DIGEST_RECIPIENT_EMAIL": "recv@test.com",
}


@patch("email_sender.smtplib.SMTP")
def test_send_digest_without_attachment_uses_alternative(mock_smtp_cls, monkeypatch):
    """Without attachment, the top-level MIME type must be multipart/alternative."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)

    mock_server = mock_smtp_cls.return_value.__enter__.return_value

    send_digest("Subj", "<p>HTML</p>", "Plain")

    mock_server.sendmail.assert_called_once()
    raw = mock_server.sendmail.call_args[0][2]
    msg = email.message_from_string(raw)
    assert msg.get_content_type() == "multipart/alternative"


@patch("email_sender.smtplib.SMTP")
def test_send_digest_with_attachment_uses_mixed(mock_smtp_cls, monkeypatch):
    """With attachment, the top-level MIME type must be multipart/mixed."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)

    mock_server = mock_smtp_cls.return_value.__enter__.return_value
    pdf_bytes = b"%PDF-1.4 fake content"

    send_digest("Subj", "<p>HTML</p>", "Plain", pdf_attachment=pdf_bytes)

    mock_server.sendmail.assert_called_once()
    raw = mock_server.sendmail.call_args[0][2]
    msg = email.message_from_string(raw)
    assert msg.get_content_type() == "multipart/mixed"


@patch("email_sender.smtplib.SMTP")
def test_send_digest_with_attachment_has_pdf_part(mock_smtp_cls, monkeypatch):
    """The mixed message must contain an application/* attachment part."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)

    mock_server = mock_smtp_cls.return_value.__enter__.return_value
    pdf_bytes = b"%PDF-1.4 fake content"

    send_digest("Subj", "<p>HTML</p>", "Plain", pdf_attachment=pdf_bytes,
                pdf_filename="digest.pdf")

    raw = mock_server.sendmail.call_args[0][2]
    msg = email.message_from_string(raw)
    parts = list(msg.walk())
    content_types = [p.get_content_type() for p in parts]
    # Must have at least one application/* part (the PDF)
    assert any(ct.startswith("application/") for ct in content_types)
    # Must contain a part with the correct filename
    dispositions = [p.get("Content-Disposition", "") for p in parts]
    assert any("digest.pdf" in d for d in dispositions)


@patch("email_sender.smtplib.SMTP")
def test_send_digest_with_attachment_contains_html_part(mock_smtp_cls, monkeypatch):
    """The mixed message must still contain the HTML body."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)

    mock_server = mock_smtp_cls.return_value.__enter__.return_value

    send_digest("Subj", "<p>HTML body</p>", "Plain body",
                pdf_attachment=b"%PDF test")

    raw = mock_server.sendmail.call_args[0][2]
    msg = email.message_from_string(raw)
    content_types = [p.get_content_type() for p in msg.walk()]
    assert "text/html" in content_types
    assert "text/plain" in content_types
```

- [ ] **Step 2: Verifica che i test falliscano**

```bash
pytest tests/test_email_sender.py -v
```

Atteso: `test_send_digest_with_attachment_uses_mixed` e gli altri attachment-related falliscono (la funzione non accetta ancora `pdf_attachment`).

### Step 3: Implementa il supporto allegati in `src/email_sender.py`

- [ ] **Sostituisci l'intera funzione `send_digest` e aggiungi l'import `MIMEApplication` in `src/email_sender.py`.**

Aggiungi import in cima (dopo le imports esistenti):
```python
from email.mime.application import MIMEApplication
```

Sostituisci la funzione `send_digest` (linee 9–28 circa):

```python
def send_digest(
    subject: str,
    html_body: str,
    plain_body: str,
    pdf_attachment: bytes | None = None,
    pdf_filename: str = "youtube_digest.pdf",
) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    sender = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    recipient = os.environ["DIGEST_RECIPIENT_EMAIL"]

    if pdf_attachment:
        msg = MIMEMultipart("mixed")
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(plain_body, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alt)
        part = MIMEApplication(pdf_attachment, Name=pdf_filename)
        part["Content-Disposition"] = f'attachment; filename="{pdf_filename}"'
        msg.attach(part)
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
    print(f"[OK] Email sent to {recipient}")
```

- [ ] **Step 4: Esegui i test e verifica che passino**

```bash
pytest tests/test_email_sender.py -v
```

Atteso: tutti e 4 i test passano.

- [ ] **Step 5: Esegui la suite completa**

```bash
pytest -v
```

Atteso: tutti i test passano.

- [ ] **Step 6: Commit**

```bash
git add src/email_sender.py tests/test_email_sender.py
git commit -m "feat: add optional PDF attachment support to send_digest()"
```

---

## Task 5: Aggiorna `run_report()` e il template email

**Files:**
- Modify: `src/main_yt.py` (funzione `run_report`, import)
- Modify: `templates/email_yt.html`

### Step 1: Aggiorna il template HTML

- [ ] **Sostituisci il contenuto di `templates/email_yt.html` con:**

```html
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>YouTube Digest</title>
</head>
<body style="margin:0;padding:0;background:#0f172a;color:#e2e8f0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="width:640px;max-width:640px;background:#0f172a;">
          <tr>
            <td style="padding:8px 24px 24px 24px;">

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-bottom:2px solid #ef4444;padding-bottom:12px;">
                <tr>
                  <td style="font-size:24px;font-weight:bold;color:#e2e8f0;">🎬 YouTube Digest</td>
                  <td align="right" style="font-size:14px;color:#fca5a5;">$date</td>
                </tr>
              </table>

              <p style="font-size:13px;color:#ef4444;text-transform:uppercase;letter-spacing:1px;margin:24px 0 4px 0;">Ranking questa settimana</p>
              $video_list

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #1e293b;margin-top:24px;">
                <tr>
                  <td align="center" style="padding-top:16px;font-size:12px;color:#64748b;">$video_count video analizzati · Il summary completo con strumenti, risorse e metodologia è allegato come PDF.</td>
                </tr>
              </table>

            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

### Step 2: Aggiorna gli import in `src/main_yt.py`

- [ ] **Aggiungi `from yt_pdf import generate_digest_pdf` agli import in cima a `src/main_yt.py`**, subito dopo gli import interni esistenti:

```python
from email_sender import send_digest
from yt_fetcher import fetch_playlist_ids
from yt_pdf import generate_digest_pdf       # <-- aggiungi questa riga
from yt_processor import (
```

### Step 3: Sostituisci `run_report()` in `src/main_yt.py`

- [ ] **Sostituisci l'intera funzione `run_report` (linee 173–293 circa) con:**

```python
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

    # Pre-parse all analyses once
    parsed = [_parse_yt_analysis(e.get("analysis", "")) for e in sorted_entries]

    # --- Compact HTML body (ranking list) ---
    if _TEMPLATE_PATH.exists():
        video_list_html = ""
        for i, (entry, af) in enumerate(zip(sorted_entries, parsed), start=1):
            stars = "⭐" * entry.get("rating", 0)
            topic = entry.get("topic", "—")
            emoji, color = _TOPIC_BADGE.get(topic, ("—", "#64748b"))
            badge = (
                f'<span style="font-size:11px;font-weight:bold;color:{color};">'
                f'{emoji} {topic}</span>'
            )
            separator = (
                '<hr style="border:none;border-top:1px solid #1e293b;margin:8px 0;">'
                if i > 1 else ""
            )
            argomento_html = (
                f'<p style="color:#cbd5e1;margin:2px 0;font-size:13px;">'
                f'{_md_to_html(af["argomento"])}</p>'
                if af["argomento"] else ""
            )
            perche_html = (
                f'<p style="color:#94a3b8;font-size:12px;margin:2px 0;font-style:italic;">'
                f'&#128161; {_md_to_html(af["perche"])}</p>'
                if af["perche"] else ""
            )
            video_list_html += f"""{separator}
            <div style="padding:12px 0;">
              <div style="margin-bottom:4px;">{badge}&nbsp;&nbsp;<span style="color:#ef4444;font-size:13px;">{stars}</span></div>
              <h3 style="margin:0 0 4px 0;font-size:15px;">
                <span style="color:#64748b;font-size:12px;">#{i}</span>&nbsp;
                <a href="{entry.get('url', '#')}" style="color:#f87171;text-decoration:none;">{escape(entry.get('title', ''))}</a>
              </h3>
              {argomento_html}
              {perche_html}
            </div>"""

        template = Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))
        html = template.substitute(
            date=date_str,
            video_count=len(sorted_entries),
            video_list=video_list_html,
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

    # --- Plain text body ---
    plain = f"YouTube Digest — {date_str}\n\n" + "\n".join([
        f"#{i}  {'*' * e.get('rating', 0)} [{e.get('topic', '—')}]  {e.get('title', '')}\n"
        f"  {e.get('url', '')}"
        for i, e in enumerate(sorted_entries, start=1)
    ]) + "\n\n(Il summary completo e' allegato come PDF.)"

    # --- PDF attachment ---
    pdf_entries = [
        {
            "title": e.get("title", ""),
            "url": e.get("url", ""),
            "rating": e.get("rating", 0),
            "topic": e.get("topic", "—"),
            **af,
        }
        for e, af in zip(sorted_entries, parsed)
    ]
    pdf_bytes = generate_digest_pdf(pdf_entries, date_str)

    send_digest(subject, html, plain, pdf_attachment=pdf_bytes)
    print(
        f"[INFO] YouTube Digest sent. Videos: {len(sorted_entries)}", flush=True)
```

- [ ] **Step 4: Esegui la suite completa dei test**

```bash
pytest -v
```

Atteso: tutti i test passano.

- [ ] **Step 5: Commit**

```bash
git add src/main_yt.py templates/email_yt.html
git commit -m "feat: compact YT Digest email body with ranking, PDF attachment in run_report"
```

---

## Task 6: Aggiorna il PROMPT Gemini

**Files:**
- Modify: `src/yt_processor.py`

- [ ] **Step 1: Sostituisci la costante `PROMPT` in `src/yt_processor.py` (linee 29–48 circa):**

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
- [punto 4]
- [punto 5]
- [punto 6 se rilevante]
- [punto 7 se rilevante]
- [punto 8 se rilevante]
**Strumenti e tecnologie:** [lista di tool/librerie/framework/servizi citati, separati da virgola, o "nessuno"]
**Risorse consigliate:** [libri, corsi, link, paper menzionati, separati da virgola, o "nessuna"]
**Metodologia:**
- [passo 1 se il video è un tutorial/how-to con passi distinti]
- [passo 2]
- (scrivi solo "N/A" su riga singola se il video non ha una metodologia passo-passo)
**Builder ROI:** [1-5, una frase — rilevanza per costruire/monetizzare prodotti AI, solopreneurship, mercato italiano]
**Engineer ROI:** [1-5, una frase — rilevanza per coding agentico, Claude Code, produttività di sviluppo]
**Topic dominante:** [Builder | Engineer | Entrambi]
**Vale il tempo?** [voto 1-5 con emoji: 1=⭐ 2=⭐⭐ 3=⭐⭐⭐ 4=⭐⭐⭐⭐ 5=⭐⭐⭐⭐⭐ — uguale al ROI del topic dominante]
**Perché:** [1-2 frasi: quale topic beneficia di più e perché, oppure "off-topic" se nessuno dei due]
**Tag:** [3-5 tag tematici es. #AI #produttività #tutorial]
"""
```

- [ ] **Step 2: Esegui la suite completa dei test**

```bash
pytest -v
```

Atteso: tutti i test passano (il PROMPT è una stringa costante, nessun test diretto su di essa).

- [ ] **Step 3: Commit**

```bash
git add src/yt_processor.py
git commit -m "feat: enrich Gemini PROMPT with tools, resources, methodology, up to 8 key points"
```

---

## Task 7: Reset cache e commit finale

**Files:**
- Modify: `cache/yt_cache.json`

- [ ] **Step 1: Svuota la cache per forzare il re-processing**

Sostituisci il contenuto di `cache/yt_cache.json` con:

```json
{}
```

La prossima run `--mode=fetch` analizzerà nuovamente il video `Zk9LxO_dB64` usando il prompt arricchito.

- [ ] **Step 2: Verifica la suite completa una volta di più**

```bash
pytest -v
```

Atteso: tutti i test passano.

- [ ] **Step 3: Commit finale**

```bash
git add cache/yt_cache.json
git commit -m "chore: clear YT cache to trigger re-analysis with enriched prompt"
```

---

## Verifica finale

Dopo tutti i task, verifica:

```bash
pytest -v
```

Tutti i test devono passare. Nessuna modifica ai workflow GitHub Actions richiesta. La prossima run `--mode=fetch` su GitHub Actions rianaalizzerà il video con il prompt arricchito e la prossima `--mode=report` invierà l'email compatta con il PDF allegato.

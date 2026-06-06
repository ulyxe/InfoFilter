# YT Digest — PDF Allegato + Summary Arricchito

**Data:** 2026-06-06  
**Stato:** Approvato

## Obiettivo

1. Rendere l'email YT Digest compatta (ranking + 2 righe per video).
2. Allegare un PDF con il summary completo e arricchito di ogni video.
3. Arricchire l'analisi Gemini per catturare strumenti citati, risorse esterne, metodologia step-by-step e più punti chiave.

---

## 1. Prompt Gemini arricchito (`src/yt_processor.py`)

Il campo `PROMPT` viene esteso con quattro nuove sezioni obbligatorie, posizionate dopo i punti chiave:

```
**Punti chiave:**
- [fino a 7-8 bullet, non più 3-4 minimi]

**Strumenti e tecnologie:** [lista di tool/librerie/servizi citati separati da virgola, o "nessuno"]
**Risorse consigliate:** [libri, corsi, link, paper menzionati separati da virgola, o "nessuna"]
**Metodologia:**
- [passaggi numerati se è un tutorial/how-to, o "N/A" su riga singola]
```

Il resto del prompt (Builder ROI, Engineer ROI, Topic dominante, Vale il tempo?, Perché, Tag) rimane invariato.

**Motivazione:** le versioni precedenti perdevano tool citati (Pinecone, LangChain, ecc.) sepolti nei bullet, e non catturavano risorse esterne né sequenze metodologiche.

---

## 2. Parsing esteso (`src/main_yt.py` — `_parse_yt_analysis()`)

I nuovi campi estratti dal testo raw dell'analisi:

| Campo | Tipo | Parsing |
|---|---|---|
| `strumenti` | `list[str]` | Riga `**Strumenti e tecnologie:**` → split per virgola |
| `risorse` | `list[str]` | Riga `**Risorse consigliate:**` → split per virgola |
| `metodologia` | `list[str]` | Bullet/numeri sotto `**Metodologia:**` → lista; vuota se "N/A" |

**Retrocompatibilità:** le entry in cache prive dei nuovi campi restituiscono liste vuote — nessun crash nel rendering PDF o email.

---

## 3. Nuovo modulo PDF (`src/yt_pdf.py`)

### API pubblica

```python
def generate_digest_pdf(entries: list[dict], date_str: str) -> bytes
```

- `entries`: lista ordinata per rating (come già usata in `run_report`).
- Ritorna i byte del PDF, pronti per l'allegato MIME.

### Layout per video

Ogni video è separato da un divisore pesante (`━━━`). Struttura:

```
#N  TITOLO  ⭐×N  [Topic]
URL: ...
Canale: ...  ·  Durata: ...

ARGOMENTO
...

PUNTI CHIAVE
• ...

STRUMENTI E TECNOLOGIE
tool1, tool2, ...

RISORSE CONSIGLIATE
• risorsa1
• risorsa2

METODOLOGIA
1. step1
2. step2
...  (omessa se vuota)

ROI
🏗 Builder N/5 — ...
⚙️ Engineer N/5 — ...

💡 Perché vale il tempo: ...
Tags: ...
```

Sezioni con dati vuoti (es. Metodologia = N/A, Risorse = nessuna) vengono omesse.

### Dipendenza

`fpdf2` — pure Python, nessuna dipendenza di sistema. Aggiunta a `requirements.txt`.  
Font: Helvetica (built-in fpdf2). Tema chiaro (sfondo bianco).

---

## 4. Allegato email (`src/email_sender.py`)

### Firma aggiornata

```python
def send_digest(
    subject: str,
    html_body: str,
    plain_body: str,
    pdf_attachment: bytes | None = None,
    pdf_filename: str = "youtube_digest.pdf",
) -> None
```

### Struttura MIME quando `pdf_attachment` è presente

```
MIMEMultipart("mixed")
  ├── MIMEMultipart("alternative")
  │   ├── MIMEText(plain, "plain")
  │   └── MIMEText(html, "html")
  └── MIMEApplication(pdf_bytes)
      Content-Disposition: attachment; filename="youtube_digest.pdf"
```

Quando `pdf_attachment=None` (Engineer digest, Builder digest), la struttura torna a `MIMEMultipart("alternative")` — retrocompatibile senza modifiche ai chiamanti esistenti.

---

## 5. Email body compatta (`templates/email_yt.html` + `main_yt.py`)

### Template

Il placeholder `$video_cards` viene rinominato `$video_list`. Il contenuto è una lista ranking, non card espanse.

### Struttura per ogni video nel corpo email

```
#1  ⭐⭐⭐⭐⭐  🔀 Entrambi
Come Diventare un AI Engineer  [link]
Una roadmap pratica in 10 passaggi per diventare AI engineer.
💡 Beneficia sia il Builder che vuole soluzioni robuste, sia l'Engineer...
```

Separatore leggero (`<hr>`) tra video. Nessun ROI, tag, canale, durata nel corpo.

Footer aggiunto al template: *"Il summary completo con strumenti, risorse e metodologia è allegato come PDF."*

### `run_report()` aggiornato

```python
# 1. Render corpo compatto
html, plain = render_compact_email(sorted_entries, date_str)
# 2. Genera PDF
pdf_bytes = generate_digest_pdf(sorted_entries, date_str)
# 3. Invia con allegato
send_digest(subject, html, plain, pdf_attachment=pdf_bytes)
```

---

## 6. Reset cache

L'entry `Zk9LxO_dB64` viene rimossa da `cache/yt_cache.json` come parte del piano di implementazione. La prossima run `--mode=fetch` la rianalizza con il prompt arricchito.

---

## File modificati / creati

| File | Tipo modifica |
|---|---|
| `src/yt_processor.py` | Modifica — PROMPT esteso |
| `src/main_yt.py` | Modifica — parsing + run_report + rendering compatto |
| `src/yt_pdf.py` | **Nuovo** — generazione PDF |
| `src/email_sender.py` | Modifica — send_digest con allegato opzionale |
| `templates/email_yt.html` | Modifica — layout compatto, placeholder rinominato |
| `requirements.txt` | Modifica — aggiunta `fpdf2` |
| `cache/yt_cache.json` | Reset — rimozione entry esistente |

---

## Non rientra nello scope

- Modifica ai workflow GitHub Actions (`.github/workflows/`)
- Nuovi GitHub Secrets
- Modifiche ai digest Engineer o Builder
- Generazione PDF per gli altri digest

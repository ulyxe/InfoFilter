import os
import json
from groq import Groq

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    return _client


def _parse_json(raw: str) -> dict:
    """Parse a model response into JSON, tolerating markdown code fences or
    surrounding prose by falling back to the outermost {...} object."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            return json.loads(raw[start:end + 1])
        raise


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
        return _parse_json(raw)
    except Exception as e:
        print(f"[WARN] Groq API error: {type(e).__name__}: {e}")
        return None

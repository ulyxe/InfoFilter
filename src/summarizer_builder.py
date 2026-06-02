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

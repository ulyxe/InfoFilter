"""Generate a PDF summary for the YouTube Digest."""
from __future__ import annotations

from fpdf import FPDF


def _safe(text: str) -> str:
    """Replace characters outside Latin-1 with '?' for Helvetica core font."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _stars(rating: int) -> str:
    if not rating:
        return "(n.d.)"
    return "*" * rating + f" ({rating}/5)"


def _section_header(pdf: FPDF, title: str) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(0, 6, text=title, new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_font("Helvetica", "", 10)


def _multi_cell(pdf: FPDF, h: float, text: str) -> None:
    """Call multi_cell after resetting x to left margin (fpdf2 leaves x at right edge)."""
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, h, text=text)


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
        _multi_cell(pdf, 7, _safe(f"#{i}  {e.get('title', '')}"))
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
            _multi_cell(pdf, 6, _safe(e["argomento"]))
            pdf.ln(2)

        # Punti chiave
        if e.get("punti"):
            _section_header(pdf, "PUNTI CHIAVE")
            for p in e["punti"]:
                _multi_cell(pdf, 6, _safe(f"- {p}"))
            pdf.ln(2)

        # Strumenti e tecnologie
        if e.get("strumenti"):
            _section_header(pdf, "STRUMENTI E TECNOLOGIE")
            _multi_cell(pdf, 6, _safe(", ".join(e["strumenti"])))
            pdf.ln(2)

        # Risorse consigliate
        if e.get("risorse"):
            _section_header(pdf, "RISORSE CONSIGLIATE")
            for r in e["risorse"]:
                _multi_cell(pdf, 6, _safe(f"- {r}"))
            pdf.ln(2)

        # Metodologia
        if e.get("metodologia"):
            _section_header(pdf, "METODOLOGIA")
            for j, step in enumerate(e["metodologia"], start=1):
                _multi_cell(pdf, 6, _safe(f"{j}. {step}"))
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
                _multi_cell(pdf, 6, _safe(r))
            pdf.ln(2)

        # Perché vale il tempo
        if e.get("perche"):
            pdf.set_font("Helvetica", "I", 10)
            _multi_cell(pdf, 6, _safe(f"Perche vale il tempo: {e['perche']}"))
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

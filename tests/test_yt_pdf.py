"""Tests for src/yt_pdf.py."""
from __future__ import annotations

import pytest
from yt_pdf import generate_digest_pdf


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

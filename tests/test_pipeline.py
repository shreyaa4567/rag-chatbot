"""Tests for chunking + deduplication (app/rag_pipeline.py)."""

from app.rag_pipeline import chunk_documents


def test_chunks_get_title_and_source_header():
    docs = ["Some reasonably sized body of text about cats and dogs."]
    meta = [{"title": "Pets", "source": "http://x.com/pets"}]
    chunks, metas = chunk_documents(docs, meta)
    assert len(chunks) == 1
    assert chunks[0].startswith("Page: Pets\nSource: http://x.com/pets")
    assert metas[0]["source"] == "http://x.com/pets"


def test_duplicate_chunks_are_removed():
    body = "The exact same paragraph repeated across pages."
    docs = [body, body, body]
    meta = [
        {"title": "P1", "source": "http://x.com/1"},
        {"title": "P2", "source": "http://x.com/2"},
        {"title": "P3", "source": "http://x.com/3"},
    ]
    chunks, metas = chunk_documents(docs, meta)
    # Identical bodies collapse to a single chunk despite different sources.
    assert len(chunks) == 1
    assert len(metas) == 1


def test_distinct_bodies_are_kept():
    docs = ["First distinct paragraph here.", "Second different paragraph here."]
    meta = [
        {"title": "A", "source": "http://x.com/a"},
        {"title": "B", "source": "http://x.com/b"},
    ]
    chunks, _ = chunk_documents(docs, meta)
    assert len(chunks) == 2

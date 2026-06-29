# app/rag_pipeline.py

import os
import json
import shutil
import logging
import ollama
import config
import chromadb

from collections import Counter
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Number of concurrent embedding requests sent to Ollama.
EMBED_WORKERS = 5

# Target maximum characters per chunk. Sections/paragraphs are packed up to
# this size; the chunker never splits mid-paragraph unless a single paragraph
# is itself larger than this.
CHUNK_MAX_CHARS = 1000

# A text block (paragraph/heading) appearing on at least this fraction of the
# crawled pages is treated as site-wide boilerplate (nav, footer, repeated
# notices) and removed before indexing.
BOILERPLATE_DOC_FRACTION = 0.4
BOILERPLATE_MIN_PAGES    = 5

# ─── EMBEDDING ────────────────────────────────────────────────────────────────

def get_embeddings_batch(texts):
    """Get embeddings for a batch of texts in parallel.

    Embedding calls are I/O-bound (HTTP requests to Ollama), so a thread
    pool lets several run concurrently. Order is preserved so embeddings
    line up with their source chunks.
    """
    with ThreadPoolExecutor(max_workers=EMBED_WORKERS) as executor:
        embeddings = list(executor.map(get_embedding, texts))
    return embeddings

def get_embedding(text):
    response = ollama.embeddings(
        model  = config.EMBED_MODEL,
        prompt = text
    )
    return response["embedding"]

# ─── LOAD DOCUMENTS ───────────────────────────────────────────────────────────

def load_documents():
    documents = []
    metadata  = []

    if not os.path.exists(config.METADATA_FILE):
        logger.warning("No metadata file at %s — nothing was crawled.",
                       config.METADATA_FILE)
        return documents, metadata

    with open(config.METADATA_FILE, "r", encoding="utf-8") as f:
        meta_list = json.load(f)

    file_to_url   = {entry["filename"]: entry["url"] for entry in meta_list}
    file_to_title = {entry["filename"]: entry.get("title", "No Title") for entry in meta_list}

    for filename in os.listdir(config.DATA_DIR):
        if not filename.endswith(".txt"):
            continue
        filepath = os.path.join(config.DATA_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read().strip()
        if not text:
            continue
        documents.append(text)
        metadata.append({
            "source"   : file_to_url.get(filename, "unknown"),
            "title"    : file_to_title.get(filename, "No Title"),
            "filename" : filename
        })

    documents = strip_cross_page_boilerplate(documents)

    logger.info("Loaded %d documents from %s/", len(documents), config.DATA_DIR)
    return documents, metadata


def strip_cross_page_boilerplate(documents):
    """Remove text blocks that repeat across many pages (site-wide template).

    Navigation, footers, accessibility widgets and repeated notices survive
    tag/class stripping and appear near-identically on most pages. Any block
    present on >= BOILERPLATE_DOC_FRACTION of pages (and on at least
    BOILERPLATE_MIN_PAGES pages) is treated as boilerplate and dropped, so it
    never gets embedded or crowds out real content in retrieval.
    """
    n = len(documents)
    if n < BOILERPLATE_MIN_PAGES:
        return documents

    doc_blocks = [
        [b.strip() for b in text.split("\n\n") if b.strip()]
        for text in documents
    ]

    # Document-frequency of each distinct block (count each page once).
    df = Counter()
    for blocks in doc_blocks:
        for block in set(blocks):
            df[block] += 1

    threshold = max(BOILERPLATE_MIN_PAGES, int(BOILERPLATE_DOC_FRACTION * n))
    common = {block for block, count in df.items() if count >= threshold}

    if not common:
        return documents

    cleaned = ["\n\n".join(b for b in blocks if b not in common)
               for blocks in doc_blocks]
    logger.info("Cross-page dedup: removed %d boilerplate block(s) "
                "appearing on >= %d/%d pages", len(common), threshold, n)
    return cleaned

# ─── CHUNK DOCUMENTS ──────────────────────────────────────────────────────────

def semantic_chunks(text, max_chars=CHUNK_MAX_CHARS):
    """Split one page's text into heading-aware, paragraph-respecting chunks.

    The crawler emits headings as Markdown lines ("## Title"). We group each
    heading with the paragraphs beneath it into a section, then pack those
    paragraphs into chunks up to `max_chars`, never cutting mid-paragraph
    (a single over-long paragraph is split on whitespace as a last resort).
    Each chunk is prefixed with its section heading so the embedded text
    carries the context of which section it came from.
    """
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]

    # Group blocks into (heading, [paragraphs]) sections.
    sections = []
    heading, paras = None, []
    for block in blocks:
        if block.startswith("#"):
            if heading is not None or paras:
                sections.append((heading, paras))
            heading, paras = block.lstrip("# ").strip(), []
        else:
            paras.append(block)
    if heading is not None or paras:
        sections.append((heading, paras))

    # A run of bare headings (heading with no body) is usually a link list —
    # e.g. the department or schools index. Dropping them loses real content,
    # so fold each run into a single list paragraph attached to the preceding
    # section (or kept standalone if there's nothing before it). Page-global
    # nav headings are already gone: they repeat across pages and were removed
    # by cross-page dedup before this point.
    grouped = []
    pending = []
    for head, paras in sections:
        if not paras:
            if head:
                pending.append(head)
            continue
        if pending:
            list_para = "; ".join(pending)
            if grouped:
                grouped[-1][1].append(list_para)
            else:
                grouped.append((None, [list_para]))
            pending = []
        grouped.append((head, list(paras)))
    if pending:
        list_para = "; ".join(pending)
        if grouped:
            grouped[-1][1].append(list_para)
        else:
            grouped.append((None, [list_para]))
    sections = grouped

    chunks = []
    for heading, paras in sections:
        if not paras:
            continue  # a bare heading with no body carries no information
        prefix = f"{heading}\n" if heading else ""
        buf = ""
        for para in paras:
            # Flush the buffer if appending this paragraph would overflow.
            if buf and len(prefix) + len(buf) + 1 + len(para) > max_chars:
                chunks.append(prefix + buf)
                buf = ""
            if len(prefix) + len(para) > max_chars:
                # Paragraph alone exceeds the budget: emit buffer, then split
                # the long paragraph on word boundaries.
                if buf:
                    chunks.append(prefix + buf)
                    buf = ""
                line = ""
                for word in para.split():
                    if line and len(prefix) + len(line) + 1 + len(word) > max_chars:
                        chunks.append(prefix + line)
                        line = word
                    else:
                        line = f"{line} {word}" if line else word
                if line:
                    buf = line
            else:
                buf = f"{buf}\n{para}" if buf else para
        if buf:
            chunks.append(prefix + buf)

    return [c.strip() for c in chunks if c.strip()]


def chunk_documents(documents, metadata):
    all_chunks   = []
    all_metadata = []
    seen_bodies  = set()
    duplicates   = 0

    for text, meta in zip(documents, metadata):
        # Prepend page title and source URL as context header for each chunk.
        # This helps the embedding model and LLM understand which page
        # and section each chunk belongs to.
        title  = meta.get("title", "No Title")
        source = meta.get("source", "unknown")
        header = f"Page: {title}\nSource: {source}\n\n"

        for chunk in semantic_chunks(text):
            # Deduplicate by chunk body (ignoring the header). Repeated content
            # across pages wastes embeddings and can crowd out the top-k.
            key = chunk.strip()
            if not key or key in seen_bodies:
                duplicates += 1
                continue
            seen_bodies.add(key)
            all_chunks.append(header + chunk)
            all_metadata.append(meta)

    logger.info("Split into %d unique chunks (%d duplicates removed)",
                len(all_chunks), duplicates)
    return all_chunks, all_metadata

# ─── BUILD VECTORSTORE ────────────────────────────────────────────────────────

def build_vectorstore(chunks, metadatas, progress_callback=None, batch_size=50):

    logger.info("Embedding %d chunks in batches of %d...", len(chunks), batch_size)

    client     = chromadb.PersistentClient(path=config.CHROMA_DIR)
    # Delete old collection if exists, create fresh one.
    try:
        client.delete_collection("rag_collection")
    except Exception:
        pass
    # Use cosine distance: nomic-embed vectors are unnormalized, so the
    # default L2 metric yields distances in the hundreds, making a sane
    # relevance threshold impossible. Cosine distance is bounded to [0, 2].
    collection = client.create_collection(
        "rag_collection",
        metadata={"hnsw:space": "cosine"},
    )

    total = len(chunks)

    for i in range(0, total, batch_size):
        batch_chunks = chunks[i:i + batch_size]
        batch_metas  = metadatas[i:i + batch_size]
        batch_ids    = [str(j) for j in range(i, i + len(batch_chunks))]

        embeddings = get_embeddings_batch(batch_chunks)

        collection.add(
            ids        = batch_ids,
            embeddings = embeddings,
            documents  = batch_chunks,
            metadatas  = batch_metas
        )

        done = min(i + batch_size, total)
        logger.info("Embedded %d/%d chunks...", done, total)

        if progress_callback:
            progress_callback(done, total)

    logger.info("Vectorstore built and saved to %s/", config.CHROMA_DIR)
    return collection

# ─── LOAD VECTORSTORE ─────────────────────────────────────────────────────────

def load_vectorstore():
    client = chromadb.PersistentClient(path=config.CHROMA_DIR)
    return client.get_collection("rag_collection")

# ─── SEARCH ───────────────────────────────────────────────────────────────────

def search(query, collection, k=None, max_distance=None):
    """Search for relevant chunks with distance-based quality filtering.

    Args:
        query: The search query text.
        collection: ChromaDB collection to search.
        k: Number of candidate results to retrieve (default config.RETRIEVAL_K).
        max_distance: Maximum cosine distance — chunks above this are filtered
                      out as irrelevant (default config.MAX_DISTANCE, [0, 2]).

    Returns:
        ChromaDB-style results dict with 'documents', 'metadatas',
        'distances' lists, filtered to only include relevant results.
    """
    if k is None:
        k = config.RETRIEVAL_K
    if max_distance is None:
        max_distance = config.MAX_DISTANCE

    query_embedding = get_embedding(query)
    results = collection.query(
        query_embeddings = [query_embedding],
        n_results        = k,
        include          = ["documents", "metadatas", "distances"]
    )

    # Filter out low-relevance results by distance threshold
    if results["distances"] and results["distances"][0]:
        filtered_docs  = []
        filtered_metas = []
        filtered_dists = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            if dist <= max_distance:
                filtered_docs.append(doc)
                filtered_metas.append(meta)
                filtered_dists.append(dist)

        results["documents"] = [filtered_docs]
        results["metadatas"] = [filtered_metas]
        results["distances"] = [filtered_dists]

    return results

# ─── RUN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting RAG pipeline...")
    documents, metadata = load_documents()
    chunks, chunk_meta  = chunk_documents(documents, metadata)
    collection          = build_vectorstore(chunks, chunk_meta)
    logger.info("RAG pipeline complete.")
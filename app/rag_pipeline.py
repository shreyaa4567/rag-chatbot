# app/rag_pipeline.py

import os
import json
import shutil
import logging
import ollama
import config
import chromadb

from concurrent.futures import ThreadPoolExecutor
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# Number of concurrent embedding requests sent to Ollama.
EMBED_WORKERS = 5

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

    logger.info("Loaded %d documents from %s/", len(documents), config.DATA_DIR)
    return documents, metadata

# ─── CHUNK DOCUMENTS ──────────────────────────────────────────────────────────

def chunk_documents(documents, metadata):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size    = 1000,
        chunk_overlap = 150,
    )
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

        chunks = splitter.split_text(text)
        for chunk in chunks:
            # Deduplicate by chunk body (ignoring the header). The same quote
            # or paragraph often repeats across paginated/tag pages; identical
            # chunks waste embeddings and can crowd out the top-k results.
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
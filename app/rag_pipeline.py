# app/rag_pipeline.py

import os
import json
import shutil
import ollama
import config
import chromadb

from langchain_text_splitters import RecursiveCharacterTextSplitter

# ─── EMBEDDING ────────────────────────────────────────────────────────────────

def get_embeddings_batch(texts):
    """Get embeddings for a batch of texts."""
    embeddings = []
    for text in texts:
        response = ollama.embeddings(
            model  = config.EMBED_MODEL,
            prompt = text
        )
        embeddings.append(response["embedding"])
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

    print(f" Loaded {len(documents)} documents from {config.DATA_DIR}/")
    return documents, metadata

# ─── CHUNK DOCUMENTS ──────────────────────────────────────────────────────────

def chunk_documents(documents, metadata):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size    = 1000,
        chunk_overlap = 200,
    )
    all_chunks   = []
    all_metadata = []

    for text, meta in zip(documents, metadata):
        # Prepend page title and source URL as context header for each chunk.
        # This helps the embedding model and LLM understand which page
        # and section each chunk belongs to.
        title  = meta.get("title", "No Title")
        source = meta.get("source", "unknown")
        header = f"Page: {title}\nSource: {source}\n\n"

        chunks = splitter.split_text(text)
        for chunk in chunks:
            all_chunks.append(header + chunk)
            all_metadata.append(meta)

    print(f" Split into {len(all_chunks)} chunks")
    return all_chunks, all_metadata

# ─── BUILD VECTORSTORE ────────────────────────────────────────────────────────

def build_vectorstore(chunks, metadatas, progress_callback=None, batch_size=50):

    print(f" Embedding {len(chunks)} chunks in batches of {batch_size}...")

    client     = chromadb.PersistentClient(path=config.CHROMA_DIR)
    # Delete old collection if exists, create fresh one
    try:
        client.delete_collection("rag_collection")
    except:
        pass
    collection = client.create_collection("rag_collection")

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
        print(f"   Embedded {done}/{total} chunks...")

        if progress_callback:
            progress_callback(done, total)

    print(f" Vectorstore built and saved to {config.CHROMA_DIR}/")
    return collection

# ─── LOAD VECTORSTORE ─────────────────────────────────────────────────────────

def load_vectorstore():
    client = chromadb.PersistentClient(path=config.CHROMA_DIR)
    return client.get_collection("rag_collection")

# ─── SEARCH ───────────────────────────────────────────────────────────────────

def search(query, collection, k=6, max_distance=1.5):
    """Search for relevant chunks with distance-based quality filtering.

    Args:
        query: The search query text.
        collection: ChromaDB collection to search.
        k: Number of candidate results to retrieve (default 6).
        max_distance: Maximum distance threshold — chunks with distance
                      above this are filtered out as irrelevant (default 1.5).

    Returns:
        ChromaDB-style results dict with 'documents', 'metadatas',
        'distances' lists, filtered to only include relevant results.
    """
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
    print("\n Starting RAG pipeline...\n")
    documents, metadata = load_documents()
    chunks, chunk_meta  = chunk_documents(documents, metadata)
    collection          = build_vectorstore(chunks, chunk_meta)
    print(" RAG pipeline complete.\n")
# app/rag_pipeline.py

import os
import json
import shutil
import ollama
import config
import chromadb

from langchain_text_splitters import RecursiveCharacterTextSplitter

# ─── DIRECT OLLAMA EMBEDDING (bypasses LangChain ollama issues) ───────────────

def get_embedding(text):
    """Get embedding for a single text using ollama directly."""
    response = ollama.embeddings(
        model  = config.EMBED_MODEL,
        prompt = text
    )
    return response["embedding"]

# ─── STEP 1: LOAD ALL TEXT FILES ──────────────────────────────────────────────

def load_documents():
    documents = []
    metadata  = []

    with open(config.METADATA_FILE, "r", encoding="utf-8") as f:
        meta_list = json.load(f)

    file_to_url = {entry["filename"]: entry["url"] for entry in meta_list}

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
            "filename" : filename
        })

    print(f" Loaded {len(documents)} documents from {config.DATA_DIR}/")
    return documents, metadata

# ─── STEP 2: SPLIT INTO CHUNKS ────────────────────────────────────────────────

def chunk_documents(documents, metadata):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size    = 1000,
        chunk_overlap = 100,
    )
    all_chunks   = []
    all_metadata = []

    for text, meta in zip(documents, metadata):
        chunks = splitter.split_text(text)
        for chunk in chunks:
            all_chunks.append(chunk)
            all_metadata.append(meta)

    print(f" Split into {len(all_chunks)} chunks")
    return all_chunks, all_metadata

# ─── STEP 3: EMBED AND STORE IN CHROMADB ──────────────────────────────────────

def build_vectorstore(chunks, metadatas):
    if os.path.exists(config.CHROMA_DIR):
        shutil.rmtree(config.CHROMA_DIR)
        print(f" Cleared old ChromaDB at {config.CHROMA_DIR}/")

    print(f" Embedding {len(chunks)} chunks — this may take 2-5 minutes...")

    client     = chromadb.PersistentClient(path=config.CHROMA_DIR)
    collection = client.get_or_create_collection("rag_collection")

    for i, (chunk, meta) in enumerate(zip(chunks, metadatas)):
        embedding = get_embedding(chunk)
        collection.add(
            ids        = [str(i)],
            embeddings = [embedding],
            documents  = [chunk],
            metadatas  = [meta]
        )
        if (i + 1) % 50 == 0:
            print(f"   Embedded {i + 1}/{len(chunks)} chunks...")

    print(f" Vectorstore built and saved to {config.CHROMA_DIR}/")
    return collection

# ─── STEP 4: LOAD EXISTING VECTORSTORE ────────────────────────────────────────

def load_vectorstore():
    client = chromadb.PersistentClient(path=config.CHROMA_DIR)
    return client.get_collection("rag_collection")

# ─── STEP 5: SEARCH ───────────────────────────────────────────────────────────

def search(query, collection, k=3):
    query_embedding = get_embedding(query)
    results = collection.query(
        query_embeddings = [query_embedding],
        n_results        = k
    )
    return results

# ─── RUN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n Starting RAG pipeline...\n")

    documents, metadata = load_documents()
    chunks, chunk_meta  = chunk_documents(documents, metadata)
    collection          = build_vectorstore(chunks, chunk_meta)

    print("\n Testing search...")
    results = search("What did Einstein say about imagination?", collection)

    docs      = results["documents"][0]
    metadatas = results["metadatas"][0]

    print(f"\n Top {len(docs)} results:\n")
    for i, (doc, meta) in enumerate(zip(docs, metadatas)):
        print(f"--- Result {i+1} ---")
        print(f"Source : {meta.get('source', 'unknown')}")
        print(f"Content: {doc[:200]}")
        print()

    print(" RAG pipeline complete. ChromaDB is ready.\n")
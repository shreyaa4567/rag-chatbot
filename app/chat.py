# app/chat.py

import ollama
import config
from app.rag_pipeline import load_vectorstore, search

# ─── STATE ────────────────────────────────────────────────────────────────────

collection = None
_model_warmed_up = False

# ─── INITIALIZATION (called explicitly, not at import time) ───────────────────

def init():
    """Initialize vectorstore and warm up model. Safe to call if DB doesn't exist yet."""
    global collection, _model_warmed_up

    # Load vectorstore if it exists
    try:
        print("\n Loading ChromaDB vectorstore...")
        collection = load_vectorstore()
        print(" Vectorstore loaded.")
    except Exception as e:
        print(f" ChromaDB not available yet: {e}")
        collection = None

    # Warm up model (always useful — do once)
    if not _model_warmed_up:
        try:
            print(f" Warming up {config.LLM_MODEL}...")
            ollama.chat(
                model    = config.LLM_MODEL,
                messages = [{"role": "user", "content": "hi"}],
                options  = {"num_predict": 1}
            )
            print(f" Model ready.")
            _model_warmed_up = True
        except Exception as e:
            print(f" Model warmup failed: {e}")

# ─── RELOAD COLLECTION (called after new website is loaded) ───────────────────

def reload_collection():
    global collection
    print("\n Reloading ChromaDB collection...")
    collection = load_vectorstore()
    print(" Collection reloaded.")

# ─── READINESS CHECK ──────────────────────────────────────────────────────────

def is_ready():
    """Check if the chat system is ready to answer questions."""
    return collection is not None

# ─── PROMPT BUILDER ───────────────────────────────────────────────────────────

def build_prompt(question, results):
    docs    = results["documents"][0]
    context = "\n\n".join(docs)

    prompt = f"""You are a helpful assistant. Answer based ONLY on the website content below.
If the answer is not found, say: "I don't have enough information from this website to answer that."

Website Content:
{context}

Question: {question}
Answer:"""
    return prompt

# ─── MAIN CHAT FUNCTION ───────────────────────────────────────────────────────

def chat(question):
    if collection is None:
        raise RuntimeError("No website loaded yet. Please load a website first.")

    results = search(question, collection, k=6)

    # Handle case where all results were filtered out by distance threshold
    if not results["documents"][0]:
        return "I don't have enough information from this website to answer that.", []

    prompt  = build_prompt(question, results)

    response = ollama.chat(
        model    = config.LLM_MODEL,
        messages = [{"role": "user", "content": prompt}],
        options  = {
            "num_predict" : 300,
            "temperature" : 0.1,
        }
    )

    answer  = response["message"]["content"]
    sources = list(set([
        m.get("source", "unknown")
        for m in results["metadatas"][0]
    ]))

    return answer, sources
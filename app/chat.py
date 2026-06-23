# app/chat.py

import logging
import ollama
import config
from app.rag_pipeline import load_vectorstore, search

logger = logging.getLogger(__name__)

# ─── STATE ────────────────────────────────────────────────────────────────────

collection = None
_model_warmed_up = False

# ─── INITIALIZATION (called explicitly, not at import time) ───────────────────

def init():
    """Initialize vectorstore and warm up model. Safe to call if DB doesn't exist yet."""
    global collection, _model_warmed_up

    # Load vectorstore if it exists
    try:
        logger.info("Loading ChromaDB vectorstore...")
        collection = load_vectorstore()
        logger.info("Vectorstore loaded.")
    except Exception as e:
        logger.warning("ChromaDB not available yet: %s", e)
        collection = None

    # Warm up model (always useful — do once)
    if not _model_warmed_up:
        try:
            logger.info("Warming up %s...", config.LLM_MODEL)
            ollama.chat(
                model    = config.LLM_MODEL,
                messages = [{"role": "user", "content": "hi"}],
                options  = {"num_predict": 1}
            )
            logger.info("Model ready.")
            _model_warmed_up = True
        except Exception as e:
            logger.warning("Model warmup failed: %s", e)

# ─── RELOAD COLLECTION (called after new website is loaded) ───────────────────

def reload_collection():
    global collection
    logger.info("Reloading ChromaDB collection...")
    collection = load_vectorstore()
    logger.info("Collection reloaded.")

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

    results = search(question, collection, k=5)

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
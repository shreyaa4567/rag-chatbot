# app/api.py

import os
import shutil
import threading
import config

from flask import Flask, request, jsonify
from flask_cors import CORS
from app.chat import chat, reload_collection, init as init_chat, is_ready

# ─── FLASK SETUP ──────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

# ─── THREAD-SAFE PROGRESS TRACKING ───────────────────────────────────────────

_progress_lock = threading.Lock()
_pipeline_lock = threading.Lock()

_progress = {
    "status"   : "idle",      # idle | crawling | embedding | ready | error
    "percent"  : 0,
    "message"  : "",
    "url"      : ""
}

def get_progress_snapshot():
    """Return a thread-safe copy of the current progress."""
    with _progress_lock:
        return dict(_progress)

def set_progress(**kwargs):
    """Thread-safe update of progress fields."""
    with _progress_lock:
        _progress.update(kwargs)

# ─── INITIALIZE CHAT (safe — won't crash if DB doesn't exist) ────────────────

init_chat()

# If vectorstore was loaded successfully, mark as ready
if is_ready():
    set_progress(status="ready", percent=100, message="Ready! Ask your questions.")

# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "running", "message": "RAG Chatbot API is live."})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status"      : "ok",
        "llm_model"   : config.LLM_MODEL,
        "embed_model" : config.EMBED_MODEL,
    })


@app.route("/progress", methods=["GET"])
def progress_endpoint():
    return jsonify(get_progress_snapshot())


@app.route("/load", methods=["POST"])
def load_website():
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "Missing 'url' in request body"}), 400

    url = data["url"].strip()
    if not url.startswith("http"):
        return jsonify({"error": "Invalid URL. Must start with http or https"}), 400

    # Prevent concurrent pipeline runs
    if not _pipeline_lock.acquire(blocking=False):
        return jsonify({"error": "A pipeline is already running. Please wait."}), 409

    # Start crawl+embed in background thread
    thread = threading.Thread(target=run_pipeline, args=(url,))
    thread.daemon = True
    thread.start()

    return jsonify({"message": "Pipeline started", "url": url})


@app.route("/chat", methods=["POST"])
def chat_endpoint():
    if not is_ready():
        return jsonify({"error": "Website not loaded yet. Please load a website first."}), 400

    data = request.get_json()
    if not data or "question" not in data:
        return jsonify({"error": "Missing 'question' in request body"}), 400

    question = data["question"].strip()
    if not question:
        return jsonify({"error": "Question cannot be empty"}), 400

    try:
        answer, sources = chat(question)
        return jsonify({"answer": answer, "sources": sources})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── BACKGROUND PIPELINE ──────────────────────────────────────────────────────

def run_pipeline(url):
    try:
        # ── Step 1: Clear old data ──
        set_progress(status="crawling", percent=0, message="Clearing old data...", url=url)
        config.TARGET_URL = url

        # Close ChromaDB before deleting
        import app.chat as chat_module
        chat_module.collection = None

        import gc
        gc.collect()

        import time
        time.sleep(1)

        for folder in [config.DATA_DIR, config.LOG_DIR]:
           if os.path.exists(folder):
             shutil.rmtree(folder)
           os.makedirs(folder)

        if not os.path.exists(config.CHROMA_DIR):
           os.makedirs(config.CHROMA_DIR)

        # ── Step 2: Crawl ──
        set_progress(percent=5, message="Crawling website...")
        from app.crawler import crawl
        crawl(url, progress_callback=update_crawl_progress)

        # ── Step 3: Embed ──
        set_progress(status="embedding", percent=50, message="Building knowledge base...")
        from app.rag_pipeline import load_documents, chunk_documents, build_vectorstore
        documents, metadata = load_documents()
        chunks, chunk_meta  = chunk_documents(documents, metadata)
        build_vectorstore(chunks, chunk_meta, progress_callback=update_embed_progress)

        # ── Step 4: Reload ──
        set_progress(percent=95, message="Loading into memory...")
        chat_module.reload_collection()

        set_progress(status="ready", percent=100, message="Ready! Ask your questions.")

    except Exception as e:
        set_progress(status="error", percent=0, message=f"Error: {str(e)}")
    finally:
        _pipeline_lock.release()


def update_crawl_progress(pages_done, max_pages):
    percent = 5 + int((pages_done / max_pages) * 45)
    set_progress(
        percent = percent,
        message = f"Crawling... {pages_done}/{max_pages} pages done"
    )


def update_embed_progress(chunks_done, total_chunks):
    percent = 50 + int((chunks_done / total_chunks) * 45)
    set_progress(
        percent = percent,
        message = f"Embedding... {chunks_done}/{total_chunks} chunks done"
    )


# ─── RUN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
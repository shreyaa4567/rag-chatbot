# app/api.py

import config
from flask import Flask, request, jsonify
from flask_cors import CORS
from app.chat import chat

# ─── FLASK SETUP ──────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status"  : "running",
        "message" : "RAG Chatbot API is live."
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status"      : "ok",
        "llm_model"   : config.LLM_MODEL,
        "embed_model" : config.EMBED_MODEL,
        "target_url"  : config.TARGET_URL
    })


@app.route("/chat", methods=["POST"])
def chat_endpoint():
    data = request.get_json()

    if not data or "question" not in data:
        return jsonify({"error": "Missing 'question' in request body"}), 400

    question = data["question"].strip()

    if not question:
        return jsonify({"error": "Question cannot be empty"}), 400

    try:
        answer, sources = chat(question)
        return jsonify({
            "answer"  : answer,
            "sources" : sources
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── RUN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(
        host  = "0.0.0.0",
        port  = 5000,
        debug = False
    )
# app/chat.py

import ollama
import config
from app.rag_pipeline import load_vectorstore, search

# ─── LOAD VECTORSTORE ─────────────────────────────────────────────────────────

print("\n Loading ChromaDB vectorstore...")
collection = load_vectorstore()
print(" Vectorstore loaded.")

# ─── WARM UP MODEL ────────────────────────────────────────────────────────────

print(f" Warming up {config.LLM_MODEL}...")
ollama.chat(
    model    = config.LLM_MODEL,
    messages = [{"role": "user", "content": "hi"}],
    options  = {"num_predict": 1}
)
print(f" Model ready.")

# ─── RELOAD COLLECTION (called after new website is loaded) ───────────────────

def reload_collection():
    global collection
    print("\n Reloading ChromaDB collection...")
    collection = load_vectorstore()
    print(" Collection reloaded.")

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
    results = search(question, collection, k=3)
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
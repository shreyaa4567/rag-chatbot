# app/chat.py

import ollama
import config
from app.rag_pipeline import load_vectorstore, search

# ─── LOAD VECTORSTORE ─────────────────────────────────────────────────────────

print("\n Loading ChromaDB vectorstore...")
collection = load_vectorstore()
print(" Vectorstore loaded.")

# ─── PROMPT BUILDER ───────────────────────────────────────────────────────────

def build_prompt(question, results):
    docs    = results["documents"][0]
    context = "\n\n".join(docs)

    prompt = f"""You are a helpful assistant that answers questions strictly based on the website content provided below.

If the answer is not found in the content, say: "I don't have enough information from this website to answer that."

Website Content:
{context}

Question: {question}

Answer:"""
    return prompt

# ─── MAIN CHAT FUNCTION ───────────────────────────────────────────────────────

def chat(question):
    results = search(question, collection, k=8)

    prompt = build_prompt(question, results)

    response = ollama.chat(
        model    = config.LLM_MODEL,
        messages = [{"role": "user", "content": prompt}]
    )

    answer  = response["message"]["content"]
    sources = list(set([
        m.get("source", "unknown")
        for m in results["metadatas"][0]
    ]))

    return answer, sources

# ─── TERMINAL CHAT LOOP ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print(" RAG Chatbot ready. Type your question below.")
    print(" Type 'exit' to quit.\n")

    while True:
        question = input("You: ").strip()
        if not question:
            continue
        if question.lower() == "exit":
            print("Goodbye!")
            break

        print("\n Searching and generating answer...\n")
        answer, sources = chat(question)

        print(f"Bot: {answer}")
        print(f"\nSources:")
        for s in sources:
            print(f"  - {s}")
        print()
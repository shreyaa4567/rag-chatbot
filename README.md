# RAG Chatbot — Website-Aware Question Answering System

A Retrieval-Augmented Generation (RAG) chatbot that crawls any website and answers questions based solely on its content. Built with Ollama, Gemma3, ChromaDB, Flask, and ASP.NET.

---

## What It Does

```
Any Website URL
      ↓
Crawler reads all pages
      ↓
Text split into chunks
      ↓
Embeddings created (nomic-embed-text)
      ↓
Stored in ChromaDB
      ↓
User asks a question (ASPX frontend)
      ↓
Relevant chunks retrieved via semantic search
      ↓
Gemma3:4b generates answer
      ↓
Answer + Source URLs shown to user
```

---

## Tech Stack

| Component     | Technology                          |
|---------------|-------------------------------------|
| LLM           | Gemma3:4b via Ollama                |
| Embeddings    | nomic-embed-text via Ollama         |
| Vector Store  | ChromaDB                            |
| Web Crawler   | BeautifulSoup + requests + tldextract |
| API           | Flask + flask-cors                  |
| Frontend      | ASP.NET WebForms (ASPX)             |

---

## Project Structure

```
rag_chatbot/
│
├── app/
│   ├── crawler.py        # Crawls website, saves text files
│   ├── rag_pipeline.py   # Chunks text, builds embeddings, stores in ChromaDB
│   ├── chat.py           # Handles question → search → answer generation
│   └── api.py            # Flask REST API (/chat, /health)
│
├── data/                 # Crawled text files saved here
├── chroma_db/            # ChromaDB vector store
├── logs/                 # Visited URLs and error logs
│
├── config.py             # All settings (URL, models, paths)
├── requirements.txt      # Python dependencies
└── venv/                 # Virtual environment
```

---

## Features

- **Web Crawler** — Crawls internal pages of any website, skips PDFs/images
- **Smart Chunking** — Splits pages into 1000-char chunks with overlap
- **Semantic Search** — Finds most relevant chunks for any question
- **Hallucination Guard** — Says "I don't have enough information" if answer not found in website
- **Source Attribution** — Shows which URL the answer came from
- **Fast Responses** — Model warmup at startup, optimized chunk retrieval
- **CORS Enabled** — Frontend and backend can run on different ports
- **REST API** — Clean `/chat` and `/health` endpoints

---

## Setup & Usage

### Prerequisites
- Python 3.10+
- [Ollama](https://ollama.com/) installed
- ASP.NET / Visual Studio (for frontend)

### Install Ollama Models
```bash
ollama pull gemma3:4b
ollama pull nomic-embed-text
```

### Install Python Dependencies
```bash
cd rag_chatbot
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Configure Target Website
Edit `config.py`:
```python
TARGET_URL = "https://your-target-website.com/"
MAX_PAGES  = 50
LLM_MODEL  = "gemma3:4b"
```

### Run the Pipeline
```bash
# Step 1: Crawl the website
python -m app.crawler

# Step 2: Build embeddings
python -m app.rag_pipeline

# Step 3: Start Flask API
python -m app.api
```

### Run the Frontend
Open the ASP.NET project in Visual Studio and press **F5**.

---

## API Endpoints

| Method | Endpoint  | Description              |
|--------|-----------|--------------------------|
| GET    | /         | API status               |
| GET    | /health   | Health check + model info |
| POST   | /chat     | Ask a question           |

### Example Request
```json
POST /chat
{
  "question": "What is IIT Delhi known for?"
}
```

### Example Response
```json
{
  "answer": "IIT Delhi is known for...",
  "sources": ["https://home.iitd.ac.in/about.php"]
}
```

---

## Performance

| Metric         | Before Optimization | After Optimization |
|----------------|--------------------|--------------------|
| Response time  | 2 min 35 sec       | ~13 seconds        |
| Chunks         | 26,844             | 2,724              |
| Model          | qwen3:8b (5.2 GB)  | gemma3:4b (3.3 GB) |
| Speed gain     | —                  | **12x faster**     |

---

## Tested On

| Website                  | Result |
|--------------------------|--------|
| quotes.toscrape.com      | ✅ Working |
| home.iitd.ac.in          | ✅ Working |

---

## Upcoming Features

- Dynamic URL input from frontend (no re-crawl needed manually)
- GPU acceleration for even faster responses
- UI polish with loading spinner and response time display
- IIS deployment for production
- Support for IOCL Barauni and other industrial websites

---

## Author

Shreya — B.Tech Project, 2026

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
| Prod Server   | Waitress (WSGI)                     |
| Config        | python-dotenv (`.env`)              |
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
│   └── api.py            # Flask REST API (/load, /progress, /chat, /health)
│
├── data/                 # Crawled text files saved here (generated)
├── chroma_db/            # ChromaDB vector store
├── logs/                 # app.log, visited URLs, and error logs
│
├── config.py             # All settings, loaded from .env with defaults
├── .env.example          # Sample environment configuration
├── requirements.txt      # Python dependencies
└── venv/                 # Virtual environment
```

---

## Features

- **Dynamic URL Loading** — Enter any URL in the frontend; the backend crawls + embeds it on the fly with live progress (no manual re-crawl)
- **Web Crawler** — Crawls internal pages of any website, skips PDFs/images, MD5-hashed filenames to prevent collisions
- **Smart Chunking** — Splits pages into 1000-char chunks (150 overlap), with page title/URL prepended for context
- **Semantic Search** — Retrieves top-k relevant chunks with a distance threshold to filter out low-relevance matches
- **Hallucination Guard** — Says "I don't have enough information" if answer not found in website
- **Source Attribution** — Shows which URL the answer came from
- **Fast Responses** — Model warmup at startup, parallelized embeddings, optimized chunk retrieval
- **Security Hardening** — SSRF protection (blocks private/internal IPs) and CORS restricted to the frontend origin
- **Configurable** — All settings via `.env` (python-dotenv); structured `logging` to console + rotating file
- **Production-Ready** — Optional Waitress WSGI server (Windows-friendly)
- **REST API** — Clean `/load`, `/progress`, `/chat`, and `/health` endpoints

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

### Configure via `.env`
Copy the sample and adjust as needed (real environment variables override these):
```bash
cp .env.example .env
```
Key settings:
```ini
MAX_PAGES=50
LLM_MODEL=gemma3:4b
EMBED_MODEL=nomic-embed-text
FRONTEND_ORIGIN=http://localhost:44300   # ASPX site origin (for CORS)
USE_WAITRESS=false                       # true = production WSGI server
LOG_LEVEL=INFO
```
> All values have sensible defaults in `config.py`, so a `.env` is optional for local use. Be sure `FRONTEND_ORIGIN` matches the origin your ASPX site is served from, or CORS will block the browser.

### Start the API
```bash
# Dev server (Flask)
python -m app.api

# Production server (Waitress) — set USE_WAITRESS=true in .env, then:
python -m app.api
```

### Load a Website
There's no manual crawl step — start the API, open the frontend, paste a URL, and click **Load Website**. The backend crawls + embeds it and streams progress back to the UI. Then ask your questions.

> The standalone `python -m app.crawler` / `python -m app.rag_pipeline` entry points still exist for offline/debug runs.

### Run the Frontend
Open the ASP.NET project in Visual Studio and press **F5**. The API endpoint is set via the `API_URL` constant at the top of the script in `Default.aspx`.

---

## API Endpoints

| Method | Endpoint   | Description                                  |
|--------|------------|----------------------------------------------|
| GET    | /          | API status                                   |
| GET    | /health    | Health check + model info                    |
| POST   | /load      | Crawl + embed a website (`{"url": "..."}`); SSRF-guarded |
| GET    | /progress  | Current pipeline status/percent for the UI   |
| POST   | /chat      | Ask a question                               |

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

- GPU acceleration for even faster responses
- Response time display in the UI
- IIS deployment for production
- Support for IOCL Barauni and other industrial websites

---

## Author

Shreya — B.Tech Project, 2026

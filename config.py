# config.py

# ─── TARGET WEBSITE ───────────────────────────────────────────────────────────
TARGET_URL = "https://home.iitd.ac.in/"

# ─── CRAWLER SETTINGS ─────────────────────────────────────────────────────────
MAX_PAGES        = 50
DELAY_SECONDS    = 1.0
REQUEST_TIMEOUT  = 10

# ─── OLLAMA MODELS ────────────────────────────────────────────────────────────
LLM_MODEL = "gemma3:4b"
EMBED_MODEL      = "nomic-embed-text"
OLLAMA_HOST      = "http://127.0.0.1:11434"

# ─── FOLDER PATHS ─────────────────────────────────────────────────────────────
DATA_DIR         = "data"
CHROMA_DIR       = "chroma_db"
LOG_DIR          = "logs"

# ─── FILE PATHS ───────────────────────────────────────────────────────────────
VISITED_LOG      = "logs/visited_urls.txt"
ERROR_LOG        = "logs/errors.txt"
METADATA_FILE    = "data/metadata.json"
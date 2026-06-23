# config.py

import os
import logging
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

# ─── LOAD .env ────────────────────────────────────────────────────────────────
# Reads key=value pairs from a local .env file (if present) into the
# environment. Real environment variables always take precedence.
load_dotenv()


def _get_bool(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_int(name, default):
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _get_float(name, default):
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


# ─── TARGET WEBSITE ───────────────────────────────────────────────────────────
TARGET_URL = os.getenv("TARGET_URL", "https://home.iitd.ac.in/")

# ─── CRAWLER SETTINGS ─────────────────────────────────────────────────────────
MAX_PAGES        = _get_int("MAX_PAGES", 50)
DELAY_SECONDS    = _get_float("DELAY_SECONDS", 1.0)
REQUEST_TIMEOUT  = _get_int("REQUEST_TIMEOUT", 10)

# ─── RETRIEVAL SETTINGS ───────────────────────────────────────────────────────
# Number of chunks to retrieve per query. 8 gives better recall than 5 when
# semantically-similar-but-unhelpful pages (e.g. author bios) crowd the top
# results, while staying small enough for the local LLM's context window.
RETRIEVAL_K      = _get_int("RETRIEVAL_K", 8)
# Max cosine distance (0=identical, 2=opposite) for a chunk to be considered
# relevant. The collection uses cosine space, so this is in the [0, 2] range.
MAX_DISTANCE     = _get_float("MAX_DISTANCE", 1.0)

# ─── OLLAMA MODELS ────────────────────────────────────────────────────────────
LLM_MODEL        = os.getenv("LLM_MODEL", "gemma3:4b")
EMBED_MODEL      = os.getenv("EMBED_MODEL", "nomic-embed-text")
OLLAMA_HOST      = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

# ─── FOLDER PATHS ─────────────────────────────────────────────────────────────
DATA_DIR         = os.getenv("DATA_DIR", "data")
CHROMA_DIR       = os.getenv("CHROMA_DIR", "chroma_db")
LOG_DIR          = os.getenv("LOG_DIR", "logs")

# ─── FILE PATHS ───────────────────────────────────────────────────────────────
VISITED_LOG      = os.path.join(LOG_DIR, "visited_urls.txt")
ERROR_LOG        = os.path.join(LOG_DIR, "errors.txt")
METADATA_FILE    = os.path.join(DATA_DIR, "metadata.json")

# ─── SERVER / SECURITY SETTINGS ───────────────────────────────────────────────
# Origin allowed to call the API via CORS (the ASP.NET WebForms frontend).
FRONTEND_ORIGIN  = os.getenv("FRONTEND_ORIGIN", "http://localhost:44300")
HOST             = os.getenv("HOST", "0.0.0.0")
PORT             = _get_int("PORT", 5000)
DEBUG            = _get_bool("DEBUG", False)

# ─── LOGGING ──────────────────────────────────────────────────────────────────
LOG_LEVEL        = os.getenv("LOG_LEVEL", "INFO").upper()

_logging_configured = False


def setup_logging():
    """Configure root logging once: console + rotating file handler.

    Idempotent — safe to call from multiple entry points (api, crawler,
    rag_pipeline). Uses LOG_LEVEL from the environment/.env.
    """
    global _logging_configured
    if _logging_configured:
        return

    os.makedirs(LOG_DIR, exist_ok=True)

    level     = getattr(logging, LOG_LEVEL, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on reload
    if not root.handlers:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)

        file_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "app.log"),
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _logging_configured = True


# Configure logging at import so every module that imports config gets it.
setup_logging()

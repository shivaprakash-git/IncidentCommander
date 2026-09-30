"""Paths and environment. Secrets come from .env only (never hardcoded)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_FILE = Path(os.getenv("SUMLOG_FILE", ROOT / "data" / "sumlog_export.txt"))
DB_PATH = Path(os.getenv("EVENTS_DB", ROOT / "events.db"))
CACHE_DIR = ROOT / "cache"

NVIDIA_CHAT_API_KEY = os.getenv("NVIDIA_CHAT_API_KEY", "")
NVIDIA_EMBED_API_KEY = os.getenv("NVIDIA_EMBED_API_KEY", "")

import os
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).resolve().parents[1]
env_path = project_root / ".env"

load_dotenv(env_path)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.2:latest")
REQUEST_LOG_PATH = os.getenv("REQUEST_LOG_PATH", "logs/requests.jsonl")
CORRECTIONS_LOG_PATH = os.getenv("CORRECTIONS_LOG_PATH", "logs/corrections.jsonl")
RESOLUTIONS_LOG_PATH = os.getenv("RESOLUTIONS_LOG_PATH", "logs/resolutions.jsonl")
ROUTER_PROVIDER = os.getenv("ROUTER_PROVIDER", "groq").strip().lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
SLA_HOURS = {
    "High": int(os.getenv("SLA_HIGH_HOURS", "2")),
    "Medium": int(os.getenv("SLA_MEDIUM_HOURS", "8")),
    "Low": int(os.getenv("SLA_LOW_HOURS", "48")),
}
DUPLICATE_LOOKBACK_HOURS = int(os.getenv("DUPLICATE_LOOKBACK_HOURS", "24"))
DUPLICATE_SIMILARITY_THRESHOLD = float(os.getenv("DUPLICATE_SIMILARITY_THRESHOLD", "0.8"))

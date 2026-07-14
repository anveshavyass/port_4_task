import os
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).resolve().parents[1]
env_path = project_root / ".env"

load_dotenv(env_path)

REQUEST_LOG_PATH = os.getenv("REQUEST_LOG_PATH", "logs/requests.jsonl")
CORRECTIONS_LOG_PATH = os.getenv("CORRECTIONS_LOG_PATH", "logs/corrections.jsonl")
RESOLUTIONS_LOG_PATH = os.getenv("RESOLUTIONS_LOG_PATH", "logs/resolutions.jsonl")
ESCALATIONS_LOG_PATH = os.getenv("ESCALATIONS_LOG_PATH", "logs/escalations.jsonl")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
SLA_HOURS = {
    "Critical": int(os.getenv("SLA_CRITICAL_HOURS", "1")),
    "High": int(os.getenv("SLA_HIGH_HOURS", "2")),
    "Medium": int(os.getenv("SLA_MEDIUM_HOURS", "12")),
    "Low": int(os.getenv("SLA_LOW_HOURS", "24")),
}
DUPLICATE_LOOKBACK_HOURS = int(os.getenv("DUPLICATE_LOOKBACK_HOURS", "24"))
DUPLICATE_SIMILARITY_THRESHOLD = float(os.getenv("DUPLICATE_SIMILARITY_THRESHOLD", "0.8"))

import os
from pathlib import Path
from dotenv import load_dotenv

# Automatically read the .env file in the backend directory
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma4:e4b"

CHROMA_PERSIST_DIR = "./chroma_db"
CHROMA_COLLECTION = "math_knowledge"
PROJECT_DIR = Path(__file__).resolve().parent.parent
CHROMA_VAULT_DIR = os.getenv("CHROMA_VAULT_DIR", str(Path(__file__).resolve().parent / "uploads"))
CHROMA_VAULT_COLLECTION = "obsidian_notes"

MAX_CONCURRENT_CHATS = int(os.getenv("MAX_CONCURRENT_CHATS", "3"))
MAX_CONTEXT_DISTANCE = float(os.getenv("MAX_CONTEXT_DISTANCE", "1.2"))   

OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
OLLAMA_MAX_CONTINUATIONS = int(os.getenv("OLLAMA_MAX_CONTINUATIONS", "4"))
MAX_HISTORY_IMAGES = int(os.getenv("MAX_HISTORY_IMAGES", "2"))

HERMES_API_URL = os.getenv("HERMES_API_URL", "")   
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "")   
HERMES_TIMEOUT = float(os.getenv("HERMES_TIMEOUT", "900"))

# Groq Config
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "")
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "4096"))
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")
GROQ_MAX_RETRIES = int(os.getenv("GROQ_MAX_RETRIES", "3"))

# Gemini Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Use Gemini's official OpenAI-compatible endpoint
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "8192"))
GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "3"))

CLASSIFY_MIN_CONFIDENCE = float(os.getenv("CLASSIFY_MIN_CONFIDENCE", "0.70"))
CLASSIFY_SAMPLE_CHARS = int(os.getenv("CLASSIFY_SAMPLE_CHARS", "4000"))   
MAX_ANALYZE_BYTES = int(os.getenv("MAX_ANALYZE_BYTES", str(15 * 1024 * 1024)))
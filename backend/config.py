import os

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:4b"   

CHROMA_PERSIST_DIR = "./chroma_db"
CHROMA_COLLECTION = "math_knowledge"

# --- Concurrency settings ---
# How many /ask requests may generate with Ollama at the same time. A single
# local Ollama instance can only run so many generations in parallel before
# GPU/CPU contention makes every response slower, so this caps it deliberately
# instead of letting every request fight for resources at once. Tune this to
# whatever your hardware can actually handle (start at 2-3 on a single GPU).
MAX_CONCURRENT_CHATS = int(os.getenv("MAX_CONCURRENT_CHATS", "3"))

# Hard timeout (seconds) for a single Ollama chat call, so one stuck request
# can't hang forever and block a slot other students are waiting on. 180s is
# generous on purpose — see the note in rag.py's ask() about model-swap
# latency, which is the likely cause if you're hitting this often.
OLLAMA_CHAT_TIMEOUT = float(os.getenv("OLLAMA_CHAT_TIMEOUT", "180"))
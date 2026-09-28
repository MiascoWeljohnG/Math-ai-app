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

# No per-request timeout by design: a slow answer finishing late is better
# than cutting a student off mid-response. The semaphore above is what
# protects the server from overload, not a timeout.

# Max distance (Chroma's squared-L2) a retrieved document chunk may have to
# still be considered "relevant" and injected as reference material. See the
# comment in rag.py's _similarity_search for how to tune this.
MAX_CONTEXT_DISTANCE = float(os.getenv("MAX_CONTEXT_DISTANCE", "1.2"))   
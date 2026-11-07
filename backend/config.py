import os
from pathlib import Path
from dotenv import load_dotenv

# Automatically read the .env file in the backend directory
load_dotenv()

# Email delivery for password recovery (Resend)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://isipnayan.vercel.app")

_DEFAULT_SECRET = "change-this-in-production"
SECRET_KEY = os.getenv("SECRET_KEY", _DEFAULT_SECRET)
if os.getenv("RENDER") and SECRET_KEY == _DEFAULT_SECRET:
    # Anyone who knows the default key can forge a login token for any account, admins included.
    raise RuntimeError("SECRET_KEY is not set. Add a long random value (e.g. `openssl rand -hex 32`) in Render's environment.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# ---- Accounts, schools and approval ----
# The platform serves exactly two schools. They are created at startup (bootstrap.ensure_schools) and no
# route can add another. Override the display names with SCHOOL_NAMES="Name one,Name two".
SCHOOL_NAMES = [n.strip() for n in os.getenv("SCHOOL_NAMES", "Saint Mark's Institute,Cavite State University Bacoor Campus").split(",") if n.strip()]
if len(SCHOOL_NAMES) != 2 or len({n.lower() for n in SCHOOL_NAMES}) != 2:
    raise RuntimeError('SCHOOL_NAMES must list exactly two different school names, e.g. "School A,School B"')

MIN_PASSWORD_LENGTH = 8
ADMIN_MIN_PASSWORD_LENGTH = 12   # for the default school admins

# Each school has exactly one default admin, created at startup from these variables (never from a built-in
# password). Slot 1 belongs to the first name in SCHOOL_NAMES, slot 2 to the second. There is no "create admin"
# feature: these two accounts are the top of the role tree.
#   SCHOOL1_ADMIN_USERNAME / SCHOOL1_ADMIN_PASSWORD     SCHOOL2_ADMIN_USERNAME / SCHOOL2_ADMIN_PASSWORD
SCHOOL_ADMIN_DEFAULTS = [
    (os.getenv(f"SCHOOL{i}_ADMIN_USERNAME", f"school{i}_admin"), os.getenv(f"SCHOOL{i}_ADMIN_PASSWORD", ""))
    for i in (1, 2)
]

# Enrollment certificate uploaded at sign-up (private storage; only reviewers can read it)
CERT_MAX_BYTES = int(os.getenv("CERT_MAX_BYTES", str(5 * 1024 * 1024)))
CERT_DIR = os.getenv("CERT_DIR", str(Path(__file__).resolve().parent / "private" / "certificates"))
MAX_SUBMISSIONS = int(os.getenv("MAX_SUBMISSIONS", "3"))   # first try + resubmissions after a rejection
# Per client address per hour. Generous on purpose: a whole class signing up from one school network shares one address.
SIGNUP_ATTEMPTS_PER_HOUR = int(os.getenv("SIGNUP_ATTEMPTS_PER_HOUR", "30"))

# File storage. "auto" = Google Drive when the four GOOGLE_*/DRIVE_* values below are set, otherwise the
# local uploads folder (fine for development, but Render's disk is wiped on every redeploy/restart).
# "drive" = always Drive (a missing value is reported as an error instead of silently using the disk),
# "local" = always the uploads folder.
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "auto").lower()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")

# Embeddings use Gemini directly; Gemini's API key and embedding endpoint are configured below.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "25"))
# Gemini rejects embedding calls over its per-minute token limit (the free tier's is about 30,000), so the
# server paces itself to this many (estimated) tokens per minute. Set it to 0 to switch pacing off once the
# key has billing enabled and a much higher limit.
EMBEDDING_TOKENS_PER_MINUTE = int(os.getenv("EMBEDDING_TOKENS_PER_MINUTE", "25000"))
EMBEDDING_MAX_RETRIES = int(os.getenv("EMBEDDING_MAX_RETRIES", "5"))   # waits as long as Gemini asks between tries
# A background indexing job is stopped (shown as failed, with Retry) after this long, so one stuck file can never
# hold up every file behind it.
INDEX_JOB_MAX_MINUTES = int(os.getenv("INDEX_JOB_MAX_MINUTES", "45"))

CHROMA_PERSIST_DIR = "./chroma_db"
CHROMA_COLLECTION = "math_knowledge"
PROJECT_DIR = Path(__file__).resolve().parent.parent
CHROMA_VAULT_DIR = os.getenv("CHROMA_VAULT_DIR", str(Path(__file__).resolve().parent / "uploads"))
CHROMA_VAULT_COLLECTION = "obsidian_notes"
# Where the AI's searchable chunks live. "auto" = the Postgres database (pgvector) when the app runs on Postgres,
# so they survive Render restarts and each file is embedded only once; otherwise the old on-disk Chroma index.
# Set "chroma" to switch back to the old index.
VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "auto")

MAX_CONCURRENT_CHATS = int(os.getenv("MAX_CONCURRENT_CHATS", "3"))
MAX_CONTEXT_DISTANCE = float(os.getenv("MAX_CONTEXT_DISTANCE", "1.2"))   

MAX_CONTINUATIONS = int(os.getenv("MAX_CONTINUATIONS", "4"))   # extra rounds when an answer hits the token limit
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

# Ollama / Cloudflare Tunnel
# Set OLLAMA_ENABLED=true to use local/Cloudflare-hosted Ollama for embeddings and chat.
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "").lower() in ("1", "true", "yes", "on")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "gemma4:e4b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")
# OLLAMA_BACKUP=true keeps Ollama as a LAST resort for chat and lessons: it is only asked after Groq and Gemini
# have failed (e.g. out of tokens). It does not touch embeddings, so the existing search index stays valid.
OLLAMA_BACKUP = os.getenv("OLLAMA_BACKUP", "").lower() in ("1", "true", "yes", "on")
OLLAMA_AVAILABLE = OLLAMA_ENABLED or OLLAMA_BACKUP
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "300"))   # seconds; a home PC without a GPU answers slowly
# The embedding backup (used only when Gemini's embedding quota runs out). Chunks made by it are tagged "nomic" in the
# database and searched with their own vectors. nomic vectors are unit length, so this is a squared distance like
# MAX_CONTEXT_DISTANCE: 1.0 means "cosine similarity of at least 0.5". Raise it to let in more (looser) matches.
OLLAMA_MAX_CONTEXT_DISTANCE = float(os.getenv("OLLAMA_MAX_CONTEXT_DISTANCE", "1.0"))
OLLAMA_EMBED_BATCH_SIZE = int(os.getenv("OLLAMA_EMBED_BATCH_SIZE", "8"))

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
# When a lesson is written from a page range, how much of those pages the model is shown (characters).
# A dense text page is roughly 3,000-4,000 characters; longer ranges keep the parts that best match the
# lesson title. Raise it if your model has a large context window.
PAGE_RANGE_CHARS = int(os.getenv("PAGE_RANGE_CHARS", "14000"))

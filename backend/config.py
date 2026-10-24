import os
from pathlib import Path
from dotenv import load_dotenv

# Automatically read the .env file in the backend directory
load_dotenv()

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
SCHOOL_NAMES = [n.strip() for n in os.getenv("SCHOOL_NAMES", "School A,School B").split(",") if n.strip()]
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

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# File storage. "auto" = Google Drive when the four GOOGLE_*/DRIVE_* values below are set, otherwise the
# local uploads folder (fine for development, but Render's disk is wiped on every redeploy/restart).
# "drive" = always Drive (a missing value is reported as an error instead of silently using the disk),
# "local" = always the uploads folder.
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "auto").lower()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "")

# Embeddings (used to index uploads). "ollama" = local dev. "gemini" = hosted, REQUIRED on Render,
# because Render has no Ollama server to talk to.
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama").lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "50"))
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
from os import getenv

LLM_API_BASE_URL = str(getenv("LLM_API_BASE_URL"))
LLM_API_KEY = str(getenv("LLM_API_KEY"))
LLM_MODELS = str(getenv("LLM_MODELS")).split(",")

VLM_API_BASE_URL = str(getenv("VLM_API_BASE_URL"))
VLM_API_KEY = str(getenv("VLM_API_KEY"))
VLM_MODELS = str(getenv("VLM_MODELS")).split(",")

HF_TOKEN = str(getenv("HF_TOKEN"))
HF_LLM_NAME = str(getenv("HF_LLM_NAME"))

DEBUG_MODE = (
    True if (getenv("DEBUG_MODE") or "false").strip().lower() == "true" else False
)

CTX_WINDOW = int(getenv("CTX_WINDOW") or "8192")

CHUNK_MAX_TOKENS = int(getenv("CHUNK_MAX_TOKENS") or "128")

WARNING_TOK_FRAC = float(getenv("WARNING_TOK_FRAC") or "0.8")
FLUSH_TOK_FRAC = float(getenv("FLUSH_TOK_FRAC") or "0.95")
FLUSH_TGT_TOK_FRAC = float(getenv("FLUSH_TGT_TOK_FRAC") or "0.6")
FLUSH_MIN_FIFO_QUEUE_LEN = int(getenv("FLUSH_MIN_FIFO_QUEUE_LEN") or "5")

OVERTHINK_WARNING_HEARTBEAT_COUNT = int(
    getenv("OVERTHINK_WARNING_HEARTBEAT_COUNT") or "10"
)

PAGE_SIZE = int(getenv("PAGE_SIZE") or "10")
PERSONA_MAX_WORDS = int(getenv("PERSONA_MAX_WORDS") or "100")

HEARTBEAT_FREQUENCY_IN_MINUTES = int(getenv("HEARTBEAT_FREQUENCY_IN_MINUTES") or "60")

POSTGRES_USER = str(getenv("POSTGRES_USER"))
POSTGRES_PASSWORD = str(getenv("POSTGRES_PASSWORD"))
POSTGRES_DB = str(getenv("POSTGRES_DB"))
